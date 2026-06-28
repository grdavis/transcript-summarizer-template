"""Send styled emails via Gmail SMTP or IMAP inbox delivery."""

from __future__ import annotations

import os
import smtplib
from email.mime.audio import MIMEAudio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

from email_html import build_email_html
from gmail_client import GmailClient


def normalize_email(address: str) -> str:
    """Extract and lower-case the mailbox from a From/To header value."""
    _, email_addr = parseaddr(address)
    return email_addr.lower()


def recipient_address() -> str:
    to = (os.environ.get("BRIEFING_TO_EMAIL") or os.environ.get("GMAIL_ADDRESS") or "").strip()
    if not to:
        raise ValueError("BRIEFING_TO_EMAIL or GMAIL_ADDRESS must be set to send email")
    return to


def sender_address() -> str:
    addr = (os.environ.get("GMAIL_ADDRESS") or "").strip()
    if not addr:
        raise ValueError("GMAIL_ADDRESS must be set to send email")
    return addr


def app_password() -> str:
    pwd = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    if not pwd:
        raise ValueError("GMAIL_APP_PASSWORD must be set to send email")
    return pwd


def delivery_method() -> str:
    """
    How to deliver email:
      - imap: append directly to INBOX (default when sending to yourself)
      - smtp: send via Gmail SMTP (use for external/different recipients)
    """
    explicit = (os.environ.get("BRIEFING_DELIVERY") or "").strip().lower()
    if explicit in {"imap", "smtp"}:
        return explicit

    from_addr = normalize_email(sender_address())
    to_addr = normalize_email(recipient_address())
    if from_addr and to_addr and from_addr == to_addr:
        return "imap"
    return "smtp"


def build_email_body_html(markdown_body: str, date_str: str, intro_template: str) -> str:
    return build_email_html(markdown_body, date_str, intro=intro_template)


def build_email_message(
    *,
    subject: str,
    markdown_body: str,
    date_str: str,
    intro_template: str,
    audio_bytes: bytes | None = None,
) -> MIMEMultipart:
    html_body = build_email_body_html(markdown_body, date_str, intro_template)

    root_msg = MIMEMultipart("mixed")
    root_msg["Subject"] = subject
    root_msg["From"] = sender_address()
    root_msg["To"] = recipient_address()

    alt_msg = MIMEMultipart("alternative")
    alt_msg.attach(MIMEText(markdown_body, "plain", "utf-8"))
    alt_msg.attach(MIMEText(html_body, "html", "utf-8"))
    root_msg.attach(alt_msg)

    if audio_bytes:
        audio_part = MIMEAudio(audio_bytes, "mpeg")
        audio_part.add_header("Content-Disposition", "attachment", filename="briefing.mp3")
        root_msg.attach(audio_part)

    return root_msg


def send_email(
    *,
    subject: str,
    markdown_body: str,
    date_str: str,
    intro_template: str,
    audio_bytes: bytes | None = None,
    gmail_client: GmailClient | None = None,
) -> None:
    """Deliver a multipart/alternative email, optionally with an audio attachment."""
    msg = build_email_message(
        subject=subject,
        markdown_body=markdown_body,
        date_str=date_str,
        intro_template=intro_template,
        audio_bytes=audio_bytes,
    )
    method = delivery_method()

    if method == "imap":
        if gmail_client is None:
            raise ValueError("IMAP inbox delivery requires an active GmailClient")
        gmail_client.append_to_inbox(msg.as_bytes())
        print(f"Email delivered to inbox via IMAP: {subject}")
        return

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender_address(), app_password())
        smtp.send_message(msg)

    print(f"Email sent via SMTP: {subject}")
