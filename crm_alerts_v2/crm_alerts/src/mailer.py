"""
Email Sender (Mailer)
======================
Sends HTML emails via Gmail SMTP. Supports file attachments (Excel reports).
"""

import os
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

log = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_body: str,
               config: dict, test_mode: bool = False,
               attachment_path: str = None) -> bool:
    if test_mode:
        log.info(f"[TEST] Would send to: {to_email} | Subject: {subject}")
        return True

    sender = config["email"]["sender_email"]
    password = config["email"]["sender_password"]
    host = config["email"]["smtp_host"]
    port = config["email"]["smtp_port"]

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    # Attach file if provided
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(attachment_path)}"
            )
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(sender, password)
            server.send_message(msg)
        log.info(f"Email sent to: {to_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error(f"SMTP auth failed for {sender}. Check app password.")
        return False
    except smtplib.SMTPException as e:
        log.error(f"SMTP error sending to {to_email}: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error sending to {to_email}: {e}")
        return False
