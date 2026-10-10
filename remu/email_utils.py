"""Envio de emails via Resend (recuperar contrasena, notificaciones)."""
from __future__ import annotations

import os
from typing import Optional


def _api_key() -> Optional[str]:
    """Lee el API key de Resend desde secrets o variables de entorno."""
    try:
        import streamlit as st
        key = st.secrets.get("RESEND_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("RESEND_API_KEY")


def _from_email() -> str:
    """Devuelve el remitente."""
    try:
        import streamlit as st
        e = st.secrets.get("FROM_EMAIL")
        if e:
            return e
    except Exception:
        pass
    return os.environ.get("FROM_EMAIL", "onboarding@resend.dev")


def _app_url() -> str:
    """URL base de la app (para los links de recuperacion)."""
    try:
        import streamlit as st
        u = st.secrets.get("APP_URL")
        if u:
            return u
    except Exception:
        pass
    return os.environ.get("APP_URL", "http://localhost:8501")


def enviar_email_recuperacion(destinatario: str, usuario: str, token: str) -> bool:
    """Envia email con link para recuperar contrasena."""
    api_key = _api_key()
    if not api_key:
        print("[email] ERROR: RESEND_API_KEY no configurado")
        return False

    try:
        import resend
    except ImportError:
        print("[email] ERROR: resend no instalado")
        return False

    resend.api_key = api_key
    link = _app_url() + "/?reset_token=" + token

    html = (
        '<div style="font-family: -apple-system, sans-serif; max-width: 520px; '
        'margin: 0 auto; padding: 2rem; background: #f5f7fb;">'
        '<div style="background: #ffffff; border-radius: 14px; padding: 2rem; '
        'box-shadow: 0 4px 12px rgba(11,31,58,0.08);">'
        '<div style="text-align: center; margin-bottom: 1.5rem;">'
        '<h1 style="color: #0b1f3a; font-size: 1.6rem; margin: 0;">BASECON</h1>'
        '<p style="color: #5a6b85; font-size: 0.9rem; margin: 0.3rem 0 0 0;">'
        'Recuperar contrasena</p></div>'
        '<hr style="border: none; border-top: 1px solid #e3e8f0; margin: 1.5rem 0;">'
        '<p style="color: #1a1a1a; font-size: 1rem; line-height: 1.6;">'
        'Hola <strong>' + usuario + '</strong>,</p>'
        '<p style="color: #1a1a1a; font-size: 1rem; line-height: 1.6;">'
        'Recibimos una solicitud para restablecer la contrasena de tu cuenta. '
        'Si fuiste tu, haz clic en el siguiente boton:</p>'
        '<div style="text-align: center; margin: 2rem 0;">'
        '<a href="' + link + '" style="display: inline-block; background: #0b1f3a; '
        'color: #ffffff; text-decoration: none; padding: 0.85rem 2rem; '
        'border-radius: 10px; font-weight: 700; font-size: 1rem;">'
        'Restablecer contrasena</a></div>'
        '<p style="color: #5a6b85; font-size: 0.88rem; line-height: 1.6;">'
        'Si no puedes hacer clic, copia este link en tu navegador:<br>'
        '<a href="' + link + '" style="color: #0b1f3a; word-break: break-all;">'
        + link + '</a></p>'
        '<hr style="border: none; border-top: 1px solid #e3e8f0; margin: 1.5rem 0;">'
        '<p style="color: #8b98ac; font-size: 0.82rem; line-height: 1.5; margin: 0;">'
        'Este link expira en 1 hora. Si no solicitaste este cambio, ignora este correo.</p>'
        '</div>'
        '<p style="text-align: center; color: #8b98ac; font-size: 0.78rem; margin-top: 1.5rem;">'
        'Basecon &copy; 2026 &mdash; Sistema de Remuneraciones Chile</p>'
        '</div>'
    )

    try:
        params = {
            "from": _from_email(),
            "to": [destinatario],
            "subject": "Recuperar contrasena - BASECON",
            "html": html,
        }
        r = resend.Emails.send(params)
        print("[email] Enviado a " + destinatario)
        return True
    except Exception as e:
        print("[email] ERROR al enviar: " + str(e))
        return False