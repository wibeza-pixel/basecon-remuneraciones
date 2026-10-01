#!/usr/bin/env python3
"""
BASECON — Sistema de Remuneraciones Multiempresa (Chile)
Interfaz Streamlit. La lógica de cálculo, base de datos y documentos está en el paquete `remu/`.
"""
from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from remu import calculos as K
from remu import config as C
from remu import db
from remu import documentos as D
from remu import finiquitos as FQ
from remu import libros as L
from remu import previred as P
from remu import seguridad as S
from remu.pdf_indicadores import parse_indicadores_pdf
from remu.procesos import calcular_periodo
import ui_rrhh

_favicon = C.BASE_DIR / "favicon.png"
if not _favicon.exists():
    _favicon = C.BASE_DIR / "basecon-logo.png"
st.set_page_config(page_title="BASECON — Remuneraciones Chile",
                   page_icon=str(_favicon) if _favicon.exists() else "🇨🇱",
                   layout="wide", initial_sidebar_state="expanded")


@st.cache_resource
def _inicializar(destino: str):
    # La clave incluye el destino: si se cambia DATABASE_URL en los secrets, se crean las tablas en la base nueva
    db.init_db()
    return True


_inicializar((db.database_url() if db.is_postgres() else str(C.DB_PATH)) + "|" + db.schema_pg())
EXPORTS_DIR = C.EXPORTS_DIR
LOGO = C.BASE_DIR / "basecon-logo.png"


# ============================================================
# Utilidades de interfaz
# ============================================================
def periodo_default() -> str:
    hoy = date.today()
    return f"{hoy.year}-{hoy.month:02d}"


def input_periodo(label="Periodo (AAAA-MM)", key=None, value=None) -> str:
    p = st.text_input(label, value=value or periodo_default(), key=key).strip()
    try:
        a, m = int(p[:4]), int(p[5:7])
        assert len(p) == 7 and p[4] == "-" and 1 <= m <= 12 and 2000 < a < 2100
    except Exception:
        st.error("Periodo inválido. Use el formato AAAA-MM, por ejemplo 2026-08.")
        st.stop()
    return p


def usuario_actual() -> dict:
    return st.session_state.get("usuario") or {}


def es_admin() -> bool:
    return usuario_actual().get("rol") == "admin"


def modulos() -> set[str]:
    return S.modulos_usuario(usuario_actual())


def puede_crear_empresas() -> bool:
    return S.empresas_permitidas(usuario_actual()) is None and "remuneraciones" in modulos()


def empresas_visibles(conn) -> list[dict]:
    todas = db.rows(conn, "SELECT * FROM empresas ORDER BY razon_social")
    perm = S.empresas_permitidas(usuario_actual())
    return todas if perm is None else [e for e in todas if e["id"] in perm]


def ids_visibles(conn) -> list[int]:
    return [e["id"] for e in empresas_visibles(conn)]


def selector_empresa(conn, key) -> dict:
    emps = empresas_visibles(conn)
    if not emps:
        st.warning("No hay empresas disponibles para su usuario. Pida al administrador que le asigne una.")
        st.stop()
    etiquetas = {f"{e['razon_social']} ({e['rut']})": e for e in emps}
    return etiquetas[st.selectbox("Empresa", list(etiquetas), key=key)]


def filtro_ids_sql(ids, col="empresa_id") -> tuple[str, list]:
    if not ids:
        return f"{col} IN (-1)", []
    return f"{col} IN ({','.join('?' * len(ids))})", list(ids)


def descargar(ruta: Path, etiqueta: str, key: str, mime=None):
    if ruta and Path(ruta).exists():
        with open(ruta, "rb") as f:
            st.download_button(etiqueta, f.read(), file_name=Path(ruta).name, key=key, mime=mime)


def mostrar_advertencias(adv, titulo=None):
    if adv:
        st.warning((f"**{titulo}**\n\n" if titulo else "") + "\n".join(f"- {a}" for a in adv))


# ============================================================
# Acceso
# ============================================================
def pantalla_configuracion_inicial():
    st.title("BASECON — Configuración inicial")
    st.info("No hay usuarios creados. Defina el usuario administrador (dueño del sistema). "
            "No existen claves por defecto.")
    with st.form("setup_admin"):
        u = st.text_input("Usuario administrador", value="admin")
        n = st.text_input("Nombre")
        c1 = st.text_input("Clave", type="password")
        c2 = st.text_input("Repetir clave", type="password")
        if st.form_submit_button("Crear administrador", type="primary"):
            if c1 != c2:
                st.error("Las claves no coinciden.")
            else:
                try:
                    S.crear_usuario(u, c1, n, rol="admin", empresas="*")
                    st.success("Administrador creado. Ingrese con sus datos.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    st.stop()


def pantalla_login():
    col = st.columns([1, 2, 1])[1]
    with col:
        if LOGO.exists():
            st.image(str(LOGO), width="stretch")
        st.markdown("### 🔒 BASECON — Remuneraciones")
        bloqueo = st.session_state.get("bloqueo_hasta", 0)
        if time.time() < bloqueo:
            st.error(f"Demasiados intentos fallidos. Espere {int(bloqueo - time.time())} segundos.")
            st.stop()
        with st.form("login"):
            u = st.text_input("Usuario")
            c = st.text_input("Clave", type="password")
            ok = st.form_submit_button("Entrar", type="primary", width="stretch")
        if ok:
            user, motivo = S.autenticar(u, c)
            if user:
                st.session_state["usuario"] = user
                st.session_state["intentos"] = 0
                st.rerun()
            else:
                n = st.session_state.get("intentos", 0) + 1
                st.session_state["intentos"] = n
                if n >= 5:
                    st.session_state["bloqueo_hasta"] = time.time() + 30
                    st.session_state["intentos"] = 0
                st.error(motivo)
    st.stop()


# ============================================================
# Pantallas
# ============================================================
def pantalla_dashboard(conn):
    st.header("Dashboard")
    ids = ids_visibles(conn)
    w, p = filtro_ids_sql(ids, "id")
    w2, p2 = filtro_ids_sql(ids)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Empresas", len(ids))
    c2.metric("Trabajadores activos", db.scalar(conn, f"SELECT COUNT(*) AS n FROM trabajadores WHERE activo=1 AND {w2}", p2) or 0)
    c3.metric("Liquidaciones", db.scalar(conn, f"SELECT COUNT(*) AS n FROM liquidaciones WHERE {w2}", p2) or 0)
    c4.metric("Finiquitos", db.scalar(conn, f"SELECT COUNT(*) AS n FROM finiquitos WHERE {w2}", p2) or 0)
    st.subheader("Empresas")
    st.dataframe(db.read_sql_df(f"SELECT id, rut, razon_social, comuna FROM empresas WHERE {w}", conn, p),
                 width="stretch")
    st.info("Flujo mensual: 1) cargar **Indicadores Previred** del mes → 2) **Liquidaciones** → "
            "3) **Libro / LRE** → 4) **Archivo Previred**.")


def _form_empresa(prefix, e=None):
    e = e or {}
    c1, c2 = st.columns(2)
    d = {}
    d["rut"] = c1.text_input("RUT empresa *", value=e.get("rut") or "", key=f"{prefix}_rut")
    d["razon_social"] = c2.text_input("Razón social *", value=e.get("razon_social") or "", key=f"{prefix}_rs")
    d["giro"] = c1.text_input("Giro", value=e.get("giro") or "", key=f"{prefix}_giro")
    d["direccion"] = c2.text_input("Dirección", value=e.get("direccion") or "", key=f"{prefix}_dir")
    d["comuna"] = c1.text_input("Comuna", value=e.get("comuna") or "", key=f"{prefix}_com")
    d["ciudad"] = c2.text_input("Ciudad", value=e.get("ciudad") or "", key=f"{prefix}_ciu")
    d["region_codigo"] = c1.number_input("Código región (LRE, 1 a 16)", min_value=0, max_value=16,
                                         value=int(e.get("region_codigo") or 13), key=f"{prefix}_reg")
    d["comuna_codigo"] = c2.number_input("Código comuna CUT (LRE, ej. 13101 Santiago)", min_value=0,
                                         value=int(e.get("comuna_codigo") or 0), key=f"{prefix}_cut")
    d["telefono"] = c1.text_input("Teléfono", value=e.get("telefono") or "", key=f"{prefix}_tel")
    d["email"] = c2.text_input("Email", value=e.get("email") or "", key=f"{prefix}_mail")
    mut = C.normalizar(e.get("mutual") or "ACHS")
    d["mutual"] = c1.selectbox("Mutual / ISL", C.MUTUALES, index=C.MUTUALES.index(mut) if mut in C.MUTUALES else 0,
                               key=f"{prefix}_mut")
    d["tasa_mutual"] = c2.number_input("Tasa mutual % (básica + adicional + SANNA)", value=float(e.get("tasa_mutual") or 0.93),
                                       step=0.01, key=f"{prefix}_tm")
    d["sucursal_mutual"] = c1.text_input("Sucursal pago mutual (Previred)", value=e.get("sucursal_mutual") or "",
                                         key=f"{prefix}_suc")
    caja = C.normalizar(e.get("caja_compensacion") or "")
    d["caja_compensacion"] = c2.selectbox("Caja de compensación", C.CCAFS,
                                          index=C.CCAFS.index(caja) if caja in C.CCAFS else 0,
                                          format_func=lambda x: x or "Sin CCAF", key=f"{prefix}_ccaf")
    d["centro_costo"] = c1.text_input("Centro de costo Previred (opcional)", value=e.get("centro_costo") or "",
                                      key=f"{prefix}_cc")
    d["representante_legal"] = c2.text_input("Representante legal", value=e.get("representante_legal") or "",
                                             key=f"{prefix}_rl")
    d["rut_representante"] = c1.text_input("RUT representante", value=e.get("rut_representante") or "",
                                           key=f"{prefix}_rrl")
    return d


def pantalla_empresas(conn):
    st.header("Empresas")
    if puede_crear_empresas():
        with st.expander("➕ Nueva empresa"):
            with st.form("nueva_empresa"):
                d = _form_empresa("ne")
                if st.form_submit_button("Guardar empresa"):
                    if not C.rut_valido(d["rut"]) or not d["razon_social"].strip():
                        st.error("RUT inválido o razón social vacía.")
                    else:
                        try:
                            db.insert(conn, "empresas", d)
                            conn.commit()
                            st.success("Empresa creada.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error: {ex}")
    emps = empresas_visibles(conn)
    if emps:
        with st.expander("✏️ Editar empresa"):
            et = {f"{e['razon_social']} ({e['rut']})": e for e in emps}
            e = et[st.selectbox("Empresa", list(et), key="ed_emp_sel")]
            with st.form("editar_empresa"):
                d = _form_empresa(f"ee{e['id']}", e)
                if st.form_submit_button("Guardar cambios"):
                    sets = ", ".join(f"{k}=?" for k in d)
                    conn.execute(f"UPDATE empresas SET {sets} WHERE id=?", [*d.values(), e["id"]])
                    conn.commit()
                    st.success("Empresa actualizada.")
                    st.rerun()
    st.dataframe(pd.DataFrame(emps), width="stretch")


def _form_trabajador(prefix, t=None):
    t = t or {}
    c1, c2, c3 = st.columns(3)
    d = {}
    d["rut"] = c1.text_input("RUT *", value=t.get("rut") or "", key=f"{prefix}_rut", placeholder="12.345.678-5")
    d["nombres"] = c2.text_input("Nombres *", value=t.get("nombres") or "", key=f"{prefix}_nom")
    d["apellido_paterno"] = c3.text_input("Apellido paterno *", value=t.get("apellido_paterno") or "", key=f"{prefix}_ap")
    d["apellido_materno"] = c1.text_input("Apellido materno", value=t.get("apellido_materno") or "", key=f"{prefix}_am")
    d["sexo"] = c2.selectbox("Sexo", ["M", "F"], index=1 if t.get("sexo") == "F" else 0, key=f"{prefix}_sexo")
    d["fecha_nacimiento"] = c3.date_input("Fecha de nacimiento", value=C.a_fecha(t.get("fecha_nacimiento")) or date(1990, 1, 1),
                                          min_value=date(1930, 1, 1), key=f"{prefix}_fn")
    d["nacionalidad"] = c1.text_input("Nacionalidad", value=t.get("nacionalidad") or "Chilena", key=f"{prefix}_nac")
    d["direccion"] = c2.text_input("Dirección", value=t.get("direccion") or "", key=f"{prefix}_dir")
    d["comuna"] = c3.text_input("Comuna", value=t.get("comuna") or "", key=f"{prefix}_com")
    d["email"] = c1.text_input("Email", value=t.get("email") or "", key=f"{prefix}_mail")
    d["afp"] = c2.selectbox("AFP", C.AFPS, index=C.AFPS.index(t["afp"]) if t.get("afp") in C.AFPS else 0, key=f"{prefix}_afp")
    d["salud"] = c3.selectbox("Salud", ["FONASA", "ISAPRE"], index=1 if t.get("salud") == "ISAPRE" else 0, key=f"{prefix}_sal")
    isap = C.normalizar(t.get("isapre") or "")
    d["isapre"] = c1.selectbox("Isapre (si aplica)", [""] + C.ISAPRES,
                               index=([""] + C.ISAPRES).index(isap) if isap in C.ISAPRES else 0, key=f"{prefix}_isa")
    d["pactado_salud_uf"] = c2.number_input("Plan pactado Isapre (UF)", value=float(t.get("pactado_salud_uf") or 0),
                                            step=0.001, format="%.3f", key=f"{prefix}_pac")
    d["banco"] = c3.text_input("Banco", value=t.get("banco") or "", key=f"{prefix}_bco")
    d["cuenta_banco"] = c1.text_input("Cuenta bancaria", value=t.get("cuenta_banco") or "", key=f"{prefix}_cta")
    d["numero_cargas"] = c2.number_input("N° cargas familiares", min_value=0, value=int(t.get("numero_cargas") or 0),
                                         key=f"{prefix}_car")
    tr = ["A", "B", "C", "D"]
    d["tramo_asignacion_familiar"] = c3.selectbox(
        "Tramo asignación familiar (según IPS/CCAF)", tr,
        index=tr.index(t["tramo_asignacion_familiar"]) if t.get("tramo_asignacion_familiar") in tr else 3,
        key=f"{prefix}_tr", help="Tramo determinado por el promedio de rentas del semestre anterior.")
    d["codigo"] = c1.text_input("Código interno", value=t.get("codigo") or "", key=f"{prefix}_cod")
    d["cargo"] = c2.text_input("Cargo", value=t.get("cargo") or "", key=f"{prefix}_cargo")
    d["centro_costo"] = c3.text_input("Centro de costo", value=t.get("centro_costo") or "", key=f"{prefix}_ccos")
    d["pensionado"] = int(c1.checkbox("Pensionado", value=bool(t.get("pensionado")), key=f"{prefix}_pen",
                                      help="Sin SIS, sin cotización empleador Ley 21.735 y sin seguro de cesantía."))
    d["cotiza_afp"] = int(c2.checkbox("Cotiza en AFP", value=bool(t.get("cotiza_afp", 1)), key=f"{prefix}_cafp",
                                      help="Desmarcar solo para pensionados que optaron por no cotizar."))
    return d


def pantalla_trabajadores(conn):
    st.header("Trabajadores")
    emp = selector_empresa(conn, "trab_emp")
    with st.expander("➕ Nuevo trabajador"):
        with st.form("nuevo_trabajador"):
            d = _form_trabajador("nt")
            if st.form_submit_button("Guardar trabajador"):
                if not C.rut_valido(d["rut"]):
                    st.error("RUT inválido (dígito verificador).")
                elif not d["nombres"].strip() or not d["apellido_paterno"].strip():
                    st.error("Nombres y apellido paterno son obligatorios.")
                else:
                    try:
                        db.insert(conn, "trabajadores", dict(d, empresa_id=emp["id"]))
                        conn.commit()
                        st.success("Trabajador creado.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error: {ex}")
    with st.expander("📥 Importar trabajadores desde Excel"):
        st.caption("Columnas: RUT, NOMBRE (o NOMBRES), AP PATERNO, AP MATERNO, CODIGO, CARGO, CENTRO COSTO. "
                   "Los RUT que ya existen se omiten. AFP, salud y demás datos previsionales se completan después.")
        arch = st.file_uploader("Archivo Excel", type=["xlsx", "xls"], key="imp_trab")
        if arch and st.button("Importar"):
            n, errs = ui_rrhh.importar_trabajadores_excel(conn, emp, arch)
            st.success(f"{n} trabajador(es) importado(s).")
            mostrar_advertencias(errs, "Filas no importadas")
    trabs = db.rows(conn, "SELECT * FROM trabajadores WHERE empresa_id=? ORDER BY apellido_paterno, nombres", (emp["id"],))
    incompletos = [t for t in trabs if t.get("activo") and not t.get("afp") and t.get("cotiza_afp", 1)]
    if incompletos and "remuneraciones" in modulos():
        st.warning(f"{len(incompletos)} trabajador(es) sin AFP registrada: complete sus datos previsionales antes de liquidar.")
    if trabs:
        with st.expander("✏️ Editar trabajador", expanded=False):
            opts = {f"{t['rut']} — {t['nombres']} {t['apellido_paterno']}": t for t in trabs}
            t0 = opts[st.selectbox("Trabajador", list(opts), key="ed_trab_sel")]
            with st.form("editar_trabajador"):
                d = _form_trabajador(f"et{t0['id']}", t0)
                d["activo"] = int(st.checkbox("Activo", value=bool(t0.get("activo", 1))))
                if st.form_submit_button("Guardar cambios"):
                    if not C.rut_valido(d["rut"]):
                        st.error("RUT inválido (dígito verificador).")
                    else:
                        sets = ", ".join(f"{k}=?" for k in d)
                        conn.execute(f"UPDATE trabajadores SET {sets} WHERE id=?", [*d.values(), t0["id"]])
                        conn.commit()
                        st.success("Trabajador actualizado. Si ya había liquidaciones del mes, vuelva a calcularlas.")
                        st.rerun()
        df = pd.DataFrame(trabs)[["id", "codigo", "rut", "nombres", "apellido_paterno", "apellido_materno", "cargo", "afp", "salud",
                                  "numero_cargas", "tramo_asignacion_familiar", "pensionado", "activo"]]
        st.dataframe(df, width="stretch")


def pantalla_contratos(conn):
    st.header("Contratos de trabajo")
    emp = selector_empresa(conn, "cont_emp")
    trabs = db.rows(conn, "SELECT id, rut, nombres, apellido_paterno FROM trabajadores WHERE empresa_id=? AND activo=1",
                    (emp["id"],))
    topts = {f"{t['rut']} - {t['nombres']} {t['apellido_paterno']}": t["id"] for t in trabs}
    jmax = C.jornada_maxima(date.today())
    with st.expander("➕ Nuevo contrato", expanded=True):
        if not topts:
            st.warning("No hay trabajadores activos en esta empresa.")
        else:
            with st.form("nuevo_contrato"):
                tsel = st.selectbox("Trabajador *", list(topts))
                c1, c2 = st.columns(2)
                cargo = c1.text_input("Cargo *")
                tipo = c2.selectbox("Tipo de contrato", C.TIPOS_CONTRATO)
                f_ini = c1.date_input("Fecha de inicio *", value=date.today())
                f_ter = c2.date_input("Fecha de término (plazo fijo)", value=None)
                sueldo = c1.number_input("Sueldo base *", value=0, step=10000)
                tg = c2.selectbox("Gratificación", C.TIPOS_GRATIFICACION)
                grat = c1.number_input("Gratificación mensual fija (solo si es monto pactado)", value=0, step=1000)
                mov = c2.number_input("Movilización (no imponible)", value=0, step=1000)
                col = c1.number_input("Colación (no imponible)", value=0, step=1000)
                jornada = c2.number_input(f"Jornada semanal (máx. legal vigente: {jmax} h)", min_value=1, max_value=45,
                                          value=jmax)
                horario = c1.text_input("Horario", value="de lunes a viernes, de 09:00 a 18:00 horas")
                lugar = c2.text_input("Lugar de trabajo")
                if st.form_submit_button("Crear contrato y generar DOCX"):
                    errores = []
                    if not cargo.strip():
                        errores.append("Indique el cargo.")
                    if jornada > jmax:
                        errores.append(f"La jornada supera la máxima legal vigente ({jmax} h, Ley 21.561).")
                    ind = db.get_indicadores(periodo_default(), conn) or {}
                    imm = float(ind.get("renta_minima") or 0)
                    minimo = imm if jornada > 30 else imm * jornada / jmax
                    if imm and sueldo < minimo:
                        errores.append(f"El sueldo base es inferior al ingreso mínimo (${C.fmt_clp(minimo)}).")
                    if tipo == "Plazo Fijo" and not f_ter:
                        errores.append("Un contrato a plazo fijo requiere fecha de término.")
                    if errores:
                        mostrar_advertencias(errores)
                    else:
                        cid = db.insert(conn, "contratos", dict(
                            trabajador_id=topts[tsel], empresa_id=emp["id"], cargo=cargo, fecha_inicio=f_ini,
                            fecha_termino=f_ter, tipo_contrato=tipo, sueldo_base=sueldo, tipo_gratificacion=tg,
                            gratificacion=grat if tg.startswith("Monto") else 0, movilizacion=mov, colacion=col,
                            jornada_semanal=jornada, horario=horario, lugar_trabajo=lugar))
                        conn.commit()
                        trab = db.row(conn, "SELECT * FROM trabajadores WHERE id=?", (topts[tsel],))
                        cont = db.row(conn, "SELECT * FROM contratos WHERE id=?", (cid,))
                        ruta = EXPORTS_DIR / f"contrato_{C.rut_partes(trab['rut'])[0]}_{date.today():%Y%m%d}.docx"
                        D.generar_contrato_docx(emp, trab, cont, str(ruta))
                        st.session_state["ultimo_contrato_docx"] = str(ruta)
                        st.success(f"Contrato creado: {ruta.name}")
        if st.session_state.get("ultimo_contrato_docx"):
            descargar(Path(st.session_state["ultimo_contrato_docx"]), "⬇️ Descargar contrato DOCX", "dl_contrato")
    df = db.read_sql_df("""
        SELECT c.id, t.rut, t.nombres || ' ' || t.apellido_paterno AS trabajador, c.cargo, c.tipo_contrato,
               c.fecha_inicio, c.fecha_termino, c.sueldo_base, c.tipo_gratificacion, c.jornada_semanal, c.activo
        FROM contratos c JOIN trabajadores t ON c.trabajador_id = t.id WHERE c.empresa_id=?""", conn, (emp["id"],))
    if not df.empty:
        viejos = df[(df["activo"] == 1) & (df["jornada_semanal"] > jmax)]
        if len(viejos):
            st.warning(f"{len(viejos)} contrato(s) activo(s) con jornada sobre {jmax} h: deben ajustarse a la Ley 21.561.")
    st.dataframe(df, width="stretch")


def pantalla_indicadores(conn):
    st.header("Indicadores previsionales")
    st.caption("Cargue UF, UTM, topes y tasas de cada mes. Los datos guardados no se sobrescriben al reiniciar la app.")
    up = st.file_uploader("PDF de indicadores Previred", type=["pdf"])
    if up:
        res = parse_indicadores_pdf(up)
        if "error" in res:
            st.error(res["error"])
        else:
            st.json({k: v for k, v in res.items() if k != "texto_completo"})
            if res.get("faltantes"):
                st.warning("No se pudieron leer: " + ", ".join(res["faltantes"]) +
                           ". Se conservará el valor anterior; complételos en la edición manual.")
            per_pdf = input_periodo("Periodo a guardar", key="ind_pdf_per")
            if st.button("Guardar indicadores del PDF"):
                db.guardar_indicadores(conn, per_pdf, res)
                conn.commit()
                st.success(f"Indicadores {per_pdf} guardados.")

    st.subheader("Edición manual")
    per = input_periodo(key="ind_per")
    prev = db.get_indicadores(per, conn) or db.get_indicadores("2026-08", conn) or {}
    with st.form("edit_ind"):
        a, b = st.columns(2)
        v = {}
        v["uf"] = a.number_input("UF ($)", value=float(prev.get("uf") or 0), step=0.01, format="%.2f")
        v["utm"] = b.number_input("UTM ($)", value=float(prev.get("utm") or 0), step=1.0, format="%.0f")
        v["tope_afp"] = a.number_input("Tope imponible AFP/salud ($)", value=float(prev.get("tope_afp") or 0), step=1.0, format="%.0f")
        v["tope_afc"] = b.number_input("Tope imponible AFC ($)", value=float(prev.get("tope_afc") or 0), step=1.0, format="%.0f")
        v["tope_inp"] = a.number_input("Tope IPS ex-INP ($)", value=float(prev.get("tope_inp") or 0), step=1.0, format="%.0f")
        v["sis_tasa"] = b.number_input("Tasa SIS (%)", value=float(prev.get("sis_tasa") or 0), step=0.01,
                                       help="Hasta julio 2026. Desde agosto 2026 el SIS está dentro del 2,5% del "
                                            "Seguro Social (Ley 21.735) y esta tasa no se usa.")
        v["renta_minima"] = a.number_input("Ingreso mínimo mensual ($)", value=float(prev.get("renta_minima") or 0), step=1.0, format="%.0f")
        v["tasa_ccaf_salud"] = b.number_input("Parte del 7% Fonasa que va a la CCAF (%)",
                                              value=float(prev.get("tasa_ccaf_salud") or C.TASA_CCAF_SALUD_DEFAULT),
                                              step=0.1, help="Previred campo 90. Solo empresas afiliadas a CCAF.")
        st.markdown("**Tasas AFP (% trabajador: 10% + comisión)**")
        tasas = prev.get("afp_tasas") or C.AFP_TASAS_DEFAULT
        cols = st.columns(len(C.AFPS))
        v["afp_tasas"] = {afp: cols[i].number_input(afp, value=float(tasas.get(afp, 0)), step=0.01, key=f"tasa_{afp}")
                          for i, afp in enumerate(C.AFPS)}
        st.markdown("**Asignación familiar (monto por carga y renta máxima del tramo)**")
        aft = prev.get("af_tramos") or C.AF_TRAMOS_DEFAULT
        cols = st.columns(3)
        v["af_tramos"] = {"D": {"monto": 0, "renta_max": 999999999}}
        for i, t in enumerate(("A", "B", "C")):
            v["af_tramos"][t] = {
                "monto": cols[i].number_input(f"Tramo {t}: monto", value=int(aft[t]["monto"]), step=1, key=f"af_m_{t}"),
                "renta_max": cols[i].number_input(f"Tramo {t}: renta hasta", value=int(aft[t]["renta_max"]), step=1,
                                                  key=f"af_r_{t}")}
        if st.form_submit_button("Guardar indicadores"):
            db.guardar_indicadores(conn, per, v)
            conn.commit()
            st.success(f"Indicadores {per} guardados.")

    st.subheader("Indicadores cargados")
    st.dataframe(db.read_sql_df("SELECT periodo, uf, utm, tope_afp, tope_afc, sis_tasa, renta_minima, tasa_ccaf_salud "
                                "FROM indicadores ORDER BY periodo DESC", conn), width="stretch")
    st.subheader("Ley 21.735 — cotización de cargo del empleador")
    st.markdown("""
| Remuneraciones | Total | Detalle |
|---|---|---|
| ago-2025 → jul-2026 | 1,0% | 0,1% cuenta individual + 0,9% expectativa de vida; **SIS aparte** |
| ago-2026 → jul-2027 | 3,5% | 0,1% cuenta individual + 0,9% rentabilidad protegida + 2,5% Seguro Social (**incluye SIS**) |
| ago-2027 en adelante | según tabla SP | revisar la gradualidad vigente |

No aplica a pensionados ni a trabajadores de 65 años o más.""")

    with st.expander("Feriados legales (para finiquitos)"):
        fer = db.read_sql_df("SELECT fecha, nombre FROM feriados ORDER BY fecha", conn)
        ed = st.data_editor(fer, num_rows="dynamic", width="stretch", key="fer_ed")
        if st.button("Guardar feriados"):
            conn.execute("DELETE FROM feriados")
            for _, r in ed.dropna(subset=["fecha"]).iterrows():
                f = C.a_fecha(r["fecha"])
                if f:
                    db.upsert(conn, "feriados", {"fecha": f, "nombre": r.get("nombre") or ""}, ["fecha"])
            conn.commit()
            st.success("Feriados guardados.")


def pantalla_liquidaciones(conn):
    st.header("Liquidaciones de sueldo")
    emp = selector_empresa(conn, "liq_emp")
    periodo = input_periodo(key="liq_per")
    ind = db.get_indicadores(periodo, conn)
    if not ind:
        st.error(f"No hay indicadores para {periodo}. Cárguelos primero en **Indicadores**.")
        return
    if not ind.get("utm"):
        st.error("Los indicadores del periodo no tienen UTM: no se puede calcular el impuesto único.")
        return
    ref = K.tasas_reforma_ley_21735(periodo)
    st.info(f"UF ${ind['uf']:,.2f} · UTM ${ind['utm']:,.0f} · Tope AFP ${ind['tope_afp']:,.0f} · "
            f"{ref['descripcion']}".replace(",", "X").replace(".", ",").replace("X", "."))
    movs, est = ui_rrhh.resumen_movimientos_para_liquidacion(conn, emp, periodo)
    conts = db.rows(conn, """SELECT c.id, t.id AS tid, t.rut, t.nombres, t.apellido_paterno
                             FROM contratos c JOIN trabajadores t ON c.trabajador_id=t.id
                             WHERE c.empresa_id=? AND c.activo=1""", (emp["id"],))
    sin_mov = [c for c in conts if c["tid"] not in movs]
    if movs:
        (st.success if est.get("estado") != "Abierto" else st.warning)(
            f"Movimientos RRHH del mes: {len(movs)} trabajador(es) · periodo **{est.get('estado')}**. "
            + ("El cliente aún no lo envía: puede calcular igual, pero los datos podrían cambiar. "
               if est.get("estado") == "Abierto" else "") + "Se usan automáticamente al calcular.")
    dias_def = st.number_input("Días trabajados por defecto (trabajadores sin movimiento)", 0, 30, 30)
    he, ant, dias = {}, {}, {}
    if sin_mov:
        with st.expander(f"Variables del mes para {len(sin_mov)} trabajador(es) sin movimiento RRHH"):
            for c in sin_mov:
                a, b, d, e = st.columns([3, 1, 1, 1])
                a.write(f"{c['rut']} — {c['nombres']} {c['apellido_paterno']}")
                dias[c["tid"]] = b.number_input("Días", 0, 30, int(dias_def), key=f"d_{c['tid']}_{periodo}")
                he[c["tid"]] = d.number_input("Horas extra", 0.0, 200.0, 0.0, 0.5, key=f"he_{c['tid']}_{periodo}")
                ant[c["tid"]] = e.number_input("Anticipo", 0, value=0, step=1000, key=f"an_{c['tid']}_{periodo}")
    if st.button("🔄 Calcular liquidaciones del periodo", type="primary"):
        n, avisos = calcular_periodo(conn, emp, periodo, ind, dias_def, he, ant, dias)
        st.success(f"Liquidaciones calculadas: {n}.")

    liqs = db.rows(conn, """
        SELECT l.*, t.rut, t.nombres, t.apellido_paterno, t.apellido_materno
        FROM liquidaciones l JOIN trabajadores t ON l.trabajador_id=t.id
        WHERE l.empresa_id=? AND l.periodo=? ORDER BY t.apellido_paterno""", (emp["id"], periodo))
    if not liqs:
        return
    df = pd.DataFrame(liqs)
    cols = ["rut", "nombres", "apellido_paterno", "total_imponible", "afp_monto", "salud_monto", "afc_trabajador",
            "base_tributable", "impuesto_unico", "anticipo", "total_haberes", "total_descuentos", "liquido"]
    st.subheader(f"Liquidaciones {periodo}")
    st.dataframe(df[cols], width="stretch")
    for l in liqs:
        adv = json.loads(l.get("advertencias") or "[]")
        mostrar_advertencias(adv, f"{l['rut']} — {l['nombres']} {l['apellido_paterno']}")

    def _doc(l):
        trab = db.row(conn, "SELECT * FROM trabajadores WHERE id=?", (l["trabajador_id"],))
        cont = db.row(conn, "SELECT cargo, fecha_inicio FROM contratos WHERE id=?", (l.get("contrato_id"),)) or {}
        ld = dict(l, cargo=cont.get("cargo") or "", fecha_inicio=cont.get("fecha_inicio") or "")
        fname = f"liquidacion_{C.rut_partes(l['rut'])[0]}_{periodo}.docx"
        ruta = EXPORTS_DIR / fname
        D.generar_liquidacion_docx(emp, trab, ld, periodo, str(ruta), indicadores=ind)
        return ruta, fname

    opts = {f"{l['rut']} — {l['nombres']} {l['apellido_paterno']} (líquido ${C.fmt_clp(l['liquido'])})": l for l in liqs}
    sel = st.multiselect("Trabajadores para generar documentos", list(opts), default=list(opts), key=f"sel_{periodo}")
    if st.button(f"📦 Generar ZIP de liquidaciones ({len(sel)})", disabled=not sel):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for lab in sel:
                ruta, fname = _doc(opts[lab])
                zf.write(str(ruta), fname)
        st.download_button("⬇️ Descargar ZIP", buf.getvalue(), file_name=f"liquidaciones_{periodo}_{emp['id']}.zip",
                           mime="application/zip", key="dl_zip_liq")
    for l in liqs:
        with st.expander(f"{l['rut']} — líquido ${C.fmt_clp(l['liquido'])}"):
            det = json.loads(l.get("detalle") or "[]")
            if det:
                st.table(pd.DataFrame(det)[["tipo", "nombre", "monto"]].rename(
                    columns={"tipo": "Tipo", "nombre": "Concepto", "monto": "Monto"}).astype(str))
            st.write({k: l.get(k) for k in ("total_imponible", "afp_monto", "salud_monto", "salud_ccaf", "adicional_isapre",
                                            "afc_trabajador", "base_tributable", "impuesto_unico", "sis_monto",
                                            "reforma_afp_emp", "reforma_crp", "reforma_seguro_social", "afc_empleador",
                                            "mutual_monto", "liquido")})
            if st.button("Generar DOCX", key=f"doc_{l['id']}"):
                ruta, _ = _doc(l)
                descargar(ruta, "⬇️ Descargar liquidación", f"dl_{l['id']}")


def pantalla_libro(conn):
    st.header("Libro de remuneraciones")
    emp = selector_empresa(conn, "libro_emp")
    periodo = input_periodo(key="libro_per")
    c1, c2 = st.columns(2)
    if c1.button("Generar libro Excel + centralización"):
        ruta = EXPORTS_DIR / f"libro_remuneraciones_{emp['id']}_{periodo}.xlsx"
        if L.generar_libro_remuneraciones(emp["id"], periodo, str(ruta)):
            descargar(ruta, "⬇️ Descargar Excel", "dl_libro")
        else:
            st.warning("No hay liquidaciones para ese periodo.")
    if c2.button("Generar LRE CSV (Mi DT)"):
        if not emp.get("region_codigo") or not emp.get("comuna_codigo"):
            st.warning("Complete el código de región y de comuna (CUT) de la empresa: el LRE los exige.")
        ruta = EXPORTS_DIR / f"{C.rut_partes(emp['rut'])[0]}{C.rut_partes(emp['rut'])[1]}_{periodo.replace('-', '')}.csv"
        if L.generar_lre_csv(emp["id"], periodo, str(ruta)):
            st.caption("Súbalo en midt.dirtrab.cl → Libro de Remuneraciones Electrónico → Cargar archivo. No lo abra en Excel.")
            descargar(ruta, "⬇️ Descargar LRE", "dl_lre", "text/csv")
        else:
            st.warning("No hay liquidaciones para ese periodo.")
    st.dataframe(db.read_sql_df("""SELECT periodo, COUNT(*) AS trabajadores, SUM(total_haberes) AS haberes,
                                   SUM(impuesto_unico) AS impuesto_unico, SUM(liquido) AS liquido
                                   FROM liquidaciones WHERE empresa_id=? GROUP BY periodo ORDER BY periodo DESC""",
                                conn, (emp["id"],)), width="stretch")


def pantalla_vacaciones(conn):
    st.header("Vacaciones y comprobante de feriado")
    emp = selector_empresa(conn, "vac_emp")
    trabs = db.rows(conn, "SELECT id, rut, nombres, apellido_paterno FROM trabajadores WHERE empresa_id=? AND activo=1",
                    (emp["id"],))
    topts = {f"{t['rut']} - {t['nombres']} {t['apellido_paterno']}": t["id"] for t in trabs}
    feriados = db.get_feriados(conn)
    if topts:
        with st.form("vac"):
            tsel = st.selectbox("Trabajador", list(topts))
            f_ini = st.date_input("Inicio de vacaciones")
            dias_hab = st.number_input("Días hábiles", 0.0, 60.0, 15.0, 0.5)
            tipo = st.selectbox("Tipo", ["Legales", "Proporcionales", "Progresivas"])
            saldo = st.number_input("Saldo pendiente (días)", 0.0, 200.0, 0.0, 0.5)
            if st.form_submit_button("Registrar y generar comprobante"):
                corridos, f_fin = FQ.habiles_a_corridos(f_ini - timedelta(days=1), dias_hab, feriados)
                db.insert(conn, "vacaciones", dict(trabajador_id=topts[tsel], empresa_id=emp["id"], fecha_inicio=f_ini,
                                                   fecha_termino=f_fin, dias_habiles=dias_hab, dias_corridos=corridos,
                                                   tipo=tipo))
                conn.commit()
                trab = db.row(conn, "SELECT * FROM trabajadores WHERE id=?", (topts[tsel],))
                cont = db.row(conn, "SELECT * FROM contratos WHERE trabajador_id=? AND activo=1 ORDER BY id DESC",
                              (topts[tsel],)) or {}
                ruta = EXPORTS_DIR / f"comprobante_feriado_{C.rut_partes(trab['rut'])[0]}_{f_ini}.docx"
                D.generar_comprobante_feriado_docx(emp, trab, dict(fecha_inicio=f_ini, fecha_termino=f_fin,
                                                                   dias_habiles=dias_hab, dias_corridos=corridos,
                                                                   tipo=tipo, saldo_pendiente=saldo), cont, str(ruta))
                st.session_state["ult_fer"] = str(ruta)
                st.success(f"Registrado: último día de vacaciones {C.fecha_ddmmaaaa(f_fin)} ({corridos:g} días corridos).")
    if st.session_state.get("ult_fer"):
        descargar(Path(st.session_state["ult_fer"]), "⬇️ Descargar comprobante", "dl_fer")
    st.dataframe(db.read_sql_df("""SELECT v.id, t.rut, t.nombres, t.apellido_paterno, v.fecha_inicio, v.fecha_termino,
                                   v.dias_habiles, v.dias_corridos, v.tipo FROM vacaciones v
                                   JOIN trabajadores t ON v.trabajador_id=t.id WHERE v.empresa_id=?
                                   ORDER BY v.fecha_inicio DESC""", conn, (emp["id"],)), width="stretch")


def pantalla_finiquitos(conn):
    st.header("Finiquitos")
    emp = selector_empresa(conn, "fin_emp")
    conts = db.rows(conn, """SELECT c.*, t.rut, t.nombres, t.apellido_paterno FROM contratos c
                             JOIN trabajadores t ON c.trabajador_id=t.id WHERE c.empresa_id=? AND c.activo=1""", (emp["id"],))
    copts = {f"{c['rut']} - {c['nombres']} {c['apellido_paterno']} ({c['cargo']})": c for c in conts}
    if not copts:
        st.info("No hay contratos activos.")
    else:
        cont = copts[st.selectbox("Contrato", list(copts), key="fin_cont")]
        ult = db.rows(conn, """SELECT periodo, gratificacion, otros_haberes, afc_empleador FROM liquidaciones
                               WHERE trabajador_id=? AND empresa_id=? ORDER BY periodo DESC""",
                      (cont["trabajador_id"], emp["id"]))
        grat_def = float(ult[0]["gratificacion"]) if ult else float(cont.get("gratificacion") or 0)
        var_def = sum(float(x["otros_haberes"] or 0) for x in ult[:3]) / max(1, len(ult[:3])) if ult else 0.0
        afc_est = sum(float(x["afc_empleador"] or 0) for x in ult) * (1.6 / 2.4) if cont["tipo_contrato"] == "Indefinido" else \
            sum(float(x["afc_empleador"] or 0) for x in ult) * (2.8 / 3.0)
        with st.form("calc_fin"):
            a, b = st.columns(2)
            f_term = a.date_input("Fecha de término", value=date.today())
            causal = b.selectbox("Causal", [c[0] for c in C.CAUSALES],
                                 index=[c[0] for c in C.CAUSALES].index("Art. 161 inc. 1 — Necesidades de la empresa"))
            aviso = a.checkbox("Se dio aviso con 30 días de anticipación")
            uf_ind = (db.get_indicadores(f"{f_term.year}-{f_term.month:02d}", conn) or
                      db.get_indicadores(periodo_default(), conn) or {}).get("uf") or 0
            uf = b.number_input("Valor UF (último día del mes anterior al pago)", value=float(uf_ind), format="%.2f")
            grat = a.number_input("Gratificación mensual", value=float(grat_def), step=1000.0)
            var = b.number_input("Promedio variables últimos 3 meses (sin horas extra)", value=float(var_def), step=1000.0)
            pend = a.number_input("Días hábiles de feriado pendientes (control de vacaciones)", 0.0, 200.0, 0.0, 0.5)
            incl = b.checkbox("Incluir gratificación en el valor día de feriado", value=False)
            afc = a.number_input("Aporte empleador a cuenta individual AFC (certificado AFC)", value=float(round(afc_est)),
                                 step=1000.0, help="Estimado desde las liquidaciones registradas; use el certificado de la AFC.")
            otros = b.number_input("Otros haberes (ej. remuneración pendiente)", value=0.0, step=1000.0)
            odesc = a.number_input("Otros descuentos", value=0.0, step=1000.0)
            if st.form_submit_button("Calcular (vista previa)"):
                try:
                    st.session_state["fin_prev"] = dict(cont_id=cont["id"], res=FQ.calcular_finiquito(
                        fecha_inicio=cont["fecha_inicio"], fecha_termino=f_term, causal=causal, aviso_dado=aviso,
                        sueldo_base=cont["sueldo_base"], gratificacion_mensual=grat, promedio_variables=var,
                        colacion=cont.get("colacion") or 0, movilizacion=cont.get("movilizacion") or 0, uf=uf,
                        dias_feriado_pendientes=pend, incluir_grat_en_feriado=incl, aporte_afc_empleador=afc,
                        otros_haberes=otros, otros_descuentos=odesc, feriados=db.get_feriados(conn),
                        tipo_contrato=cont["tipo_contrato"]))
                except ValueError as ex:
                    st.error(str(ex))
        prev = st.session_state.get("fin_prev")
        if prev and prev["cont_id"] == cont["id"]:
            r = prev["res"]
            st.subheader("Vista previa")
            tabla = [("Antigüedad", r["antiguedad"]), ("Base art. 172", r["base_calculo"]),
                     ("Base con tope 90 UF", r["base_con_tope"]), ("Años a pagar", r["anos_pagar"]),
                     ("Indemnización años de servicio", r["indemnizacion_anos"]), ("Aviso previo", r["aviso_previo"]),
                     ("Feriado (días hábiles)", r["vacaciones_proporcionales_dias"]),
                     ("Feriado (días corridos)", r["feriado_dias_corridos"]), ("Valor día", r["valor_dia_feriado"]),
                     ("Feriado ($)", r["vacaciones_proporcionales_monto"]), ("Otros haberes", r["otros_montos"]),
                     ("(−) Aporte AFC", r["descuento_afc"]), ("(−) Otros descuentos", r["otros_descuentos"]),
                     ("TOTAL FINIQUITO", r["total_finiquito"])]
            st.table(pd.DataFrame(tabla, columns=["Concepto", "Valor"]).astype(str))
            mostrar_advertencias(r["advertencias"], "Revisar antes de confirmar")
            if st.button("✅ Confirmar: registrar finiquito, cerrar contrato y generar documento", type="primary"):
                fid = db.insert(conn, "finiquitos", dict(
                    trabajador_id=cont["trabajador_id"], empresa_id=emp["id"], contrato_id=cont["id"],
                    fecha_termino=r["fecha_termino"], causal=r["causal"], causal_codigo=r["causal_codigo"],
                    aviso_dado=int(r["aviso_dado"]), base_calculo=r["base_calculo"], base_con_tope=r["base_con_tope"],
                    anos_pagar=r["anos_pagar"], vacaciones_proporcionales_dias=r["vacaciones_proporcionales_dias"],
                    vacaciones_proporcionales_monto=r["vacaciones_proporcionales_monto"],
                    feriado_dias_corridos=r["feriado_dias_corridos"], valor_dia_feriado=r["valor_dia_feriado"],
                    indemnizacion_anos=r["indemnizacion_anos"], aviso_previo=r["aviso_previo"],
                    descuento_afc=r["descuento_afc"], otros_montos=r["otros_montos"],
                    otros_descuentos=r["otros_descuentos"], total_finiquito=r["total_finiquito"],
                    detalle=json.dumps({k: str(v) for k, v in r.items()}, ensure_ascii=False)))
                conn.execute("UPDATE contratos SET activo=0, fecha_termino=? WHERE id=?", (r["fecha_termino"], cont["id"]))
                otros_act = db.scalar(conn, "SELECT COUNT(*) AS n FROM contratos WHERE trabajador_id=? AND activo=1",
                                      (cont["trabajador_id"],))
                if not otros_act:
                    conn.execute("UPDATE trabajadores SET activo=0 WHERE id=?", (cont["trabajador_id"],))
                conn.commit()
                trab = db.row(conn, "SELECT * FROM trabajadores WHERE id=?", (cont["trabajador_id"],))
                ruta = EXPORTS_DIR / f"finiquito_{C.rut_partes(trab['rut'])[0]}_{r['fecha_termino']}.docx"
                D.generar_finiquito_docx(emp, trab, r, cont, str(ruta))
                st.session_state["ult_fin"] = str(ruta)
                st.session_state.pop("fin_prev", None)
                st.success(f"Finiquito N° {fid} registrado.")
    if st.session_state.get("ult_fin"):
        descargar(Path(st.session_state["ult_fin"]), "⬇️ Descargar finiquito DOCX", "dl_fin")
    st.subheader("Finiquitos registrados")
    st.dataframe(db.read_sql_df("""SELECT f.id, t.rut, t.nombres || ' ' || t.apellido_paterno AS trabajador, f.fecha_termino,
                                   f.causal, f.indemnizacion_anos, f.aviso_previo, f.vacaciones_proporcionales_monto,
                                   f.descuento_afc, f.total_finiquito
                                   FROM finiquitos f JOIN trabajadores t ON f.trabajador_id=t.id WHERE f.empresa_id=?""",
                                conn, (emp["id"],)), width="stretch")


def pantalla_previred(conn):
    st.header("Archivo Previred")
    st.markdown("Formato **largo variable por separador** (105 campos, `;`), versión 82 del instructivo Previred. "
                "Valide el archivo con el validador de Previred antes de la primera carga.")
    emp = selector_empresa(conn, "prev_emp")
    periodo = input_periodo(key="prev_per")
    if st.button("Generar archivo Previred"):
        ruta = EXPORTS_DIR / f"previred_{C.rut_partes(emp['rut'])[0]}_{periodo.replace('-', '')}.txt"
        res = P.generar_previred_txt(emp["id"], periodo, str(ruta))
        mostrar_advertencias(res["errores"], "Revisar")
        if res["ruta"]:
            st.success(f"{res['lineas']} línea(s) generadas.")
            descargar(ruta, "⬇️ Descargar TXT", "dl_prev", "text/plain")
            st.code(open(ruta, encoding="latin-1").read()[:1500], language="text")


def pantalla_1887(conn):
    st.header("Declaración Jurada 1887 y certificados")
    emp = selector_empresa(conn, "dj_emp")
    at = int(st.number_input("Año tributario", 2020, 2035, date.today().year))
    ar = at - 1
    st.subheader(f"Factores de actualización (rentas {ar})")
    fac = db.get_factores_actualizacion(ar, conn)
    cols = st.columns(6)
    nuevos = {m: cols[(m - 1) % 6].number_input(C.MESES_ES[m - 1][:3].title(), 0.5, 3.0, float(fac.get(m, 1.0)), 0.001,
                                                format="%.3f", key=f"fac_{ar}_{m}") for m in range(1, 13)}
    if st.button("💾 Guardar factores"):
        for m, f in nuevos.items():
            db.upsert(conn, "factores_actualizacion", dict(anio_rentas=ar, mes=m, factor=f), ["anio_rentas", "mes"])
        conn.commit()
        st.success("Factores guardados.")
    c1, c2 = st.columns(2)
    if c1.button("Formulario 1887 (Excel)"):
        ruta = EXPORTS_DIR / f"formulario_1887_AT{at}_{emp['id']}.xlsx"
        if L.generar_formulario_1887(emp["id"], at, str(ruta)):
            descargar(ruta, "⬇️ Descargar formulario", "dl_f1887")
        else:
            st.warning(f"No hay liquidaciones de {ar}.")
    if c1.button("CSV importador SII"):
        ruta = EXPORTS_DIR / f"1887_importador_AT{at}_{emp['id']}.csv"
        if L.generar_1887_csv_sii(emp["id"], at, str(ruta)):
            descargar(ruta, "⬇️ Descargar CSV", "dl_1887csv", "text/csv")
        else:
            st.warning(f"No hay liquidaciones de {ar}.")
    if c2.button("Certificados 1887 (ZIP)"):
        ruta = EXPORTS_DIR / f"certificados_1887_AT{at}_{emp['id']}.zip"
        if L.generar_certificados_1887(emp["id"], at, str(ruta)):
            descargar(ruta, "⬇️ Descargar certificados", "dl_c1887")
        else:
            st.warning(f"No hay liquidaciones de {ar}.")
    st.caption("Renta total neta = base tributable (imponible − cotizaciones obligatorias) actualizada; impuesto único "
               "retenido actualizado con los mismos factores.")


def pantalla_usuarios(conn):
    st.header("Usuarios y accesos")
    emps = db.rows(conn, "SELECT id, razon_social FROM empresas ORDER BY razon_social")
    nombres = {e["id"]: e["razon_social"] for e in emps}
    if not S._secret():
        st.info("Para impedir que alguien modifique plazos o permisos editando la base de datos, defina "
                "`BASECON_SECRET` en los *secrets* de Streamlit o en el entorno.")
    with st.expander("➕ Nuevo usuario", expanded=True):
        with st.form("nuevo_usuario"):
            a, b = st.columns(2)
            u = a.text_input("Usuario")
            n = b.text_input("Nombre")
            c = a.text_input("Clave inicial", type="password")
            rol = b.selectbox("Rol", ["usuario", "admin"])
            todas = a.checkbox("Acceso a todas las empresas")
            sel = b.multiselect("Empresas", list(nombres), format_func=lambda i: nombres[i])
            mods = b.multiselect("Módulos", list(C.MODULOS), default=["remuneraciones"],
                                 format_func=lambda m: C.MODULOS[m])
            modo = a.selectbox("Plazo de acceso", ["Sin plazo", "Días desde el primer acceso", "Hasta una fecha"])
            dias = b.number_input("Días", 1, 3650, 15)
            fexp = a.date_input("Fecha de expiración", value=date.today())
            if st.form_submit_button("Crear usuario"):
                try:
                    if rol != "admin" and not mods:
                        raise ValueError("Asigne al menos un módulo.")
                    S.crear_usuario(u, c, n, rol=rol, empresas="*" if todas else sel, modulos=mods,
                                    dias_acceso=int(dias) if modo.startswith("Días") else None,
                                    fecha_expira=fexp if modo.startswith("Hasta") else None)
                    st.success("Usuario creado.")
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))
    us = db.rows(conn, "SELECT id, usuario, nombre, rol, empresas, modulos, activo, dias_acceso, fecha_expira, primer_acceso, "
                       "ultimo_acceso FROM usuarios ORDER BY usuario")
    for u in us:
        u["dias_restantes"] = S.dias_restantes(u)
    st.dataframe(pd.DataFrame(us), width="stretch")
    if us:
        with st.expander("✏️ Modificar usuario"):
            uo = {x["usuario"]: x for x in us}
            x = uo[st.selectbox("Usuario", list(uo))]
            with st.form("mod_usuario"):
                activo = st.checkbox("Activo", value=bool(x["activo"]))
                todas = st.checkbox("Todas las empresas", value=x["empresas"] == "*")
                act = [] if x["empresas"] == "*" else json.loads(x["empresas"] or "[]")
                sel = st.multiselect("Empresas", list(nombres), default=[i for i in act if i in nombres],
                                     format_func=lambda i: nombres[i])
                try:
                    mact = [m for m in json.loads(x.get("modulos") or "[]") if m in C.MODULOS]
                except Exception:
                    mact = ["remuneraciones"]
                mods = st.multiselect("Módulos", list(C.MODULOS), default=mact, format_func=lambda m: C.MODULOS[m])
                nueva = st.text_input("Nueva clave (dejar vacío para mantener)", type="password")
                reiniciar = st.checkbox("Reiniciar plazo (cuenta desde el próximo acceso)")
                fexp = st.date_input("Nueva fecha de expiración (opcional)", value=None)
                if st.form_submit_button("Guardar"):
                    campos = dict(activo=int(activo), empresas="*" if todas else sel, modulos=mods)
                    if nueva:
                        campos["clave"] = nueva
                    if reiniciar:
                        campos["primer_acceso"] = None
                    if fexp:
                        campos["fecha_expira"] = fexp
                    try:
                        if x["id"] == usuario_actual().get("id") and not activo:
                            raise ValueError("No puede desactivar su propio usuario.")
                        S.actualizar_usuario(x["id"], **campos)
                        st.success("Usuario actualizado.")
                        st.rerun()
                    except Exception as ex:
                        st.error(str(ex))


def pantalla_ayuda(_conn):
    st.header("Ayuda")
    st.markdown(f"""
**Versión 2.1** — ver `CAMBIOS.md`.

**Módulos y permisos.** Cada usuario tiene empresas y módulos asignados (menú Usuarios):
- *Movimientos RRHH*: trabajadores, movimientos del mes (asistencia, licencias, horas extra, anticipos, bonos,
  conceptos propios) y envío del periodo a remuneraciones.
- *Remuneraciones*: contratos, indicadores, liquidaciones, libros, Previred, finiquitos y DJ 1887.

**Flujo mensual.** El cliente registra los movimientos y presiona *Enviar a remuneraciones* → la oficina calcula
las liquidaciones (toma los movimientos automáticamente) → cierra el periodo.

- **Impuesto único** calculado con la tabla mensual en UTM; se refleja en la liquidación, el libro, el LRE (3161) y el 1887.
- **Gratificación**: por contrato, *Art. 50* (25% con tope 4,75 IMM), monto fijo o sin gratificación.
- **Jornada**: máximo legal vigente {C.jornada_maxima(date.today())} horas (Ley 21.561).
- **Previred**: 105 campos, formato v82. **LRE**: estructura completa del Suplemento DT.
- **Finiquitos**: base art. 172, tope 90 UF, años con fracción > 6 meses (tope 11), aviso previo, feriado
  proporcional desde el último aniversario en días corridos, descuento AFC; vista previa antes de confirmar.
- **Base de datos**: en Streamlit Cloud use Supabase (`DATABASE_URL` en *secrets*); el disco local se borra al reiniciar.
""")


# ============================================================
# Principal
# ============================================================
def main():
    if not S.hay_usuarios():
        pantalla_configuracion_inicial()
    if not st.session_state.get("usuario"):
        pantalla_login()
    u = usuario_actual()

    if S.en_la_nube_sin_bd_persistente():
        st.error("⚠️ La app corre en la nube con base SQLite local: los datos se borran cada vez que el servidor se "
                 "reinicia. Configure `DATABASE_URL` (Supabase) en los *secrets* antes de cargar datos reales.")
    if u.get("dias_restantes") is not None:
        (st.sidebar.warning if u["dias_restantes"] <= 3 else st.sidebar.caption)(
            f"Acceso: quedan {max(0, u['dias_restantes'])} día(s)")
    if LOGO.exists():
        st.sidebar.image(str(LOGO), width="stretch")
    st.sidebar.markdown(f"**{u.get('nombre') or u.get('usuario')}** · {u.get('rol')}  \n"
                        + " · ".join(C.MODULOS[m] for m in sorted(modulos())))

    mods = modulos()
    ctx = {"selector_empresa": selector_empresa, "input_periodo": input_periodo, "usuario": usuario_actual,
           "modulos": modulos, "advertencias": mostrar_advertencias}
    pantallas = {"🏠 Dashboard": pantalla_dashboard}
    if "remuneraciones" in mods:
        pantallas["🏢 Empresas"] = pantalla_empresas
    pantallas["👥 Trabajadores"] = pantalla_trabajadores
    if "rrhh" in mods or "remuneraciones" in mods:
        pantallas["🗓 Movimientos del mes"] = lambda c: ui_rrhh.pantalla_movimientos(c, ctx)
        pantallas["🧩 Conceptos adicionales"] = lambda c: ui_rrhh.pantalla_conceptos(c, ctx)
    if "remuneraciones" in mods:
        pantallas.update({
            "📄 Contratos": pantalla_contratos, "📊 Indicadores": pantalla_indicadores,
            "💰 Liquidaciones": pantalla_liquidaciones, "📒 Libro de Remuneraciones": pantalla_libro,
            "🏖 Vacaciones": pantalla_vacaciones, "📝 Finiquitos": pantalla_finiquitos,
            "📤 Archivo Previred": pantalla_previred, "📋 DJ 1887": pantalla_1887})
    pantallas["ℹ️ Ayuda"] = pantalla_ayuda
    if es_admin():
        pantallas["🔐 Usuarios"] = pantalla_usuarios
    menu = st.sidebar.radio("Menú", list(pantallas))
    if st.sidebar.button("Cerrar sesión"):
        st.session_state.clear()
        st.rerun()

    st.title("BASECON · Remuneraciones" if "remuneraciones" in mods else "BASECON · Movimientos RRHH")
    conn = db.get_conn()
    try:
        pantallas[menu](conn)
    finally:
        conn.close()


main()
