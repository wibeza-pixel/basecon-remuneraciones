"""Envio de emails via Resend."""
from __future__ import annotations
import os
from typing import Optional


def _api_key() -> Optional[str]:
    try:
        import streamlit as st
        key = st.secrets.get("RESEND_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("RESEND_API_KEY")


def _from_email() -> str:
    try:
        import streamlit as st
        e = st.secrets.get("FROM_EMAIL")
        if e:
            return e
    except Exception:
        pass
    return os.environ.get("FROM_EMAIL", "onboarding@resend.dev")


def _app_url() -> str:
    try:
        import streamlit as st
        u = st.secrets.get("APP_URL")
        if u:
            return u
    except Exception:
        pass
    return os.environ.get("APP_URL", "http://localhost:8501")


def _set_debug(key: str, value: str) -> None:
    try:
        import streamlit as st
        st.session_state[key] = value
    except Exception:
        pass


def enviar_email_recuperacion(destinatario: str, usuario: str, token: str) -> bool:
    """Envia email con link para recuperar contrasena."""
    #_set_debug("_resend_debug_0", "inicio")

    api_key = _api_key()
    if not api_key:
        #_set_debug("_email_error", "RESEND_API_KEY vacio")
        return False

    #_set_debug("_resend_debug_1", "llegue antes de resend.api_key")

    try:
        import resend
    except ImportError:
        #_set_debug("_email_error", "resend no instalado")
        return False

    try:
        resend.api_key = api_key
        #_set_debug("_resend_debug_2", "API key seteado OK")
    except Exception as e:
        #_set_debug("_email_error", "ERROR api_key: " + str(e))
        return False

    #_set_debug("_resend_debug_3", "construyendo html")

    link = _app_url() + "/?reset_token=" + token

    html = (
        '<div style="font-family: sans-serif; max-width: 520px; margin: 0 auto; padding: 2rem;">'
        '<h1>BASECON</h1>'
        '<p>Hola ' + usuario + ',</p>'
        '<p>Haz clic para restablecer tu contrasena:</p>'
        '<p><a href="' + link + '">Restablecer contrasena</a></p>'
        '<p>O copia este link: ' + link + '</p>'
        '</div>'
    )

    #_set_debug("_resend_debug_4", "antes de resend.Emails.send")

    try:
        params = {
            "from": _from_email(),
            "to": [destinatario],
            "subject": "Recuperar contrasena - BASECON",
            "html": html,
        }
        r = resend.Emails.send(params)
        #_set_debug("_resend_response", repr(r))
        return True
    except Exception as e:
        #_set_debug("_email_error", "ERROR en send: " + str(e))
        #_set_debug("_resend_debug_4", "EXCEPCION: " + str(e))
        return False