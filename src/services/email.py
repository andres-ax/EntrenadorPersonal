"""Envio de correos via SMTP (Private Email) con fallback opcional a Resend."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


def smtp_configured() -> bool:
    return bool(
        settings.smtp_host
        and settings.smtp_user
        and settings.smtp_pass
        and settings.smtp_from
    )


def _from_header() -> str:
    return f"EntrenadorAX <{settings.smtp_from}>"


def _send_smtp_sync(to: str, subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = _from_header()
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    host = settings.smtp_host
    port = settings.smtp_port
    user = settings.smtp_user
    password = settings.smtp_pass.get_secret_value() if settings.smtp_pass else ""

    if settings.smtp_secure:
        with smtplib.SMTP_SSL(host, port, timeout=15) as server:
            server.login(user, password)
            server.sendmail(settings.smtp_from, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(settings.smtp_from, [to], msg.as_string())


async def _send_resend(to: str, subject: str, html: str) -> None:
    from_addr = settings.smtp_from or "entrenadorax@axsoftware.codes"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"EntrenadorAX <{from_addr}>",
                "to": [to],
                "subject": subject,
                "html": html,
            },
        )
        resp.raise_for_status()


async def send_email(to: str, subject: str, html: str) -> bool:
    """Envia email HTML. Retorna True si se envio correctamente."""
    if smtp_configured():
        try:
            await asyncio.to_thread(_send_smtp_sync, to, subject, html)
            logger.info("Email enviado via SMTP a %s", to)
            return True
        except Exception:
            logger.exception("Error enviando email via SMTP a %s", to)
            return False

    if settings.resend_api_key:
        try:
            await _send_resend(to, subject, html)
            logger.info("Email enviado via Resend a %s", to)
            return True
        except Exception:
            logger.exception("Error enviando email via Resend a %s", to)
            return False

    logger.warning(
        "Email no enviado a %s: configure SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM o RESEND_API_KEY",
        to,
    )
    return False


def otp_login_html(codigo: str) -> str:
    return (
        "<p>Hola,</p>"
        "<p>Tu codigo de acceso temporal para iniciar sesion en la aplicacion de EntrenadorAX es:</p>"
        f"<h2 style='font-size: 24px; font-weight: bold; letter-spacing: 2px; color: #1e3a8a;'>{codigo}</h2>"
        "<p>Este codigo es de un solo uso y expira en 5 minutos.</p>"
        "<p>Si no solicitaste este codigo, puedes ignorar este mensaje.</p>"
    )


def otp_complete_profile_html(codigo: str) -> str:
    return (
        "<p>Hola,</p>"
        "<p>Tu codigo de confirmacion para completar tu perfil en la aplicacion de EntrenadorAX es:</p>"
        f"<h2 style='font-size: 24px; font-weight: bold; letter-spacing: 2px; color: #1e3a8a;'>{codigo}</h2>"
        "<p>Este codigo expira en 5 minutos.</p>"
    )


def magic_link_html(verify_url: str) -> str:
    return (
        "<p>Hola,</p>"
        "<p>Aqui esta tu link para entrar a EntrenadorAX:</p>"
        f"<p><a href='{verify_url}'>Entrar</a></p>"
        "<p>Expira en 15 minutos.</p>"
        "<p>Si no fuiste tu, ignora este email.</p>"
    )
