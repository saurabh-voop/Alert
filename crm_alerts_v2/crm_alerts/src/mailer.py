"""
Email Sender (Mailer)
======================
Sends HTML emails via Gmail SMTP. Supports file attachments and CC.
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
               attachment_path: str = None,
               cc_emails: list = None) -> bool:
    if test_mode:
        cc_str = f" | CC: {', '.join(cc_emails)}" if cc_emails else ""
        log.info(f"[TEST] Would send to: {to_email}{cc_str} | Subject: {subject}")
        return True

    sender = config["email"]["sender_email"]
    password = config["email"]["sender_password"]
    host = config["email"]["smtp_host"]
    port = config["email"]["smtp_port"]

    msg = MIMEMultipart("mixed")
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject

    if cc_emails:
        msg["Cc"] = ", ".join(cc_emails)

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

    # Build full recipient list (To + CC)
    all_recipients = [to_email]
    if cc_emails:
        all_recipients.extend(cc_emails)

    try:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(sender, password)
            server.send_message(msg)
        cc_str = f" (CC: {', '.join(cc_emails)})" if cc_emails else ""
        log.info(f"Email sent to: {to_email}{cc_str}")
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