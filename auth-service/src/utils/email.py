from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..config import settings

logger = logging.getLogger("auth.email")

async def send_email(*, to_email: str, subject: str, text_body: str, html_body: Optional[str] = None) -> None:
    if settings.EMAIL_DELIVERY_MODE.lower() == "smtp":
        await asyncio.to_thread(
            _send_smtp_email,
            to_email,
            subject,
            text_body,
            html_body,
        )
        return

    await asyncio.to_thread(_write_email_file, to_email, subject, text_body, html_body)

def _build_message(to_email: str, subject: str, text_body: str, html_body: Optional[str]) -> EmailMessage:
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message

def _send_smtp_email(to_email: str, subject: str, text_body: str, html_body: Optional[str]) -> None:
    message = _build_message(to_email, subject, text_body, html_body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)
    logger.info("email delivered via smtp to=%s subject=%s", to_email, subject)

def _write_email_file(to_email: str, subject: str, text_body: str, html_body: Optional[str]) -> None:
    output_dir = Path(settings.EMAIL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "to": to_email,
        "from": settings.EMAIL_FROM,
        "subject": subject,
        "text": text_body,
        "html": html_body,
    }
    target = output_dir / f"{uuid4()}.json"
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("email captured to file path=%s to=%s subject=%s", target, to_email, subject)
