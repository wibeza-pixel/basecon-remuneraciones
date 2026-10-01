"""
Usuarios, contraseñas y licencia de demostración.

- Contraseñas con PBKDF2-HMAC-SHA256 (200.000 iteraciones) y sal por usuario; comparación en tiempo constante.
- Sin claves por defecto: en la primera ejecución se crea el administrador desde la pantalla de configuración.
- Cada usuario ve solo las empresas asignadas ("*" = todas). Rol admin administra usuarios.
- Plazo de acceso por usuario (fecha fija o N días desde el primer acceso). Se registra la última fecha
  de acceso para detectar si el reloj del equipo se retrocede.
- Si existe la variable BASECON_SECRET (secrets de Streamlit o entorno), los datos de licencia se firman
  con HMAC y cualquier edición manual de la base los invalida.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import date, timedelta

from . import config as C
from . import db

ITER = 200_000


def _secret() -> str | None:
    s = os.environ.get("BASECON_SECRET")
    if not s:
        try:
            import streamlit as st
            s = st.secrets.get("BASECON_SECRET")
        except Exception:
            s = None
    return s or None


def hash_clave(clave: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", (clave or "").encode(), bytes.fromhex(salt), ITER).hex()
    return h, salt


def validar_clave_nueva(clave: str) -> str | None:
    if len(clave or "") < 8:
        return "La clave debe tener al menos 8 caracteres."
    if clave.isdigit() or clave.isalpha():
        return "La clave debe combinar letras y números."
    return None


def _firma(u: dict) -> str:
    s = _secret()
    if not s:
        return ""
    payload = json.dumps([u.get("usuario"), u.get("rol"), u.get("empresas"), u.get("modulos"), str(u.get("fecha_expira") or ""),
                          u.get("dias_acceso"), str(u.get("primer_acceso") or "")], sort_keys=True)
    return hmac.new(s.encode(), payload.encode(), hashlib.sha256).hexdigest()


def hay_usuarios() -> bool:
    conn = db.get_conn()
    try:
        return int(db.scalar(conn, "SELECT COUNT(*) AS n FROM usuarios") or 0) > 0
    finally:
        conn.close()


def _guardar_firma(conn, uid: int):
    u = db.row(conn, "SELECT * FROM usuarios WHERE id=?", (uid,))
    db.upsert(conn, "configuracion", {"clave": f"firma_usuario_{uid}", "valor": _firma(u)}, ["clave"])


def crear_usuario(usuario: str, clave: str, nombre: str = "", rol: str = "usuario", empresas="*",
                  fecha_expira=None, dias_acceso=None, modulos=("remuneraciones",)) -> int:
    err = validar_clave_nueva(clave)
    if err:
        raise ValueError(err)
    h, s = hash_clave(clave)
    emp = empresas if isinstance(empresas, str) else json.dumps(list(empresas))
    conn = db.get_conn()
    try:
        uid = db.insert(conn, "usuarios", dict(usuario=usuario.strip().lower(), nombre=nombre, hash=h, salt=s,
                                               rol=rol, empresas=emp, activo=1,
                                               modulos=json.dumps(list(modulos or [])),
                                               fecha_expira=C.a_fecha(fecha_expira), dias_acceso=dias_acceso))
        _guardar_firma(conn, uid)
        conn.commit()
        return uid
    finally:
        conn.close()


def actualizar_usuario(uid: int, **campos):
    conn = db.get_conn()
    try:
        if "clave" in campos:
            clave = campos.pop("clave")
            if clave:
                err = validar_clave_nueva(clave)
                if err:
                    raise ValueError(err)
                campos["hash"], campos["salt"] = hash_clave(clave)
        if "modulos" in campos and not isinstance(campos["modulos"], str):
            campos["modulos"] = json.dumps(list(campos["modulos"]))
        if "empresas" in campos and not isinstance(campos["empresas"], str):
            campos["empresas"] = json.dumps(list(campos["empresas"]))
        if campos:
            sets = ", ".join(f"{k}=?" for k in campos)
            conn.execute(f"UPDATE usuarios SET {sets} WHERE id=?", [*campos.values(), uid])
        _guardar_firma(conn, uid)
        conn.commit()
    finally:
        conn.close()


def fecha_vencimiento(u: dict) -> date | None:
    """Fecha de término del acceso (None = sin plazo). Si el plazo es en días y aún no entra, cuenta desde hoy."""
    if u.get("fecha_expira"):
        return C.a_fecha(u["fecha_expira"])
    if u.get("dias_acceso"):
        inicio = C.a_fecha(u.get("primer_acceso")) or date.today()
        return inicio + timedelta(days=int(u["dias_acceso"]))
    return None


def dias_restantes(u: dict, hoy: date | None = None) -> int | None:
    hoy = hoy or date.today()
    if u.get("fecha_expira"):
        return (C.a_fecha(u["fecha_expira"]) - hoy).days
    if u.get("dias_acceso") and u.get("primer_acceso"):
        return (C.a_fecha(u["primer_acceso"]) + timedelta(days=int(u["dias_acceso"])) - hoy).days
    if u.get("dias_acceso"):
        return int(u["dias_acceso"])
    return None


def autenticar(usuario: str, clave: str) -> tuple[dict | None, str]:
    """Devuelve (usuario, '') si es válido o (None, motivo)."""
    conn = db.get_conn()
    try:
        u = db.row(conn, "SELECT * FROM usuarios WHERE usuario=?", ((usuario or "").strip().lower(),))
        if not u or not u.get("activo"):
            hash_clave(clave or "", "00" * 16)  # tiempo similar aunque no exista
            return None, "Usuario o clave incorrectos."
        h, _ = hash_clave(clave or "", u["salt"])
        if not hmac.compare_digest(h, u["hash"]):
            return None, "Usuario o clave incorrectos."
        if _secret():
            f = db.scalar(conn, "SELECT valor FROM configuracion WHERE clave=?", (f"firma_usuario_{u['id']}",))
            if not f or not hmac.compare_digest(f, _firma(u)):
                return None, "Los datos de acceso de este usuario fueron modificados fuera de la aplicación."
        hoy = date.today()
        ult = C.a_fecha(u.get("ultimo_acceso"))
        if ult and hoy < ult - timedelta(days=1) and u["rol"] != "admin":
            return None, "La fecha del equipo es anterior al último acceso registrado. Corrija la fecha del sistema."
        if not u.get("primer_acceso"):
            conn.execute("UPDATE usuarios SET primer_acceso=? WHERE id=?", (hoy, u["id"]))
            u["primer_acceso"] = hoy
            _guardar_firma(conn, u["id"])
        dr = dias_restantes(u, hoy)
        if dr is not None and dr < 0 and u["rol"] != "admin":
            conn.commit()
            return None, "El periodo de acceso ha finalizado. Contacte al administrador."
        conn.execute("UPDATE usuarios SET ultimo_acceso=? WHERE id=?", (max(hoy, ult or hoy), u["id"]))
        conn.commit()
        u["dias_restantes"] = dr
        return u, ""
    finally:
        conn.close()


def empresas_permitidas(u: dict) -> set[int] | None:
    """None = todas."""
    if not u:
        return set()
    if u.get("rol") == "admin":
        return None
    e = u.get("empresas") or "[]"
    if e == "*":
        return None
    try:
        return {int(x) for x in json.loads(e)}
    except Exception:
        return set()


def modulos_usuario(u: dict) -> set[str]:
    """Módulos habilitados: 'rrhh' (movimientos del mes) y/o 'remuneraciones'. El administrador tiene todos."""
    if not u:
        return set()
    if u.get("rol") == "admin":
        return set(C.MODULOS)
    try:
        return {m for m in json.loads(u.get("modulos") or '["remuneraciones"]') if m in C.MODULOS}
    except Exception:
        return {"remuneraciones"}


def en_la_nube_sin_bd_persistente() -> bool:
    """Streamlit Community Cloud monta la app en /mount/src y su disco se borra al reiniciar."""
    en_cloud = str(C.BASE_DIR).startswith("/mount/src") or bool(os.environ.get("STREAMLIT_SHARING_MODE")) \
        or os.environ.get("HOSTNAME", "").startswith("streamlit")
    return en_cloud and not db.is_postgres()
