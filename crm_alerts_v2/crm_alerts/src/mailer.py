"""
Email Sender (Mailer)
======================
Sends HTML emails via Gmail SMTP (or any SMTP server).
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_body: str,
               config: dict, test_mode: bool = False) -> bool:
    """
    Send an HTML email.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: Full HTML content
        config: App config dict
        test_mode: If True, skip actual sending

    Returns:
        True if sent (or test mode), False on failure
    """
    if test_mode:
        log.info(f"[TEST] Would send to: {to_email} | Subject: {subject}")
        return True

    sender = config["email"]["sender_email"]
    password = config["email"]["sender_password"]
    host = config["email"]["smtp_host"]
    port = config["email"]["smtp_port"]

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(sender, password)
            server.send_message(msg)
        log.info(f"Email sent to: {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error(
            f"SMTP auth failed for {sender}. "
            f"Check email and app password in config.json. "
            f"Ensure 2-Step Verification is ON and you're using an App Password."
        )
        return False

    except smtplib.SMTPException as e:
        log.error(f"SMTP error sending to {to_email}: {e}")
        return False

    except Exception as e:
        log.error(f"Unexpected error sending to {to_email}: {e}")
        return False
