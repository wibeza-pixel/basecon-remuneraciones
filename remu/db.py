"""
Acceso a datos: SQLite local o Postgres (Supabase) con la misma API.

- Un solo esquema declarado aquí sirve para ambos motores (no se depende de un schema.sql aparte).
- Las inserciones con conflicto usan `INSERT ... ON CONFLICT (...) DO UPDATE/NOTHING`,
  sintaxis válida en SQLite ≥ 3.24 y en Postgres: no hay reescritura de SQL "por casos".
- Postgres usa un pool de conexiones: `conn.close()` devuelve la conexión al pool.
- `init_db()` es idempotente y NO pisa datos existentes (antes reescribía los indicadores
  de agosto 2026 en cada clic de Streamlit).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime

import pandas as pd

from . import config as C

sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime, lambda d: d.isoformat(sep=" "))

_pool = None
_pool_lock = threading.Lock()
_init_done = False


# ------------------------------------------------------------------
# Conexión
# ------------------------------------------------------------------
def database_url() -> str:
    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        try:
            import streamlit as st  # opcional
            url = st.secrets.get("DATABASE_URL", "") or ""
        except Exception:
            url = ""
    return url.strip()


def is_postgres() -> bool:
    u = database_url().lower()
    return bool(u) and ("postgres" in u or "supabase" in u)


def schema_pg() -> str:
    """Schema de Postgres donde viven las tablas de BASECON (separado de otras apps en el mismo Supabase)."""
    s = os.environ.get("BASECON_SCHEMA") or ""
    if not s:
        try:
            import streamlit as st
            s = st.secrets.get("BASECON_SCHEMA", "") or ""
        except Exception:
            s = ""
    s = (s or "basecon").strip().lower()
    return s if s.replace("_", "").isalnum() else "basecon"


def _adapt(sql: str) -> str:
    return sql.replace("?", "%s") if is_postgres() else sql


class _PgCursor:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def execute(self, sql, params=None):
        self._cur.execute(_adapt(sql), tuple(params or ()))
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def description(self):
        return self._cur.description


class _PgConn:
    def __init__(self, pool):
        from psycopg2.extras import RealDictCursor
        self._pool = pool
        self._conn = pool.getconn()
        self._rdc = RealDictCursor
        self._set_path()

    def _set_path(self):
        cur = self._conn.cursor()
        sch = schema_pg()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {sch}")
        cur.execute(f"SET search_path TO {sch}")
        self._conn.commit()

    def cursor(self):
        return _PgCursor(self._conn.cursor(cursor_factory=self._rdc))

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def commit(self):
        self._conn.commit()
        self._set_path()  # con pooler en modo transacción, el search_path se reafirma tras cada commit

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._conn is not None:
            try:
                self._conn.rollback()
            except Exception:
                pass
            self._pool.putconn(self._conn)
            self._conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg2.pool import ThreadedConnectionPool
            dsn = database_url()
            if "sslmode" not in dsn and "supabase" in dsn:
                dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
            _pool = ThreadedConnectionPool(1, 8, dsn)
    return _pool


def get_conn():
    if is_postgres():
        return _PgConn(_get_pool())
    conn = sqlite3.connect(str(C.DB_PATH), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def scalar(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    if r is None:
        return None
    return list(dict(r).values())[0]


def read_sql_df(sql, conn, params=None) -> pd.DataFrame:
    """DataFrame desde una consulta, igual en SQLite y Postgres (placeholders '?')."""
    return pd.DataFrame(rows(conn, sql, params or ()))


def insert(conn, table: str, data: dict) -> int | None:
    cols = list(data)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    if is_postgres():
        r = conn.execute(sql + " RETURNING id", [data[c] for c in cols]).fetchone()
        return int(dict(r)["id"]) if r else None
    cur = conn.execute(sql, [data[c] for c in cols])
    return cur.lastrowid


def upsert(conn, table: str, data: dict, conflict: list[str], update: bool = True):
    cols = list(data)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
           f"ON CONFLICT ({', '.join(conflict)}) ")
    upd = [c for c in cols if c not in conflict]
    if update and upd:
        sql += "DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in upd)
    else:
        sql += "DO NOTHING"
    conn.execute(sql, [data[c] for c in cols])


# ------------------------------------------------------------------
# Esquema (un solo lugar para SQLite y Postgres)
# ------------------------------------------------------------------
TABLAS = {
    "empresas": """
        id {PK}, rut TEXT UNIQUE NOT NULL, razon_social TEXT NOT NULL, giro TEXT,
        direccion TEXT, comuna TEXT, ciudad TEXT, telefono TEXT, email TEXT,
        region_codigo INTEGER, comuna_codigo INTEGER,
        mutual TEXT DEFAULT 'ACHS', tasa_mutual {REAL} DEFAULT 0.93, sucursal_mutual TEXT,
        caja_compensacion TEXT, centro_costo TEXT,
        representante_legal TEXT, rut_representante TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP""",
    "trabajadores": """
        id {PK}, empresa_id INTEGER NOT NULL REFERENCES empresas(id), rut TEXT NOT NULL,
        nombres TEXT NOT NULL, apellido_paterno TEXT NOT NULL, apellido_materno TEXT,
        sexo TEXT DEFAULT 'M', fecha_nacimiento DATE, nacionalidad TEXT DEFAULT 'Chilena',
        estado_civil TEXT, direccion TEXT, comuna TEXT, email TEXT, telefono TEXT,
        afp TEXT, salud TEXT, isapre TEXT, pactado_salud_uf {REAL} DEFAULT 0,
        cuenta_banco TEXT, banco TEXT, tipo_cuenta TEXT DEFAULT 'RUT',
        codigo TEXT, cargo TEXT, centro_costo TEXT,
        tramo_asignacion_familiar TEXT DEFAULT 'D', numero_cargas INTEGER DEFAULT 0,
        pensionado INTEGER DEFAULT 0, cotiza_afp INTEGER DEFAULT 1,
        activo INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, rut)""",
    "contratos": """
        id {PK}, trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
        empresa_id INTEGER NOT NULL REFERENCES empresas(id), cargo TEXT NOT NULL,
        fecha_inicio DATE NOT NULL, fecha_termino DATE, tipo_contrato TEXT DEFAULT 'Indefinido',
        sueldo_base {REAL} NOT NULL, tipo_gratificacion TEXT DEFAULT 'Monto fijo pactado',
        gratificacion {REAL} DEFAULT 0, movilizacion {REAL} DEFAULT 0, colacion {REAL} DEFAULT 0,
        otros_haberes {REAL} DEFAULT 0, jornada_semanal INTEGER DEFAULT 42, horario TEXT,
        lugar_trabajo TEXT, observaciones TEXT, activo INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP""",
    "indicadores": """
        id {PK}, periodo TEXT UNIQUE NOT NULL, uf {REAL}, utm {REAL}, tope_afp {REAL},
        tope_afc {REAL}, tope_inp {REAL}, sis_tasa {REAL} DEFAULT 0, renta_minima {REAL},
        afp_tasas TEXT, af_tramos TEXT, tasa_ccaf_salud {REAL},
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP""",
    "factores_actualizacion": """
        id {PK}, anio_rentas INTEGER NOT NULL, mes INTEGER NOT NULL, factor {REAL} NOT NULL,
        UNIQUE(anio_rentas, mes)""",
    "feriados": """
        fecha DATE PRIMARY KEY, nombre TEXT""",
    "liquidaciones": """
        id {PK}, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id), contrato_id INTEGER,
        periodo TEXT NOT NULL, dias_trabajados INTEGER DEFAULT 30,
        horas_extras {REAL} DEFAULT 0, monto_horas_extras {REAL} DEFAULT 0,
        sueldo_base {REAL}, sueldo_calculado {REAL}, gratificacion {REAL}, movilizacion {REAL},
        colacion {REAL}, asignacion_familiar {REAL} DEFAULT 0, otros_haberes {REAL},
        total_haberes {REAL}, total_imponible {REAL}, afp_monto {REAL}, salud_monto {REAL},
        salud_fonasa {REAL} DEFAULT 0, salud_ccaf {REAL} DEFAULT 0, adicional_isapre {REAL},
        sis_monto {REAL}, afc_trabajador {REAL}, afc_empleador {REAL}, mutual_monto {REAL},
        reforma_afp_emp {REAL} DEFAULT 0, reforma_crp {REAL} DEFAULT 0,
        reforma_seguro_social {REAL} DEFAULT 0, base_tributable {REAL},
        impuesto_unico {REAL} DEFAULT 0, anticipo {REAL} DEFAULT 0,
        aguinaldo {REAL} DEFAULT 0, bonos_imponibles {REAL} DEFAULT 0, haberes_no_imponibles {REAL} DEFAULT 0,
        otros_descuentos {REAL} DEFAULT 0, dias_licencia {REAL} DEFAULT 0, dias_vacaciones {REAL} DEFAULT 0,
        detalle TEXT,
        total_descuentos {REAL}, liquido {REAL}, tramo_asignacion TEXT, advertencias TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, trabajador_id, periodo)""",
    "vacaciones": """
        id {PK}, trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
        empresa_id INTEGER NOT NULL REFERENCES empresas(id), fecha_inicio DATE, fecha_termino DATE,
        dias_habiles {REAL}, dias_corridos {REAL}, tipo TEXT DEFAULT 'Legales', periodo_devengo TEXT,
        comprobante_generado INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP""",
    "finiquitos": """
        id {PK}, trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
        empresa_id INTEGER NOT NULL REFERENCES empresas(id), contrato_id INTEGER,
        fecha_termino DATE NOT NULL, causal TEXT, causal_codigo INTEGER, aviso_dado INTEGER DEFAULT 0,
        base_calculo {REAL}, base_con_tope {REAL}, anos_pagar INTEGER DEFAULT 0,
        vacaciones_proporcionales_dias {REAL}, vacaciones_proporcionales_monto {REAL},
        feriado_dias_corridos {REAL}, valor_dia_feriado {REAL},
        indemnizacion_anos {REAL} DEFAULT 0, aviso_previo {REAL} DEFAULT 0,
        descuento_afc {REAL} DEFAULT 0, otros_montos {REAL} DEFAULT 0, otros_descuentos {REAL} DEFAULT 0,
        total_finiquito {REAL}, observaciones TEXT, detalle TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP""",
    "periodos_rrhh": """
        id {PK}, empresa_id INTEGER NOT NULL REFERENCES empresas(id), periodo TEXT NOT NULL,
        estado TEXT DEFAULT 'Abierto', enviado_por TEXT, enviado_at TIMESTAMP,
        UNIQUE(empresa_id, periodo)""",
    "conceptos": """
        id {PK}, empresa_id INTEGER NOT NULL REFERENCES empresas(id), nombre TEXT NOT NULL,
        tipo TEXT DEFAULT 'Haber imponible', codigo_lre INTEGER, activo INTEGER DEFAULT 1, orden INTEGER DEFAULT 0""",
    "movimientos": """
        id {PK}, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id), periodo TEXT NOT NULL,
        dias_trabajados {REAL}, ausencias {REAL} DEFAULT 0, licencia {REAL} DEFAULT 0,
        licencia_desde DATE, licencia_hasta DATE, dias_vacaciones {REAL} DEFAULT 0,
        anticipo {REAL} DEFAULT 0, aguinaldo {REAL} DEFAULT 0, bono_desempeno {REAL} DEFAULT 0,
        cant_he_50 {REAL} DEFAULT 0, cant_he_100 {REAL} DEFAULT 0, cant_hd {REAL} DEFAULT 0, cant_hed {REAL} DEFAULT 0,
        valor_he_50 {REAL} DEFAULT 0, valor_he_100 {REAL} DEFAULT 0, valor_hd {REAL} DEFAULT 0, valor_hed {REAL} DEFAULT 0,
        colacion {REAL} DEFAULT 0, movilizacion {REAL} DEFAULT 0, extras TEXT, observacion TEXT,
        updated_by TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, trabajador_id, periodo)""",
    "usuarios": """
        id {PK}, usuario TEXT UNIQUE NOT NULL, nombre TEXT, hash TEXT NOT NULL, salt TEXT NOT NULL,
        rol TEXT DEFAULT 'usuario', empresas TEXT DEFAULT '[]', modulos TEXT DEFAULT '["remuneraciones"]',
        activo INTEGER DEFAULT 1,
        dias_acceso INTEGER, fecha_expira DATE, primer_acceso DATE, ultimo_acceso DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP""",
    "configuracion": """
        clave TEXT PRIMARY KEY, valor TEXT""",
}

# Columnas agregadas en v2 (para bases existentes de la v1)
MIGRACIONES = [
    ("empresas", "giro", "TEXT"), ("empresas", "region_codigo", "INTEGER"),
    ("empresas", "comuna_codigo", "INTEGER"), ("empresas", "sucursal_mutual", "TEXT"),
    ("empresas", "centro_costo", "TEXT"),
    ("trabajadores", "sexo", "TEXT DEFAULT 'M'"), ("trabajadores", "pensionado", "INTEGER DEFAULT 0"),
    ("trabajadores", "cotiza_afp", "INTEGER DEFAULT 1"),
    ("trabajadores", "tramo_asignacion_familiar", "TEXT DEFAULT 'D'"),
    ("trabajadores", "numero_cargas", "INTEGER DEFAULT 0"),
    ("contratos", "tipo_gratificacion", "TEXT DEFAULT 'Monto fijo pactado'"),
    ("indicadores", "af_tramos", "TEXT"), ("indicadores", "tasa_ccaf_salud", "{REAL}"),
    ("liquidaciones", "horas_extras", "{REAL} DEFAULT 0"),
    ("liquidaciones", "monto_horas_extras", "{REAL} DEFAULT 0"),
    ("liquidaciones", "asignacion_familiar", "{REAL} DEFAULT 0"),
    ("liquidaciones", "reforma_afp_emp", "{REAL} DEFAULT 0"),
    ("liquidaciones", "reforma_crp", "{REAL} DEFAULT 0"),
    ("liquidaciones", "reforma_seguro_social", "{REAL} DEFAULT 0"),
    ("liquidaciones", "anticipo", "{REAL} DEFAULT 0"),
    ("liquidaciones", "impuesto_unico", "{REAL} DEFAULT 0"),
    ("liquidaciones", "salud_fonasa", "{REAL} DEFAULT 0"),
    ("liquidaciones", "salud_ccaf", "{REAL} DEFAULT 0"),
    ("liquidaciones", "tramo_asignacion", "TEXT"), ("liquidaciones", "advertencias", "TEXT"),
    ("trabajadores", "codigo", "TEXT"), ("trabajadores", "cargo", "TEXT"), ("trabajadores", "centro_costo", "TEXT"),
    ("usuarios", "modulos", "TEXT DEFAULT '[\"remuneraciones\"]'"),
    ("liquidaciones", "aguinaldo", "{REAL} DEFAULT 0"), ("liquidaciones", "bonos_imponibles", "{REAL} DEFAULT 0"),
    ("liquidaciones", "haberes_no_imponibles", "{REAL} DEFAULT 0"),
    ("liquidaciones", "otros_descuentos", "{REAL} DEFAULT 0"), ("liquidaciones", "dias_licencia", "{REAL} DEFAULT 0"),
    ("liquidaciones", "dias_vacaciones", "{REAL} DEFAULT 0"), ("liquidaciones", "detalle", "TEXT"),
    ("finiquitos", "causal_codigo", "INTEGER"), ("finiquitos", "aviso_dado", "INTEGER DEFAULT 0"),
    ("finiquitos", "base_calculo", "{REAL}"), ("finiquitos", "base_con_tope", "{REAL}"),
    ("finiquitos", "anos_pagar", "INTEGER DEFAULT 0"), ("finiquitos", "feriado_dias_corridos", "{REAL}"),
    ("finiquitos", "valor_dia_feriado", "{REAL}"), ("finiquitos", "descuento_afc", "{REAL} DEFAULT 0"),
    ("finiquitos", "otros_descuentos", "{REAL} DEFAULT 0"), ("finiquitos", "detalle", "TEXT"),
]


def _tipos():
    if is_postgres():
        return {"PK": "BIGSERIAL PRIMARY KEY", "REAL": "DOUBLE PRECISION"}
    return {"PK": "INTEGER PRIMARY KEY AUTOINCREMENT", "REAL": "REAL"}


def ddl_completo() -> str:
    """Script SQL del esquema para el motor activo (se usa para generar supabase/schema.sql)."""
    t = _tipos()
    return "\n\n".join(f"CREATE TABLE IF NOT EXISTS {n} ({body.format(**t)}\n);" for n, body in TABLAS.items())


def init_db(force: bool = False):
    """Crea tablas, aplica migraciones y carga datos base SIN sobrescribir lo existente."""
    global _init_done
    if _init_done and not force:
        return
    t = _tipos()
    conn = get_conn()
    try:
        for nombre, body in TABLAS.items():
            conn.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({body.format(**t)})")
        conn.commit()
        for tabla, col, tipo in MIGRACIONES:
            tipo = tipo.format(**t)
            try:
                if is_postgres():
                    conn.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col} {tipo}")
                else:
                    existentes = {r["name"] for r in rows(conn, f"PRAGMA table_info({tabla})")}
                    if col not in existentes:
                        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {tipo}")
                conn.commit()
            except Exception:
                conn.rollback() if hasattr(conn, "rollback") else None
        _seed(conn)
        conn.commit()
        _init_done = True
    finally:
        conn.close()


def _seed(conn):
    afp = json.dumps(C.AFP_TASAS_DEFAULT)
    af = json.dumps(C.AF_TRAMOS_DEFAULT)
    base = [
        # periodo, uf, utm, tope_afp, tope_afc, tope_inp, sis, renta_minima
        ("2026-07", 40844.79, 71649, 3676031, 5522216, 2449219, 1.88, 553553),
        ("2026-08", 40864.55, 71649, 3676031, 5522215, 2450687, 0.0, 553553),
    ]
    for p, uf, utm, ta, tafc, tinp, sis, rm in base:
        upsert(conn, "indicadores", dict(periodo=p, uf=uf, utm=utm, tope_afp=ta, tope_afc=tafc, tope_inp=tinp,
                                         sis_tasa=sis, renta_minima=rm, afp_tasas=afp, af_tramos=af,
                                         tasa_ccaf_salud=C.TASA_CCAF_SALUD_DEFAULT),
               ["periodo"], update=False)  # DO NOTHING: nunca pisa lo que el usuario cargó
    fac_2025 = {1: 1.026, 2: 1.022, 3: 1.016, 4: 1.014, 5: 1.012, 6: 1.017,
                7: 1.008, 8: 1.007, 9: 1.003, 10: 1.003, 11: 1.000, 12: 1.000}
    for m, f in fac_2025.items():
        upsert(conn, "factores_actualizacion", dict(anio_rentas=2025, mes=m, factor=f), ["anio_rentas", "mes"], False)
    for m in range(1, 13):
        upsert(conn, "factores_actualizacion", dict(anio_rentas=2026, mes=m, factor=1.0), ["anio_rentas", "mes"], False)
    for f, n in C.FERIADOS_DEFAULT:
        upsert(conn, "feriados", dict(fecha=f, nombre=n), ["fecha"], False)


# ------------------------------------------------------------------
# Lecturas frecuentes
# ------------------------------------------------------------------
def get_indicadores(periodo: str, conn=None) -> dict | None:
    propia = conn is None
    conn = conn or get_conn()
    try:
        d = row(conn, "SELECT * FROM indicadores WHERE periodo = ?", (periodo,))
    finally:
        if propia:
            conn.close()
    if not d:
        return None
    d["afp_tasas"] = json.loads(d["afp_tasas"]) if d.get("afp_tasas") else dict(C.AFP_TASAS_DEFAULT)
    d["af_tramos"] = json.loads(d["af_tramos"]) if d.get("af_tramos") else dict(C.AF_TRAMOS_DEFAULT)
    if d.get("tasa_ccaf_salud") is None:
        d["tasa_ccaf_salud"] = C.TASA_CCAF_SALUD_DEFAULT
    return d


def guardar_indicadores(conn, periodo: str, valores: dict):
    """Guarda/actualiza indicadores; los campos en None conservan el valor anterior."""
    prev = get_indicadores(periodo, conn) or {}
    d = {"periodo": periodo}
    for k in ("uf", "utm", "tope_afp", "tope_afc", "tope_inp", "sis_tasa", "renta_minima", "tasa_ccaf_salud"):
        v = valores.get(k)
        d[k] = v if v is not None else prev.get(k)
    for k, default in (("afp_tasas", C.AFP_TASAS_DEFAULT), ("af_tramos", C.AF_TRAMOS_DEFAULT)):
        v = valores.get(k) or prev.get(k) or default
        d[k] = json.dumps(v)
    upsert(conn, "indicadores", d, ["periodo"], update=True)


def get_factores_actualizacion(anio_rentas: int, conn=None) -> dict:
    propia = conn is None
    conn = conn or get_conn()
    try:
        rs = rows(conn, "SELECT mes, factor FROM factores_actualizacion WHERE anio_rentas = ? ORDER BY mes",
                  (anio_rentas,))
    finally:
        if propia:
            conn.close()
    return {int(r["mes"]): float(r["factor"]) for r in rs} if rs else {m: 1.0 for m in range(1, 13)}


def get_feriados(conn=None) -> set[date]:
    propia = conn is None
    conn = conn or get_conn()
    try:
        rs = rows(conn, "SELECT fecha FROM feriados")
    finally:
        if propia:
            conn.close()
    return {C.a_fecha(r["fecha"]) for r in rs if C.a_fecha(r["fecha"])}
