"""Tests for email rendering and delivery."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from email_delivery import (
    build_email_body_html,
    delivery_method,
    send_email,
)


def test_build_email_body_html_contains_content_and_date():
    html = build_email_body_html(
        "## Top stories\n\nImportant news here.",
        "June 25, 2026",
        "Your AI &amp; Tech briefing for <strong>{date}</strong> is below.",
    )
    assert "Important news here" in html
    assert "June 25, 2026" in html
    assert "AI &amp; Tech briefing" in html
    assert "<h2" in html


def test_delivery_method_defaults_to_imap_for_self_send():
    with patch.dict(
        os.environ,
        {
            "GMAIL_ADDRESS": "me@gmail.com",
            "GMAIL_APP_PASSWORD": "app-password",
            "BRIEFING_TO_EMAIL": "me@gmail.com",
        },
        clear=False,
    ):
        assert delivery_method() == "imap"


def test_delivery_method_uses_smtp_for_external_recipient():
    with patch.dict(
        os.environ,
        {
            "GMAIL_ADDRESS": "me@gmail.com",
            "GMAIL_APP_PASSWORD": "app-password",
            "BRIEFING_TO_EMAIL": "other@example.com",
        },
        clear=False,
    ):
        assert delivery_method() == "smtp"


def test_send_email_imap_append():
    mock_client = MagicMock()

    with patch.dict(
        os.environ,
        {
            "GMAIL_ADDRESS": "me@gmail.com",
            "GMAIL_APP_PASSWORD": "app-password",
            "BRIEFING_TO_EMAIL": "me@gmail.com",
        },
        clear=False,
    ):
        send_email(
            subject="AI & Tech Daily Briefing - June 25, 2026",
            markdown_body="## Briefing\n\nContent.",
            date_str="June 25, 2026",
            intro_template="Intro <strong>{date}</strong>.",
            gmail_client=mock_client,
        )

    mock_client.append_to_inbox.assert_called_once()
    raw = mock_client.append_to_inbox.call_args[0][0]
    assert b"AI & Tech Daily Briefing" in raw
    assert b"multipart/alternative" in raw


@patch("email_delivery.smtplib.SMTP_SSL")
def test_send_email_smtp(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    with patch.dict(
        os.environ,
        {
            "GMAIL_ADDRESS": "me@gmail.com",
            "GMAIL_APP_PASSWORD": "app-password",
            "BRIEFING_TO_EMAIL": "other@gmail.com",
            "BRIEFING_DELIVERY": "smtp",
        },
        clear=False,
    ):
        send_email(
            subject="AI & Tech Daily Briefing - June 25, 2026",
            markdown_body="## Briefing\n\nContent.",
            date_str="June 25, 2026",
            intro_template="Intro <strong>{date}</strong>.",
        )

    mock_smtp.login.assert_called_once_with("me@gmail.com", "app-password")
    mock_smtp.send_message.assert_called_once()
    sent = mock_smtp.send_message.call_args[0][0]
    assert sent["Subject"] == "AI & Tech Daily Briefing - June 25, 2026"
    assert sent["To"] == "other@gmail.com"
    alt_part = sent.get_payload()[0]
    parts = alt_part.get_payload()
    assert len(parts) == 2
    assert parts[0].get_content_type() == "text/plain"
    assert parts[1].get_content_type() == "text/html"
