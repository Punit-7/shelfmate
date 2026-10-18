import logging
import smtplib
from email.message import EmailMessage

from shelfmate.config import settings

log = logging.getLogger(__name__)


def send_email(subject: str, html: str) -> None:
    if not (settings.email_address and settings.email_app_password):
        raise RuntimeError(
            "Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in .env to send email"
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_address
    msg["To"] = settings.email_address
    msg.set_content("Open this email in an HTML viewer.")
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(settings.email_address, settings.email_app_password)
            smtp.send_message(msg)
    except smtplib.SMTPException:
        log.exception("Email failed to send", extra={"subject": subject})
        raise
    log.info("Email sent", extra={"subject": subject, "html_bytes": len(html)})
