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

from remu import anexos as AN
from remu import archivo as A
from remu import calculadora as CALC
from remu import calculos as K
from remu import config as C
from remu import db
from remu import documentos as D
from remu import finiquitos as FQ
from remu import libros as L
from remu import previred as P
from remu import seguridad as S
from remu import email_utils as EU
from remu.pdf_indicadores import parse_indicadores_pdf
from remu.procesos import calcular_periodo
from remu import procesos as PR
import ui_rrhh

_favicon = C.BASE_DIR / "favicon.png"
if not _favicon.exists():
    _favicon = C.BASE_DIR / "basecon-logo.png"
st.set_page_config(page_title="BASECON — Remuneraciones Chile",
                   page_icon=str(_favicon) if _favicon.exists() else "🇨🇱",
                   layout="wide", initial_sidebar_state="expanded")

# Letra más grande y color más fuerte en toda la app; menú lateral más amplio
st.markdown("""
<style>
/* Texto general */
html, body, [data-testid="stAppViewContainer"] { color: #111111; }
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] li { font-size: 1.05rem; color: #111111; }
/* Títulos de pantalla y secciones */
[data-testid="stMain"] h1 { color: #0b1f3a !important; font-weight: 800 !important; }
[data-testid="stMain"] h2 { color: #0b1f3a !important; font-weight: 800 !important; font-size: 2rem !important; }
[data-testid="stMain"] h3 { color: #0b1f3a !important; font-weight: 700 !important; font-size: 1.5rem !important; }
/* Etiquetas de cada campo (Usuario, Nombre, RUT, Periodo...) */
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [data-testid="stWidgetLabel"] label {
    font-size: 1.08rem !important; font-weight: 700 !important; color: #111111 !important;
}
/* Texto dentro de los campos y listas */
[data-testid="stMain"] input, [data-testid="stMain"] textarea, [data-testid="stMain"] [data-baseweb="select"] div { font-size: 1.05rem !important; color: #111111 !important; }
/* Encabezados de los desplegables (➕ Nuevo..., ✏️ Modificar...) */
[data-testid="stMain"] [data-testid="stExpander"] summary p {
    font-size: 1.15rem !important; font-weight: 700 !important; color: #0b1f3a !important;
}
/* Pestañas */
[data-testid="stMain"] [data-baseweb="tab"] p { font-size: 1.1rem !important; font-weight: 700 !important; }
/* Indicadores del dashboard */
[data-testid="stMain"] [data-testid="stMetricLabel"] p { font-size: 1.05rem !important; font-weight: 700 !important; color: #111111 !important; }
[data-testid="stMain"] [data-testid="stMetricValue"],
[data-testid="stMain"] [data-testid="stMetricValue"] p,
[data-testid="stMain"] [data-testid="stMetricValue"] div { font-size: 2.3rem !important; font-weight: 700 !important; color: #0b1f3a !important; }
/* Botones */
[data-testid="stMain"] button p { font-size: 1.05rem !important; font-weight: 600 !important; }
/* Notas pequeñas (captions) más legibles */
[data-testid="stMain"] [data-testid="stCaptionContainer"] { font-size: 0.98rem !important; color: #333333 !important; }
/* Mes activo destacado (esquina superior derecha) */
.mes-activo { position: fixed; top: 0.5rem; right: 14rem; z-index: 999990; display: flex; align-items: center;
    gap: 0.6rem; background: #0b1f3a; color: #ffffff; padding: 0.35rem 0.95rem; border-radius: 0.6rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.18); }
.mes-activo-et { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; color: #f2a900; }
.mes-activo-val { font-size: 1.15rem; font-weight: 800; letter-spacing: 0.02em; }
@media (max-width: 640px) { .mes-activo { right: 3.2rem; padding: 0.25rem 0.6rem; }
    .mes-activo-et { display: none; } .mes-activo-val { font-size: 0.95rem; } }
/* Menú lateral */
section[data-testid="stSidebar"] div[role="radiogroup"] label p { color: #111111 !important; font-weight: 500; }
section[data-testid="stSidebar"][aria-expanded="true"] {
    min-width: 20rem !important;
    width: 20rem !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label p {
    font-size: 1.15rem !important;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    padding: 0.35rem 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 1.25rem !important;
    font-weight: 700 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] button p {
    font-size: 1.05rem !important;
}

/* ══════════════════════════════════════════════════════ */
/* LOGIN                                                   */
/* ══════════════════════════════════════════════════════ */
.login-bg {
    position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
    background: linear-gradient(135deg, #e8eef7 0%, #f5f7fb 50%, #e0e8f5 100%);
    z-index: -1;
}
/* Sidebar logo en login */
.login-sidebar-logo {
    padding: 1rem 1rem 0.5rem 1rem;
    text-align: center;
}
.login-sidebar-logo img {
    max-width: 120px; height: auto;
    margin: 0 auto; display: block;
}
.login-sidebar-brand {
    text-align: center;
    font-size: 1.15rem; font-weight: 800;
    color: #0b1f3a; letter-spacing: 0.02em;
    margin: 0.3rem 0 1rem 0;
}
/* Tarjeta grande centrada */
.login-card {
    max-width: 520px; margin: 3rem auto 2rem auto;
    background: #ffffff;
    border-radius: 18px;
    box-shadow: 0 16px 48px rgba(11, 31, 58, 0.14), 0 4px 12px rgba(11, 31, 58, 0.08);
    padding: 3rem 3rem 2rem 3rem;
    border: 1px solid rgba(11, 31, 58, 0.06);
}
.login-title {
    text-align: center;
    font-size: 2.2rem; font-weight: 800;
    color: #0b1f3a; letter-spacing: -0.02em;
    margin: 0 0 0.35rem 0;
}
.login-subtitle {
    text-align: center;
    font-size: 1.1rem; font-weight: 500;
    color: #5a6b85; letter-spacing: 0.02em;
    margin: 0 0 2rem 0;
}
.login-footer {
    text-align: center; font-size: 0.88rem;
    color: #8b98ac; margin-top: 2rem;
}
.login-soporte {
    text-align: center; font-size: 0.95rem;
    color: #5a6b85; line-height: 1.7;
    margin-top: 2rem; padding-top: 1.5rem;
    border-top: 1px solid #eaeff5;
}
.login-soporte a { color: #0b1f3a; text-decoration: none; font-weight: 600; }
.login-soporte a:hover { color: #f2a900; }
/* Boton ENTRAR con letra blanca */
[data-testid="stForm"] button[kind="primary"],
[data-testid="stForm"] button[kind="primaryFormSubmit"],
[data-testid="stForm"] button[type="submit"] {
    background: linear-gradient(135deg, #0b1f3a 0%, #1a3a63 100%) !important;
    border: none !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
    padding: 0.85rem 1rem !important;
    border-radius: 10px !important;
    transition: all 0.2s ease !important;
    box-shadow: 0 4px 14px rgba(11, 31, 58, 0.25) !important;
}
[data-testid="stForm"] button[kind="primary"] p,
[data-testid="stForm"] button[kind="primaryFormSubmit"] p,
[data-testid="stForm"] button[kind="primary"] div,
[data-testid="stForm"] button[kind="primaryFormSubmit"] div,
[data-testid="stForm"] button[type="submit"] p,
[data-testid="stForm"] button[type="submit"] div {
    color: #ffffff !important;
    font-weight: 700 !important;
    font-size: 1.15rem !important;
    letter-spacing: 0.05em !important;
}
[data-testid="stForm"] button[kind="primary"]:hover,
[data-testid="stForm"] button[kind="primaryFormSubmit"]:hover,
[data-testid="stForm"] button[type="submit"]:hover {
    background: linear-gradient(135deg, #1a3a63 0%, #0b1f3a 100%) !important;
    box-shadow: 0 6px 18px rgba(11, 31, 58, 0.35) !important;
    transform: translateY(-1px);
}
/* Inputs */
[data-testid="stForm"] input {
    border-radius: 8px !important;
    border: 1.5px solid #d0dae8 !important;
    padding: 0.7rem 0.85rem !important;
    font-size: 1rem !important;
    transition: all 0.2s ease !important;
}
[data-testid="stForm"] input:focus {
    border-color: #0b1f3a !important;
    box-shadow: 0 0 0 3px rgba(11, 31, 58, 0.1) !important;
}


/* SIDEBAR - tarjetas destacadas */
.sidebar-user-card {
    background: #f4f6fa;
    border-radius: 10px;
    padding: 0.7rem 0.9rem;
    margin: 0.3rem 0 0.6rem 0;
    border: 1px solid #e3e8f0;
}
.sidebar-user-card .u-name {
    font-size: 1rem; font-weight: 700; color: #0b1f3a;
    line-height: 1.2;
}
.sidebar-user-card .u-role {
    font-size: 0.8rem; color: #5a6b85; margin-top: 0.15rem;
    text-transform: uppercase; letter-spacing: 0.06em;
}
.sidebar-active-card {
    background: linear-gradient(135deg, #0b1f3a 0%, #1a3a63 100%);
    border-radius: 10px;
    padding: 0.55rem 0.85rem 0.35rem 0.85rem;
    margin: 0.35rem 0;
    box-shadow: 0 3px 8px rgba(11, 31, 58, 0.18);
}
.sidebar-active-card .card-et {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
    color: #f2a900; text-transform: uppercase;
    display: block; margin-bottom: 0.1rem;
}
.sidebar-active-card .card-val {
    font-size: 1.05rem; font-weight: 700; color: #ffffff;
    line-height: 1.25; word-break: break-word;
}
.sidebar-active-card [data-testid="stSelectbox"] label { display: none !important; }
.sidebar-active-card [data-testid="stSelectbox"] > div > div {
    background: rgba(255, 255, 255, 0.12) !important;
    border: 1px solid rgba(255, 255, 255, 0.25) !important;
    border-radius: 6px !important;
    color: #ffffff !important;
    min-height: 1.9rem !important;
}
.sidebar-active-card [data-testid="stSelectbox"] > div > div:hover {
    background: rgba(255, 255, 255, 0.2) !important;
}
.sidebar-active-card [data-testid="stSelectbox"] input,
.sidebar-active-card [data-testid="stSelectbox"] div[role="button"] {
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
}
section[data-testid="stSidebar"] hr {
    margin: 0.6rem 0;
    border-color: #e3e8f0;
}


/* ══════════════════════════════════════════════════ */
/* MENU LATERAL — Acordeon con pill style             */
/* ══════════════════════════════════════════════════ */
/* Expander del grupo (el titulo clickeable) */
section[data-testid="stSidebar"] details {
    border: none !important;
    margin-bottom: 0.2rem !important;
}
section[data-testid="stSidebar"] details > summary {
    font-size: 1rem !important;
    font-weight: 700 !important;
    color: #0b1f3a !important;
    padding: 0.55rem 0.6rem !important;
    border-radius: 8px !important;
    list-style: none !important;
    cursor: pointer !important;
    transition: background 0.15s ease !important;
    background: transparent !important;
}
section[data-testid="stSidebar"] details > summary:hover {
    background: rgba(11, 31, 58, 0.06) !important;
}
section[data-testid="stSidebar"] details[open] > summary {
    background: rgba(11, 31, 58, 0.04) !important;
}
/* Ocultar la flecha nativa del expander */
section[data-testid="stSidebar"] details > summary::-webkit-details-marker {
    display: none !important;
}
section[data-testid="stSidebar"] details > summary::marker {
    content: "" !important;
}
/* Contenedor interno del expander */
section[data-testid="stSidebar"] details > div {
    padding: 0.2rem 0 0.3rem 0.4rem !important;
    border-left: 2px solid rgba(11, 31, 58, 0.08) !important;
    margin-left: 0.5rem !important;
}
/* Botones dentro del expander (pill style) */
section[data-testid="stSidebar"] details button {
    width: 100% !important;
    text-align: left !important;
    justify-content: flex-start !important;
    background: transparent !important;
    border: none !important;
    padding: 0.45rem 0.7rem !important;
    margin: 0.05rem 0 !important;
    border-radius: 8px !important;
    box-shadow: none !important;
    font-size: 0.98rem !important;
    font-weight: 500 !important;
    color: #1a1a1a !important;
    transition: all 0.12s ease !important;
}
section[data-testid="stSidebar"] details button:hover {
    background: rgba(11, 31, 58, 0.08) !important;
    color: #0b1f3a !important;
}
section[data-testid="stSidebar"] details button p {
    font-size: 0.98rem !important;
    font-weight: 500 !important;
    color: inherit !important;
    text-align: left !important;
    margin: 0 !important;
}
/* Item activo (marcado con st.markdown) */
.menu-item-activo {
    display: block;
    padding: 0.5rem 0.75rem !important;
    margin: 0.05rem 0 !important;
    border-radius: 8px !important;
    background: linear-gradient(135deg, #0b1f3a 0%, #1a3a63 100%) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    font-size: 0.98rem !important;
    box-shadow: 0 2px 6px rgba(11, 31, 58, 0.2) !important;
}

</style>
""", unsafe_allow_html=True)


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


def periodo_valido(p: str) -> bool:
    try:
        a, m = int(p[:4]), int(p[5:7])
        return len(p) == 7 and p[4] == "-" and 1 <= m <= 12 and 2000 < a < 2100
    except Exception:
        return False


def periodo_activo() -> str:
    """Mes de trabajo de la sesión. Parte en el último mes con indicadores cargados (el que se está procesando)."""
    if not st.session_state.get("periodo_activo"):
        ult = None
        try:
            conn = db.get_conn()
            try:
                ult = db.scalar(conn, "SELECT MAX(periodo) AS p FROM indicadores WHERE periodo <= ?", (periodo_default(),))
            finally:
                conn.close()
        except Exception:
            pass
        st.session_state["periodo_activo"] = ult if ult and periodo_valido(ult) else periodo_default()
    return st.session_state["periodo_activo"]


def _sync_periodo(key):
    v = (st.session_state.get(key) or "").strip()
    if periodo_valido(v):
        st.session_state["periodo_activo"] = v
    else:
        st.session_state["periodo_invalido"] = v


def input_periodo(label="Periodo (AAAA-MM)", key=None, value=None, sincronizar=True) -> str:
    """Campo de periodo. Parte en el mes activo; si se cambia aquí, pasa a ser el mes activo de toda la app."""
    if sincronizar and key and value is None:
        st.session_state[key] = periodo_activo()
        p = st.text_input(label, key=key, on_change=_sync_periodo, args=(key,),
                          help="Al cambiarlo aquí cambia el mes activo de toda la aplicación.").strip()
        malo = st.session_state.pop("periodo_invalido", None)
        if malo is not None:
            st.warning(f"“{malo}” no es un periodo válido (use AAAA-MM, por ejemplo 2026-09). Se mantiene {p}.")
    else:
        p = st.text_input(label, value=value or periodo_activo(), key=key).strip()
    try:
        a, m = int(p[:4]), int(p[5:7])
        assert len(p) == 7 and p[4] == "-" and 1 <= m <= 12 and 2000 < a < 2100
    except Exception:
        st.error("Periodo inválido. Use el formato AAAA-MM, por ejemplo 2026-08.")
        st.stop()
    return p


def nombre_mes(periodo: str) -> str:
    a, m = int(periodo[:4]), int(periodo[5:7])
    return f"{C.MESES_ES[m - 1].capitalize()} {a}"


def _cambiar_mes_activo():
    st.session_state["periodo_activo"] = st.session_state["sel_mes_activo"]


def selector_mes_activo():
    """Selector en el menú lateral: últimos 24 meses y el próximo."""
    act = periodo_activo()
    hoy = date.today()
    a, m = hoy.year, hoy.month + 1
    if m == 13:
        a, m = a + 1, 1
    opciones = []
    for _ in range(26):
        opciones.append(f"{a}-{m:02d}")
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    if act not in opciones:
        opciones.insert(0, act)
    st.session_state["sel_mes_activo"] = act
    st.sidebar.selectbox("📅 Mes activo", opciones, key="sel_mes_activo", format_func=nombre_mes,
                         on_change=_cambiar_mes_activo,
                         help="Periodo con que se abren Movimientos, Liquidaciones, Libro, Previred e Indicadores.")


def insignia_mes_activo():
    """Mes activo destacado en la esquina superior derecha de la zona de trabajo."""
    st.markdown(
        f"""<div class="mes-activo"><span class="mes-activo-et">MES ACTIVO</span>
        <span class="mes-activo-val">{nombre_mes(periodo_activo()).upper()}</span></div>""",
        unsafe_allow_html=True)


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


CONTACTO_CAMPOS = [("contacto_nombre", "Nombre / empresa de soporte"), ("contacto_telefono", "Teléfono"),
                   ("contacto_whatsapp", "WhatsApp"), ("contacto_email", "Correo"),
                   ("contacto_horario", "Horario de atención")]


def leer_contacto() -> dict:
    conn = db.get_conn()
    try:
        return {k: (db.scalar(conn, "SELECT valor FROM configuracion WHERE clave=?", (k,)) or "").strip()
                for k, _ in CONTACTO_CAMPOS}
    except Exception:
        return {}
    finally:
        conn.close()


def texto_contacto(ct: dict) -> str:
    partes = []
    if ct.get("contacto_nombre"):
        partes.append(f"**{ct['contacto_nombre']}**")
    if ct.get("contacto_telefono"):
        partes.append(f"📞 {ct['contacto_telefono']}")
    if ct.get("contacto_whatsapp"):
        num = "".join(ch for ch in ct["contacto_whatsapp"] if ch.isdigit())
        partes.append(f"💬 [WhatsApp {ct['contacto_whatsapp']}](https://wa.me/{num})" if num else f"💬 {ct['contacto_whatsapp']}")
    if ct.get("contacto_email"):
        partes.append(f"✉️ [{ct['contacto_email']}](mailto:{ct['contacto_email']})")
    if ct.get("contacto_horario"):
        partes.append(f"🕘 {ct['contacto_horario']}")
    return "  \n".join(partes)


def mostrar_advertencias(adv, titulo=None):
    if adv:
        st.warning((f"**{titulo}**\n\n" if titulo else "") + "\n".join(f"- {a}" for a in adv))


# ============================================================
# Acceso
# ============================================================


def empresa_activa(conn):
    """Devuelve la empresa activa del session_state (o la primera disponible)."""
    emps = empresas_visibles(conn)
    if not emps:
        return None
    eid = st.session_state.get("empresa_activa_id")
    if eid and any(e["id"] == eid for e in emps):
        return next(e for e in emps if e["id"] == eid)
    u = usuario_actual()
    ultima = u.get("ultima_empresa_id")
    if ultima and any(e["id"] == ultima for e in emps):
        st.session_state["empresa_activa_id"] = ultima
        return next(e for e in emps if e["id"] == ultima)
    st.session_state["empresa_activa_id"] = emps[0]["id"]
    return emps[0]


def _guardar_preferencia_usuario(empresa_id=None, periodo=None):
    """Guarda ultima_empresa_id y/o ultimo_periodo en la DB del usuario actual."""
    u = usuario_actual()
    uid = u.get("id")
    if not uid:
        return
    try:
        conn = db.get_conn()
        try:
            if empresa_id is not None:
                conn.execute("UPDATE usuarios SET ultima_empresa_id=? WHERE id=?",
                             (empresa_id, uid))
            if periodo is not None:
                conn.execute("UPDATE usuarios SET ultimo_periodo=? WHERE id=?",
                             (periodo, uid))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print("[warn] No se pudo guardar preferencia: " + str(e))


def _sidebar_header(conn):
    """Renderiza las 3 tarjetas destacadas en el sidebar."""
    u = usuario_actual()
    emps = empresas_visibles(conn)

    st.sidebar.markdown(
        '<div class="sidebar-user-card">'
        '<div class="u-name">' + (u.get("nombre") or u.get("usuario") or "Usuario") + '</div>'
        '<div class="u-role">' + (u.get("rol") or "usuario") + '</div>'
        '</div>',
        unsafe_allow_html=True)

    st.sidebar.markdown('<div class="sidebar-active-card">'
                        '<span class="card-et">Empresa activa</span>',
                        unsafe_allow_html=True)
    if not emps:
        st.sidebar.markdown('<div class="card-val">Sin empresa asignada</div></div>',
                            unsafe_allow_html=True)
    elif len(emps) == 1:
        st.sidebar.markdown('<div class="card-val">' + emps[0]["razon_social"] + '</div></div>',
                            unsafe_allow_html=True)
        st.session_state["empresa_activa_id"] = emps[0]["id"]
    else:
        opciones = {}
        for e in emps:
            opciones[e["razon_social"]] = e["id"]
        eid_actual = st.session_state.get("empresa_activa_id") or emps[0]["id"]
        idx = 0
        for i, e in enumerate(emps):
            if e["id"] == eid_actual:
                idx = i
                break

        def _on_empresa_change():
            nueva_id = opciones[st.session_state["_sel_empresa_activa"]]
            st.session_state["empresa_activa_id"] = nueva_id
            _guardar_preferencia_usuario(empresa_id=nueva_id)

        sel = st.sidebar.selectbox("Empresa activa", list(opciones), index=idx,
                                    key="_sel_empresa_activa", label_visibility="collapsed",
                                    on_change=_on_empresa_change)
        st.sidebar.markdown('</div>', unsafe_allow_html=True)
        st.session_state["empresa_activa_id"] = opciones[sel]

    st.sidebar.markdown('<div class="sidebar-active-card">'
                        '<span class="card-et">Mes activo</span>',
                        unsafe_allow_html=True)
    _render_selector_mes()
    st.sidebar.markdown('</div>', unsafe_allow_html=True)


def _render_selector_mes():
    """Selector de mes activo (version interna para la tarjeta)."""
    act = periodo_activo()
    hoy = date.today()
    a, m = hoy.year, hoy.month + 1
    if m == 13:
        a, m = a + 1, 1
    opciones = []
    for _ in range(26):
        opciones.append(f"{a}-{m:02d}")
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    if act not in opciones:
        opciones.insert(0, act)

    def _on_mes_change():
        nuevo = st.session_state["_sel_mes_activo_tarjeta"]
        st.session_state["periodo_activo"] = nuevo
        _guardar_preferencia_usuario(periodo=nuevo)

    st.session_state["_sel_mes_activo_tarjeta"] = act
    st.sidebar.selectbox("Mes activo", opciones, key="_sel_mes_activo_tarjeta",
                         format_func=nombre_mes, label_visibility="collapsed",
                         on_change=_on_mes_change)




def pantalla_recuperar_clave():
    """Pantalla para solicitar recuperacion de contrasena."""
    st.markdown('<div class="login-bg"></div>', unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown('<div class="login-title">Recuperar contrasena</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">Te enviaremos un correo con un link para restablecer tu clave</div>',
                    unsafe_allow_html=True)

        with st.form("recuperar"):
            ident = st.text_input("Usuario o email", placeholder="Tu usuario o email registrado")
            enviar = st.form_submit_button("Enviar link de recuperacion", type="primary", width="stretch")

        if enviar:
            ident = (ident or "").strip()
            if not ident:
                st.error("Ingresa tu usuario o email.")
            else:
                info = S.generar_token_recuperacion(ident)
                if info:
                    _api = __import__("remu.email_utils", fromlist=["_api_key"])._api_key()
                    _from = __import__("remu.email_utils", fromlist=["_from_email"])._from_email()
                    ok = EU.enviar_email_recuperacion(info["email"], info["nombre"], info["token"])
                    if ok:
                        st.success("Si el usuario existe, te enviamos un email con las instrucciones.")
                    else:
                        _d1 = st.session_state.pop("_resend_debug_1", "(no d1)")
                        _d2 = st.session_state.pop("_resend_debug_2", "(no d2)")
                        st.code("D1=" + _d1 + " | D2=" + _d2)
                        _resp = st.session_state.pop("_resend_response", "(sin response)")
                        st.code("RESEND RESPONSE: " + _resp)
                        _err = st.session_state.pop("_email_error", "(sin detalle)")
                        st.error("No se pudo enviar el email: " + _err)
                else:
                    st.success("Si el usuario existe, te enviamos un email con las instrucciones.")

        st.markdown('<div class="login-soporte">', unsafe_allow_html=True)
        if st.button("Volver al login", key="volver_login"):
            st.session_state.pop("_ir_recuperar", None)
            st.query_params.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

def pantalla_reset_clave(token: str):
    """Pantalla para cambiar contrasena usando un token valido."""
    st.markdown('<div class="login-bg"></div>', unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        info = S.validar_token_recuperacion(token)
        if not info:
            st.markdown('<div class="login-title">Link invalido o expirado</div>', unsafe_allow_html=True)
            st.error("Este link ya no es valido. Solicita uno nuevo.")
            if st.button("Volver al login", key="volver_login_inv"):
                st.query_params.clear()
                st.rerun()
            st.stop()

        st.markdown('<div class="login-title">Nueva contrasena</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">Usuario: ' + info["usuario"] + '</div>', unsafe_allow_html=True)

        with st.form("reset_clave"):
            c1 = st.text_input("Nueva contrasena", type="password",
                               placeholder="Minimo 8 caracteres, letras y numeros")
            c2 = st.text_input("Repetir contrasena", type="password")
            guardar = st.form_submit_button("Cambiar contrasena", type="primary", width="stretch")

        if guardar:
            if c1 != c2:
                st.error("Las contrasenas no coinciden.")
            else:
                err = S.validar_clave_nueva(c1)
                if err:
                    st.error(err)
                else:
                    ok = S.cambiar_clave_con_token(token, c1)
                    if ok:
                        st.success("Contrasena cambiada. Ya puedes iniciar sesion.")
                        st.query_params.clear()
                        if st.button("Ir al login", key="ir_login"):
                            st.rerun()
                    else:
                        st.error("No se pudo cambiar la contrasena. Intenta de nuevo.")
    st.stop()



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
    # Fondo con gradiente (overlay)
    st.markdown('<div class="login-bg"></div>', unsafe_allow_html=True)

    # ─── Logo en el sidebar (arriba izquierda) ───
    if LOGO.exists():
        st.sidebar.markdown(
            f'<div class="login-sidebar-logo"><img src="data:image/png;base64,{_logo_b64()}"></div>'
            '<div class="login-sidebar-brand">BASECON</div>',
            unsafe_allow_html=True)

    # ─── Tarjeta de login centrada y mas grande ───
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown('<div class="login-title">BASECON</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">Sistema de Remuneraciones Chile</div>',
                    unsafe_allow_html=True)

        # Bloqueo por intentos
        bloqueo = st.session_state.get("bloqueo_hasta", 0)
        if time.time() < bloqueo:
            st.error(f"Demasiados intentos fallidos. Espere {int(bloqueo - time.time())} segundos.")
            st.stop()

        # Formulario
        with st.form("login"):
            u = st.text_input("Usuario", placeholder="Ingrese su usuario")
            c = st.text_input("Clave", type="password", placeholder="Ingrese su clave")
            ok = st.form_submit_button("ENTRAR", type="primary", width="stretch")

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

        # Link "olvidaste tu contrasena"
        if st.button("Olvide mi contrasena", key="olvide_clave", use_container_width=True):
            st.session_state["_ir_recuperar"] = True
            st.rerun()

        # Info de soporte
        ct = texto_contacto(leer_contacto())
        if ct:
            st.markdown('<div class="login-soporte"><strong>¿Necesita ayuda o una cuenta de prueba?</strong><br>' + ct + '</div>',
                        unsafe_allow_html=True)

        # Footer
        st.markdown('<div class="login-footer">Basecon © 2026 — Todos los derechos reservados</div>',
                    unsafe_allow_html=True)
    st.stop()


def _logo_b64() -> str:
    """Devuelve el logo en base64 para incrustarlo en el HTML del login."""
    import base64
    if not LOGO.exists():
        return ""
    with open(LOGO, "rb") as f:
        return base64.b64encode(f.read()).decode()




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
    d["pensionado"] = int(c1.checkbox("Pensionado / jubilado", value=bool(t.get("pensionado")), key=f"{prefix}_pen",
                                      help="Paga solo salud 7%: sin AFP (salvo cotización voluntaria), sin seguro de "
                                           "cesantía, sin SIS y sin cotización del empleador Ley 21.735."))
    d["afp_voluntaria_pensionado"] = int(c2.checkbox(
        "AFP voluntaria (pensionado)", value=bool(t.get("afp_voluntaria_pensionado")), key=f"{prefix}_avol",
        help="Solo para pensionados que decidieron seguir cotizando en su AFP. Si no se marca, no se descuenta AFP."))
    d["cotiza_afp"] = int(c3.checkbox("Cotiza en AFP", value=bool(t.get("cotiza_afp", 1)),
                                      key=f"{prefix}_cafp",
                                      help="Para trabajadores no pensionados. Desmarcar solo en casos de exención expresa, "
                                           "por ejemplo técnicos extranjeros (Ley 18.156)."))
    return d


def pantalla_trabajadores(conn):
    st.header("Trabajadores")
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
    incompletos = [t for t in trabs if t.get("activo") and not t.get("afp") and C.cotiza_afp_efectivo(t)]
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
        st.divider()
        st.subheader("📁 Documentos del trabajador")        
        seccion_historial(conn, emp, trabs)


def seccion_historial(conn, emp, trabs):
    """Carpeta del trabajador: documentos generados por la app y archivos subidos (licencias, firmados, etc.)."""
    st.subheader("📁 Historial y documentos del trabajador")
    opts = {f"{t['rut']} — {t['nombres']} {t['apellido_paterno']}{'' if t.get('activo', 1) else ' (inactivo)'}": t
            for t in trabs}
    t = opts[st.selectbox("Trabajador", list(opts), key="hist_trab")]
    usuario = usuario_actual().get("usuario", "")

    docs = A.listar(conn, t["id"])
    c1, c2, c3, c4 = st.columns(4)
    cuenta = {k: sum(1 for d in docs if d["tipo"] == k) for k in ("Contrato", "Liquidación", "Licencia médica")}
    c1.metric("Documentos", len(docs))
    c2.metric("Contratos y anexos", cuenta["Contrato"] + sum(1 for d in docs if d["tipo"] == "Anexo de contrato"))
    c3.metric("Liquidaciones", cuenta["Liquidación"])
    c4.metric("Licencias", cuenta["Licencia médica"])

    if docs:
        tipos = sorted({d["tipo"] for d in docs})
        filtro = st.multiselect("Filtrar por tipo", tipos, key=f"hist_filtro_{t['id']}")
        vis = [d for d in docs if not filtro or d["tipo"] in filtro]
        tabla = pd.DataFrame([{
            "Fecha": C.fecha_ddmmaaaa(d["fecha"]), "Tipo": d["tipo"], "Periodo": d.get("periodo") or "",
            "Descripción": d.get("descripcion") or "", "Archivo": d["nombre_archivo"],
            "Tamaño": A.tamano_legible(d["tamano"]),
            "Origen": "Subido" if d["origen"] == "subido" else "Generado", "Por": d.get("creado_por") or ""} for d in vis])
        st.dataframe(tabla, hide_index=True, width="stretch")
        etiquetas = {f"{C.fecha_ddmmaaaa(d['fecha'])} · {d['tipo']}{' ' + d['periodo'] if d.get('periodo') else ''} · "
                     f"{d['nombre_archivo']}": d for d in vis}
        if etiquetas:
            a, b = st.columns([4, 1])
            d = etiquetas[a.selectbox("Documento", list(etiquetas), key=f"hist_doc_{t['id']}")]
            full = A.obtener(conn, d["id"])
            b.markdown("&nbsp;")
            b.download_button("⬇️ Descargar", full["contenido"], file_name=d["nombre_archivo"], mime=d["mime"],
                              key=f"hist_dl_{d['id']}", width="stretch")
            puede_borrar = es_admin() or (d["origen"] == "subido" and d.get("creado_por") == usuario)
            if puede_borrar:
                with st.popover("🗑️ Eliminar este documento"):
                    st.write(f"Se eliminará **{d['nombre_archivo']}** del historial. No se puede deshacer.")
                    if st.button("Sí, eliminar", key=f"hist_del_{d['id']}", type="primary"):
                        A.eliminar(conn, d["id"])
                        conn.commit()
                        st.success("Documento eliminado.")
                        st.rerun()
    else:
        st.info("Este trabajador aún no tiene documentos. Los contratos, anexos, liquidaciones, comprobantes de "
                "vacaciones y finiquitos se guardan aquí automáticamente al generarlos.")

    with st.expander("📎 Subir un documento (licencia médica, contrato firmado, certificado…)"):
        with st.form(f"hist_subir_{t['id']}", clear_on_submit=True):
            a, b = st.columns(2)
            tipo = a.selectbox("Tipo de documento", A.TIPOS_SUBIDA)
            fecha = b.date_input("Fecha del documento", value=date.today(), format="DD/MM/YYYY")
            per = a.text_input("Periodo (AAAA-MM, opcional)", value="")
            desc = b.text_input("Descripción", placeholder="Ej.: licencia 5 días, del 10 al 14 de septiembre")
            arch = st.file_uploader(f"Archivo ({', '.join(A.EXTENSIONES_SUBIDA).upper()}; máximo {A.MAX_SUBIDA_MB} MB)",
                                    type=A.EXTENSIONES_SUBIDA)
            if st.form_submit_button("Guardar en el historial", type="primary"):
                per = per.strip()
                if not arch:
                    st.error("Seleccione el archivo.")
                elif per and not periodo_valido(per):
                    st.error("Periodo inválido. Use AAAA-MM o déjelo vacío.")
                else:
                    try:
                        A.guardar(conn, emp["id"], t["id"], tipo, arch.name, arch.getvalue(), periodo=per or None,
                                  fecha=fecha, descripcion=desc, origen="subido", usuario=usuario)
                        conn.commit()
                        st.success(f"{arch.name} guardado en el historial.")
                        st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))
    if es_admin():
        u = A.uso(conn)
        st.caption(f"Espacio usado por documentos (todas las empresas): {A.tamano_legible(u['bytes'])} en {u['n']} archivo(s). "
                   "El plan gratuito de Supabase permite 500 MB para toda la base.")


def pantalla_contratos(conn):
    st.header("Contratos de trabajo")
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
                        A.guardar_archivo(conn, emp["id"], trab["id"], "Contrato", ruta, fecha=f_ini,
                                          descripcion=f"{cargo} · {tipo}", ref_tabla="contratos", ref_id=cid,
                                          usuario=usuario_actual().get("usuario", ""))
                        conn.commit()
                        st.session_state["ultimo_contrato_docx"] = str(ruta)
                        st.success(f"Contrato creado: {ruta.name}")
        if st.session_state.get("ultimo_contrato_docx"):
            descargar(Path(st.session_state["ultimo_contrato_docx"]), "⬇️ Descargar contrato DOCX", "dl_contrato")
    seccion_anexo(conn, emp)
    df = db.read_sql_df("""
        SELECT c.id, t.rut, t.nombres || ' ' || t.apellido_paterno AS trabajador, c.cargo, c.tipo_contrato,
               c.fecha_inicio, c.fecha_termino, c.sueldo_base, c.tipo_gratificacion, c.jornada_semanal, c.activo
        FROM contratos c JOIN trabajadores t ON c.trabajador_id = t.id WHERE c.empresa_id=?""", conn, (emp["id"],))
    if not df.empty:
        viejos = df[(df["activo"] == 1) & (df["jornada_semanal"] > jmax)]
        if len(viejos):
            st.warning(f"{len(viejos)} contrato(s) activo(s) con jornada sobre {jmax} h: deben ajustarse a la Ley 21.561.")
    st.dataframe(df, width="stretch")


def seccion_anexo(conn, emp):
    """Anexo de contrato: genera el documento, lo guarda en el historial y actualiza el contrato."""
    conts = db.rows(conn, """SELECT c.*, t.rut, t.nombres, t.apellido_paterno FROM contratos c
                             JOIN trabajadores t ON c.trabajador_id=t.id WHERE c.empresa_id=? AND c.activo=1
                             ORDER BY t.apellido_paterno""", (emp["id"],))
    with st.expander("📝 Anexo de contrato"):
        if not conts:
            st.info("No hay contratos activos.")
            return
        copts = {f"{c['rut']} — {c['nombres']} {c['apellido_paterno']} ({c['cargo']}, {c['tipo_contrato']})": c for c in conts}
        cont = copts[st.selectbox("Contrato", list(copts), key="anx_cont")]
        k = f"anx_{cont['id']}"
        st.caption(f"Actual: sueldo base \\${C.fmt_clp(cont['sueldo_base'])} · {cont['jornada_semanal']} h · "
                   f"colación \\${C.fmt_clp(cont.get('colacion'))} · movilización \\${C.fmt_clp(cont.get('movilizacion'))}"
                   + (f" · término {C.fecha_ddmmaaaa(cont['fecha_termino'])}" if cont.get("fecha_termino") else ""))
        a, b = st.columns(2)
        f_anexo = a.date_input("Fecha del anexo", value=date.today(), format="DD/MM/YYYY", key=f"{k}_f")
        vig = b.date_input("Vigente a contar del", value=date.today(), format="DD/MM/YYYY", key=f"{k}_v")
        st.markdown("**Marque lo que cambia:**")
        cambios = {}
        a, b = st.columns([1, 2])
        if a.checkbox("Sueldo base", key=f"{k}_csb"):
            cambios["sueldo_base"] = b.number_input("Nuevo sueldo base", min_value=0, value=int(cont["sueldo_base"] or 0),
                                                    step=10000, key=f"{k}_sb")
        a, b = st.columns([1, 2])
        if a.checkbox("Cargo", key=f"{k}_ccar"):
            cambios["cargo"] = b.text_input("Nuevo cargo", value=cont.get("cargo") or "", key=f"{k}_car").strip()
        a, b = st.columns([1, 2])
        jmax = C.jornada_maxima(date.today())
        if a.checkbox("Jornada / horario", key=f"{k}_cjor"):
            cambios["jornada_semanal"] = b.number_input(f"Nueva jornada semanal (máx. {jmax} h)", min_value=1, max_value=45,
                                                        value=min(int(cont.get("jornada_semanal") or jmax), jmax), key=f"{k}_jor")
            cambios["horario"] = b.text_input("Distribución / horario", value=cont.get("horario") or "", key=f"{k}_hor").strip()
        a, b = st.columns([1, 2])
        if a.checkbox("Colación", key=f"{k}_ccol"):
            cambios["colacion"] = b.number_input("Nueva colación", min_value=0, value=int(cont.get("colacion") or 0),
                                                 step=1000, key=f"{k}_col")
        a, b = st.columns([1, 2])
        if a.checkbox("Movilización", key=f"{k}_cmov"):
            cambios["movilizacion"] = b.number_input("Nueva movilización", min_value=0,
                                                     value=int(cont.get("movilizacion") or 0), step=1000, key=f"{k}_mov")
        a, b = st.columns([1, 2])
        if a.checkbox("Lugar de trabajo", key=f"{k}_clug"):
            cambios["lugar_trabajo"] = b.text_input("Nuevo lugar de trabajo", value=cont.get("lugar_trabajo") or "",
                                                    key=f"{k}_lug").strip()
        if cont.get("tipo_contrato") == "Plazo Fijo":
            a, b = st.columns([1, 2])
            if a.checkbox("Duración", key=f"{k}_cdur"):
                op = b.radio("Duración", ["Pasa a indefinido", "Prorrogar plazo fijo"], horizontal=True,
                             label_visibility="collapsed", key=f"{k}_dur")
                if op.startswith("Pasa"):
                    cambios["duracion"] = "indefinido"
                else:
                    cambios["duracion"] = b.date_input("Nueva fecha de término", value=None, format="DD/MM/YYYY",
                                                       key=f"{k}_ft")
        texto = st.text_area("Cláusula adicional (opcional)", key=f"{k}_txt",
                             placeholder="Ej.: Se pacta un bono de asistencia mensual de $30.000…")
        if texto.strip():
            cambios["texto_libre"] = texto.strip()
        aplicar = st.checkbox("Actualizar el contrato con estos cambios (las liquidaciones siguientes los usarán)",
                              value=True, key=f"{k}_apl")
        ind = db.get_indicadores(periodo_activo(), conn) or db.get_indicadores(periodo_default(), conn) or {}
        errores, avisos = AN.validar(cont, {kk: v for kk, v in cambios.items() if kk != "horario"},
                                     float(ind.get("renta_minima") or 0), AN.renovaciones(conn, cont["id"]))
        if cambios.get("duracion") is None and "duracion" in cambios:
            errores.append("Indique la nueva fecha de término.")
        mostrar_advertencias(avisos, "Atención")
        if st.button("Generar anexo", type="primary", key=f"{k}_btn"):
            if errores:
                st.error("\n".join(f"- {e}" for e in errores))
            else:
                trab = db.row(conn, "SELECT * FROM trabajadores WHERE id=?", (cont["trabajador_id"],))
                r = AN.crear_anexo(conn, emp, trab, cont, f_anexo, vig, cambios, EXPORTS_DIR,
                                   usuario=usuario_actual().get("usuario", ""), aplicar=aplicar)
                st.session_state["ult_anexo"] = r["ruta"]
                st.success(f"Anexo generado ({r['resumen']}) y guardado en el historial del trabajador."
                           + (" Contrato actualizado." if aplicar else ""))
        if st.session_state.get("ult_anexo"):
            descargar(Path(st.session_state["ult_anexo"]), "⬇️ Descargar anexo DOCX", "dl_anexo")
        anx = db.rows(conn, """SELECT a.fecha, a.vigencia, t.rut, t.nombres || ' ' || t.apellido_paterno AS trabajador,
                                      a.cambios FROM anexos_contrato a JOIN trabajadores t ON a.trabajador_id=t.id
                               WHERE a.empresa_id=? ORDER BY a.fecha DESC, a.id DESC""", (emp["id"],))
        if anx:
            st.markdown("**Anexos registrados**")
            st.dataframe(pd.DataFrame([{"Fecha": C.fecha_ddmmaaaa(x["fecha"]), "Vigencia": C.fecha_ddmmaaaa(x["vigencia"]),
                                        "RUT": x["rut"], "Trabajador": x["trabajador"],
                                        "Cambios": ", ".join(AN._resumen(json.loads(x["cambios"] or "{}")))} for x in anx]),
                         hide_index=True, width="stretch")


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
            per_pdf = input_periodo("Periodo a guardar", key="ind_pdf_per", sincronizar=False)
            if st.button("Guardar indicadores del PDF"):
                errs = C.validar_indicadores({**(db.get_indicadores(per_pdf, conn) or {}),
                                              **{k: v for k, v in res.items() if v}})
                if errs:
                    st.error("No se guardó. " + " ".join(errs) + " Corrija el dato en Edición manual.")
                    st.stop()
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
            errs = C.validar_indicadores(v)
            if errs:
                st.error("No se guardó. " + " ".join(errs))
                st.stop()
            db.guardar_indicadores(conn, per, v)
            conn.commit()
            st.success(f"Indicadores {per} guardados.")

    st.subheader("Indicadores cargados")
    for x in db.rows(conn, "SELECT periodo FROM indicadores ORDER BY periodo DESC"):
        e = C.validar_indicadores(db.get_indicadores(x["periodo"], conn) or {})
        if e:
            st.error(f"**{x['periodo']}:** " + " ".join(e) + " Corríjalo en Edición manual (arriba) y vuelva a calcular "
                     "las liquidaciones de ese mes.")
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
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
    periodo = input_periodo(key="liq_per")
    ind = db.get_indicadores(periodo, conn)
    if not ind:
        st.error(f"No hay indicadores para {periodo}. Cárguelos primero en **Indicadores**.")
        return
    if not ind.get("utm"):
        st.error("Los indicadores del periodo no tienen UTM: no se puede calcular el impuesto único.")
        return
    errs = C.validar_indicadores(ind)
    if errs:
        st.error(f"Los indicadores de {periodo} tienen un error y el cálculo saldría mal: " + " ".join(errs)
                 + " Corríjalos en **Indicadores → Edición manual** y vuelva a calcular las liquidaciones del mes.")
        return
    ref = K.tasas_reforma_ley_21735(periodo)
    def _cl(v, dec=0):
        return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    st.info(f"UF \\${_cl(ind['uf'], 2)} · UTM \\${_cl(ind['utm'])} · Tope AFP \\${_cl(ind['tope_afp'])} · "
            + ref["descripcion"].replace("$", "\\$"))
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
        A.guardar_archivo(conn, emp["id"], l["trabajador_id"], "Liquidación", ruta, periodo=periodo,
                          fecha=C.fin_de_mes(periodo), descripcion=f"Líquido ${C.fmt_clp(l['liquido'])}",
                          ref_tabla="liquidaciones", ref_id=l["id"], usuario=usuario_actual().get("usuario", ""),
                          reemplazar=True)
        conn.commit()
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
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
                vid = db.insert(conn, "vacaciones", dict(trabajador_id=topts[tsel], empresa_id=emp["id"], fecha_inicio=f_ini,
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
                A.guardar_archivo(conn, emp["id"], topts[tsel], "Comprobante de vacaciones", ruta, fecha=f_ini,
                                  descripcion=f"{dias_hab:g} días hábiles {tipo.lower()} · hasta {C.fecha_ddmmaaaa(f_fin)}",
                                  ref_tabla="vacaciones", ref_id=vid, usuario=usuario_actual().get("usuario", ""))
                conn.commit()
                st.session_state["ult_fer"] = str(ruta)
                st.success(f"Registrado: último día de vacaciones {C.fecha_ddmmaaaa(f_fin)} ({corridos:g} días corridos).")
    if st.session_state.get("ult_fer"):
        descargar(Path(st.session_state["ult_fer"]), "⬇️ Descargar comprobante", "dl_fer")
    st.dataframe(db.read_sql_df("""SELECT v.id, t.rut, t.nombres, t.apellido_paterno, v.fecha_inicio, v.fecha_termino,
                                   v.dias_habiles, v.dias_corridos, v.tipo FROM vacaciones v
                                   JOIN trabajadores t ON v.trabajador_id=t.id WHERE v.empresa_id=?
                                   ORDER BY v.fecha_inicio DESC""", conn, (emp["id"],)), width="stretch")




def pantalla_prestamos(conn):
    st.header("💰 Préstamos")
    st.caption("Préstamos internos de la empresa y descuentos CCAF. Se descuentan automáticamente "
               "en las liquidaciones según el período.")
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
    
    # ═══════════════════════════════════════════════════════════════
    # FORMULARIO NUEVO PRÉSTAMO
    # ═══════════════════════════════════════════════════════════════
    trabs = db.rows(conn, "SELECT id, rut, nombres, apellido_paterno FROM trabajadores "
                          "WHERE empresa_id=? AND activo=1 ORDER BY apellido_paterno, nombres",
                    (emp["id"],))
    topts = {f"{t['rut']} — {t['nombres']} {t['apellido_paterno']}": t["id"] for t in trabs}
    
    with st.expander("➕ Nuevo préstamo", expanded=False):
        if not topts:
            st.warning("No hay trabajadores activos en esta empresa.")
        else:
            with st.form("nuevo_prestamo"):
                tsel = st.selectbox("Trabajador *", list(topts), key="np_trab")
                c1, c2 = st.columns(2)
                tipo = c1.selectbox("Tipo de préstamo", ["Empresa", "CCAF"], key="np_tipo")
                descripcion = c2.text_input("Descripción", placeholder="Ej: Préstamo personal, Crédito dental",
                                             key="np_desc")
                
                c1, c2, c3 = st.columns(3)
                if tipo == "Empresa":
                    monto_total = c1.number_input("Monto total *", min_value=0, step=10000,
                                                   value=0, key="np_monto")
                    num_cuotas = c2.number_input("Número de cuotas *", min_value=1, max_value=120,
                                                  value=12, step=1, key="np_cuotas")
                    cuota_auto = round(monto_total / num_cuotas) if num_cuotas > 0 and monto_total > 0 else 0
                    cuota_mensual = cuota_auto
                    c3.metric("Cuota mensual (calculada)", f"${cuota_auto:,.0f}")
                else:  # CCAF
                    monto_total = None
                    cuota_mensual = c1.number_input("Cuota mensual *", min_value=0, step=1000,
                                                     value=0, key="np_cuota_ccaf")
                    num_cuotas = c2.number_input("Número de cuotas *", min_value=1, max_value=120,
                                                  value=12, step=1, key="np_cuotas_ccaf")
                    c3.caption(f"Total: ${cuota_mensual * num_cuotas:,.0f}")
                
                c1, c2 = st.columns(2)
                anio = c1.number_input("Año de inicio *", min_value=2020, max_value=2100,
                                        value=date.today().year, step=1, key="np_anio")
                mes = c2.selectbox("Mes de inicio *",
                                    list(range(1, 13)),
                                    index=date.today().month - 1,
                                    format_func=lambda m: f"{m:02d}",
                                    key="np_mes")
                fecha_inicio = f"{anio:04d}-{mes:02d}"
                
                st.caption(f"📅 Primera cuota: **{fecha_inicio}** — se generarán {num_cuotas} cuotas automáticamente.")
                
                if st.form_submit_button("💾 Crear préstamo", type="primary"):
                    errores = []
                    if not descripcion.strip():
                        errores.append("Falta descripción.")
                    if tipo == "Empresa" and (not monto_total or monto_total <= 0):
                        errores.append("Monto total debe ser > 0.")
                    if not cuota_mensual or cuota_mensual <= 0:
                        errores.append("Cuota mensual debe ser > 0.")
                    
                    if errores:
                        for e in errores:
                            st.error(e)
                    else:
                        try:
                            pid = PR.crear_prestamo(
                                conn, emp["id"], topts[tsel], tipo, descripcion.strip(),
                                monto_total, cuota_mensual, num_cuotas, fecha_inicio
                            )
                            st.success(f"✓ Préstamo creado (id={pid}). {num_cuotas} cuotas generadas desde {fecha_inicio}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al crear: {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # LISTA DE PRÉSTAMOS
    # ═══════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("Préstamos registrados")
    
    # Filtros
    c1, c2 = st.columns([2, 3])
    filtro_estado = c1.selectbox("Filtrar", ["Solo activos", "Todos", "Solo finalizados"], key="prest_filtro")
    buscar = c2.text_input("🔍 Buscar (RUT o nombre)", key="prest_buscar").strip().upper()
    
    prestamos = PR.listar_prestamos(conn, emp["id"], solo_activos=(filtro_estado == "Solo activos"))
    if filtro_estado == "Solo finalizados":
        prestamos = [p for p in prestamos if not p.get("activo")]
    
    # Filtrar por búsqueda
    if buscar:
        prestamos = [p for p in prestamos
                     if buscar in (p.get("rut") or "").upper()
                     or buscar in (f"{p.get('nombres', '')} {p.get('apellido_paterno', '')}").upper()]
    
    st.caption(f"Mostrando {len(prestamos)} préstamo(s).")
    
    if not prestamos:
        st.info("No hay préstamos con los filtros actuales. Usa **+ Nuevo préstamo** para agregar uno.")
        return
    
    # Tarjetas
    for p in prestamos:
        nombre_completo = f"{p.get('nombres', '')} {p.get('apellido_paterno', '')} {p.get('apellido_materno', '')}".strip()
        tipo = p.get("tipo", "")
        estado_badge = "✅ Activo" if p.get("activo") else "🔒 Finalizado"
        cuota_act = int(p.get("cuota_actual") or 1)
        num_cuotas = int(p.get("num_cuotas") or 0)
        saldo = p.get("saldo_pendiente")
        
        # Resumen para la cabecera
        resumen = f"Cuota {cuota_act}/{num_cuotas}"
        if saldo is not None:
            resumen += f" · Saldo: ${saldo:,.0f}"
        resumen += f" · {estado_badge}"
        
        titulo = f"**{nombre_completo}** · RUT {p.get('rut', '')} · {tipo} — {resumen}"
        
        with st.expander(titulo, expanded=False):
            # Info
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tipo", tipo)
            c2.metric("Cuota mensual", f"${float(p.get('cuota_mensual') or 0):,.0f}")
            c3.metric("Cuota actual", f"{cuota_act} / {num_cuotas}")
            if saldo is not None:
                c4.metric("Saldo pendiente", f"${float(saldo):,.0f}")
            else:
                c4.metric("Progreso", f"{cuota_act}/{num_cuotas}")
            
            if p.get("descripcion"):
                st.caption(f"📝 {p['descripcion']}")
            if p.get("fecha_otorgado"):
                st.caption(f"📅 Otorgado: {p['fecha_otorgado']} · Inicio: {p['fecha_inicio']}")
            
            # Cuotas del préstamo
            st.markdown("##### Cuotas")
            cuotas = db.rows(conn, """SELECT * FROM prestamos_cuotas 
                                       WHERE prestamo_id = ? ORDER BY numero_cuota""",
                             (p["id"],))
            if cuotas:
                df_cuotas = pd.DataFrame([{
                    "#": c["numero_cuota"],
                    "Período": c["periodo"],
                    "Monto": f"${float(c['monto']):,.0f}",
                    "Estado": c["estado"],
                    "Fecha pago": str(c["fecha_pago"] or ""),
                } for c in cuotas])
                st.dataframe(df_cuotas, hide_index=True, width="stretch")
                
                # Botones de acción sobre cuotas pendientes
                pendientes = [c for c in cuotas if c["estado"] == "pendiente"]
                if pendientes:
                    st.markdown("**Próximas cuotas pendientes:**")
                    for c in pendientes[:3]:
                        cc1, cc2, cc3 = st.columns([3, 1, 1])
                        cc1.write(f"Cuota {c['numero_cuota']}/{num_cuotas} · {c['periodo']} · ${float(c['monto']):,.0f}")
                        if cc2.button("⏩ Aplazar al final", key=f"apl_{c['id']}"):
                            ok = PR.aplazar_cuota_al_final(conn, c["id"])
                            if ok:
                                st.success(f"Cuota {c['numero_cuota']} aplazada al final.")
                            else:
                                st.warning("No se pudo aplazar.")
                            st.rerun()
                        if cc3.button("✅ Marcar pagada", key=f"pag_{c['id']}"):
                            PR.marcar_cuota_pagada(conn, c["id"])
                            st.success(f"Cuota {c['numero_cuota']} marcada como pagada (solo referencia).")
                            st.rerun()
            else:
                st.warning("Sin cuotas generadas (¿préstamo antiguo?).")


def pantalla_finiquitos(conn):
    st.header("Finiquitos")
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
                A.guardar_archivo(conn, emp["id"], trab["id"], "Finiquito", ruta, fecha=r["fecha_termino"],
                                  descripcion=f"{r['causal']} · total ${C.fmt_clp(r['total_finiquito'])}",
                                  ref_tabla="finiquitos", ref_id=fid, usuario=usuario_actual().get("usuario", ""))
                conn.commit()
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
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
    emp = empresa_activa(conn)
    if not emp:
        st.warning("Seleccione una empresa en el menu lateral.")
        return
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
        v = S.fecha_vencimiento(u)
        u["vence"] = C.fecha_ddmmaaaa(v) if v else "sin plazo"
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
                venc = S.fecha_vencimiento(x)
                st.caption(f"Vencimiento actual: {C.fecha_ddmmaaaa(venc) if venc else 'sin plazo'}")
                prorroga = st.number_input("Prorrogar (días adicionales)", 0, 3650, 0,
                                           help="Suma días al vencimiento actual (o desde hoy si ya venció).")
                reiniciar = st.checkbox("Reiniciar plazo (cuenta desde el próximo acceso)")
                fexp = st.date_input("Nueva fecha de expiración (opcional)", value=None)
                sin_plazo = st.checkbox("Quitar plazo (acceso permanente)")
                if st.form_submit_button("Guardar"):
                    campos = dict(activo=int(activo), empresas="*" if todas else sel, modulos=mods)
                    if nueva:
                        campos["clave"] = nueva
                    if reiniciar:
                        campos["primer_acceso"] = None
                    if fexp:
                        campos["fecha_expira"] = fexp
                    if prorroga:
                        base = max(date.today(), venc or date.today())
                        campos["fecha_expira"] = base + timedelta(days=int(prorroga))
                    if sin_plazo:
                        campos.update(fecha_expira=None, dias_acceso=None)
                    try:
                        if x["id"] == usuario_actual().get("id") and not activo:
                            raise ValueError("No puede desactivar su propio usuario.")
                        S.actualizar_usuario(x["id"], **campos)
                        st.success("Usuario actualizado.")
                        st.rerun()
                    except Exception as ex:
                        st.error(str(ex))

    with st.expander("📞 Datos de contacto para ayuda"):
        st.caption("Se muestran en la pantalla de ingreso, en el menú lateral y en Ayuda, para todos los usuarios. "
                   "Deje vacío lo que no quiera mostrar.")
        actual = leer_contacto()
        with st.form("contacto"):
            a, b = st.columns(2)
            nuevos = {k: (a if i % 2 == 0 else b).text_input(lab, value=actual.get(k, ""), key=f"ct_{k}")
                      for i, (k, lab) in enumerate(CONTACTO_CAMPOS)}
            if st.form_submit_button("Guardar contacto"):
                for k, v in nuevos.items():
                    db.upsert(conn, "configuracion", {"clave": k, "valor": v.strip()}, ["clave"])
                conn.commit()
                st.success("Datos de contacto guardados.")
                st.rerun()


def pantalla_calculadora(conn):
    st.header("Calculadora de sueldo")
    st.caption("Simula un sueldo sin guardar nada. Usa el mismo cálculo de las liquidaciones: topes, gratificación, "
               "impuesto único, seguro de cesantía y Ley 21.735.")
    per = periodo_activo()
    ind = db.get_indicadores(per, conn)
    if not ind:
        ult = db.scalar(conn, "SELECT MAX(periodo) AS p FROM indicadores")
        if not ult:
            st.error("No hay indicadores cargados. Cárguelos en **Indicadores** para usar la calculadora.")
            return
        per, ind = ult, db.get_indicadores(ult, conn)
        st.warning(f"No hay indicadores de {nombre_mes(periodo_activo())}; se usan los de {nombre_mes(per)}.")
    errs = C.validar_indicadores(ind)
    if errs:
        st.error(f"Los indicadores de {nombre_mes(per)} tienen un error: " + " ".join(errs)
                 + " Corríjalos en **Indicadores** para usar la calculadora.")
        return
    uf_txt = f"{float(ind.get('uf') or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    st.info(f"Indicadores de **{nombre_mes(per)}** · UF \\${uf_txt} · UTM \\${C.fmt_clp(ind.get('utm'))} · "
            f"Ingreso mínimo \\${C.fmt_clp(ind.get('renta_minima'))}")

    modo = st.radio("¿Qué quiere calcular?", ["Sueldo base → líquido", "Líquido deseado → sueldo base"], horizontal=True)
    a, b, c = st.columns(3)
    if modo.startswith("Sueldo"):
        monto = a.number_input("Sueldo base mensual ($)", min_value=0, value=int(ind.get("renta_minima") or 539000),
                               step=10000, key="calc_base")
    else:
        monto = a.number_input("Líquido deseado ($)", min_value=0, value=800000, step=10000, key="calc_liq",
                               help="Lo que el trabajador recibe a mano, incluida colación y movilización.")
    tg = b.selectbox("Gratificación", C.TIPOS_GRATIFICACION, key="calc_tg")
    gfija = c.number_input("Gratificación fija ($)", min_value=0, value=0, step=1000, key="calc_gf",
                           disabled=not tg.startswith("Monto"))
    col = a.number_input("Colación ($, no imponible)", min_value=0, value=0, step=1000, key="calc_col")
    mov = b.number_input("Movilización ($, no imponible)", min_value=0, value=0, step=1000, key="calc_mov")
    bono = c.number_input("Bono imponible mensual ($)", min_value=0, value=0, step=1000, key="calc_bono")
    afp = a.selectbox("AFP", C.AFPS, index=C.AFPS.index("Habitat"), key="calc_afp")
    salud = b.selectbox("Salud", ["FONASA", "ISAPRE"], key="calc_salud")
    plan = c.number_input("Plan Isapre (UF)", min_value=0.0, value=0.0, step=0.1, format="%.2f", key="calc_plan",
                          disabled=salud != "ISAPRE")
    tipo = a.selectbox("Tipo de contrato", C.TIPOS_CONTRATO, key="calc_tipo")
    jmax = C.jornada_maxima(C.fin_de_mes(per))
    jornada = b.number_input("Jornada semanal (h)", min_value=1, max_value=jmax, value=jmax, key="calc_jor")
    he = c.number_input("Horas extra 50% en el mes", min_value=0.0, value=0.0, step=1.0, key="calc_he")
    with st.expander("Más opciones"):
        d, e, f = st.columns(3)
        cargas = d.number_input("Cargas familiares", min_value=0, value=0, key="calc_cargas")
        tramo = e.selectbox("Tramo asignación familiar", ["A", "B", "C", "D"], index=3, key="calc_tramo")
        mutual = f.number_input("Tasa mutual %", min_value=0.0, value=0.93, step=0.01, key="calc_mut")
        ccaf = d.checkbox("Empresa afiliada a CCAF", key="calc_ccaf")
        pens = e.checkbox("Pensionado", key="calc_pens")

    params = dict(tipo_gratificacion=tg, gratificacion_fija=gfija, colacion=col, movilizacion=mov, bono_imponible=bono,
                  horas_extra_50=he, jornada=int(jornada), afp=afp, salud=salud, plan_isapre_uf=plan, tipo_contrato=tipo,
                  numero_cargas=int(cargas), tramo_af=tramo, pensionado=pens, tasa_mutual=mutual, afiliado_ccaf=ccaf)
    try:
        r = CALC.simular(ind, per, monto, **params) if modo.startswith("Sueldo") else \
            CALC.sueldo_para_liquido(monto, ind, per, **params)
    except ValueError as ex:
        st.error(str(ex))
        return

    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    m1.metric("Sueldo base", f"${C.fmt_clp(r['sueldo_base'])}")
    m2.metric("Sueldo líquido", f"${C.fmt_clp(r['liquido'])}")
    m3.metric("Costo empresa", f"${C.fmt_clp(r['costo_empresa'])}")

    hab = [("Sueldo base", r["sueldo_calculado"]), ("Gratificación", r["gratificacion"]),
           ("Horas extra", r["monto_horas_extras"]), ("Bono imponible", r["bonos_imponibles"]),
           ("Total imponible", r["total_imponible"]), ("Colación", r["colacion"]), ("Movilización", r["movilizacion"]),
           ("Asignación familiar", r["asignacion_familiar"]), ("TOTAL HABERES", r["total_haberes"])]
    tasa_afp = float((ind.get("afp_tasas") or C.AFP_TASAS_DEFAULT).get(afp, 0) or 0)
    des = [(f"AFP {afp} ({tasa_afp:.2f}%)".replace(".", ","), r["afp_monto"]), ("Salud 7%", r["salud_monto"]),
           ("Adicional Isapre", r["adicional_isapre"]), ("Seguro de cesantía", r["afc_trabajador"]),
           ("Impuesto único", r["impuesto_unico"]), ("TOTAL DESCUENTOS", r["total_descuentos"]),
           ("LÍQUIDO A PAGAR", r["liquido"])]
    crp_lbl = "Expectativa de vida" if r.get("reforma_etapa") == "1pct" else "Rentabilidad protegida"
    emp = [("Cesantía empleador", r["afc_empleador"]), ("SIS", r["sis_monto"]),
           ("Cuenta individual", r["reforma_afp_emp"]), (crp_lbl, r["reforma_crp"]),
           ("Seguro Social", r["reforma_seguro_social"]), ("Mutual", r["mutual_monto"]),
           ("TOTAL APORTES", r["carga_empleador_previsional"]), ("COSTO EMPRESA", r["costo_empresa"])]

    def _tabla(filas):
        return pd.DataFrame([(n, f"${C.fmt_clp(v)}") for n, v in filas if v or n.startswith(("TOTAL", "LÍQUIDO", "COSTO"))], columns=["Concepto", "Monto"])
    cfg = {"Concepto": st.column_config.TextColumn(width="medium"), "Monto": st.column_config.TextColumn(width="small")}
    t1, t2, t3 = st.columns(3)
    t1.markdown("**Haberes**")
    t1.dataframe(_tabla(hab), hide_index=True, width="stretch", column_config=cfg)
    t2.markdown("**Descuentos del trabajador**")
    t2.dataframe(_tabla(des), hide_index=True, width="stretch", column_config=cfg)
    t3.markdown("**Aportes del empleador**")
    t3.dataframe(_tabla(emp), hide_index=True, width="stretch", column_config=cfg)
    st.caption(f"Base tributable \\${C.fmt_clp(r['base_tributable'])} · {r['reforma_descripcion']}. "
               "Cuenta individual, rentabilidad protegida y Seguro Social corresponden a la Ley 21.735. "
               "Simulación referencial para un mes completo (30 días)."
               + ("" if modo.startswith("Sueldo") else " En el cálculo inverso el líquido puede quedar uno o dos pesos "
                  "sobre lo pedido, por el redondeo de las cotizaciones."))
    mostrar_advertencias(r["advertencias"], "Observaciones")


def pantalla_ayuda(_conn):
    st.header("Ayuda")
    ct = texto_contacto(leer_contacto())
    if ct:
        st.info("**¿Dudas o problemas? Contáctenos:**  \n" + ct)
    st.markdown(f"""
**Versión 2.3** — ver `CAMBIOS.md`.

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

    # ─── Detectar token de recuperacion en URL ───
    qp = st.query_params
    reset_token = qp.get("reset_token")
    if reset_token:
        pantalla_reset_clave(reset_token)
        return

    # ─── Pantalla de recuperar contrasena (activada por boton) ───
    print("[DEBUG] RESEND_API_KEY leido:", "SI" if __import__("remu.email_utils", fromlist=["_api_key"])._api_key() else "NO")
    if st.session_state.get("_ir_recuperar") and not st.session_state.get("usuario"):
        pantalla_recuperar_clave()
        return

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

    # FASE 1: inicializar empresa y periodo desde DB del usuario
    if "empresa_activa_id" not in st.session_state and u.get("ultima_empresa_id"):
        st.session_state["empresa_activa_id"] = u["ultima_empresa_id"]
    if "periodo_activo" not in st.session_state and u.get("ultimo_periodo"):
        if periodo_valido(u["ultimo_periodo"]):
            st.session_state["periodo_activo"] = u["ultimo_periodo"]

    # Renderizar tarjetas destacadas (usuario, empresa activa, mes activo)
    _conn_header = db.get_conn()
    try:
        _sidebar_header(_conn_header)
    finally:
        _conn_header.close()

    # Persistir periodo si cambio
    if st.session_state.get("_periodo_persistido") != periodo_activo():
        _guardar_preferencia_usuario(periodo=periodo_activo())
        st.session_state["_periodo_persistido"] = periodo_activo()

    mods = modulos()
    ctx = {"selector_empresa": selector_empresa, "empresa_activa": empresa_activa, "input_periodo": input_periodo, "usuario": usuario_actual,
           "modulos": modulos, "advertencias": mostrar_advertencias}
    pantallas = {"🏠 Dashboard": pantalla_dashboard}
    if "remuneraciones" in mods:
        pantallas["🏢 Empresas"] = pantalla_empresas
    pantallas["👤 Ficha del Personal"] = pantalla_trabajadores
    if "rrhh" in mods or "remuneraciones" in mods:
        pantallas["🗓 Movimientos del mes"] = lambda c: ui_rrhh.pantalla_movimientos(c, ctx)
        pantallas["🧩 Conceptos adicionales"] = lambda c: ui_rrhh.pantalla_conceptos(c, ctx)
    if "remuneraciones" in mods:
        pantallas.update({
            "📄 Contratos": pantalla_contratos, "📊 Indicadores": pantalla_indicadores,
            "💰 Liquidaciones": pantalla_liquidaciones, "📒 Libro de Remuneraciones": pantalla_libro,
            "🏖️ Vacaciones": pantalla_vacaciones, "💰 Préstamos": pantalla_prestamos,
            "📑 Finiquitos": pantalla_finiquitos,
            "📤 Archivo Previred": pantalla_previred, "📋 DJ 1887": pantalla_1887})
    pantallas["🧮 Calculadora de sueldo"] = pantalla_calculadora
    pantallas["ℹ️ Ayuda"] = pantalla_ayuda
    if es_admin():
        pantallas["🔐 Usuarios"] = pantalla_usuarios
    # ─── Menu acordeon por grupos ───
    GRUPOS = [
        ("🏠 Principal",       ["🏠 Dashboard"]),
        ("👥 RRHH",            ["👤 Ficha del Personal", "🗓 Movimientos del mes",
                                "🧩 Conceptos adicionales", "🏖️ Vacaciones"]),
        ("💰 Remuneraciones",  ["📄 Contratos", "📊 Indicadores", "💰 Liquidaciones",
                                "📒 Libro de Remuneraciones", "💰 Préstamos", "📑 Finiquitos"]),
        ("🧾 Impuestos",       ["📤 Archivo Previred", "📋 DJ 1887"]),
        ("⚙️ Herramientas",    ["🧮 Calculadora de sueldo", "ℹ️ Ayuda"]),
        ("🔐 Administración",  ["🏢 Empresas", "🔐 Usuarios"]),
    ]

    # Inicializar pantalla actual
    if "pantalla_actual" not in st.session_state:
        st.session_state["pantalla_actual"] = list(pantallas)[0]
    # Si la pantalla actual ya no existe (por permisos), ir al primero
    if st.session_state["pantalla_actual"] not in pantallas:
        st.session_state["pantalla_actual"] = list(pantallas)[0]

    # Renderizar acordeon
    for grupo, items in GRUPOS:
        items_ok = [i for i in items if i in pantallas]
        if not items_ok:
            continue
        activo_aqui = st.session_state["pantalla_actual"] in items_ok
        with st.sidebar.expander(grupo, expanded=activo_aqui):
            for item in items_ok:
                if item == st.session_state["pantalla_actual"]:
                    # Item activo — texto destacado
                    st.markdown(f'<div class="menu-item-activo">{item}</div>',
                                unsafe_allow_html=True)
                else:
                    # Item clickeable — boton
                    if st.button(item, key=f"nav_{item}", use_container_width=True):
                        st.session_state["pantalla_actual"] = item
                        st.rerun()

    if st.sidebar.button("Cerrar sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    menu = st.session_state["pantalla_actual"]
    ct = texto_contacto(leer_contacto())
    if ct:
        st.sidebar.markdown("---\n**Ayuda y soporte**  \n" + ct)

    insignia_mes_activo()
    st.title("BASECON · Remuneraciones" if "remuneraciones" in mods else "BASECON · Movimientos RRHH")
    conn = db.get_conn()
    try:
        pantallas[menu](conn)
    finally:
        conn.close()


main()
