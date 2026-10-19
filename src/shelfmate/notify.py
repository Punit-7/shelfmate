import logging
import smtplib
from email.message import EmailMessage

from shelfmate.config import settings

log = logging.getLogger(__name__)


def email_ready() -> bool:
    return bool(settings.email_address and settings.email_app_password)


def build_message(subject: str, html: str, to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    # Gmail sends as the account that logs in, so From is always EMAIL_ADDRESS.
    msg["From"] = settings.email_address
    msg["To"] = to
    msg.set_content("Open this email in an HTML viewer.")
    msg.add_alternative(html, subtype="html")
    return msg


def send_email(subject: str, html: str) -> None:
    if not email_ready():
        raise RuntimeError(
            "Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in .env to send email"
        )
    msg = build_message(
        subject, html, to=settings.recipient_email or settings.email_address
    )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(
                settings.email_address, settings.email_app_password.get_secret_value()
            )
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError):
        log.exception("Email failed to send", extra={"subject": subject})
        raise
    log.info("Email sent", extra={"subject": subject, "html_bytes": len(html)})
