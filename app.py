#!/usr/bin/env python3
"""
Sistema de Remuneraciones Multiempresa - Chile
Incluye: Trabajadores, Contratos, Liquidaciones, Finiquitos, Vacaciones, Previred
Basado en formatos de liquidación, contrato, finiquito e indicadores Previred 2026
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
import pdfplumber
import io
import re
from docx import Document
from docx.shared import Pt, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import zipfile
import os
import json
import hashlib

# ============================================================
# CONFIGURACIÓN Y BASE DE DATOS
# ============================================================
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "remuneraciones.db"
EXPORTS_DIR = BASE_DIR / "exports"
ACCESS_CONFIG_PATH = BASE_DIR / "data" / "acceso_demo.json"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="BASECON — Remuneraciones Chile",
    page_icon="🇨🇱",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# CONTROL DE ACCESO / DEMO (clave + plazo)
# ============================================================
def _hash_clave(clave: str) -> str:
    return hashlib.sha256((clave or "").encode("utf-8")).hexdigest()


def cargar_config_acceso() -> dict:
    """Carga o crea configuración de acceso demo."""
    default = {
        "activo": True,  # True = exige clave; False = acceso libre (solo tu PC)
        "clave_hash": _hash_clave("demo2026"),  # clave por defecto para demostración
        "admin_hash": _hash_clave("admin2026"),  # clave dueño para configurar plazo
        "fecha_inicio": None,  # se fija al primer acceso válido
        "dias_demo": 15,  # plazo por defecto
        "fecha_expira": None,  # YYYY-MM-DD opcional fija
        "titulo": "BASECON — Demostración",
        "mensaje": "Sistema de Remuneraciones Multiempresa. Solicite la clave al administrador.",
    }
    if ACCESS_CONFIG_PATH.exists():
        try:
            with open(ACCESS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            default.update(data)
        except Exception:
            pass
    return default


def guardar_config_acceso(cfg: dict):
    ACCESS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCESS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _dias_restantes(cfg: dict):
    """Retorna días restantes o None si no aplica / ilimitado."""
    hoy = date.today()
    if cfg.get("fecha_expira"):
        try:
            exp = datetime.strptime(cfg["fecha_expira"], "%Y-%m-%d").date()
            return (exp - hoy).days
        except Exception:
            pass
    if cfg.get("fecha_inicio") and cfg.get("dias_demo"):
        try:
            ini = datetime.strptime(cfg["fecha_inicio"], "%Y-%m-%d").date()
            exp = ini + timedelta(days=int(cfg["dias_demo"]))
            return (exp - hoy).days
        except Exception:
            pass
    return None


def pantalla_acceso():
    """Muestra login. Retorna True si el usuario puede entrar."""
    cfg = cargar_config_acceso()

    # Acceso libre (tú desactivas el candado en tu copia)
    if not cfg.get("activo", True):
        return True

    if st.session_state.get("acceso_ok"):
        # Verificar que no haya vencido durante la sesión
        dias = _dias_restantes(cfg)
        if dias is not None and dias < 0:
            st.session_state["acceso_ok"] = False
            st.session_state["acceso_motivo"] = "expirado"
        else:
            return True

    logo_path = BASE_DIR / "basecon-logo.png"
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
        st.markdown(
            f"""
            <div style="padding:1rem 1.5rem;border:1px solid #e2e8f0;
            border-radius:12px;background:#f8fafc;font-family:Arial,sans-serif;margin-top:0.5rem;">
            <h3 style="text-align:center;margin:0.2rem 0 0.6rem 0;">🔒 {cfg.get('titulo') or 'Acceso'}</h3>
            <p style="text-align:center;color:#555;margin:0;">{cfg.get('mensaje') or ''}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        if st.session_state.get("acceso_motivo") == "expirado":
            st.error("El periodo de demostración ha finalizado. Contacte al administrador.")
        elif st.session_state.get("acceso_motivo") == "clave":
            st.error("Clave incorrecta.")

        clave = st.text_input("Clave de acceso", type="password", key="login_clave")
        entrar = st.button("Entrar", type="primary", use_container_width=True)

        if entrar:
            h = _hash_clave(clave)
            ok_demo = h == cfg.get("clave_hash")
            ok_admin = h == cfg.get("admin_hash")
            if ok_demo or ok_admin:
                # Primer acceso: fijar fecha_inicio si no existe
                if not cfg.get("fecha_inicio"):
                    cfg["fecha_inicio"] = date.today().isoformat()
                    guardar_config_acceso(cfg)
                dias = _dias_restantes(cfg)
                if dias is not None and dias < 0:
                    st.session_state["acceso_motivo"] = "expirado"
                    st.rerun()
                st.session_state["acceso_ok"] = True
                st.session_state["es_admin"] = bool(ok_admin)
                st.session_state["acceso_motivo"] = None
                st.rerun()
            else:
                st.session_state["acceso_motivo"] = "clave"
                st.rerun()

        # Info de plazo (sin revelar clave)
        dias = _dias_restantes(cfg)
        if cfg.get("fecha_expira"):
            st.caption(f"Válido hasta: {cfg['fecha_expira']}")
        elif cfg.get("dias_demo"):
            if cfg.get("fecha_inicio") and dias is not None:
                st.caption(f"Plazo de demostración: {cfg['dias_demo']} días · Restan aprox. {max(dias, 0)} día(s)")
            else:
                st.caption(f"Plazo de demostración: {cfg['dias_demo']} días (desde el primer acceso)")

    return False


def panel_admin_acceso():
    """Configuración de clave y plazo (solo con clave admin o ya logueado como admin)."""
    cfg = cargar_config_acceso()
    st.subheader("🔐 Control de acceso / Demostración")
    st.caption("Define la clave que darás al cliente y el plazo. Tú usas la clave de administrador.")

    activo = st.checkbox("Exigir clave de acceso", value=bool(cfg.get("activo", True)))
    dias = st.number_input("Días de demostración (desde primer acceso)", min_value=1, max_value=365,
                           value=int(cfg.get("dias_demo") or 15))
    fecha_fija = st.text_input(
        "Fecha de expiración fija (opcional, YYYY-MM-DD)",
        value=cfg.get("fecha_expira") or "",
        help="Si la completas, tiene prioridad sobre los días de demo.",
    )
    titulo = st.text_input("Título pantalla de acceso", value=cfg.get("titulo") or "")
    mensaje = st.text_area("Mensaje", value=cfg.get("mensaje") or "", height=80)

    col1, col2 = st.columns(2)
    with col1:
        nueva_demo = st.text_input("Nueva clave de demostración", type="password",
                                   help="La que entregarás al cliente")
    with col2:
        nueva_admin = st.text_input("Nueva clave de administrador", type="password",
                                    help="Solo tuya; permite reconfigurar")

    if st.button("Guardar configuración de acceso"):
        cfg["activo"] = bool(activo)
        cfg["dias_demo"] = int(dias)
        cfg["fecha_expira"] = fecha_fija.strip() or None
        cfg["titulo"] = titulo
        cfg["mensaje"] = mensaje
        if nueva_demo:
            cfg["clave_hash"] = _hash_clave(nueva_demo)
        if nueva_admin:
            cfg["admin_hash"] = _hash_clave(nueva_admin)
        # Reiniciar contador de demo si el admin lo pide
        if st.session_state.get("reset_demo_fecha"):
            cfg["fecha_inicio"] = None
        guardar_config_acceso(cfg)
        st.success("Configuración de acceso guardada.")

    if st.button("Reiniciar contador de días (nuevo plazo desde próximo acceso)"):
        cfg = cargar_config_acceso()
        cfg["fecha_inicio"] = None
        guardar_config_acceso(cfg)
        st.success("Al próximo acceso válido se reinicia el plazo.")

    st.info(
        f"**Estado actual:** acceso {'activo' if cfg.get('activo') else 'libre'} · "
        f"días demo={cfg.get('dias_demo')} · inicio={cfg.get('fecha_inicio') or 'aún no'} · "
        f"expira fija={cfg.get('fecha_expira') or '—'}"
    )

def get_conn():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS empresas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut TEXT UNIQUE NOT NULL,
        razon_social TEXT NOT NULL,
        direccion TEXT,
        comuna TEXT,
        ciudad TEXT,
        telefono TEXT,
        email TEXT,
        mutual TEXT DEFAULT 'ACHS',
        tasa_mutual REAL DEFAULT 0.93,
        caja_compensacion TEXT,
        representante_legal TEXT,
        rut_representante TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS trabajadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL,
        rut TEXT NOT NULL,
        nombres TEXT NOT NULL,
        apellido_paterno TEXT NOT NULL,
        apellido_materno TEXT,
        fecha_nacimiento DATE,
        nacionalidad TEXT DEFAULT 'Chilena',
        estado_civil TEXT,
        direccion TEXT,
        comuna TEXT,
        email TEXT,
        telefono TEXT,
        afp TEXT,
        salud TEXT,  -- FONASA o ISAPRE
        isapre TEXT,
        pactado_salud_uf REAL DEFAULT 0,
        cuenta_banco TEXT,
        banco TEXT,
        tipo_cuenta TEXT DEFAULT 'RUT',
        tramo_asignacion_familiar TEXT DEFAULT 'D',  -- A, B, C, D
        numero_cargas INTEGER DEFAULT 0,
        activo INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, rut),
        FOREIGN KEY (empresa_id) REFERENCES empresas(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS contratos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trabajador_id INTEGER NOT NULL,
        empresa_id INTEGER NOT NULL,
        cargo TEXT NOT NULL,
        fecha_inicio DATE NOT NULL,
        fecha_termino DATE,
        tipo_contrato TEXT DEFAULT 'Indefinido',  -- Indefinido, Plazo Fijo, Obra
        sueldo_base REAL NOT NULL,
        gratificacion REAL DEFAULT 0,
        movilizacion REAL DEFAULT 0,
        colacion REAL DEFAULT 0,
        otros_haberes REAL DEFAULT 0,
        jornada_semanal INTEGER DEFAULT 45,
        horario TEXT,
        lugar_trabajo TEXT,
        observaciones TEXT,
        activo INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trabajador_id) REFERENCES trabajadores(id),
        FOREIGN KEY (empresa_id) REFERENCES empresas(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS indicadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        periodo TEXT UNIQUE NOT NULL,  -- YYYY-MM
        uf REAL,
        utm REAL,
        tope_afp REAL,
        tope_afc REAL,
        tope_inp REAL,
        sis_tasa REAL DEFAULT 2.0,
        renta_minima REAL,
        afp_tasas TEXT,  -- JSON string
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS factores_actualizacion (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anio_rentas INTEGER NOT NULL,
        mes INTEGER NOT NULL,
        factor REAL NOT NULL,
        UNIQUE(anio_rentas, mes)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS liquidaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id INTEGER NOT NULL,
        trabajador_id INTEGER NOT NULL,
        contrato_id INTEGER,
        periodo TEXT NOT NULL,  -- YYYY-MM
        dias_trabajados INTEGER DEFAULT 30,
        horas_extras REAL DEFAULT 0,
        monto_horas_extras REAL DEFAULT 0,
        sueldo_base REAL,
        sueldo_calculado REAL,
        gratificacion REAL,
        movilizacion REAL,
        colacion REAL,
        asignacion_familiar REAL DEFAULT 0,
        otros_haberes REAL,
        total_haberes REAL,
        total_imponible REAL,
        afp_monto REAL,
        salud_monto REAL,
        adicional_isapre REAL,
        sis_monto REAL,
        afc_trabajador REAL,
        afc_empleador REAL,
        mutual_monto REAL,
        reforma_afp_emp REAL DEFAULT 0,
        reforma_crp REAL DEFAULT 0,
        reforma_seguro_social REAL DEFAULT 0,
        total_descuentos REAL,
        liquido REAL,
        base_tributable REAL,
        anticipo REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, trabajador_id, periodo),
        FOREIGN KEY (empresa_id) REFERENCES empresas(id),
        FOREIGN KEY (trabajador_id) REFERENCES trabajadores(id)
    )
    """)

    # Migración suave: agregar columnas si la tabla ya existía sin ellas
    for col, typ in [
        ("horas_extras", "REAL DEFAULT 0"),
        ("monto_horas_extras", "REAL DEFAULT 0"),
        ("asignacion_familiar", "REAL DEFAULT 0"),
        ("reforma_afp_emp", "REAL DEFAULT 0"),
        ("reforma_crp", "REAL DEFAULT 0"),
        ("reforma_seguro_social", "REAL DEFAULT 0"),
        ("anticipo", "REAL DEFAULT 0"),
    ]:
        try:
            c.execute(f"ALTER TABLE liquidaciones ADD COLUMN {col} {typ}")
        except Exception:
            pass
    try:
        c.execute("ALTER TABLE trabajadores ADD COLUMN tramo_asignacion_familiar TEXT DEFAULT 'D'")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE trabajadores ADD COLUMN numero_cargas INTEGER DEFAULT 0")
    except Exception:
        pass

    c.execute("""
    CREATE TABLE IF NOT EXISTS vacaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trabajador_id INTEGER NOT NULL,
        empresa_id INTEGER NOT NULL,
        fecha_inicio DATE,
        fecha_termino DATE,
        dias_habiles REAL,
        dias_corridos REAL,
        tipo TEXT DEFAULT 'Legales',  -- Legales, Proporcionales, Progresivas
        periodo_devengo TEXT,
        comprobante_generado INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trabajador_id) REFERENCES trabajadores(id),
        FOREIGN KEY (empresa_id) REFERENCES empresas(id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS finiquitos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trabajador_id INTEGER NOT NULL,
        empresa_id INTEGER NOT NULL,
        contrato_id INTEGER,
        fecha_termino DATE NOT NULL,
        causal TEXT,
        vacaciones_proporcionales_dias REAL,
        vacaciones_proporcionales_monto REAL,
        indemnizacion_anos REAL DEFAULT 0,
        aviso_previo REAL DEFAULT 0,
        otros_montos REAL DEFAULT 0,
        total_finiquito REAL,
        observaciones TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (trabajador_id) REFERENCES trabajadores(id),
        FOREIGN KEY (empresa_id) REFERENCES empresas(id)
    )
    """)

    # Datos iniciales de ejemplo basados en los documentos
    c.execute("SELECT COUNT(*) FROM empresas")
    if c.fetchone()[0] == 0:
        c.execute("""
        INSERT INTO empresas (rut, razon_social, direccion, comuna, ciudad, telefono, mutual, tasa_mutual, representante_legal, rut_representante)
        VALUES 
        ('76.065.376-4', 'I PROPIEDADES LIMITADA', 'LOS ABEDULES 3090', 'VITACURA', 'SANTIAGO', '224349552', 'ACHS', 0.93, 'Representante Legal', '11.111.111-1'),
        ('77.217.854-9', 'INVERSIONES AGROTURISMO Y ECOTURISMO LOS PUENTES SpA', 'Camino Las Parcelas, Parcela N° 24', 'ISLA DE MAIPO', 'ISLA DE MAIPO', '', 'ACHS', 0.93, 'CARLOS EUGENIO VELASCO CAVERLOTTY', '8.377.242-5')
        """)

    # Indicadores base (idempotente) — UF/UTM/topes oficiales + Ley 21.735
    import json
    afp_tasas = {
        "Capital": 11.44, "Cuprum": 11.44, "Habitat": 11.27,
        "PlanVital": 11.16, "Provida": 11.45, "Modelo": 10.58, "Uno": 10.46
    }
    # Julio 2026 (antes del tramo 3,5% de la reforma)
    c.execute("""
    INSERT OR IGNORE INTO indicadores (periodo, uf, utm, tope_afp, tope_afc, tope_inp, sis_tasa, renta_minima, afp_tasas)
    VALUES ('2026-07', 40844.79, 71649, 3676031, 5522216, 2449219, 1.88, 553553, ?)
    """, (json.dumps(afp_tasas),))
    # Agosto 2026 (entra cotización empleador 3,5% Ley 21.735) — asegurar UTM y topes
    c.execute("""
    INSERT OR REPLACE INTO indicadores (periodo, uf, utm, tope_afp, tope_afc, tope_inp, sis_tasa, renta_minima, afp_tasas)
    VALUES ('2026-08', 40864.55, 71649, 3676031, 5522215, 2450687, 0.0, 553553, ?)
    """, (json.dumps(afp_tasas),))
    # Asegurar UTM en julio si ya existía sin ella
    c.execute("UPDATE indicadores SET utm = COALESCE(utm, 71649), sis_tasa = COALESCE(sis_tasa, 1.88) WHERE periodo = '2026-07'")

    # Factores de actualización Superintendencia de Pensiones (referencia a Dic 2025)
    # Usados para actualizar rentas mensuales en Formulario 1887 (C3, C4, etc.)
    c.execute("SELECT COUNT(*) FROM factores_actualizacion WHERE anio_rentas = 2025")
    if c.fetchone()[0] == 0:
        # Columna 2025 de tabla SP "Factores de Actualización Diciembre de 2025"
        factores_2025 = {
            1: 1.026, 2: 1.022, 3: 1.016, 4: 1.014, 5: 1.012, 6: 1.017,
            7: 1.008, 8: 1.007, 9: 1.003, 10: 1.003, 11: 1.000, 12: 1.000,
        }
        # Dic se actualiza a 1.0 (mismo mes de cierre). Ajuste: SP muestra 1.036 para dic de años anteriores;
        # para el año corriente a diciembre el factor del mes de cierre es 1.0.
        for mes, fac in factores_2025.items():
            c.execute(
                "INSERT OR REPLACE INTO factores_actualizacion (anio_rentas, mes, factor) VALUES (?,?,?)",
                (2025, mes, fac),
            )
        # Placeholder 2026 (identidad hasta publicar SP) — usuario puede editar
        for mes in range(1, 13):
            c.execute(
                "INSERT OR IGNORE INTO factores_actualizacion (anio_rentas, mes, factor) VALUES (?,?,?)",
                (2026, mes, 1.0),
            )

    conn.commit()
    conn.close()

init_db()

# ============================================================
# FUNCIONES DE CÁLCULO CHILE
# ============================================================

def get_indicadores(periodo: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM indicadores WHERE periodo = ?", (periodo,)).fetchone()
    conn.close()
    if row:
        import json
        d = dict(row)
        d["afp_tasas"] = json.loads(d["afp_tasas"]) if d["afp_tasas"] else {}
        return d
    return None

# Tramos Asignación Familiar (valores Julio 2026 Previred – se pueden actualizar vía indicadores)
ASIGNACION_FAMILIAR_TRAMOS = {
    "A": {"monto": 22601, "renta_max": 649039},
    "B": {"monto": 13870, "renta_max": 947990},
    "C": {"monto": 4382,  "renta_max": 1478539},
    "D": {"monto": 0,     "renta_max": 999999999},
}

def get_factores_actualizacion(anio_rentas: int) -> dict:
    """Devuelve {mes: factor} para actualizar rentas del año comercial a diciembre."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT mes, factor FROM factores_actualizacion WHERE anio_rentas = ? ORDER BY mes",
        (anio_rentas,),
    ).fetchall()
    conn.close()
    if rows:
        return {int(r["mes"]): float(r["factor"]) for r in rows}
    # Fallback identidad
    return {m: 1.0 for m in range(1, 13)}

def determinar_tramo_asignacion(renta_imponible):
    """Determina tramo A/B/C/D según renta imponible del trabajador"""
    if renta_imponible <= 649039:
        return "A"
    if renta_imponible <= 947990:
        return "B"
    if renta_imponible <= 1478539:
        return "C"
    return "D"

def calcular_horas_extras(sueldo_base, jornada_semanal, horas_extras, recargo=1.5):
    """
    Valor hora ordinaria = sueldo_base / (jornada_semanal * 30/7) ≈ sueldo / horas mensuales
    Horas extras con recargo 50% (Art. 32 Código del Trabajo) por defecto.
    """
    if not horas_extras or horas_extras <= 0 or not sueldo_base:
        return 0.0
    horas_mensuales = jornada_semanal * (30.0 / 7.0)  # ≈ 4.2857 semanas
    if horas_mensuales <= 0:
        horas_mensuales = 180.0
    valor_hora = sueldo_base / horas_mensuales
    return round(valor_hora * recargo * horas_extras)


def tasas_reforma_ley_21735(periodo: str) -> dict:
    """
    Gradualidad cotización empleador Ley N° 21.735 (remuneraciones del mes indicado).
    Retorna tasas en proporción (0.001 = 0,1%) y flags de aplicación.

    Tramos oficiales (Superintendencia de Pensiones / Previsión Social):
    - ago-2025 a jul-2026: total 1,0%  = 0,1% CCI + 0,9% CRP/FAPP  (+ SIS clásico aparte)
    - ago-2026 a jul-2027: total 3,5%  = 0,1% CCI + 0,9% CRP + 2,5% Seguro Social (incluye SIS)
    - ago-2027 a jul-2028: total 4,25% = 0,25% CCI + 1,5% CRP + 2,5% Seguro Social
    - ... hasta 8,5% en ago-2033
    """
    out = {
        "aplica": False,
        "etapa": "pre",
        "cci": 0.0,          # cuenta capitalización individual (cargo empleador)
        "crp": 0.0,          # cotización con rentabilidad protegida / FAPP
        "seguro_social": 0.0,# 2,5% SSP (SIS + CEV) desde ago-2026
        "sis_clasico": True, # si aún se usa tasa SIS de indicadores
        "total_empleador": 0.0,
        "descripcion": "Sin reforma (solo SIS clásico)",
    }
    if not periodo or len(periodo) < 7:
        return out
    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
    except Exception:
        return out

    # Antes de agosto 2025: no aplica
    if anio < 2025 or (anio == 2025 and mes < 8):
        return out

    out["aplica"] = True
    # Clave año-mes como número comparable YYYYMM
    ym = anio * 100 + mes

    if ym <= 202607:  # ago-2025 .. jul-2026
        out.update({
            "etapa": "1pct",
            "cci": 0.001,
            "crp": 0.009,
            "seguro_social": 0.0,
            "sis_clasico": True,
            "total_empleador": 0.01,
            "descripcion": "Ley 21.735 etapa 1% (0,1% CCI + 0,9% CRP) + SIS clásico",
        })
    elif ym <= 202707:  # ago-2026 .. jul-2027
        out.update({
            "etapa": "3.5pct",
            "cci": 0.001,
            "crp": 0.009,
            "seguro_social": 0.025,
            "sis_clasico": False,
            "total_empleador": 0.035,
            "descripcion": "Ley 21.735 etapa 3,5% (0,1% CCI + 0,9% CRP + 2,5% Seguro Social)",
        })
    elif ym <= 202807:
        out.update({
            "etapa": "4.25pct",
            "cci": 0.0025,
            "crp": 0.015,
            "seguro_social": 0.025,
            "sis_clasico": False,
            "total_empleador": 0.0425,
            "descripcion": "Ley 21.735 etapa 4,25% (0,25% CCI + 1,5% CRP + 2,5% Seguro Social)",
        })
    elif ym <= 202907:
        out.update({
            "etapa": "5pct",
            "cci": 0.01,
            "crp": 0.015,
            "seguro_social": 0.025,
            "sis_clasico": False,
            "total_empleador": 0.05,
            "descripcion": "Ley 21.735 etapa 5,0%",
        })
    else:
        # Aproximación siguientes tramos hasta 8,5% (ago-2033)
        out.update({
            "etapa": "posterior",
            "cci": 0.01,
            "crp": 0.015,
            "seguro_social": 0.025,
            "sis_clasico": False,
            "total_empleador": 0.05,
            "descripcion": "Ley 21.735 tramo posterior (revisar tabla SP vigente)",
        })
    return out


def calcular_liquidacion(sueldo_base, gratificacion, movilizacion, colacion, otros,
                         dias, afp_nombre, salud_tipo, isapre_pactado_uf,
                         tipo_contrato, tasa_mutual, indicadores,
                         horas_extras=0, jornada_semanal=45,
                         numero_cargas=0, tramo_af=None, periodo=None,
                         anticipo=0):
    """
    Cálculo completo de liquidación Chile:
    - Horas extras (recargo 50%)
    - Asignación familiar (no imponible, no tributable)
    - Anticipo (descuento no previsional)
    - UTM disponible en indicadores (impuesto único / parámetros tributarios)
    - Reforma de Pensiones Ley 21.735 (gradualidad por periodo)
    """
    factor = dias / 30.0
    sueldo_calc = round(sueldo_base * factor)
    grat = round(gratificacion * factor)
    mov = round(movilizacion * factor)
    col = round(colacion * factor)
    otr = round(otros * factor)

    # Horas extras (imponibles)
    monto_he = calcular_horas_extras(sueldo_base, jornada_semanal, horas_extras)

    # Base imponible previsional: sueldo + gratificación + HE + otros imponibles
    # Movilización, colación y asignación familiar NO son imponibles
    total_imponible = sueldo_calc + grat + monto_he + otr

    uf = float(indicadores.get("uf") or 0)
    utm = float(indicadores.get("utm") or 0)
    tope_afp = float(indicadores.get("tope_afp") or 0)
    tope_afc = float(indicadores.get("tope_afc") or 0)
    sis_tasa = float(indicadores.get("sis_tasa") or 0) / 100.0
    afp_tasas = indicadores.get("afp_tasas") or {}
    renta_minima = float(indicadores.get("renta_minima") or 0)

    base_afp = min(total_imponible, tope_afp) if tope_afp else total_imponible
    base_afc = min(total_imponible, tope_afc) if tope_afc else total_imponible

    # --- Asignación familiar (no imponible, se paga al trabajador) ---
    if tramo_af is None:
        tramo_af = determinar_tramo_asignacion(total_imponible)
    monto_carga = ASIGNACION_FAMILIAR_TRAMOS.get(tramo_af, ASIGNACION_FAMILIAR_TRAMOS["D"])["monto"]
    asignacion_familiar = round(monto_carga * max(0, int(numero_cargas or 0)))

    # AFP trabajador (cotización obligatoria ~10% + comisión)
    tasa_afp = float(afp_tasas.get(afp_nombre, 11.44)) / 100.0
    afp_monto = round(base_afp * tasa_afp)

    # Salud 7%
    salud_7 = round(base_afp * 0.07)
    adicional_isapre = 0
    if salud_tipo and salud_tipo.upper() == "ISAPRE" and isapre_pactado_uf and isapre_pactado_uf > 0:
        pactado_pesos = round(float(isapre_pactado_uf) * uf)
        adicional_isapre = max(0, pactado_pesos - salud_7)

    # --- Reforma Ley 21.735 / SIS ---
    ref = tasas_reforma_ley_21735(periodo)
    reforma_afp_emp = round(base_afp * ref["cci"]) if ref["aplica"] else 0.0
    reforma_crp = round(base_afp * ref["crp"]) if ref["aplica"] else 0.0
    reforma_seguro_social = round(base_afp * ref["seguro_social"]) if ref["aplica"] else 0.0

    if ref["aplica"] and not ref["sis_clasico"]:
        # Desde ago-2026 el 2,5% Seguro Social reemplaza al SIS clásico
        sis_monto = reforma_seguro_social
    else:
        # SIS clásico cargo empleador (tasa de indicadores, ej. 1,88% / 2%)
        sis_monto = round(base_afp * sis_tasa)

    # AFC
    if tipo_contrato == "Plazo Fijo":
        afc_trab = 0
        afc_emp = round(base_afc * 0.03)
    else:
        afc_trab = round(base_afc * 0.006)
        afc_emp = round(base_afc * 0.024)

    # Mutual (cargo empleador)
    mutual_monto = round(base_afp * (float(tasa_mutual) / 100.0))

    # Total haberes (incluye no imponibles)
    total_haberes = sueldo_calc + grat + mov + col + otr + monto_he + asignacion_familiar

    # Anticipo (descuento no previsional; no afecta imponible ni cotizaciones)
    anticipo_monto = max(0.0, float(anticipo or 0))

    # Descuentos del trabajador = imposiciones + anticipo
    total_imposiciones = afp_monto + salud_7 + adicional_isapre + afc_trab
    total_descuentos = total_imposiciones + anticipo_monto
    liquido = total_haberes - total_descuentos

    # Base tributable (aprox.): imponible - cotizaciones previsionales trabajador
    base_tributable = max(0, total_imponible - afp_monto - salud_7 - adicional_isapre)

    # Carga empleador previsional total (informativo)
    carga_empleador = (
        reforma_afp_emp + reforma_crp + reforma_seguro_social
        + (sis_monto if ref.get("sis_clasico", True) else 0)
        + afc_emp + mutual_monto
    )

    return {
        "sueldo_calculado": sueldo_calc,
        "gratificacion": grat,
        "movilizacion": mov,
        "colacion": col,
        "otros_haberes": otr,
        "horas_extras": horas_extras or 0,
        "monto_horas_extras": monto_he,
        "asignacion_familiar": asignacion_familiar,
        "tramo_asignacion": tramo_af,
        "total_haberes": total_haberes,
        "total_imponible": total_imponible,
        "afp_monto": afp_monto,
        "salud_monto": salud_7,
        "adicional_isapre": adicional_isapre,
        "sis_monto": sis_monto,
        "afc_trabajador": afc_trab,
        "afc_empleador": afc_emp,
        "mutual_monto": mutual_monto,
        "reforma_afp_emp": reforma_afp_emp,
        "reforma_crp": reforma_crp,
        "reforma_seguro_social": reforma_seguro_social,
        "aplica_reforma": ref["aplica"],
        "reforma_etapa": ref["etapa"],
        "reforma_descripcion": ref["descripcion"],
        "anticipo": anticipo_monto,
        "otros_descuentos": anticipo_monto,  # alias para DOCX
        "total_imposiciones": total_imposiciones,
        "total_descuentos": total_descuentos,
        "liquido": liquido,
        "base_tributable": base_tributable,
        "base_afp": base_afp,
        "utm": utm,
        "uf": uf,
        "renta_minima": renta_minima,
        "carga_empleador_previsional": carga_empleador,
    }

def calcular_vacaciones_proporcionales(fecha_inicio, fecha_termino, sueldo_mensual):
    """Cálculo feriado proporcional según Código del Trabajo Art. 73"""
    if fecha_termino < fecha_inicio:
        return 0, 0
    delta = fecha_termino - fecha_inicio
    dias_trabajados = delta.days + 1
    # 15 días hábiles / 365
    dias_habiles = round((dias_trabajados / 365.0) * 15, 2)
    # Valor diario = sueldo / 30
    valor_diario = sueldo_mensual / 30.0
    # Se pagan días corridos aproximados (factor ~1.4 común en práctica)
    dias_a_pagar = round(dias_habiles * 1.4, 2)  # aproximación días corridos
    monto = round(valor_diario * dias_habiles)  # DT usa días hábiles * valor diario
    return dias_habiles, monto

def numero_a_palabras(n):
    """Convierte número entero a palabras (hasta cientos de millones)."""
    try:
        n = int(round(float(n)))
    except Exception:
        return str(n)
    unidades = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
    decenas = ["", "DIEZ", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
    especiales = {
        11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE",
        16: "DIECISEIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE",
    }
    centenas = [
        "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS",
        "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
    ]
    if n < 0:
        return "MENOS " + numero_a_palabras(-n)
    if n == 0:
        return "CERO"
    if n < 10:
        return unidades[n]
    if n < 20:
        return especiales.get(n, "DIEZ")
    if n < 100:
        d, u = divmod(n, 10)
        if d == 2 and u:
            return "VEINTI" + unidades[u]
        return decenas[d] + ((" Y " + unidades[u]) if u else "")
    if n < 1000:
        c, r = divmod(n, 100)
        if n == 100:
            return "CIEN"
        pref = centenas[c]
        return (pref + (" " + numero_a_palabras(r) if r else "")).strip()
    if n < 1000000:
        m, r = divmod(n, 1000)
        pref = "MIL" if m == 1 else numero_a_palabras(m) + " MIL"
        return (pref + (" " + numero_a_palabras(r) if r else "")).strip()
    if n < 1000000000:
        mill, r = divmod(n, 1000000)
        pref = "UN MILLON" if mill == 1 else numero_a_palabras(mill) + " MILLONES"
        return (pref + (" " + numero_a_palabras(r) if r else "")).strip()
    return str(n)

# ============================================================
# GENERADORES DE DOCUMENTOS
# ============================================================

def generar_contrato_docx(empresa, trabajador, contrato, ruta):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(11)

    doc.add_heading('CONTRATO DE TRABAJO', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.add_run(f"En {empresa['comuna'] or 'Santiago'}, a {datetime.now().strftime('%d de %B de %Y')}, entre ").bold = False
    p.add_run(f"{empresa['razon_social']}, RUT {empresa['rut']}").bold = True
    p.add_run(f", representada por don/ña {empresa['representante_legal'] or 'Representante Legal'}, RUN {empresa['rut_representante'] or ''}, "
              f"con domicilio en {empresa['direccion']}, comuna de {empresa['comuna']}, en lo sucesivo “El empleador” y don/ña ")
    p.add_run(f"{trabajador['nombres']} {trabajador['apellido_paterno']} {trabajador['apellido_materno'] or ''}, RUN {trabajador['rut']}").bold = True
    p.add_run(f", de nacionalidad {trabajador['nacionalidad']}, domiciliado en {trabajador['direccion'] or ''}, "
              f"comuna de {trabajador['comuna'] or ''}, en adelante “El trabajador”, se suscribe el siguiente contrato de trabajo:")

    doc.add_paragraph()
    doc.add_paragraph("PRIMERO.- El trabajador se compromete a ejecutar la siguiente labor: ").add_run(f"{contrato['cargo']}").bold = True
    doc.add_paragraph(f"en el establecimiento denominado {empresa['razon_social']}, ubicado en {contrato['lugar_trabajo'] or empresa['direccion']}, "
                      f"pudiendo ser trasladado a otro domicilio o labores similares por causa justificada, sin menoscabo para el trabajador.")

    doc.add_paragraph()
    doc.add_paragraph("SEGUNDO.- La jornada de trabajo será de ").add_run(f"{contrato['jornada_semanal']} horas semanales").bold = True
    doc.add_paragraph(f"en el siguiente horario: {contrato['horario'] or 'Lunes a viernes de 09:00 a 18:00 hrs.'}")
    doc.add_paragraph("Cuando por necesidades del funcionamiento de la empresa sea necesario trabajar tiempo extraordinario, "
                      "las partes acordarán por escrito previo a su realización. Queda prohibido realizar horas extras sin autorización.")

    doc.add_paragraph()
    doc.add_paragraph("TERCERO.- El empleador se compromete a remunerar al trabajador mensualmente:")
    doc.add_paragraph(f"Sueldo base: $ {contrato['sueldo_base']:,.0f}".replace(",", "."))
    if contrato['gratificacion']:
        doc.add_paragraph(f"Gratificación: $ {contrato['gratificacion']:,.0f}".replace(",", "."))
    if contrato['movilizacion']:
        doc.add_paragraph(f"Asignación de Movilización: $ {contrato['movilizacion']:,.0f} (no imponible)".replace(",", "."))
    if contrato['colacion']:
        doc.add_paragraph(f"Asignación de Colación: $ {contrato['colacion']:,.0f} (no imponible)".replace(",", "."))

    doc.add_paragraph()
    tipo = contrato['tipo_contrato']
    if tipo == "Plazo Fijo" and contrato['fecha_termino']:
        doc.add_paragraph(f"CUARTO.- El presente contrato será a Plazo Fijo y tendrá duración hasta el {contrato['fecha_termino']}.")
    else:
        doc.add_paragraph("CUARTO.- El presente contrato será de duración Indefinida.")

    doc.add_paragraph()
    doc.add_paragraph(f"QUINTO.- Se deja constancia que el trabajador ingresó al servicio el {contrato['fecha_inicio']}.")
    doc.add_paragraph(f"Para efectos previsionales el trabajador declara encontrarse afiliado a AFP {trabajador['afp']} "
                      f"y sistema de salud {trabajador['salud']}{' ('+trabajador['isapre']+')' if trabajador['isapre'] else ''}.")

    doc.add_paragraph()
    doc.add_paragraph("SEXTO.- Se entienden incorporadas al presente contrato todas las disposiciones legales vigentes.")

    doc.add_paragraph()
    doc.add_paragraph("Para constancia firman las partes el presente contrato en tres ejemplares.")
    doc.add_paragraph()
    doc.add_paragraph()
    tabla = doc.add_table(rows=2, cols=2)
    tabla.cell(0, 0).text = "_____________________________"
    tabla.cell(0, 1).text = "_____________________________"
    tabla.cell(1, 0).text = f"{empresa['razon_social']}\nRUT: {empresa['rut']}\nEMPLEADOR"
    tabla.cell(1, 1).text = f"{trabajador['nombres']} {trabajador['apellido_paterno']}\nRUT: {trabajador['rut']}\nTRABAJADOR"

    doc.save(ruta)
    return ruta

def _fmt_clp(n):
    """Formato pesos chilenos: 1.234.567"""
    try:
        return f"{int(round(float(n or 0))):,}".replace(",", ".")
    except Exception:
        return "0"


def _set_run(paragraph, text, bold=False, size=9, center=False):
    paragraph.clear() if hasattr(paragraph, "clear") else None
    if center:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(str(text))
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.bold = bold
    return run


def _cell(cell, text, bold=False, size=9, align="left"):
    """Escribe en celda limpiando párrafos previos."""
    cell.text = ""
    p = cell.paragraphs[0]
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "right":
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(str(text if text is not None else ""))
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.bold = bold


def _set_table_borders(table, color="000000", sz="4"):
    """Bordes finos tipo formulario (no grilla gruesa de Excel)."""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), sz)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color)
        borders.append(el)
    # quitar bordes previos
    for child in list(tblPr):
        if child.tag == qn("w:tblBorders"):
            tblPr.remove(child)
    tblPr.append(borders)


def generar_liquidacion_docx(empresa, trabajador, liq, periodo, ruta):
    """
    Liquidación formato profesional chileno (referencia PDF Joacime / AGOSTO 2026).
    Layout tipo formulario: encabezado centrado, ficha 2 columnas, haberes|descuentos, líquido.
    """
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.0)
        sec.bottom_margin = Cm(1.0)
        sec.left_margin = Cm(1.8)
        sec.right_margin = Cm(1.8)

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(9)

    ind = get_indicadores(periodo) or {}
    uf = float(ind.get("uf") or 0)
    tope_afp = float(ind.get("tope_afp") or 0)
    tope_afc = float(ind.get("tope_afc") or 0)

    def _p(text, bold=False, size=9, center=False, space_after=0):
        p = doc.add_paragraph()
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(str(text))
        run.font.name = "Arial"
        run.font.size = Pt(size)
        run.bold = bold
        return p

    # ----- Encabezado -----
    _p(str(empresa.get("razon_social") or "").upper(), bold=True, size=11, center=True)
    _p(str(empresa.get("rut") or ""), size=9, center=True)
    giro = empresa.get("giro") or empresa.get("actividad") or ""
    if giro:
        _p(str(giro).upper(), size=8, center=True)
    dir_line = f"{empresa.get('direccion') or ''}, {empresa.get('comuna') or ''} - {empresa.get('ciudad') or ''}".strip(" ,-")
    _p(dir_line.upper(), size=8, center=True)
    if empresa.get("telefono"):
        _p(str(empresa["telefono"]), size=8, center=True)

    _p("L I Q U I D A C I O N    D E   R E M U N E R A C I O N", bold=True, size=12, center=True)

    try:
        mes_anio = datetime.strptime(periodo + "-01", "%Y-%m-%d").strftime("%B / %Y").upper()
        for en, es in {
            "JANUARY": "ENERO", "FEBRUARY": "FEBRERO", "MARCH": "MARZO", "APRIL": "ABRIL",
            "MAY": "MAYO", "JUNE": "JUNIO", "JULY": "JULIO", "AUGUST": "AGOSTO",
            "SEPTEMBER": "SEPTIEMBRE", "OCTOBER": "OCTUBRE", "NOVEMBER": "NOVIEMBRE", "DECEMBER": "DICIEMBRE",
        }.items():
            mes_anio = mes_anio.replace(en, es)
    except Exception:
        mes_anio = periodo
    _p(mes_anio, bold=True, size=11, center=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(str(liq.get("area") or "ADMINISTRACION").upper())
    r.font.name = "Arial"
    r.font.size = Pt(9)

    # ----- Ficha trabajador -----
    nombre = f"{trabajador.get('nombres') or ''} {trabajador.get('apellido_paterno') or ''} {trabajador.get('apellido_materno') or ''}".strip()
    salud = (trabajador.get("salud") or "FONASA").upper()
    pactado = trabajador.get("pactado_salud_uf") or 0
    pactado_txt = "7,00  %" if not pactado else f"{float(pactado):.2f}".replace(".", ",") + " UF"
    fecha_ing = str(liq.get("fecha_inicio") or "")[:10]
    if len(fecha_ing) == 10 and fecha_ing[4] == "-":
        fecha_ing = f"{fecha_ing[8:10]}-{fecha_ing[5:7]}-{fecha_ing[0:4]}"
    uf_txt = f"{uf:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    info = doc.add_table(rows=5, cols=4)
    _set_table_borders(info, sz="4")
    filas_info = [
        ("Código", str(trabajador.get("id") or liq.get("trabajador_id") or ""), "Pactado Salud", pactado_txt),
        ("Nombre", nombre.upper(), "Base Tributable", _fmt_clp(liq.get("base_tributable"))),
        ("R.U.T.", trabajador.get("rut") or "", "U.F. del Mes", uf_txt),
        ("Fecha Ingreso", fecha_ing, "Tope Imponible", _fmt_clp(tope_afp)),
        ("Cargo", str(liq.get("cargo") or "").upper(), "Tope Imponible AFC", _fmt_clp(tope_afc)),
    ]
    for i, (a, b, c, d) in enumerate(filas_info):
        _cell(info.cell(i, 0), f"{a}  :", bold=False, size=8)
        _cell(info.cell(i, 1), b, size=9)
        _cell(info.cell(i, 2), f"{c}  :", bold=False, size=8)
        _cell(info.cell(i, 3), d, size=9, align="right")
    for col, w in enumerate([2.8, 5.5, 3.2, 2.8]):
        for row in info.rows:
            row.cells[col].width = Cm(w)

    doc.add_paragraph().paragraph_format.space_after = Pt(6)

    # ----- Haberes / Descuentos -----
    afp_nombre = (trabajador.get("afp") or "").upper()
    tasa_afp = ""
    try:
        tasas = ind.get("afp_tasas") or {}
        if isinstance(tasas, str):
            import json as _json
            tasas = _json.loads(tasas)
        key = afp_nombre.title() if afp_nombre.title() in (tasas or {}) else afp_nombre
        if key in (tasas or {}):
            tasa_afp = f"{float(tasas[key]):.2f}".replace(".", ",")
    except Exception:
        tasa_afp = ""

    total_imposicion = (
        float(liq.get("afp_monto") or 0)
        + float(liq.get("salud_monto") or 0)
        + float(liq.get("adicional_isapre") or 0)
        + float(liq.get("afc_trabajador") or 0)
    )
    otros_desc = float(liq.get("anticipo") or liq.get("otros_descuentos") or 0)
    total_desc = float(liq.get("total_descuentos") or (total_imposicion + otros_desc))

    haberes_rows = [
        ("SUELDO BASE", _fmt_clp(liq.get("sueldo_base") or liq.get("sueldo_calculado"))),
        ("SUELDO CALCULADO (30)", _fmt_clp(liq.get("sueldo_calculado"))),
    ]
    if float(liq.get("gratificacion") or 0) > 0:
        haberes_rows.append(("GRATIFICACION LEGAL", _fmt_clp(liq.get("gratificacion"))))
    if float(liq.get("monto_horas_extras") or 0) > 0:
        haberes_rows.append(("HORAS EXTRAS", _fmt_clp(liq.get("monto_horas_extras"))))
    if float(liq.get("movilizacion") or 0) > 0:
        haberes_rows.append(("MOVILIZACION", _fmt_clp(liq.get("movilizacion"))))
    if float(liq.get("colacion") or 0) > 0:
        haberes_rows.append(("COLACION", _fmt_clp(liq.get("colacion"))))
    if float(liq.get("asignacion_familiar") or 0) > 0:
        haberes_rows.append(("ASIGNACION FAMILIAR", _fmt_clp(liq.get("asignacion_familiar"))))
    if float(liq.get("otros_haberes") or 0) > 0:
        haberes_rows.append(("OTROS HABERES", _fmt_clp(liq.get("otros_haberes"))))
    haberes_rows.append(("TOTAL IMPONIBLE", _fmt_clp(liq.get("total_imponible"))))

    desc_rows = []
    if tasa_afp:
        desc_rows.append((f"{tasa_afp}  % {afp_nombre}", _fmt_clp(liq.get("afp_monto"))))
    else:
        desc_rows.append((afp_nombre or "AFP", _fmt_clp(liq.get("afp_monto"))))
    desc_rows.append((f"7,00  % {salud}", _fmt_clp(liq.get("salud_monto"))))
    if float(liq.get("adicional_isapre") or 0) > 0:
        desc_rows.append(("ADICIONAL ISAPRE", _fmt_clp(liq.get("adicional_isapre"))))
    if float(liq.get("afc_trabajador") or 0) > 0:
        desc_rows.append(("SEGURO CESANTIA", _fmt_clp(liq.get("afc_trabajador"))))
    desc_rows.append(("TOTAL IMPOSICION", _fmt_clp(total_imposicion)))
    if otros_desc > 0:
        desc_rows.append(("ANTICIPO 1", _fmt_clp(otros_desc)))
        desc_rows.append(("TOTAL OTROS DESCUENTOS", _fmt_clp(otros_desc)))

    n = max(len(haberes_rows), len(desc_rows))
    # +1 encabezado +1 totales +1 liquido
    tab = doc.add_table(rows=n + 3, cols=4)
    _set_table_borders(tab, sz="4")

    # Encabezados fusionados visualmente
    _cell(tab.cell(0, 0), "H A B E R E S", bold=True, size=9, align="center")
    _cell(tab.cell(0, 1), "", size=9)
    _cell(tab.cell(0, 2), "D E S C U E N T O S", bold=True, size=9, align="center")
    _cell(tab.cell(0, 3), "", size=9)
    try:
        tab.cell(0, 0).merge(tab.cell(0, 1))
        tab.cell(0, 2).merge(tab.cell(0, 3))
    except Exception:
        pass

    for i in range(n):
        row = i + 1
        if i < len(haberes_rows):
            _cell(tab.cell(row, 0), haberes_rows[i][0], size=9)
            _cell(tab.cell(row, 1), haberes_rows[i][1], size=9, align="right")
        else:
            _cell(tab.cell(row, 0), "", size=9)
            _cell(tab.cell(row, 1), "", size=9)
        if i < len(desc_rows):
            _cell(tab.cell(row, 2), desc_rows[i][0], size=9)
            _cell(tab.cell(row, 3), desc_rows[i][1], size=9, align="right")
        else:
            _cell(tab.cell(row, 2), "", size=9)
            _cell(tab.cell(row, 3), "", size=9)

    # Totales
    tr = n + 1
    _cell(tab.cell(tr, 0), "TOTAL HABERES  $", bold=True, size=9)
    _cell(tab.cell(tr, 1), _fmt_clp(liq.get("total_haberes")), bold=True, size=9, align="right")
    _cell(tab.cell(tr, 2), "TOTAL DESCUENTOS  $", bold=True, size=9)
    _cell(tab.cell(tr, 3), _fmt_clp(total_desc), bold=True, size=9, align="right")

    # Líquido (fila completa)
    lr = n + 2
    try:
        tab.cell(lr, 0).merge(tab.cell(lr, 3))
    except Exception:
        pass
    _cell(tab.cell(lr, 0), f"L I Q U I D O      $     {_fmt_clp(liq.get('liquido'))}", bold=True, size=12, align="center")

    for col, w in enumerate([5.0, 2.5, 5.0, 2.5]):
        for row in tab.rows:
            row.cells[col].width = Cm(w)

    palabras = numero_a_palabras(int(round(float(liq.get("liquido") or 0))))
    _p(f"SON: {palabras} PESOS", size=9)

    doc.add_paragraph()
    cert = doc.add_paragraph()
    cert.paragraph_format.space_after = Pt(6)
    run = cert.add_run(
        f"CERTIFICO QUE HE RECIBIDO DE  {str(empresa.get('razon_social') or '').upper()} "
        f"A MI ENTERA SATISFACCION, LA CANTIDAD INDICADA ANTERIORMENTE, COMO SALDO LIQUIDO DE MI SUELDO Y  NO TENGO CARGO NI "
        f"COBRO ALGUNO POSTERIOR QUE HACER, POR NINGUNO DE LOS MOTIVOS COMPRENDIDOS EN ESTA LIQUIDACION."
    )
    run.font.name = "Arial"
    run.font.size = Pt(8)

    doc.add_paragraph()
    doc.add_paragraph()
    firm = doc.add_paragraph()
    firm.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    fr = firm.add_run("_____________________________\nFIRMA DEL TRABAJADOR\nRECIBI COPIA")
    fr.font.name = "Arial"
    fr.font.size = Pt(9)

    doc.save(ruta)
    return ruta

def generar_comprobante_feriado_docx(empresa, trabajador, vac, contrato, ruta):
    """
    Comprobante de Feriado (formato profesional chileno).
    vac: dict con fecha_inicio, fecha_termino, dias_habiles, dias_corridos, tipo, valor (opcional)
    contrato: dict con fecha_inicio y sueldo_base si existe
    """
    doc = Document()
    for sec in doc.sections:
        sec.top_margin = Cm(1.2)
        sec.bottom_margin = Cm(1.2)
        sec.left_margin = Cm(1.5)
        sec.right_margin = Cm(1.5)

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(9)

    def _p(text, bold=False, size=9, center=False, right=False):
        p = doc.add_paragraph()
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif right:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(str(text))
        run.font.name = "Arial"
        run.font.size = Pt(size)
        run.bold = bold
        return p

    # Encabezado
    _p(str(empresa.get("razon_social") or "").upper(), bold=True, size=11, center=True)
    _p(str(empresa.get("rut") or ""), size=9, center=True)
    dir_line = f"{empresa.get('direccion') or ''}, {empresa.get('comuna') or ''} - {empresa.get('ciudad') or ''}".strip(" ,-")
    _p(dir_line.upper(), size=8, center=True)
    _p("ADMINISTRACION", size=9, right=True)

    # Título caja
    t = doc.add_table(rows=2, cols=3)
    _set_table_borders(t, sz="8")
    try:
        t.cell(0, 0).merge(t.cell(1, 0))
    except Exception:
        pass
    _cell(t.cell(0, 0), "COMPROBANTE\nDE FERIADO", bold=True, size=12, align="center")
    _cell(t.cell(0, 1), "LUGAR", bold=True, size=8, align="center")
    _cell(t.cell(0, 2), "FECHA EMISION", bold=True, size=8, align="center")
    lugar = (empresa.get("ciudad") or empresa.get("comuna") or "SANTIAGO").upper()
    fecha_em = datetime.now().strftime("%d de %B de %Y")
    # Meses ES
    for en, es in {
        "January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril",
        "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto",
        "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre",
    }.items():
        fecha_em = fecha_em.replace(en, es)
    _cell(t.cell(1, 1), lugar, size=9, align="center")
    _cell(t.cell(1, 2), fecha_em, size=9, align="center")

    doc.add_paragraph()
    texto = (
        "En cumplimiento a las disposiciones legales vigentes se deja constancia que a contar de las fechas que se indican, el "
        "trabajador hara uso (Total o Parcial) del Feriado Anual con Remuneración integra de acuerdo al siguiente detalle:"
    )
    _p(texto, size=8)

    # Trabajador / RUT / Periodo
    nombre = f"{trabajador.get('nombres') or ''} {trabajador.get('apellido_paterno') or ''} {trabajador.get('apellido_materno') or ''}".strip().upper()
    info = doc.add_table(rows=2, cols=3)
    _set_table_borders(info, sz="4")
    _cell(info.cell(0, 0), "TRABAJADOR", bold=True, size=8)
    _cell(info.cell(0, 1), "RUT", bold=True, size=8, align="center")
    _cell(info.cell(0, 2), "PERIODO", bold=True, size=8, align="center")
    _cell(info.cell(1, 0), nombre, size=10)
    _cell(info.cell(1, 1), trabajador.get("rut") or "", size=10, align="center")
    _cell(info.cell(1, 2), "TOTAL", size=9, align="center")

    _p("DESCANSO EFECTIVO ENTRE LAS FECHAS QUE SE INDICAN:", bold=True, size=8)

    def _fmt_f(f):
        if not f:
            return ""
        s = str(f)[:10]
        if len(s) == 10 and s[4] == "-":
            return f"{s[8:10]}-{s[5:7]}-{s[0:4]}"
        return s

    f_ini = vac.get("fecha_inicio")
    f_fin = vac.get("fecha_termino")
    # Periodo contractual del contrato (año de feriado)
    c_ini = ""
    c_fin = ""
    if contrato:
        c_ini = contrato.get("fecha_inicio") or ""
        # Periodo feriado anual típico: año calendario del inicio de vacaciones
        try:
            y = int(str(f_ini)[:4]) if f_ini else datetime.now().year
            c_ini = f"01-01-{y}"
            c_fin = f"31-12-{y}"
        except Exception:
            pass

    fechas = doc.add_table(rows=2, cols=5)
    _set_table_borders(fechas, sz="4")
    _cell(fechas.cell(0, 0), "PERIODO CONTRACTUAL", bold=True, size=8)
    _cell(fechas.cell(0, 1), "DESDE:", size=8)
    _cell(fechas.cell(0, 2), _fmt_f(f_ini), size=9)
    _cell(fechas.cell(0, 3), "HASTA:", size=8)
    _cell(fechas.cell(0, 4), _fmt_f(f_fin), size=9)
    _cell(fechas.cell(1, 0), "", size=8)
    _cell(fechas.cell(1, 1), "DESDE:", size=8)
    _cell(fechas.cell(1, 2), c_ini if isinstance(c_ini, str) and "-" in str(c_ini)[-5:] else _fmt_f(c_ini), size=9)
    _cell(fechas.cell(1, 3), "HASTA:", size=8)
    _cell(fechas.cell(1, 4), c_fin, size=9)
    # Corregir etiquetas fila 0 = descanso efectivo
    _cell(fechas.cell(0, 0), "DESCANSO EFECTIVO", bold=True, size=8)
    _cell(fechas.cell(1, 0), "PERIODO CONTRACTUAL", bold=True, size=8)

    doc.add_paragraph()

    dias_hab = float(vac.get("dias_habiles") or 0)
    dias_prog = float(vac.get("dias_progresivas") or 0) if vac.get("tipo") == "Progresivas" else 0.0
    dias_adic = float(vac.get("dias_adicionales") or 0)
    domingo = float(vac.get("domingo_inhabiles") or 0)
    fraccionado = float(vac.get("feriado_fraccionado") or 0)
    saldo = float(vac.get("saldo_pendiente") or 0)
    total_dias = dias_hab + dias_prog + dias_adic

    # Valor: sueldo/30 * dias hábiles (práctica habitual)
    sueldo = 0.0
    if contrato:
        sueldo = float(contrato.get("sueldo_base") or 0)
    valor = float(vac.get("valor") or 0)
    if not valor and sueldo and total_dias:
        valor = round(sueldo / 30.0 * total_dias)

    # Detalle + totales lado a lado
    outer = doc.add_table(rows=1, cols=2)
    left = outer.cell(0, 0)
    right = outer.cell(0, 1)
    left.text = ""
    right.text = ""

    # Tabla detalle en celda izquierda
    det = left.add_table(rows=7, cols=2)
    _set_table_borders(det, sz="4")
    _cell(det.cell(0, 0), "DETALLE DE FERIADO", bold=True, size=8, align="center")
    _cell(det.cell(0, 1), "DIAS", bold=True, size=8, align="center")
    filas_d = [
        ("DIAS HABILES", f"{dias_hab:.2f}"),
        ("VACACIONES PROGRESIVAS", f"{dias_prog:.2f}"),
        ("DIAS ADICIONALES", f"{dias_adic:.2f}"),
        ("DOMINGO E INHABILES", f"{domingo:.2f}"),
        ("FERIADO FRACCIONADO", f"{fraccionado:.2f}" if fraccionado else ""),
        ("SALDO PENDIENTE", f"{saldo:.2f}"),
    ]
    for i, (lab, val) in enumerate(filas_d, 1):
        _cell(det.cell(i, 0), lab, size=8)
        _cell(det.cell(i, 1), val, size=9, align="right")

    # Tabla valor a la derecha
    val_t = right.add_table(rows=3, cols=2)
    _set_table_borders(val_t, sz="4")
    _cell(val_t.cell(0, 0), "DIAS", bold=True, size=8, align="center")
    _cell(val_t.cell(0, 1), "VALOR", bold=True, size=8, align="center")
    _cell(val_t.cell(1, 0), f"{total_dias:.2f}", size=11, align="center")
    _cell(val_t.cell(1, 1), _fmt_clp(valor), size=11, align="center")
    _cell(val_t.cell(2, 0), "TOTAL", bold=True, size=9, align="center")
    _cell(val_t.cell(2, 1), _fmt_clp(valor), bold=True, size=9, align="center")

    doc.add_paragraph()
    doc.add_paragraph()

    firmas = doc.add_table(rows=3, cols=2)
    _set_table_borders(firmas, sz="4")
    _cell(firmas.cell(0, 0), "", size=9)
    _cell(firmas.cell(0, 1), "", size=9)
    _cell(firmas.cell(1, 0), "", size=9)
    _cell(firmas.cell(1, 1), "", size=9)
    _cell(firmas.cell(2, 0), "NOMBRE Y FIRMA DEL EMPLEADOR O EMPRESA", bold=True, size=7, align="center")
    _cell(firmas.cell(2, 1), "NOMBRE Y FIRMA DEL TRABAJADOR", bold=True, size=7, align="center")

    doc.add_paragraph()
    nota = doc.add_paragraph()
    nr = nota.add_run(
        'NOTA:  Se deja constancia que el cálculo del feriado se ha hecho de conformidad a lo dispuesto en el capítulo VII, '
        '"Del Feriado anual y de los permisos, Capítulo 1 del Código del Trabajo".'
    )
    nr.font.name = "Arial"
    nr.font.size = Pt(7)

    doc.save(ruta)
    return ruta


def generar_finiquito_docx(empresa, trabajador, finiquito, contrato, ruta):
    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(11)

    doc.add_heading('Finiquito de Contrato de Trabajo', 0).alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.add_run(f"En {empresa['comuna'] or 'Santiago'}, a {datetime.now().strftime('%d de %B de %Y')}, entre ")
    p.add_run(f"{empresa['razon_social']}, RUT {empresa['rut']}").bold = True
    p.add_run(f", representada legalmente por don/ña {empresa['representante_legal']}, RUN {empresa['rut_representante']}, "
              f"domiciliado en {empresa['direccion']}, Comuna de {empresa['comuna']}, en adelante “el empleador” por una parte y la otra don/ña ")
    p.add_run(f"{trabajador['nombres']} {trabajador['apellido_paterno']} {trabajador['apellido_materno'] or ''}, RUN {trabajador['rut']}").bold = True
    p.add_run(f", de nacionalidad {trabajador['nacionalidad']}, en adelante “el trabajador”, se deja testimonio y se ha acordado el finiquito que consta de las siguientes cláusulas:")

    doc.add_paragraph()
    doc.add_paragraph("PRIMERO:").bold = True
    doc.add_paragraph(f"El trabajador prestó servicios al empleador en calidad de: {contrato['cargo']}, "
                      f"desde el {contrato['fecha_inicio']} hasta el {finiquito['fecha_termino']}, "
                      f"fecha esta última en que su contrato de trabajo ha terminado por la causal contemplada en el "
                      f"Artículo {finiquito['causal']} del Código del Trabajo.")

    doc.add_paragraph()
    doc.add_paragraph("SEGUNDO:").bold = True
    doc.add_paragraph(f"Don/ña {trabajador['nombres']} {trabajador['apellido_paterno']}, declara recibir en este acto, a su entera satisfacción, "
                      f"de parte de {empresa['razon_social']}, las sumas que a continuación se indican por los siguientes conceptos:")

    doc.add_paragraph(f"Vacaciones Proporcionales {finiquito['vacaciones_proporcionales_dias']:.2f} Días    $ {finiquito['vacaciones_proporcionales_monto']:,.0f}".replace(",", "."))
    if finiquito['indemnizacion_anos']:
        doc.add_paragraph(f"Indemnización por años de servicio    $ {finiquito['indemnizacion_anos']:,.0f}".replace(",", "."))
    if finiquito['aviso_previo']:
        doc.add_paragraph(f"Aviso previo    $ {finiquito['aviso_previo']:,.0f}".replace(",", "."))
    if finiquito['otros_montos']:
        doc.add_paragraph(f"Otros conceptos    $ {finiquito['otros_montos']:,.0f}".replace(",", "."))

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.add_run(f"TOTAL FINIQUITO    $ {finiquito['total_finiquito']:,.0f}".replace(",", ".")).bold = True

    doc.add_paragraph()
    doc.add_paragraph("TERCERO:").bold = True
    doc.add_paragraph(f"En consecuencia, el empleador pagará a don/ña {trabajador['nombres']} {trabajador['apellido_paterno']}, "
                      f"la cantidad de $ {finiquito['total_finiquito']:,.0f} ({numero_a_palabras(int(finiquito['total_finiquito']))} pesos), "
                      f"este valor será cancelado con transferencia electrónica a la cuenta del trabajador.")

    doc.add_paragraph()
    doc.add_paragraph("CUARTO:").bold = True
    doc.add_paragraph(f"Don/ña {trabajador['nombres']} {trabajador['apellido_paterno']}, deja constancia que durante el tiempo que prestó servicios "
                      f"a {empresa['razon_social']}, recibió oportunamente el total de las remuneraciones, beneficios y demás prestaciones convenidas "
                      f"de acuerdo a su contrato de trabajo, y que en tal virtud el empleador nada le adeuda por tales conceptos, ni por horas "
                      f"extraordinarias, asignación familiar, feriados legales, imposiciones previsionales, así como por ningún otro concepto. "
                      f"En consecuencia, declara que no tiene reclamo alguno que formular, otorgando el más amplio, completo, total y definitivo finiquito.")

    doc.add_paragraph()
    doc.add_paragraph("Para constancia, las partes firman el presente finiquito en dos ejemplares.")
    doc.add_paragraph()
    doc.add_paragraph()
    tabla = doc.add_table(rows=2, cols=2)
    tabla.cell(0, 0).text = "_____________________________"
    tabla.cell(0, 1).text = "_____________________________"
    tabla.cell(1, 0).text = f"{empresa['razon_social']}\nRUT {empresa['rut']}\nEMPLEADOR"
    tabla.cell(1, 1).text = f"{trabajador['nombres']} {trabajador['apellido_paterno']}\nRUN {trabajador['rut']}\nTRABAJADOR"

    doc.save(ruta)
    return ruta

def generar_previred_txt(empresa_id, periodo, ruta):
    """Genera archivo TXT formato largo variable por separador (simplificado 105 campos)"""
    conn = get_conn()
    liqs = conn.execute("""
        SELECT l.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno, t.afp, t.salud, t.isapre,
               c.tipo_contrato, c.fecha_inicio, e.rut as empresa_rut, e.razon_social
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        JOIN contratos c ON l.contrato_id = c.id
        JOIN empresas e ON l.empresa_id = e.id
        WHERE l.empresa_id = ? AND l.periodo = ?
    """, (empresa_id, periodo)).fetchall()
    conn.close()

    if not liqs:
        return None

    lineas = []
    for liq in liqs:
        rut = liq['rut'].replace(".", "").replace("-", "")
        dv = rut[-1]
        rut_num = rut[:-1]
        ap_pat = (liq['apellido_paterno'] or "")[:30]
        ap_mat = (liq['apellido_materno'] or "")[:30]
        nombres = (liq['nombres'] or "")[:30]
        # Campos mínimos del formato Previred (simplificado para prototipo)
        # En producción se deben mapear los 105 campos exactos
        campos = [
            rut_num, dv, ap_pat, ap_mat, nombres,
            liq['periodo'].replace("-", ""),  # periodo
            str(int(liq['total_imponible'])),  # renta imponible
            str(int(liq['afp_monto'])),        # cotización AFP
            str(int(liq['salud_monto'] + liq['adicional_isapre'])),  # salud
            str(int(liq['sis_monto'])),        # SIS
            str(int(liq['afc_trabajador'])),   # AFC trab
            str(int(liq['afc_empleador'])),    # AFC emp
            str(int(liq['mutual_monto'])),     # mutual
            liq['afp'] or "Provida",
            liq['salud'] or "FONASA",
            "0",  # días licencia etc.
        ]
        lineas.append(";".join(campos))

    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    return ruta


# ============================================================
# LIBRO DE REMUNERACIONES + FORMULARIO / CERTIFICADO 1887
# ============================================================

def generar_libro_remuneraciones(empresa_id, periodo, ruta):
    """Genera Libro de Remuneraciones mensual en Excel (formato legal simplificado DT)"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, numbers
    from openpyxl.utils import get_column_letter

    conn = get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    liqs = conn.execute("""
        SELECT l.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno,
               t.afp, t.salud, c.cargo, c.tipo_contrato
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        LEFT JOIN contratos c ON l.contrato_id = c.id
        WHERE l.empresa_id = ? AND l.periodo = ?
        ORDER BY t.apellido_paterno, t.nombres
    """, (empresa_id, periodo)).fetchall()
    conn.close()

    if not liqs:
        return None

    wb = Workbook()
    ws = wb.active
    ws.title = f"Libro {periodo}"

    thin = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF", size=9)
    title_font = Font(bold=True, size=14)
    subtitle_font = Font(bold=True, size=11)

    # Encabezado
    ws.merge_cells('A1:AC1')
    ws['A1'] = "LIBRO DE REMUNERACIONES"
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A2:AC2')
    ws['A2'] = f"{emp['razon_social']}  |  RUT: {emp['rut']}  |  Periodo: {periodo}"
    ws['A2'].font = subtitle_font
    ws['A2'].alignment = Alignment(horizontal='center')

    ws.merge_cells('A3:AC3')
    ws['A3'] = f"Dirección: {emp.get('direccion') or ''} , {emp.get('comuna') or ''} - {emp.get('ciudad') or ''}"
    ws['A3'].alignment = Alignment(horizontal='center')

    # Columnas Libro de Remuneraciones Chile (incluye HE, Asig. Familiar y Reforma Pensiones)
    headers = [
        "N°", "RUT", "Apellido Paterno", "Apellido Materno", "Nombres", "Cargo",
        "Días Trab.", "Hrs Extras", "Monto HE", "Sueldo Base", "Gratificación",
        "Movilización", "Colación", "Asig. Familiar", "Otros Haberes",
        "Total Haberes", "Total Imponible",
        "AFP", "Salud", "Adic. Isapre", "AFC Trab.", "Total Descuentos", "Líquido a Pago",
        "SIS / Seg.Social (Emp)", "Mutual (Emp)", "AFC Emp",
        "Reforma 0,1% AFP Emp", "Reforma 0,9% CRP", "Reforma 2,5% Seg.Social"
    ]

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
        cell.border = thin

    def _g(liq, key, default=0):
        try:
            return liq[key] if liq[key] is not None else default
        except (KeyError, IndexError, TypeError):
            return default

    for i, liq in enumerate(liqs, 1):
        row = [
            i,
            liq['rut'],
            liq['apellido_paterno'] or "",
            liq['apellido_materno'] or "",
            liq['nombres'] or "",
            liq['cargo'] or "",
            _g(liq, 'dias_trabajados', 30),
            _g(liq, 'horas_extras'),
            _g(liq, 'monto_horas_extras'),
            _g(liq, 'sueldo_base'),
            _g(liq, 'gratificacion'),
            _g(liq, 'movilizacion'),
            _g(liq, 'colacion'),
            _g(liq, 'asignacion_familiar'),
            _g(liq, 'otros_haberes'),
            _g(liq, 'total_haberes'),
            _g(liq, 'total_imponible'),
            _g(liq, 'afp_monto'),
            _g(liq, 'salud_monto'),
            _g(liq, 'adicional_isapre'),
            _g(liq, 'afc_trabajador'),
            _g(liq, 'total_descuentos'),
            _g(liq, 'liquido'),
            _g(liq, 'sis_monto'),
            _g(liq, 'mutual_monto'),
            _g(liq, 'afc_empleador'),
            _g(liq, 'reforma_afp_emp'),
            _g(liq, 'reforma_crp'),
            _g(liq, 'reforma_seguro_social'),
        ]
        for col, val in enumerate(row, 1):
            cell = ws.cell(row=5 + i, column=col, value=val)
            cell.border = thin
            if col >= 8 and isinstance(val, (int, float)):
                cell.number_format = '#,##0'
            cell.alignment = Alignment(horizontal='center' if col <= 7 else 'right')

    # Totales
    total_row = 6 + len(liqs)
    ws.cell(row=total_row, column=1, value="TOTALES").font = Font(bold=True)
    for col in range(8, len(headers) + 1):
        col_letter = get_column_letter(col)
        cell = ws.cell(row=total_row, column=col,
                       value=f"=SUM({col_letter}6:{col_letter}{5+len(liqs)})")
        cell.font = Font(bold=True)
        cell.number_format = '#,##0'
        cell.border = thin

    # Anchos
    widths = [5, 14, 15, 15, 16, 16, 9, 9, 11, 12, 12, 11, 11, 12, 11,
              12, 12, 10, 10, 11, 10, 12, 12, 14, 11, 10, 12, 12, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.row_dimensions[5].height = 30

    # Pie legal
    pie = total_row + 2
    ws.cell(row=pie, column=1,
            value="Libro de Remuneraciones confeccionado conforme al Art. 54 del Código del Trabajo y normativa de la Dirección del Trabajo.")
    ws.merge_cells(start_row=pie, start_column=1, end_row=pie, end_column=10)

    # ===== Hoja: Asiento de Centralización Contable =====
    _agregar_hoja_asiento_centralizacion(wb, emp, periodo, liqs)

    wb.save(ruta)
    return ruta


def _agregar_hoja_asiento_centralizacion(wb, emp, periodo, liqs):
    """
    Asiento de centralización de remuneraciones (estilo ERP chileno / AVSOFT).
    Debe = gasto + aportes empleador; Haber = retenciones + anticipos + líquido por pagar.
    """
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter

    def _sum(key):
        total = 0.0
        for liq in liqs:
            try:
                v = liq[key]
                total += float(v or 0)
            except (KeyError, TypeError, ValueError):
                pass
        return round(total)

    # Haberes (gasto)
    sueldo = _sum("sueldo_calculado") or _sum("sueldo_base")
    grat = _sum("gratificacion")
    mov = _sum("movilizacion")
    col = _sum("colacion")
    he = _sum("monto_horas_extras")
    af_fam = _sum("asignacion_familiar")
    otros_h = _sum("otros_haberes")

    # Aportes empleador
    afc_emp = _sum("afc_empleador")
    reforma_afp = _sum("reforma_afp_emp")       # 0,1% CCI
    reforma_crp = _sum("reforma_crp")           # 0,9% / seguro vida
    reforma_ss = _sum("reforma_seguro_social")  # 2,5%
    sis = _sum("sis_monto")
    mutual = _sum("mutual_monto")

    # Retenciones trabajador (por AFP / salud)
    afp_total = _sum("afp_monto")
    salud = _sum("salud_monto") + _sum("adicional_isapre")
    afc_trab = _sum("afc_trabajador")
    anticipos = _sum("anticipo")
    liquido = _sum("liquido")

    # Desglose AFP por institución
    afp_por = {}
    for liq in liqs:
        try:
            nombre = (liq["afp"] or "AFP").upper()
            afp_por[nombre] = afp_por.get(nombre, 0) + float(liq["afp_monto"] or 0)
        except Exception:
            pass
    afp_por = {k: round(v) for k, v in afp_por.items() if v}

    # Salud: FONASA vs ISAPRE (simplificado: si salud contiene FONASA)
    fonasa = 0
    isapre = 0
    for liq in liqs:
        try:
            mon = float(liq["salud_monto"] or 0) + float(liq["adicional_isapre"] or 0)
            if str(liq["salud"] or "").upper().startswith("FON"):
                fonasa += mon
            else:
                isapre += mon
        except Exception:
            pass
    fonasa, isapre = round(fonasa), round(isapre)

    # Líneas DEBE
    debe_lineas = []
    if sueldo:
        debe_lineas.append(("SUELDO BASE CALC.", sueldo))
    if grat:
        debe_lineas.append(("GRATIFICACION", grat))
    if he:
        debe_lineas.append(("HORAS EXTRAS", he))
    if mov:
        debe_lineas.append(("MOVILIZACION", mov))
    if col:
        debe_lineas.append(("COLACION", col))
    if af_fam:
        debe_lineas.append(("ASIGNACION FAMILIAR", af_fam))
    if otros_h:
        debe_lineas.append(("OTROS HABERES", otros_h))
    if afc_emp:
        debe_lineas.append(("SEGURO DE CESANTIA EMPLEADOR", afc_emp))
    if reforma_afp:
        debe_lineas.append(("APORTE EMPLEADOR CAP.INDIVIDUAL", reforma_afp))
    if reforma_crp:
        debe_lineas.append(("APORTE EMPLEADOR CAP. DE VIDA", reforma_crp))
    if mutual:
        debe_lineas.append(("ACC. DEL TRABAJO", mutual))
    if sis:
        debe_lineas.append(("S.I.S.", sis))
    if reforma_ss:
        debe_lineas.append(("SEGURO SOCIAL", reforma_ss))

    # Líneas HABER
    haber_lineas = []
    for nombre, mon in sorted(afp_por.items()):
        haber_lineas.append((nombre, mon))
    if fonasa:
        haber_lineas.append(("I.P.S. / FONASA", fonasa))
    if isapre:
        haber_lineas.append(("ISAPRE", isapre))
    if afc_trab:
        haber_lineas.append(("SEGURO CESANTIA TRABAJADOR", afc_trab))
    if anticipos:
        haber_lineas.append(("ANTICIPOS", anticipos))
    if liquido:
        haber_lineas.append(("REMUNERACIONES POR PAGAR", liquido))
    if mutual:
        haber_lineas.append(("MUTUAL DE SEGURIDAD", mutual))
    if reforma_ss:
        haber_lineas.append(("SEGURO SOCIAL (por pagar)", reforma_ss))
    if reforma_afp:
        haber_lineas.append(("APORTE CAP.INDIVIDUAL (por pagar)", reforma_afp))
    if reforma_crp:
        haber_lineas.append(("APORTE CAP. DE VIDA (por pagar)", reforma_crp))
    if sis:
        haber_lineas.append(("S.I.S. (por pagar)", sis))
    if afc_emp:
        haber_lineas.append(("SEGURO CESANTIA EMPLEADOR (por pagar)", afc_emp))

    total_debe = sum(x[1] for x in debe_lineas)
    total_haber = sum(x[1] for x in haber_lineas)

    # Cuadratura: si hay diferencia por redondeo, ajustar REMUNERACIONES POR PAGAR
    dif = total_debe - total_haber
    if abs(dif) >= 1 and haber_lineas:
        # buscar remuneraciones por pagar
        for i, (nom, mon) in enumerate(haber_lineas):
            if "REMUNERACIONES POR PAGAR" in nom:
                haber_lineas[i] = (nom, mon + dif)
                total_haber += dif
                break

    ws = wb.create_sheet("Asiento Centralizacion")
    thin = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(bold=True, color="FFFFFF", size=10)
    debe_fill = PatternFill("solid", fgColor="FFF2CC")
    haber_fill = PatternFill("solid", fgColor="DDEBF7")
    total_fill = PatternFill("solid", fgColor="E2EFDA")

    ws.merge_cells("A1:D1")
    ws["A1"] = "ASIENTO DE CENTRALIZACIÓN DE REMUNERACIONES"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A1"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A2:D2")
    ws["A2"] = f"{emp.get('razon_social') or ''}  |  RUT: {emp.get('rut') or ''}  |  Periodo: {periodo}"
    ws["A2"].alignment = Alignment(horizontal="center")

    ws.merge_cells("A3:D3")
    ws["A3"] = "Consulta Asiento Remuneraciones (centralización contable)"
    ws["A3"].font = Font(italic=True, size=9)

    for col, h in enumerate(["Descripción", "Debe", "Haber", "Observación"], 1):
        cell = ws.cell(row=5, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = thin
        cell.alignment = Alignment(horizontal="center")

    row = 6
    # Debe primero
    for desc, mon in debe_lineas:
        ws.cell(row=row, column=1, value=desc).border = thin
        c = ws.cell(row=row, column=2, value=mon)
        c.number_format = '#,##0'
        c.border = thin
        c.fill = debe_fill
        ws.cell(row=row, column=3, value=None).border = thin
        ws.cell(row=row, column=4, value="Gasto / aporte empleador").border = thin
        row += 1

    for desc, mon in haber_lineas:
        ws.cell(row=row, column=1, value=desc).border = thin
        ws.cell(row=row, column=2, value=None).border = thin
        c = ws.cell(row=row, column=3, value=mon)
        c.number_format = '#,##0'
        c.border = thin
        c.fill = haber_fill
        ws.cell(row=row, column=4, value="Retención / pasivo").border = thin
        row += 1

    # Totales
    ws.cell(row=row, column=1, value="TOTALES").font = Font(bold=True)
    ws.cell(row=row, column=1).border = thin
    c1 = ws.cell(row=row, column=2, value=total_debe)
    c1.font = Font(bold=True)
    c1.number_format = '#,##0'
    c1.fill = total_fill
    c1.border = thin
    c2 = ws.cell(row=row, column=3, value=total_haber)
    c2.font = Font(bold=True)
    c2.number_format = '#,##0'
    c2.fill = total_fill
    c2.border = thin
    ws.cell(row=row, column=4, value="Debe = Haber" if total_debe == total_haber else f"Dif: {total_debe - total_haber}").border = thin

    row += 2
    ws.cell(row=row, column=1, value="Nota: Asiento generado automáticamente desde liquidaciones del periodo. Ajustar cuentas contables según plan de cuentas de la empresa.")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 28


def generar_formulario_1887(empresa_id, anio_tributario, ruta):
    """
    Genera Formulario 1887 (Declaración Jurada Anual Impuesto Único 2ª Categoría)
    basado en el formato del archivo form1887-at2026.xls proporcionado.
    anio_tributario = año de la declaración (ej. 2026 declara rentas 2025)
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter

    conn = get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    # Periodo de rentas = año anterior al tributario
    anio_rentas = anio_tributario - 1
    periodos = [f"{anio_rentas}-{m:02d}" for m in range(1, 13)]

    # Agregar liquidaciones del año de rentas por trabajador
    rows = conn.execute("""
        SELECT t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno,
               SUM(l.total_imponible) as renta_total,
               SUM(l.liquido) as liquido_total,
               COUNT(l.id) as meses,
               GROUP_CONCAT(l.periodo) as periodos_list
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        WHERE l.empresa_id = ? AND l.periodo IN ({})
        GROUP BY t.id
        ORDER BY t.apellido_paterno, t.nombres
    """.format(",".join("?" * 12)), (empresa_id, *periodos)).fetchall()

    # Detalle mensual por trabajador para la grilla de meses
    detalle = {}
    for r in rows:
        tid = r['id']
        meses_data = conn.execute("""
            SELECT periodo, total_imponible, liquido, base_tributable
            FROM liquidaciones
            WHERE trabajador_id = ? AND periodo IN ({})
        """.format(",".join("?" * 12)), (tid, *periodos)).fetchall()
        detalle[tid] = {d['periodo']: d for d in meses_data}

    conn.close()

    if not rows:
        return None

    # Factores de actualización del año de rentas (SP / SII)
    factores = get_factores_actualizacion(anio_rentas)

    wb = Workbook()
    ws = wb.active
    ws.title = f"Formulario 1887 AT {anio_tributario}"

    thin = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    bold = Font(bold=True, size=10)
    title_font = Font(bold=True, size=14)
    header_fill = PatternFill("solid", fgColor="D9E2F3")

    # Encabezado Formulario 1887
    ws['A1'] = "FORMULARIO 1887"
    ws['A1'].font = title_font
    ws.merge_cells('A1:N1')

    ws['A3'] = "AÑO TRIBUTARIO:"
    ws['C3'] = anio_tributario
    ws['C3'].font = bold
    ws['E3'] = f"Factores act. rentas {anio_rentas} aplicados"
    ws['E3'].font = Font(italic=True, size=9)

    ws['A5'] = "DECLARANTES"
    ws['A5'].font = bold
    ws['L5'] = f"Fecha de Emisión: {datetime.now().strftime('%d de %B de %Y')}"

    ws['A7'] = f"R.U.T.: {emp['rut']}     {emp['razon_social']}"
    ws['A8'] = f"Dirección: {emp.get('direccion') or ''}       Comuna: {emp.get('comuna') or ''}"
    ws['A9'] = f"Teléfono: {emp.get('telefono') or ''}"

    ws['A11'] = "INFORMADOS"
    ws['A11'].font = bold

    # Cabeceras columnas principales (basado en form1887-at2026.xls)
    # Nº | RUT | Renta Total Neta Pag. (Art.42 N°1) | Impuesto Unico Retenido | Mayor Retención Solic. (Art.88) |
    # Rta.Total No Gravada | Rta.Total Exenta | Rebaja por Zonas Extremas | 3% Prestamo Tasa 0% | Meses 1-12 | Cant.Hrs Jornada Semana | Nº Certif.
    headers1 = ["Nº", "R.U.T.", "Renta Total Neta Pag. (Art.42 N°1)", "Impuesto Unico Retenido",
                "Mayor Retención Solic. (Art.88)", "Rta.Total No Gravada", "Rta.Total Exenta",
                "Rebaja por Zonas Extremas", "3% Prestamo Tasa 0%", "Meses trabajados",
                "Cant. Hrs Jornada Semana", "Nº Certif."]
    for col, h in enumerate(headers1, 1):
        cell = ws.cell(row=13, column=col, value=h)
        cell.font = Font(bold=True, size=8)
        cell.fill = header_fill
        cell.border = thin
        cell.alignment = Alignment(wrap_text=True, horizontal='center')

    for i, r in enumerate(rows, 1):
        rut = r['rut']
        tid = r['id']
        # Renta total neta ACTUALIZADA: suma (monto_mes × factor_mes) según SII / SP
        renta_neta_act = 0.0
        renta_sin_act = 0.0
        if tid in detalle:
            for per, d in detalle[tid].items():
                try:
                    mes = int(per.split("-")[1])
                except Exception:
                    mes = 12
                fac = factores.get(mes, 1.0)
                monto = float(d['total_imponible'] or 0)
                renta_sin_act += monto
                renta_neta_act += monto * fac
        else:
            renta_neta_act = float(r['renta_total'] or 0)
            renta_sin_act = renta_neta_act
        renta_neta = int(round(renta_neta_act))
        # Impuesto único retenido: por ahora 0 (integrar tabla SII + factor si se retiene)
        impuesto = 0
        meses = r['meses'] or 0
        row_data = [
            i, rut, renta_neta, impuesto, 0, 0, 0, 0, 0, meses, 45.0, i
        ]
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=13 + i, column=col, value=val)
            cell.border = thin
            if col >= 3 and isinstance(val, (int, float)) and col != 10 and col != 11:
                cell.number_format = '#,##0'

    # Totales
    tot_row = 14 + len(rows)
    ws.cell(row=tot_row, column=1, value="TOTALES").font = bold
    for col in [3, 4]:
        col_letter = get_column_letter(col)
        cell = ws.cell(row=tot_row, column=col,
                       value=f"=SUM({col_letter}14:{col_letter}{13+len(rows)})")
        cell.font = bold
        cell.number_format = '#,##0'
        cell.border = thin

    # Segunda sección: detalle mensual (como en el ejemplo)
    det_start = tot_row + 3
    ws.cell(row=det_start, column=1, value="DETALLE MENSUAL DE RENTAS (Total Imponible por mes)").font = bold

    meses_nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    ws.cell(row=det_start + 1, column=1, value="Nº").font = Font(bold=True, size=8)
    ws.cell(row=det_start + 1, column=2, value="RUT").font = Font(bold=True, size=8)
    for m, nombre in enumerate(meses_nombres, 3):
        cell = ws.cell(row=det_start + 1, column=m, value=nombre)
        cell.font = Font(bold=True, size=8)
        cell.fill = header_fill
        cell.border = thin
    ws.cell(row=det_start + 1, column=15, value="TOTAL").font = Font(bold=True, size=8)

    for i, r in enumerate(rows, 1):
        tid = r['id']
        ws.cell(row=det_start + 1 + i, column=1, value=i).border = thin
        ws.cell(row=det_start + 1 + i, column=2, value=r['rut']).border = thin
        total_anio = 0
        for m in range(1, 13):
            per = f"{anio_rentas}-{m:02d}"
            val = 0
            if tid in detalle and per in detalle[tid]:
                val = int(detalle[tid][per]['total_imponible'] or 0)
            total_anio += val
            cell = ws.cell(row=det_start + 1 + i, column=2 + m, value=val if val else "")
            cell.border = thin
            cell.number_format = '#,##0'
        cell = ws.cell(row=det_start + 1 + i, column=15, value=total_anio)
        cell.border = thin
        cell.number_format = '#,##0'
        cell.font = bold

    # Totales mensuales
    trow = det_start + 2 + len(rows)
    ws.cell(row=trow, column=1, value="TOTALES").font = bold
    for m in range(3, 16):
        col_letter = get_column_letter(m)
        cell = ws.cell(row=trow, column=m,
                       value=f"=SUM({col_letter}{det_start+2}:{col_letter}{det_start+1+len(rows)})")
        cell.font = bold
        cell.number_format = '#,##0'
        cell.border = thin

    # Representante
    rep_row = trow + 3
    ws.cell(row=rep_row, column=1, value="Representante Legal:")
    ws.cell(row=rep_row, column=3, value=f"{emp.get('rut_representante') or ''}     {emp.get('representante_legal') or ''}")
    ws.cell(row=rep_row + 1, column=1, value="Casos Informados")
    ws.cell(row=rep_row + 1, column=3, value=len(rows))

    # Anchos
    for col in range(1, 16):
        ws.column_dimensions[get_column_letter(col)].width = 14
    ws.column_dimensions['C'].width = 22
    ws.row_dimensions[13].height = 35

    wb.save(ruta)
    return ruta


def generar_certificados_1887(empresa_id, anio_tributario, ruta_zip):
    """
    Genera Certificados individuales de Sueldos (Certificado 1887) por trabajador
    y los empaqueta en un ZIP. Basado en formato cer1887-2023.xls.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    import zipfile
    import tempfile
    import os

    conn = get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    anio_rentas = anio_tributario - 1
    periodos = [f"{anio_rentas}-{m:02d}" for m in range(1, 13)]
    meses_nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

    trabajadores = conn.execute("""
        SELECT DISTINCT t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        WHERE l.empresa_id = ? AND l.periodo IN ({})
        ORDER BY t.apellido_paterno, t.nombres
    """.format(",".join("?" * 12)), (empresa_id, *periodos)).fetchall()

    if not trabajadores:
        conn.close()
        return None

    temp_dir = tempfile.mkdtemp()
    archivos = []

    for idx, trab in enumerate(trabajadores, 1):
        tid = trab['id']
        liqs = conn.execute("""
            SELECT periodo, sueldo_calculado, total_imponible, total_haberes,
                   afp_monto, salud_monto, adicional_isapre, total_descuentos, liquido, base_tributable
            FROM liquidaciones
            WHERE trabajador_id = ? AND periodo IN ({})
            ORDER BY periodo
        """.format(",".join("?" * 12)), (tid, *periodos)).fetchall()
        liq_by_mes = {l['periodo']: l for l in liqs}

        wb = Workbook()
        ws = wb.active
        ws.title = "Certificado Sueldos"

        # Encabezado empresa
        ws['A1'] = emp['razon_social']
        ws['A1'].font = Font(bold=True, size=12)
        ws['A2'] = emp['rut']
        ws['A3'] = f"{emp.get('direccion') or ''}, {emp.get('comuna') or ''}"
        ws['A4'] = emp.get('ciudad') or ""

        ws.merge_cells('A6:H6')
        ws['A6'] = f"CERTIFICADO N° {idx} SOBRE SUELDOS Y OTRAS RENTAS"
        ws['A6'].font = Font(bold=True, size=12)
        ws['A6'].alignment = Alignment(horizontal='center')

        ws['A8'] = f"Certificado Nº: {idx}"
        ws['A9'] = f"{emp.get('ciudad') or 'SANTIAGO'},  {datetime.now().strftime('%d de %B de %Y')}"

        nombre_completo = f"{trab['apellido_paterno'] or ''} {trab['apellido_materno'] or ''} {trab['nombres'] or ''}".strip()
        ws['A11'] = f"El empleador, Habilitado o Pagador, {emp['razon_social']}, RUT {emp['rut']},"
        ws['A12'] = f"certifica que a don/ña {nombre_completo} RUT Nº: {trab['rut']},"
        ws['A13'] = f"durante el año {anio_rentas}, se le han pagado las siguientes rentas:"

        # Cabecera tabla mensual
        headers = ["Mes", "Total Haberes", "Total Imponible", "AFP", "Salud + Adic.", "Total Descuentos", "Líquido", "Base Tributable"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=15, column=col, value=h)
            cell.font = Font(bold=True, size=9)
            cell.border = Border(bottom=Side(style='thin'))

        tot_hab = tot_imp = tot_afp = tot_salud = tot_desc = tot_liq = tot_base = 0
        for m, nombre in enumerate(meses_nombres, 1):
            per = f"{anio_rentas}-{m:02d}"
            row = 15 + m
            ws.cell(row=row, column=1, value=nombre)
            if per in liq_by_mes:
                l = liq_by_mes[per]
                vals = [
                    int(l['total_haberes'] or 0),
                    int(l['total_imponible'] or 0),
                    int(l['afp_monto'] or 0),
                    int((l['salud_monto'] or 0) + (l['adicional_isapre'] or 0)),
                    int(l['total_descuentos'] or 0),
                    int(l['liquido'] or 0),
                    int(l['base_tributable'] or 0),
                ]
                for c, v in enumerate(vals, 2):
                    cell = ws.cell(row=row, column=c, value=v)
                    cell.number_format = '#,##0'
                tot_hab += vals[0]
                tot_imp += vals[1]
                tot_afp += vals[2]
                tot_salud += vals[3]
                tot_desc += vals[4]
                tot_liq += vals[5]
                tot_base += vals[6]
            else:
                for c in range(2, 9):
                    ws.cell(row=row, column=c, value=0)

        # Totales
        trow = 28
        ws.cell(row=trow, column=1, value="TOTAL").font = Font(bold=True)
        for col, val in enumerate([tot_hab, tot_imp, tot_afp, tot_salud, tot_desc, tot_liq, tot_base], 2):
            cell = ws.cell(row=trow, column=col, value=val)
            cell.font = Font(bold=True)
            cell.number_format = '#,##0'

        ws['A30'] = "Se extiende el presente certificado en cumplimiento de lo dispuesto en la Resolución Exenta"
        ws['A31'] = "del Servicio de Impuestos Internos sobre certificados de sueldos y otras rentas."
        ws['A33'] = "_______________________________"
        ws['A34'] = f"{emp.get('representante_legal') or 'Representante Legal'}"
        ws['A35'] = f"RUT: {emp.get('rut_representante') or emp['rut']}"
        ws['A36'] = emp['razon_social']

        for col in range(1, 9):
            ws.column_dimensions[get_column_letter(col)].width = 16
        ws.column_dimensions['A'].width = 14

        fname = f"Certificado_1887_{trab['rut'].replace('.', '').replace('-', '')}_{anio_rentas}.xlsx"
        fpath = os.path.join(temp_dir, fname)
        wb.save(fpath)
        archivos.append(fpath)

    conn.close()

    # Empaquetar en ZIP
    with zipfile.ZipFile(ruta_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in archivos:
            zf.write(f, os.path.basename(f))

    # Limpiar temp
    for f in archivos:
        try:
            os.remove(f)
        except Exception:
            pass
    try:
        os.rmdir(temp_dir)
    except Exception:
        pass

    return ruta_zip

# ============================================================
# LECTURA PDF INDICADORES PREVIRED
# ============================================================

def parse_indicadores_pdf(uploaded_file):
    """Lee PDF de indicadores Previred y extrae valores"""
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        # Extracciones con regex (tolerantes a formato Previred)
        uf = None
        for pat in [
            r'Al 31 de \w+ del \d{4}:\s*\$\s*([\d.]+,\d+)',
            r'Valor UF.*?\$\s*([\d.]+,\d+)',
            r'\bUF\b.*?\$\s*([\d.]+,\d+)',
        ]:
            uf_match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if uf_match:
                uf = float(uf_match.group(1).replace(".", "").replace(",", "."))
                break

        utm = None
        for pat in [
            r'UTM\s*\$?\s*([\d.]+)',
            r'Unidad Tributaria Mensual.*?\$\s*([\d.]+)',
            r'UTM.*?([\d]{2,3}\.[\d]{3})',
        ]:
            utm_match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if utm_match:
                utm = float(utm_match.group(1).replace(".", ""))
                break
        # Fallback habitual 2026 si el PDF no trae UTM legible
        if utm is None:
            utm = 71649.0

        tope_afp_match = re.search(r'afiliados a una AFP.*?\$\s*([\d.]+)', text, re.IGNORECASE | re.DOTALL)
        tope_afp = float(tope_afp_match.group(1).replace(".", "")) if tope_afp_match else None

        tope_afc_match = re.search(r'Seguro de Cesant[ií]a.*?\$\s*([\d.]+)', text, re.IGNORECASE | re.DOTALL)
        tope_afc = float(tope_afc_match.group(1).replace(".", "")) if tope_afc_match else None

        sis_match = re.search(r'Tasa SIS\s*([\d,]+)\s*%', text, re.IGNORECASE)
        sis = float(sis_match.group(1).replace(",", ".")) if sis_match else 0.0

        # AFP tasas
        afp_tasas = {}
        for afp in ["Capital", "Cuprum", "Habitat", "PlanVital", "Provida", "Modelo", "Uno"]:
            m = re.search(rf'{afp}\s+([\d,]+)\s*%', text)
            if m:
                afp_tasas[afp] = float(m.group(1).replace(",", "."))

        return {
            "uf": uf,
            "utm": utm,
            "tope_afp": tope_afp,
            "tope_afc": tope_afc,
            "sis_tasa": sis,
            "afp_tasas": afp_tasas,
            "texto_completo": text[:500]
        }
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

def _rut_sin_puntos(rut: str) -> str:
    """RUT limpio con guión (ej: 12345678-9)"""
    if not rut:
        return ""
    r = rut.replace(".", "").replace(" ", "").upper()
    return r


def generar_lre_csv(empresa_id, periodo, ruta):
    """
    Genera Libro de Remuneraciones Electrónico (LRE) en CSV/TXT
    delimitado por punto y coma para carga en portal Mi DT (Dirección del Trabajo).
    Nombre sugerido: RUTEMPLEADOR_YYYYMM.csv
    Columnas alineadas a conceptos habituales del Suplemento LRE (subconjunto operativo).
    """
    import csv
    conn = get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)
    liqs = conn.execute("""
        SELECT l.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno,
               t.afp, t.salud, t.numero_cargas, t.tramo_af,
               c.cargo, c.tipo_contrato, c.fecha_inicio
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        LEFT JOIN contratos c ON l.contrato_id = c.id
        WHERE l.empresa_id = ? AND l.periodo = ?
        ORDER BY t.apellido_paterno, t.nombres
    """, (empresa_id, periodo)).fetchall()
    conn.close()
    if not liqs:
        return None

    # Headers con códigos DT habituales (identificación + haberes + descuentos + totales)
    # El portal DT valida headers; este set cubre lo mínimo operativo del sistema.
    headers = [
        "1101",  # RUT trabajador
        "1102",  # Nombre completo
        "1103",  # Fecha inicio contrato
        "1107",  # Tipo jornada (1=ordinaria simplificado)
        "1115",  # Días trabajados
        "2001",  # Sueldo base
        "2002",  # Horas extras
        "2003",  # Gratificación
        "2101",  # Asignación familiar
        "2110",  # Movilización
        "2111",  # Colación
        "2201",  # Total haberes
        "2301",  # Total imponible
        "3101",  # Cotización AFP trabajador
        "3102",  # Cotización salud trabajador
        "3103",  # Adicional isapre
        "3104",  # AFC trabajador
        "3201",  # Impuesto único
        "3301",  # Total descuentos
        "4001",  # SIS / seguro empleador (info)
        "4002",  # Mutual / reforma (info)
        "5001",  # Líquido a pago
        "AFP",
        "SALUD",
    ]

    rows = []
    for l in liqs:
        l = dict(l)
        nombre = f"{l.get('nombres') or ''} {l.get('apellido_paterno') or ''} {l.get('apellido_materno') or ''}".strip()
        fecha_ini = (l.get("fecha_inicio") or "")[:10]
        def n(v):
            try:
                return str(int(round(float(v or 0))))
            except Exception:
                return "0"
        rows.append([
            _rut_sin_puntos(l.get("rut") or ""),
            nombre,
            fecha_ini,
            "1",
            n(l.get("dias_trabajados") or 30),
            n(l.get("sueldo_base")),
            n(l.get("monto_horas_extras") or l.get("horas_extras_monto") or 0),
            n(l.get("gratificacion")),
            n(l.get("asignacion_familiar")),
            n(l.get("movilizacion")),
            n(l.get("colacion")),
            n(l.get("total_haberes")),
            n(l.get("total_imponible")),
            n(l.get("afp_monto") or l.get("descuento_afp")),
            n(l.get("salud_monto") or l.get("descuento_salud")),
            n(l.get("salud_adicional") or 0),
            n(l.get("afc_trabajador") or l.get("descuento_afc")),
            n(l.get("impuesto_unico") or 0),
            n(l.get("total_descuentos")),
            n(l.get("sis") or l.get("sis_monto") or 0),
            n((l.get("mutual") or 0) + (l.get("reforma_empleador") or 0)),
            n(l.get("liquido")),
            l.get("afp") or "",
            l.get("salud") or "",
        ])

    path = Path(ruta)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(headers)
        w.writerows(rows)
    return str(path)


def generar_1887_csv_sii(empresa_id, anio_tributario, ruta):
    """
    Genera CSV para Importador de Datos del SII - Formulario 1887.
    Delimitador punto y coma. Montos enteros sin separador de miles.
    Columnas orientadas a la estructura habitual del importador 1887
    (RUT, nombre, renta neta actualizada, impuesto único, etc.).
    """
    import csv
    anio_rentas = int(anio_tributario) - 1
    conn = get_conn()
    emp = conn.execute("SELECT * FROM empresas WHERE id=?", (empresa_id,)).fetchone()
    if not emp:
        conn.close()
        return None
    emp = dict(emp)

    # Factores
    fac_rows = conn.execute(
        "SELECT mes, factor FROM factores_actualizacion WHERE anio_rentas=?",
        (anio_rentas,),
    ).fetchall()
    factores = {int(r["mes"]): float(r["factor"]) for r in fac_rows} if fac_rows else {m: 1.0 for m in range(1, 13)}

    periodos = [f"{anio_rentas}-{m:02d}" for m in range(1, 13)]
    trabajadores = conn.execute(f"""
        SELECT DISTINCT t.id, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
        FROM liquidaciones l
        JOIN trabajadores t ON l.trabajador_id = t.id
        WHERE l.empresa_id = ? AND l.periodo IN ({",".join("?"*12)})
        ORDER BY t.apellido_paterno, t.nombres
    """, (empresa_id, *periodos)).fetchall()

    if not trabajadores:
        conn.close()
        return None

    headers = [
        "RUT", "DV", "APELLIDO_PATERNO", "APELLIDO_MATERNO", "NOMBRES",
        "RENTA_TOTAL_NETA_ACTUALIZADA", "IMPUESTO_UNICO_RETENIDO",
        "MAYOR_RETENCION", "RENTA_TOTAL_NO_GRAVADA", "RENTA_EXENTA",
        "COTIZACIONES_PREVISIONALES", "IMPONIBLE_ANUAL",
    ]
    rows = []
    for t in trabajadores:
        t = dict(t)
        dets = conn.execute(f"""
            SELECT periodo, total_imponible, liquido, base_tributable,
                   COALESCE(afp_monto,0)+COALESCE(salud_monto,0)+COALESCE(afc_trabajador,0) as cotiz
            FROM liquidaciones
            WHERE trabajador_id=? AND empresa_id=? AND periodo IN ({",".join("?"*12)})
        """, (t["id"], empresa_id, *periodos)).fetchall()
        renta_act = 0.0
        impuesto = 0.0
        cotiz = 0.0
        imponible = 0.0
        for d in dets:
            d = dict(d)
            mes = int(d["periodo"][5:7])
            fac = factores.get(mes, 1.0)
            # renta neta aproximada: líquido o base tributaria según disponibilidad
            base = float(d.get("base_tributable") or d.get("liquido") or 0)
            renta_act += base * fac
            impuesto += float(d.get("impuesto_unico") or 0) * fac
            cotiz += float(d.get("cotiz") or 0)
            imponible += float(d.get("total_imponible") or 0)
        rut_full = _rut_sin_puntos(t.get("rut") or "")
        if "-" in rut_full:
            rut_num, dv = rut_full.split("-", 1)
        else:
            rut_num, dv = rut_full, ""
        rows.append([
            rut_num,
            dv,
            t.get("apellido_paterno") or "",
            t.get("apellido_materno") or "",
            t.get("nombres") or "",
            str(int(round(renta_act))),
            str(int(round(impuesto))),
            "0",
            "0",
            "0",
            str(int(round(cotiz))),
            str(int(round(imponible))),
        ])
    conn.close()

    path = Path(ruta)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(headers)
        w.writerows(rows)
    return str(path)



def main():
    # --- Candado de acceso / demo ---
    if not pantalla_acceso():
        st.stop()

    cfg_acc = cargar_config_acceso()
    dias_rest = _dias_restantes(cfg_acc)
    if cfg_acc.get("activo") and dias_rest is not None:
        if dias_rest <= 3:
            st.sidebar.warning(f"Demo: quedan {dias_rest} día(s)")
        else:
            st.sidebar.caption(f"Demo · {dias_rest} día(s) restantes")

    logo_path = BASE_DIR / "basecon-logo.png"
    h1, h2 = st.columns([1, 5])
    with h1:
        if logo_path.exists():
            st.image(str(logo_path), width=120)
        else:
            st.markdown("### 🇨🇱")
    with h2:
        st.title("BASECON")
        st.subheader("Sistema de Remuneraciones Multiempresa")
        st.caption("Contratos • Liquidaciones • Libro • Finiquitos • Vacaciones • Previred • DJ 1887 | Chile")

    if logo_path.exists():
        st.sidebar.image(str(logo_path), use_container_width=True)

    menu_items = [
        "🏠 Dashboard", "🏢 Empresas", "👥 Trabajadores", "📄 Contratos",
        "📊 Indicadores Previred", "💰 Liquidaciones", "📒 Libro de Remuneraciones",
        "🏖 Vacaciones", "📝 Finiquitos", "📤 Archivo Previred",
        "📋 Declaración Jurada 1887", "ℹ️ Ayuda",
    ]
    if st.session_state.get("es_admin"):
        menu_items.append("🔐 Acceso Demo")

    menu = st.sidebar.radio("Menú Principal", menu_items)

    if st.sidebar.button("Cerrar sesión"):
        st.session_state["acceso_ok"] = False
        st.session_state["es_admin"] = False
        st.rerun()

    conn = get_conn()

    # -------------------- DASHBOARD --------------------
    if menu == "🏠 Dashboard":
        st.header("Dashboard")
        col1, col2, col3, col4 = st.columns(4)
        n_emp = conn.execute("SELECT COUNT(*) FROM empresas").fetchone()[0]
        n_trab = conn.execute("SELECT COUNT(*) FROM trabajadores WHERE activo=1").fetchone()[0]
        n_liq = conn.execute("SELECT COUNT(*) FROM liquidaciones").fetchone()[0]
        n_fin = conn.execute("SELECT COUNT(*) FROM finiquitos").fetchone()[0]
        col1.metric("Empresas", n_emp)
        col2.metric("Trabajadores Activos", n_trab)
        col3.metric("Liquidaciones", n_liq)
        col4.metric("Finiquitos", n_fin)

        st.subheader("Empresas registradas")
        df = pd.read_sql("SELECT id, rut, razon_social, comuna FROM empresas", conn)
        st.dataframe(df, use_container_width=True)

        st.info("💡 Comienza cargando los **Indicadores Previred** del mes, luego crea/selecciona empresa y trabajadores.")

    # -------------------- EMPRESAS --------------------
    elif menu == "🏢 Empresas":
        st.header("Gestión de Empresas")
        with st.expander("➕ Nueva Empresa", expanded=False):
            with st.form("nueva_empresa"):
                c1, c2 = st.columns(2)
                rut = c1.text_input("RUT Empresa *", placeholder="76.065.376-4")
                razon = c2.text_input("Razón Social *")
                direccion = c1.text_input("Dirección")
                comuna = c2.text_input("Comuna")
                ciudad = c1.text_input("Ciudad")
                telefono = c2.text_input("Teléfono")
                mutual = c1.selectbox("Mutual", ["ACHS", "IST", "Mutual de Seguridad", "ISL"])
                tasa_mutual = c2.number_input("Tasa Mutual %", value=0.93, step=0.01)
                caja = c1.text_input("Caja Compensación (opcional)")
                repr_legal = c2.text_input("Representante Legal")
                rut_repr = c1.text_input("RUT Representante")
                if st.form_submit_button("Guardar Empresa"):
                    try:
                        conn.execute("""
                            INSERT INTO empresas (rut, razon_social, direccion, comuna, ciudad, telefono, mutual, tasa_mutual, caja_compensacion, representante_legal, rut_representante)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (rut, razon, direccion, comuna, ciudad, telefono, mutual, tasa_mutual, caja, repr_legal, rut_repr))
                        conn.commit()
                        st.success("Empresa creada correctamente")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.subheader("Listado de Empresas")
        df = pd.read_sql("SELECT * FROM empresas", conn)
        st.dataframe(df, use_container_width=True)

    # -------------------- TRABAJADORES --------------------
    elif menu == "👥 Trabajadores":
        st.header("Gestión de Trabajadores")
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}

        with st.expander("➕ Nuevo Trabajador", expanded=True):
            with st.form("nuevo_trabajador"):
                emp_sel = st.selectbox("Empresa *", list(emp_opts.keys()))
                c1, c2, c3 = st.columns(3)
                rut = c1.text_input("RUT *", placeholder="10.207.613-3")
                nombres = c2.text_input("Nombres *")
                ap_pat = c3.text_input("Apellido Paterno *")
                ap_mat = c1.text_input("Apellido Materno")
                f_nac = c2.date_input("Fecha Nacimiento", value=date(1990,1,1))
                nacionalidad = c3.text_input("Nacionalidad", value="Chilena")
                direccion = c1.text_input("Dirección")
                comuna = c2.text_input("Comuna")
                email = c3.text_input("Email")
                afp = c1.selectbox("AFP", ["Provida", "Habitat", "Capital", "Cuprum", "PlanVital", "Modelo", "Uno"])
                salud = c2.selectbox("Salud", ["FONASA", "ISAPRE"])
                isapre = c3.text_input("Isapre (si aplica)", placeholder="COLMENA")
                pactado = c1.number_input("Pactado Salud (UF)", value=0.0, step=0.001)
                cuenta = c2.text_input("Cuenta Bancaria")
                banco = c3.text_input("Banco", value="Banco Estado")
                num_cargas = c1.number_input("Nº Cargas familiares", min_value=0, value=0, step=1)
                tramo_af = c2.selectbox("Tramo Asignación Familiar", ["A", "B", "C", "D"],
                                        help="A: renta ≤ $649.039 → $22.601/carga | B: ≤ $947.990 → $13.870 | C: ≤ $1.478.539 → $4.382 | D: sin derecho")
                if st.form_submit_button("Guardar Trabajador"):
                    try:
                        conn.execute("""
                            INSERT INTO trabajadores (empresa_id, rut, nombres, apellido_paterno, apellido_materno,
                            fecha_nacimiento, nacionalidad, direccion, comuna, email, afp, salud, isapre, pactado_salud_uf,
                            cuenta_banco, banco, tramo_asignacion_familiar, numero_cargas)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (emp_opts[emp_sel], rut, nombres, ap_pat, ap_mat, f_nac, nacionalidad, direccion, comuna, email,
                              afp, salud, isapre, pactado, cuenta, banco, tramo_af, num_cargas))
                        conn.commit()
                        st.success("Trabajador creado")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.subheader("Trabajadores")
        df = pd.read_sql("""
            SELECT t.id, e.razon_social as empresa, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno,
                   t.afp, t.salud, t.numero_cargas, t.tramo_asignacion_familiar, t.activo
            FROM trabajadores t JOIN empresas e ON t.empresa_id = e.id
        """, conn)
        st.dataframe(df, use_container_width=True)

    # -------------------- CONTRATOS --------------------
    elif menu == "📄 Contratos":
        st.header("Contratos de Trabajo")
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="cont_emp")
        trabs = conn.execute("SELECT id, rut, nombres, apellido_paterno FROM trabajadores WHERE empresa_id=? AND activo=1", (emp_opts[emp_sel],)).fetchall()
        trab_opts = {f"{t['rut']} - {t['nombres']} {t['apellido_paterno']}": t['id'] for t in trabs}

        with st.expander("➕ Nuevo Contrato", expanded=True):
            with st.form("nuevo_contrato"):
                if not trab_opts:
                    st.warning("No hay trabajadores activos en esta empresa")
                else:
                    trab_sel = st.selectbox("Trabajador *", list(trab_opts.keys()))
                    c1, c2 = st.columns(2)
                    cargo = c1.text_input("Cargo *", value="GERENTE GENERAL")
                    tipo = c2.selectbox("Tipo Contrato", ["Indefinido", "Plazo Fijo", "Obra o faena"])
                    f_inicio = c1.date_input("Fecha Inicio *", value=date(2023,5,1))
                    f_termino = c2.date_input("Fecha Término (si aplica)", value=None)
                    sueldo = c1.number_input("Sueldo Base *", value=1200000, step=10000)
                    grat = c2.number_input("Gratificación", value=0, step=1000)
                    mov = c1.number_input("Movilización (no imponible)", value=0, step=1000)
                    col = c2.number_input("Colación (no imponible)", value=0, step=1000)
                    jornada = c1.number_input("Jornada Semanal", value=45)
                    horario = c2.text_input("Horario", value="Lunes a viernes 09:00 a 18:00")
                    lugar = st.text_input("Lugar de Trabajo")
                    if st.form_submit_button("Crear Contrato y Generar DOCX"):
                        tid = trab_opts[trab_sel]
                        eid = emp_opts[emp_sel]
                        cur = conn.execute("""
                            INSERT INTO contratos (trabajador_id, empresa_id, cargo, fecha_inicio, fecha_termino, tipo_contrato,
                            sueldo_base, gratificacion, movilizacion, colacion, jornada_semanal, horario, lugar_trabajo)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """, (tid, eid, cargo, f_inicio, f_termino, tipo, sueldo, grat, mov, col, jornada, horario, lugar))
                        conn.commit()
                        cid = cur.lastrowid

                        # Generar DOCX
                        emp = dict(conn.execute("SELECT * FROM empresas WHERE id=?", (eid,)).fetchone())
                        trab = dict(conn.execute("SELECT * FROM trabajadores WHERE id=?", (tid,)).fetchone())
                        cont = dict(conn.execute("SELECT * FROM contratos WHERE id=?", (cid,)).fetchone())
                        ruta = EXPORTS_DIR / f"contrato_{trab['rut'].replace('.','').replace('-','')}_{datetime.now().strftime('%Y%m%d')}.docx"
                        generar_contrato_docx(emp, trab, cont, str(ruta))
                        st.session_state["ultimo_contrato_docx"] = str(ruta)
                        st.success(f"Contrato creado y documento generado: {ruta.name}")

            # download_button DEBE ir fuera del form
            if st.session_state.get("ultimo_contrato_docx"):
                ruta_dl = Path(st.session_state["ultimo_contrato_docx"])
                if ruta_dl.exists():
                    with open(ruta_dl, "rb") as f:
                        st.download_button("⬇️ Descargar Contrato DOCX", f, file_name=ruta_dl.name, key="dl_contrato_docx")

        st.subheader("Contratos existentes")
        df = pd.read_sql("""
            SELECT c.id, e.razon_social, t.rut, t.nombres || ' ' || t.apellido_paterno as trabajador,
                   c.cargo, c.tipo_contrato, c.fecha_inicio, c.fecha_termino, c.sueldo_base, c.activo
            FROM contratos c
            JOIN empresas e ON c.empresa_id = e.id
            JOIN trabajadores t ON c.trabajador_id = t.id
        """, conn)
        st.dataframe(df, use_container_width=True)

    # -------------------- INDICADORES --------------------
    elif menu == "📊 Indicadores Previred":
        st.header("Indicadores Previsionales Previred")
        st.markdown("""
        Carga **UF, UTM, topes imponibles y tasas** del mes.  
        La **Ley 21.735** (reforma de pensiones) se aplica automáticamente según el periodo de la liquidación.
        """)

        uploaded = st.file_uploader("PDF Indicadores Previred", type=["pdf"])
        if uploaded:
            result = parse_indicadores_pdf(uploaded)
            if "error" in result:
                st.error(result["error"])
            else:
                st.success("PDF leído correctamente")
                st.json({k: v for k, v in result.items() if k != "texto_completo"})
                periodo_pdf = st.text_input("Periodo a guardar (YYYY-MM)", value="2026-08", key="ind_pdf_periodo")
                if st.button("Guardar Indicadores desde PDF"):
                    import json
                    conn.execute("""
                        INSERT OR REPLACE INTO indicadores
                        (periodo, uf, utm, tope_afp, tope_afc, tope_inp, sis_tasa, renta_minima, afp_tasas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        periodo_pdf,
                        result.get("uf"),
                        result.get("utm"),
                        result.get("tope_afp"),
                        result.get("tope_afc"),
                        result.get("tope_inp"),
                        result.get("sis_tasa") if result.get("sis_tasa") is not None else 0,
                        result.get("renta_minima"),
                        json.dumps(result.get("afp_tasas") or {}),
                    ))
                    conn.commit()
                    st.success(f"Indicadores {periodo_pdf} guardados (incl. UTM)")

        st.subheader("Edición manual de indicadores (incluye UTM)")
        with st.form("edit_indicadores"):
            col_a, col_b = st.columns(2)
            per_edit = col_a.text_input("Periodo (YYYY-MM)", value="2026-08")
            uf_e = col_a.number_input("UF ($)", value=40864.55, step=0.01, format="%.2f")
            utm_e = col_b.number_input("UTM ($)", value=71649.0, step=1.0, format="%.0f")
            tope_afp_e = col_a.number_input("Tope AFP / Salud ($)", value=3676031.0, step=1.0, format="%.0f")
            tope_afc_e = col_b.number_input("Tope AFC ($)", value=5522215.0, step=1.0, format="%.0f")
            tope_inp_e = col_a.number_input("Tope IPS/ex-INP ($)", value=2450687.0, step=1.0, format="%.0f")
            sis_e = col_b.number_input("Tasa SIS clásico (%)", value=0.0, step=0.01,
                                       help="Desde ago-2026 el SIS va dentro del 2,5% Seguro Social (dejar 0). Antes: 1,88% o 2%.")
            renta_min_e = col_a.number_input("Renta mínima imponible ($)", value=553553.0, step=1.0, format="%.0f")
            if st.form_submit_button("Guardar / actualizar indicadores"):
                import json
                afp_default = {
                    "Capital": 11.44, "Cuprum": 11.44, "Habitat": 11.27,
                    "PlanVital": 11.16, "Provida": 11.45, "Modelo": 10.58, "Uno": 10.46
                }
                prev = get_indicadores(per_edit)
                tasas = (prev or {}).get("afp_tasas") or afp_default
                conn.execute("""
                    INSERT OR REPLACE INTO indicadores
                    (periodo, uf, utm, tope_afp, tope_afc, tope_inp, sis_tasa, renta_minima, afp_tasas)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (per_edit, uf_e, utm_e, tope_afp_e, tope_afc_e, tope_inp_e, sis_e, renta_min_e, json.dumps(tasas)))
                conn.commit()
                st.success(f"Indicadores {per_edit} guardados — UF={uf_e:,.2f} | UTM={utm_e:,.0f}")

        st.subheader("Indicadores cargados")
        df = pd.read_sql(
            "SELECT periodo, uf, utm, tope_afp, tope_afc, tope_inp, sis_tasa, renta_minima FROM indicadores ORDER BY periodo DESC",
            conn,
        )
        st.dataframe(df, use_container_width=True)

        st.subheader("Ley 21.735 — qué aplica según periodo")
        st.markdown("""
        | Periodo remuneraciones | Cotización empleador | Detalle |
        |---|---|---|
        | ago-2025 → jul-2026 | **1,0%** | 0,1% CCI + 0,9% CRP + **SIS clásico** (indicadores) |
        | ago-2026 → jul-2027 | **3,5%** | 0,1% CCI + 0,9% CRP + **2,5% Seguro Social** (reemplaza SIS) |
        | ago-2027 → jul-2028 | **4,25%** | 0,25% CCI + 1,5% CRP + 2,5% Seguro Social |
        """)

        ind = get_indicadores("2026-08") or get_indicadores("2026-07")
        if ind:
            st.subheader("Detalle indicadores vigentes")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("UF", f"${ind['uf']:,.2f}")
            c2.metric("UTM", f"${ind.get('utm') or 0:,.0f}")
            c3.metric("Tope AFP", f"${ind['tope_afp']:,.0f}")
            c4.metric("SIS ind.", f"{ind['sis_tasa']}%")
            st.write("Tasas AFP:", ind.get("afp_tasas"))

    # -------------------- LIQUIDACIONES --------------------
    elif menu == "💰 Liquidaciones":
        st.header("Cálculo y Generación de Liquidaciones")
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="liq_emp")
        periodo = st.text_input("Periodo (YYYY-MM)", value="2026-07")
        dias_trab = st.number_input("Días trabajados (default)", min_value=1, max_value=30, value=30)

        ind = get_indicadores(periodo)
        if not ind:
            st.error(f"No hay indicadores para {periodo}. Cárgalos primero en **Indicadores Previred** (UF, UTM, topes).")
        else:
            ref = tasas_reforma_ley_21735(periodo)
            utm_val = ind.get("utm") or 0
            msg = (
                f"UF=${ind['uf']:,.2f} | **UTM=${utm_val:,.0f}** | "
                f"Tope AFP=${ind['tope_afp']:,.0f} | Tope AFC=${ind.get('tope_afc') or 0:,.0f} | "
                f"SIS ind.={ind['sis_tasa']}%"
            )
            if ref["aplica"]:
                msg += f" | ✅ {ref['descripcion']}"
            else:
                msg += " | Sin etapa reforma 21.735 (solo SIS clásico si corresponde)"
            st.info(msg)

            contratos = conn.execute("""
                SELECT c.id, t.id as tid, t.rut, t.nombres, t.apellido_paterno, t.afp, t.salud, t.isapre, t.pactado_salud_uf,
                       t.numero_cargas, t.tramo_asignacion_familiar,
                       c.sueldo_base, c.gratificacion, c.movilizacion, c.colacion, c.tipo_contrato, c.jornada_semanal
                FROM contratos c
                JOIN trabajadores t ON c.trabajador_id = t.id
                WHERE c.empresa_id = ? AND c.activo = 1
            """, (emp_opts[emp_sel],)).fetchall()

            st.subheader("Horas extras del periodo (opcional)")
            st.caption("Ingrese horas extras por trabajador. Recargo 50% (Art. 32 CT). Valor hora = sueldo ÷ (jornada semanal × 30/7).")
            he_inputs = {}
            if contratos:
                cols = st.columns(min(3, len(contratos)))
                for i, cont in enumerate(contratos):
                    with cols[i % len(cols)]:
                        he_inputs[cont['tid']] = st.number_input(
                            f"HE {cont['rut'][-8:]}", min_value=0.0, value=0.0, step=0.5,
                            key=f"he_{cont['tid']}_{periodo}"
                        )

            st.subheader("Anticipos del periodo (opcional)")
            st.caption("Monto ya pagado al trabajador que se descuenta del líquido (no afecta imponible ni cotizaciones).")
            anticipo_inputs = {}
            if contratos:
                cols_a = st.columns(min(3, len(contratos)))
                for i, cont in enumerate(contratos):
                    with cols_a[i % len(cols_a)]:
                        anticipo_inputs[cont['tid']] = st.number_input(
                            f"Anticipo {cont['rut'][-8:]}", min_value=0, value=0, step=1000,
                            key=f"ant_{cont['tid']}_{periodo}"
                        )

            if st.button("🔄 Calcular Liquidaciones del Periodo"):
                emp = dict(conn.execute("SELECT * FROM empresas WHERE id=?", (emp_opts[emp_sel],)).fetchone())
                for cont in contratos:
                    he = he_inputs.get(cont['tid'], 0)
                    ant = anticipo_inputs.get(cont['tid'], 0)
                    calc = calcular_liquidacion(
                        cont['sueldo_base'], cont['gratificacion'] or 0, cont['movilizacion'] or 0,
                        cont['colacion'] or 0, 0, dias_trab,
                        cont['afp'], cont['salud'], cont['pactado_salud_uf'] or 0,
                        cont['tipo_contrato'], emp['tasa_mutual'], ind,
                        horas_extras=he,
                        jornada_semanal=cont['jornada_semanal'] or 45,
                        numero_cargas=cont['numero_cargas'] or 0,
                        tramo_af=cont['tramo_asignacion_familiar'] or None,
                        periodo=periodo,
                        anticipo=ant,
                    )
                    conn.execute("""
                        INSERT OR REPLACE INTO liquidaciones
                        (empresa_id, trabajador_id, contrato_id, periodo, dias_trabajados,
                         horas_extras, monto_horas_extras, sueldo_base, sueldo_calculado,
                         gratificacion, movilizacion, colacion, asignacion_familiar, otros_haberes,
                         total_haberes, total_imponible, afp_monto, salud_monto,
                         adicional_isapre, sis_monto, afc_trabajador, afc_empleador, mutual_monto,
                         reforma_afp_emp, reforma_crp, reforma_seguro_social, anticipo,
                         total_descuentos, liquido, base_tributable)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (emp_opts[emp_sel], cont['tid'], cont['id'], periodo, dias_trab,
                          calc['horas_extras'], calc['monto_horas_extras'], cont['sueldo_base'],
                          calc['sueldo_calculado'], calc['gratificacion'], calc['movilizacion'], calc['colacion'],
                          calc['asignacion_familiar'], calc['otros_haberes'],
                          calc['total_haberes'], calc['total_imponible'], calc['afp_monto'], calc['salud_monto'],
                          calc['adicional_isapre'], calc['sis_monto'], calc['afc_trabajador'], calc['afc_empleador'],
                          calc['mutual_monto'], calc['reforma_afp_emp'], calc['reforma_crp'],
                          calc['reforma_seguro_social'], calc['anticipo'],
                          calc['total_descuentos'], calc['liquido'],
                          calc['base_tributable']))
                conn.commit()
                st.success(f"Liquidaciones calculadas para {len(contratos)} trabajadores")
                ref_ok = tasas_reforma_ley_21735(periodo)
                if ref_ok.get("aplica"):
                    st.success(f"Incluye cotizaciones Ley 21.735: {ref_ok.get('descripcion', '')}")

            # Mostrar y generar documentos
            liqs = conn.execute("""
                SELECT l.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno, t.afp, t.salud, t.isapre, t.pactado_salud_uf
                FROM liquidaciones l JOIN trabajadores t ON l.trabajador_id = t.id
                WHERE l.empresa_id = ? AND l.periodo = ?
            """, (emp_opts[emp_sel], periodo)).fetchall()

            if liqs:
                st.subheader(f"Liquidaciones {periodo}")
                cols_show = ["rut", "nombres", "apellido_paterno", "horas_extras", "monto_horas_extras",
                             "asignacion_familiar", "anticipo", "total_haberes", "total_descuentos", "liquido"]
                df = pd.DataFrame([dict(l) for l in liqs])
                for c in cols_show:
                    if c not in df.columns:
                        df[c] = 0
                st.dataframe(df[cols_show], use_container_width=True)

                def _prep_liq_doc(liq_row):
                    """Prepara dict de liquidación + genera DOCX. Retorna (ruta Path, nombre archivo)."""
                    emp = dict(conn.execute("SELECT * FROM empresas WHERE id=?", (emp_opts[emp_sel],)).fetchone())
                    trab = dict(conn.execute("SELECT * FROM trabajadores WHERE id=?", (liq_row["trabajador_id"],)).fetchone())
                    liq_d = dict(liq_row)
                    cont_row = conn.execute(
                        "SELECT cargo, fecha_inicio FROM contratos WHERE id=?",
                        (liq_d.get("contrato_id"),)
                    ).fetchone()
                    if cont_row:
                        cont_row = dict(cont_row)
                        liq_d["cargo"] = cont_row.get("cargo") or ""
                        liq_d["fecha_inicio"] = cont_row.get("fecha_inicio") or ""
                    if liq_d.get("anticipo") and not liq_d.get("otros_descuentos"):
                        liq_d["otros_descuentos"] = liq_d["anticipo"]
                    rut_clean = (liq_row["rut"] or "").replace(".", "").replace("-", "")
                    fname = f"liquidacion_{rut_clean}_{periodo}.docx"
                    ruta = EXPORTS_DIR / fname
                    generar_liquidacion_docx(emp, trab, liq_d, periodo, str(ruta))
                    return ruta, fname

                # --- Selección múltiple ---
                st.markdown("#### Generar / descargar liquidaciones")
                opts_map = {
                    f"{l['rut']} — {l['nombres']} {l['apellido_paterno']}  (líq. ${float(l['liquido'] or 0):,.0f})": l
                    for l in liqs
                }
                c1, c2 = st.columns([3, 1])
                with c1:
                    seleccion = st.multiselect(
                        "Seleccione trabajadores (puede marcar varios)",
                        options=list(opts_map.keys()),
                        default=list(opts_map.keys()),
                        key=f"liq_sel_{periodo}_{emp_opts[emp_sel]}",
                    )
                with c2:
                    st.caption("")
                    if st.button("Marcar todos", key=f"liq_all_{periodo}"):
                        st.session_state[f"liq_sel_{periodo}_{emp_opts[emp_sel]}"] = list(opts_map.keys())
                        st.rerun()

                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    gen_sel = st.button(
                        f"📄 Generar DOCX seleccionados ({len(seleccion)})",
                        disabled=not seleccion,
                        key=f"gen_sel_{periodo}",
                    )
                with col_g2:
                    gen_zip = st.button(
                        f"📦 Generar ZIP de seleccionados ({len(seleccion)})",
                        disabled=not seleccion,
                        key=f"gen_zip_{periodo}",
                    )

                if gen_sel and seleccion:
                    generados = []
                    for label in seleccion:
                        liq_row = opts_map[label]
                        ruta, fname = _prep_liq_doc(liq_row)
                        generados.append((ruta, fname, liq_row["rut"]))
                    st.success(f"Se generaron {len(generados)} liquidaciones DOCX")
                    st.session_state[f"liq_docs_{periodo}"] = [(str(r), n, rut) for r, n, rut in generados]

                if gen_zip and seleccion:
                    buf = io.BytesIO()
                    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                        for label in seleccion:
                            liq_row = opts_map[label]
                            ruta, fname = _prep_liq_doc(liq_row)
                            zf.write(str(ruta), fname)
                    buf.seek(0)
                    st.success(f"ZIP con {len(seleccion)} liquidaciones listo")
                    st.download_button(
                        "⬇️ Descargar ZIP de liquidaciones",
                        data=buf.getvalue(),
                        file_name=f"liquidaciones_{periodo}_{emp_opts[emp_sel]}.zip",
                        mime="application/zip",
                        key=f"dl_zip_{periodo}_{emp_opts[emp_sel]}",
                    )

                # Descargas individuales (de la última generación o bajo demanda)
                docs_prev = st.session_state.get(f"liq_docs_{periodo}") or []
                if docs_prev:
                    st.markdown("**Descargas individuales (última generación):**")
                    for ruta_s, fname, rut in docs_prev:
                        if Path(ruta_s).exists():
                            with open(ruta_s, "rb") as f:
                                st.download_button(
                                    f"⬇️ {fname}",
                                    f,
                                    file_name=fname,
                                    key=f"dl_ind_{periodo}_{rut}",
                                )

                # También una a una en expanders
                st.markdown("**Una a una:**")
                for liq in liqs:
                    with st.expander(f"Liquidación {liq['rut']} - Líquido ${float(liq['liquido'] or 0):,.0f}"):
                        st.write({
                            k: liq[k] for k in (
                                "total_haberes", "total_imponible", "afp_monto", "salud_monto",
                                "afc_trabajador", "anticipo", "total_descuentos", "liquido", "base_tributable"
                            ) if k in liq.keys()
                        })
                        if st.button(f"Generar y descargar DOCX — {liq['rut']}", key=f"doc_{liq['id']}"):
                            ruta, fname = _prep_liq_doc(dict(liq))
                            with open(ruta, "rb") as f:
                                st.download_button(
                                    "⬇️ Descargar Liquidación",
                                    f,
                                    file_name=fname,
                                    key=f"dl_{liq['id']}",
                                )

    # -------------------- VACACIONES --------------------
    elif menu == "🏖 Vacaciones":
        st.header("Control de Vacaciones / Comprobante de Feriado")
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="vac_emp")
        trabs = conn.execute(
            "SELECT id, rut, nombres, apellido_paterno, apellido_materno FROM trabajadores WHERE empresa_id=? AND activo=1",
            (emp_opts[emp_sel],)
        ).fetchall()
        trab_opts = {f"{t['rut']} - {t['nombres']} {t['apellido_paterno']}": t['id'] for t in trabs}

        with st.form("registrar_vacaciones"):
            trab_sel = st.selectbox("Trabajador", list(trab_opts.keys()) if trab_opts else ["Sin trabajadores"])
            f_ini = st.date_input("Fecha Inicio Vacaciones")
            f_fin = st.date_input("Fecha Término Vacaciones")
            tipo = st.selectbox("Tipo", ["Legales", "Proporcionales", "Progresivas"])
            dias_hab_in = st.number_input("Días hábiles", min_value=0.0, value=15.0, step=0.5)
            saldo_in = st.number_input("Saldo pendiente (días)", min_value=0.0, value=0.0, step=0.5)
            gen_comp = st.checkbox("Generar Comprobante de Feriado al registrar", value=True)
            if st.form_submit_button("Registrar"):
                if trab_opts:
                    dias_corr = (f_fin - f_ini).days + 1
                    conn.execute("""
                        INSERT INTO vacaciones (trabajador_id, empresa_id, fecha_inicio, fecha_termino, dias_habiles, dias_corridos, tipo)
                        VALUES (?,?,?,?,?,?,?)
                    """, (trab_opts[trab_sel], emp_opts[emp_sel], f_ini, f_fin, dias_hab_in, dias_corr, tipo))
                    conn.commit()
                    st.success("Vacaciones registradas")
                    if gen_comp:
                        emp = dict(conn.execute("SELECT * FROM empresas WHERE id=?", (emp_opts[emp_sel],)).fetchone())
                        trab = dict(conn.execute("SELECT * FROM trabajadores WHERE id=?", (trab_opts[trab_sel],)).fetchone())
                        cont = conn.execute(
                            "SELECT * FROM contratos WHERE trabajador_id=? AND activo=1 ORDER BY id DESC LIMIT 1",
                            (trab_opts[trab_sel],)
                        ).fetchone()
                        cont = dict(cont) if cont else {}
                        vac = {
                            "fecha_inicio": f_ini,
                            "fecha_termino": f_fin,
                            "dias_habiles": dias_hab_in,
                            "dias_corridos": dias_corr,
                            "tipo": tipo,
                            "saldo_pendiente": saldo_in,
                        }
                        rut_c = (trab.get("rut") or "").replace(".", "").replace("-", "")
                        ruta = EXPORTS_DIR / f"comprobante_feriado_{rut_c}_{f_ini}.docx"
                        generar_comprobante_feriado_docx(emp, trab, vac, cont, str(ruta))
                        st.session_state["ultimo_feriado_docx"] = str(ruta)
                        st.success("Comprobante de Feriado generado")

        if st.session_state.get("ultimo_feriado_docx"):
            ruta_f = Path(st.session_state["ultimo_feriado_docx"])
            if ruta_f.exists():
                with open(ruta_f, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar Comprobante de Feriado",
                        f,
                        file_name=ruta_f.name,
                        key="dl_feriado_ultimo",
                    )

        st.subheader("Historial de Vacaciones")
        vacs = conn.execute("""
            SELECT v.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno, t.id as tid
            FROM vacaciones v JOIN trabajadores t ON v.trabajador_id = t.id
            WHERE v.empresa_id = ?
            ORDER BY v.fecha_inicio DESC
        """, (emp_opts[emp_sel],)).fetchall()
        if vacs:
            df = pd.DataFrame([dict(v) for v in vacs])
            cols_show = [c for c in ["id", "rut", "nombres", "apellido_paterno", "fecha_inicio", "fecha_termino",
                                     "dias_habiles", "dias_corridos", "tipo"] if c in df.columns]
            st.dataframe(df[cols_show], use_container_width=True)

            st.markdown("#### Generar comprobante desde historial")
            for v in vacs:
                v = dict(v)
                label = f"{v.get('rut')} | {v.get('fecha_inicio')} → {v.get('fecha_termino')} ({v.get('dias_habiles')} días)"
                if st.button(f"📄 Comprobante Feriado — {label}", key=f"fer_{v['id']}"):
                    emp = dict(conn.execute("SELECT * FROM empresas WHERE id=?", (emp_opts[emp_sel],)).fetchone())
                    trab = dict(conn.execute("SELECT * FROM trabajadores WHERE id=?", (v["trabajador_id"],)).fetchone())
                    cont = conn.execute(
                        "SELECT * FROM contratos WHERE trabajador_id=? ORDER BY id DESC LIMIT 1",
                        (v["trabajador_id"],)
                    ).fetchone()
                    cont = dict(cont) if cont else {}
                    vac = {
                        "fecha_inicio": v.get("fecha_inicio"),
                        "fecha_termino": v.get("fecha_termino"),
                        "dias_habiles": v.get("dias_habiles") or 0,
                        "dias_corridos": v.get("dias_corridos") or 0,
                        "tipo": v.get("tipo") or "Legales",
                        "saldo_pendiente": 0,
                    }
                    rut_c = (trab.get("rut") or "").replace(".", "").replace("-", "")
                    ruta = EXPORTS_DIR / f"comprobante_feriado_{rut_c}_{v.get('fecha_inicio')}.docx"
                    generar_comprobante_feriado_docx(emp, trab, vac, cont, str(ruta))
                    with open(ruta, "rb") as f:
                        st.download_button(
                            "⬇️ Descargar Comprobante",
                            f,
                            file_name=ruta.name,
                            key=f"dl_fer_{v['id']}",
                        )
        else:
            st.info("Sin registros de vacaciones para esta empresa.")

    # -------------------- FINIQUITOS --------------------
    elif menu == "📝 Finiquitos":
        st.header("Cálculo y Generación de Finiquitos")
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="fin_emp")

        contratos = conn.execute("""
            SELECT c.id, c.trabajador_id, t.rut, t.nombres, t.apellido_paterno, c.cargo, c.fecha_inicio, c.sueldo_base, c.tipo_contrato
            FROM contratos c JOIN trabajadores t ON c.trabajador_id = t.id
            WHERE c.empresa_id = ? AND c.activo = 1
        """, (emp_opts[emp_sel],)).fetchall()
        cont_opts = {f"{c['rut']} - {c['nombres']} {c['apellido_paterno']} ({c['cargo']})": c for c in contratos}

        with st.form("nuevo_finiquito"):
            if not cont_opts:
                st.warning("No hay contratos activos")
            else:
                sel = st.selectbox("Contrato / Trabajador", list(cont_opts.keys()))
                cont = cont_opts[sel]
                f_term = st.date_input("Fecha Término", value=date.today())
                causal = st.selectbox("Causal", [
                    "159 N° 1 - Mutuo acuerdo de las partes",
                    "159 N° 2 - Renuncia del trabajador",
                    "159 N° 4 - Vencimiento del plazo",
                    "159 N° 5 - Conclusión del trabajo o servicio",
                    "160 - Causal disciplinaria",
                    "161 - Necesidades de la empresa"
                ])
                otros = st.number_input("Otros montos ($)", value=0)
                if st.form_submit_button("Calcular y Generar Finiquito"):
                    f_inicio = datetime.strptime(str(cont['fecha_inicio']), "%Y-%m-%d").date() if isinstance(cont['fecha_inicio'], str) else cont['fecha_inicio']
                    dias_prop, monto_prop = calcular_vacaciones_proporcionales(f_inicio, f_term, cont['sueldo_base'])

                    # Indemnización simplificada (solo si 161 y >1 año)
                    indemn = 0
                    if "161" in causal:
                        anios = (f_term - f_inicio).days / 365.25
                        if anios >= 1:
                            indemn = round(min(anios, 11) * cont['sueldo_base'])  # tope 11 años

                    total = monto_prop + indemn + otros
                    conn.execute("""
                        INSERT INTO finiquitos (trabajador_id, empresa_id, contrato_id, fecha_termino, causal,
                        vacaciones_proporcionales_dias, vacaciones_proporcionales_monto, indemnizacion_anos, otros_montos, total_finiquito)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                    """, (cont['trabajador_id'], emp_opts[emp_sel], cont['id'], f_term, causal,
                          dias_prop, monto_prop, indemn, otros, total))
                    # Desactivar contrato
                    conn.execute("UPDATE contratos SET activo=0, fecha_termino=? WHERE id=?", (f_term, cont['id']))
                    conn.execute("UPDATE trabajadores SET activo=0 WHERE id=?", (cont['trabajador_id'],))
                    conn.commit()

                    # Generar documento
                    emp = dict(conn.execute("SELECT * FROM empresas WHERE id=?", (emp_opts[emp_sel],)).fetchone())
                    trab = dict(conn.execute("SELECT * FROM trabajadores WHERE id=?", (cont['trabajador_id'],)).fetchone())
                    fin = {
                        "fecha_termino": f_term,
                        "causal": causal,
                        "vacaciones_proporcionales_dias": dias_prop,
                        "vacaciones_proporcionales_monto": monto_prop,
                        "indemnizacion_anos": indemn,
                        "aviso_previo": 0,
                        "otros_montos": otros,
                        "total_finiquito": total
                    }
                    ruta = EXPORTS_DIR / f"finiquito_{cont['rut'].replace('.','').replace('-','')}_{f_term}.docx"
                    generar_finiquito_docx(emp, trab, fin, cont, str(ruta))
                    st.success(f"Finiquito generado. Total: ${total:,.0f}")
                    st.write(f"Vacaciones proporcionales: {dias_prop:.2f} días → ${monto_prop:,.0f}")
                    if indemn:
                        st.write(f"Indemnización años servicio: ${indemn:,.0f}")
                    st.session_state["ultimo_finiquito_docx"] = str(ruta)

        if st.session_state.get("ultimo_finiquito_docx"):
            ruta_dl = Path(st.session_state["ultimo_finiquito_docx"])
            if ruta_dl.exists():
                with open(ruta_dl, "rb") as f:
                    st.download_button("⬇️ Descargar Finiquito DOCX", f, file_name=ruta_dl.name, key="dl_finiquito_docx")

        st.subheader("Finiquitos registrados")
        df = pd.read_sql("""
            SELECT f.id, t.rut, t.nombres || ' ' || t.apellido_paterno as trabajador, f.fecha_termino, f.causal, f.total_finiquito
            FROM finiquitos f JOIN trabajadores t ON f.trabajador_id = t.id
            WHERE f.empresa_id = ?
        """, conn, params=(emp_opts[emp_sel],))
        st.dataframe(df, use_container_width=True)

    # -------------------- LIBRO DE REMUNERACIONES --------------------
    elif menu == "📒 Libro de Remuneraciones":
        st.header("Libro de Remuneraciones")
        st.markdown("""
        Genera el **Libro de Remuneraciones** mensual:
        - **Excel** → uso interno / respaldo Art. 54 Código del Trabajo  
        - **Hoja «Asiento Centralizacion»** → asiento contable Debe/Haber (estilo ERP)  
        - **CSV LRE** → carga masiva en **Mi DT** (Dirección del Trabajo). Delimitador `;`
        """)
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="libro_emp")
        periodo = st.text_input("Periodo (YYYY-MM)", value="2026-07", key="libro_periodo")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Generar Libro Excel"):
                ruta = EXPORTS_DIR / f"libro_remuneraciones_{emp_opts[emp_sel]}_{periodo}.xlsx"
                res = generar_libro_remuneraciones(emp_opts[emp_sel], periodo, str(ruta))
                if res:
                    st.success(f"Libro generado: {ruta.name}")
                    with open(ruta, "rb") as f:
                        st.download_button("⬇️ Descargar Excel", f, file_name=ruta.name,
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           key="dl_libro_xlsx")
                else:
                    st.warning("No hay liquidaciones para ese periodo/empresa.")
        with c2:
            if st.button("Generar LRE CSV (Mi DT)"):
                emp_row = conn.execute("SELECT rut FROM empresas WHERE id=?", (emp_opts[emp_sel],)).fetchone()
                rut_emp = (emp_row["rut"] if emp_row else "00000000").replace(".", "").replace("-", "")[:9]
                yyyymm = periodo.replace("-", "")
                ruta = EXPORTS_DIR / f"{rut_emp}_{yyyymm}.csv"
                res = generar_lre_csv(emp_opts[emp_sel], periodo, str(ruta))
                if res:
                    st.success(f"LRE generado: {ruta.name}")
                    st.caption("Súbelo en midt.dirtrab.cl → Libro de Remuneraciones Electrónico → Archivo CSV. No lo abras en Excel.")
                    with open(ruta, "rb") as f:
                        st.download_button("⬇️ Descargar LRE CSV", f, file_name=ruta.name,
                                           mime="text/csv", key="dl_lre_csv")
                else:
                    st.warning("No hay liquidaciones para ese periodo/empresa.")

        st.info("""
        **LRE → Dirección del Trabajo (no SII)**  
        1. Entra a https://midt.dirtrab.cl con ClaveÚnica (perfil empleador)  
        2. Libro de Remuneraciones Electrónico → mes → Archivo CSV  
        3. Sube el archivo `RUT_YYYYMM.csv` (sin abrirlo en Excel)  
        El SII arma la propuesta 1887 con los datos del LRE declarado en la DT.
        """)

        st.subheader("Liquidaciones disponibles (referencia)")
        df = pd.read_sql("""
            SELECT periodo, COUNT(*) as trabajadores, SUM(total_haberes) as total_haberes, SUM(liquido) as total_liquido
            FROM liquidaciones WHERE empresa_id = ?
            GROUP BY periodo ORDER BY periodo DESC
        """, conn, params=(emp_opts[emp_sel],))
        st.dataframe(df, use_container_width=True)

    # -------------------- PREVIRED --------------------
    elif menu == "📤 Archivo Previred":
        st.header("Generación Archivo Previred")
        st.markdown("""
        Genera archivo TXT en formato **largo variable por separador (punto y coma)**  
        compatible con la carga en Previred (versión simplificada del estándar 105 campos).
        """)
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="prev_emp")
        periodo = st.text_input("Periodo remuneraciones (YYYY-MM)", value="2026-07")

        if st.button("Generar Archivo TXT Previred"):
            ruta = EXPORTS_DIR / f"previred_{emp_opts[emp_sel]}_{periodo}.txt"
            res = generar_previred_txt(emp_opts[emp_sel], periodo, str(ruta))
            if res:
                st.success(f"Archivo generado: {ruta.name}")
                with open(ruta, "rb") as f:
                    st.download_button("⬇️ Descargar TXT Previred", f, file_name=ruta.name)
                st.code(open(ruta).read()[:1000], language="text")
            else:
                st.warning("No hay liquidaciones para ese periodo/empresa. Calcula liquidaciones primero.")

    # -------------------- DECLARACIÓN JURADA 1887 --------------------
    elif menu == "📋 Declaración Jurada 1887":
        st.header("Formulario 1887 y Certificados de Sueldos")
        st.markdown("""
        **Formulario 1887** – Declaración Jurada Anual de Impuesto Único de Segunda Categoría (SII)  
        **Certificados 1887** – Certificados individuales de sueldos y otras rentas para cada trabajador  

        Basado en los formatos oficiales que proporcionaste (`form1887-at2026.xls` y `cer1887-2023.xls`).
        """)
        empresas = conn.execute("SELECT id, razon_social FROM empresas").fetchall()
        emp_opts = {e['razon_social']: e['id'] for e in empresas}
        emp_sel = st.selectbox("Empresa", list(emp_opts.keys()), key="dj_emp")
        anio_tributario = st.number_input("Año Tributario (año de la declaración)", min_value=2020, max_value=2030, value=2026,
                                          help="Ej: Año Tributario 2026 declara las rentas del año calendario 2025")
        anio_rentas = int(anio_tributario) - 1

        st.subheader(f"Factores de actualización (rentas {anio_rentas} → dic {anio_rentas})")
        st.caption(
            "Fuente de referencia: Superintendencia de Pensiones (tabla a Diciembre). "
            "El SII aplica estos factores a C3 (Renta total neta), C4 (Impuesto único), etc. "
            "Puedes editarlos antes de generar la DJ."
        )
        factores = get_factores_actualizacion(anio_rentas)
        meses_nom = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        cols_f = st.columns(6)
        nuevos_factores = {}
        for m in range(1, 13):
            with cols_f[(m - 1) % 6]:
                nuevos_factores[m] = st.number_input(
                    f"{meses_nom[m-1]}",
                    min_value=0.5,
                    max_value=3.0,
                    value=float(factores.get(m, 1.0)),
                    step=0.001,
                    format="%.3f",
                    key=f"fac_{anio_rentas}_{m}",
                )
        if st.button("💾 Guardar factores de actualización"):
            for m, fac in nuevos_factores.items():
                conn.execute(
                    "INSERT OR REPLACE INTO factores_actualizacion (anio_rentas, mes, factor) VALUES (?,?,?)",
                    (anio_rentas, m, fac),
                )
            conn.commit()
            st.success(f"Factores {anio_rentas} guardados")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Formulario 1887 (DJ Anual)")
            if st.button("Generar Formulario 1887 Excel"):
                ruta = EXPORTS_DIR / f"formulario_1887_AT{anio_tributario}_emp{emp_opts[emp_sel]}.xlsx"
                res = generar_formulario_1887(emp_opts[emp_sel], int(anio_tributario), str(ruta))
                if res:
                    st.success(f"Formulario generado: {ruta.name}")
                    with open(ruta, "rb") as f:
                        st.download_button("⬇️ Descargar Formulario 1887", f, file_name=ruta.name,
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           key="dl_f1887")
                else:
                    st.warning(f"No hay liquidaciones del año {anio_tributario - 1} para esta empresa.")
            if st.button("Generar CSV Importador SII (1887)"):
                ruta = EXPORTS_DIR / f"1887_importador_AT{anio_tributario}_emp{emp_opts[emp_sel]}.csv"
                res = generar_1887_csv_sii(emp_opts[emp_sel], int(anio_tributario), str(ruta))
                if res:
                    st.success(f"CSV Importador generado: {ruta.name}")
                    st.caption("SII → Declaraciones Juradas → Importador de Datos → Formulario 1887")
                    with open(ruta, "rb") as f:
                        st.download_button("⬇️ Descargar CSV 1887 SII", f, file_name=ruta.name,
                                           mime="text/csv", key="dl_f1887_csv")
                else:
                    st.warning(f"No hay liquidaciones del año {anio_tributario - 1} para esta empresa.")

        with col2:
            st.subheader("Certificados 1887 (individuales)")
            if st.button("Generar Certificados 1887 (ZIP)"):
                ruta = EXPORTS_DIR / f"certificados_1887_AT{anio_tributario}_emp{emp_opts[emp_sel]}.zip"
                res = generar_certificados_1887(emp_opts[emp_sel], int(anio_tributario), str(ruta))
                if res:
                    st.success(f"Certificados generados: {ruta.name}")
                    with open(ruta, "rb") as f:
                        st.download_button("⬇️ Descargar ZIP Certificados", f, file_name=ruta.name,
                                           mime="application/zip", key="dl_c1887")
                else:
                    st.warning(f"No hay liquidaciones del año {anio_tributario - 1} para esta empresa.")

        st.info("""
        **Notas:**  
        - El Año Tributario N declara las rentas del año calendario N-1.  
        - **Factores de actualización**: cada mes de renta se multiplica por su factor (tabla SP a diciembre) para obtener C3 y demás columnas actualizadas del F1887.  
        - El detalle mensual del formulario se informa **sin actualizar** (como indica el SII); el total anual de renta neta sí va actualizado.  
        - El Impuesto Único retenido se deja en 0 por defecto (se puede integrar la tabla progresiva del SII + factor).  
        - Los certificados se generan uno por trabajador y se empaquetan en ZIP.  
        - Para que aparezcan datos, primero genera liquidaciones de todos los meses del año de rentas.
        """)

    # -------------------- AYUDA --------------------
    elif menu == "ℹ️ Ayuda":
        st.header("Ayuda y Referencias")
        st.markdown("""
        ### Funcionalidades implementadas
        1. **Empresas** multiempresa con mutual y caja de compensación  
        2. **Trabajadores** con AFP, Salud (Fonasa/Isapre + pactado UF)  
        3. **Contratos** (Indefinido / Plazo Fijo) → genera DOCX con formato similar al de Joissaint Cineus  
        4. **Indicadores Previred** → lectura automática desde PDF oficial  
        5. **Liquidaciones** → cálculo AFP, 7% salud, adicional Isapre, SIS 2%, AFC, Mutual → genera DOCX estilo liquidación Pacheco  
        6. **Libro de Remuneraciones** → Excel mensual (Art. 54 Código del Trabajo)  
        7. **Vacaciones** → registro y control  
        8. **Finiquitos** → vacaciones proporcionales (Art. 73 CT) + indemnización → genera DOCX estilo finiquito Cineus  
        9. **Archivo Previred** → TXT por separador listo para carga  
        10. **Formulario 1887** → Declaración Jurada Anual Impuesto Único 2ª Categoría (formato SII)  
        11. **Certificados 1887** → Certificados individuales de sueldos por trabajador (ZIP)

        ### Datos de ejemplo precargados
        - Empresa **I PROPIEDADES LIMITADA** (liquidación Pacheco Julio 2026)  
        - Empresa **LOS PUENTES SpA** (contrato y finiquito Cineus)  
        - Indicadores **Julio 2026** (UF 40.844,79 | Tope AFP 3.676.031 | SIS 2,00%)  

        ### Notas técnicas
        - El formato Previred generado es una **versión simplificada**. Para producción se debe completar el mapeo exacto de los 105 campos según el instructivo vigente de Previred (versión Agosto 2026+).  
        - El Impuesto Único de 2ª Categoría en el Formulario 1887 se deja en 0 (se puede integrar la tabla progresiva del SII).  
        - La reforma de pensiones (nuevas cotizaciones empleador desde agosto 2026) se puede extender fácilmente en la función `calcular_liquidacion`.  
        - Formatos 1887 basados en los archivos oficiales que subiste (`form1887-at2026.xls` y `cer1887-2023.xls`).
        """)

    # -------------------- CONTROL ACCESO DEMO (solo admin) --------------------
    elif menu == "🔐 Acceso Demo":
        if not st.session_state.get("es_admin"):
            st.error("Solo disponible con clave de administrador.")
        else:
            panel_admin_acceso()

    conn.close()

if __name__ == "__main__":
    main()
