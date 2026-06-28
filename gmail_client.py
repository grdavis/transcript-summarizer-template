"""Gmail IMAP client for reading newsletters and marking them as read."""

from __future__ import annotations

import email
import imaplib
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from email import policy
from email.utils import parsedate_to_datetime
from typing import Callable

from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")


@dataclass(frozen=True)
class EmailMessage:
    uid: str
    sender: str
    subject: str
    received_at: datetime
    body: str


def default_lookback_hours() -> int:
    raw = (os.environ.get("BRIEFING_LOOKBACK_HOURS") or "24").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 24


def lookback_cutoff(now: datetime, lookback_hours: int) -> datetime:
    return now - timedelta(hours=lookback_hours)


def imap_since_date(dt: datetime) -> str:
    """IMAP SINCE uses day granularity (dd-Mon-yyyy)."""
    return dt.strftime("%d-%b-%Y")


def extract_body(msg: email.message.Message) -> str:
    """Prefer text/plain; fall back to stripped text/html."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition.lower():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    if html_parts:
        soup = BeautifulSoup("\n".join(html_parts), "html.parser")
        return soup.get_text(separator="\n", strip=True)
    return ""


def within_lookback(received_at: datetime, cutoff: datetime) -> bool:
    """True when received_at is on or after the lookback cutoff."""
    recv = received_at
    if recv.tzinfo is None:
        recv = recv.replace(tzinfo=cutoff.tzinfo)
    else:
        recv = recv.astimezone(cutoff.tzinfo)
    return recv >= cutoff


def parse_raw_message(uid: str | bytes, raw: bytes) -> EmailMessage | None:
    msg = email.message_from_bytes(raw, policy=policy.default)
    date_header = msg.get("Date")
    if not date_header:
        return None
    try:
        received_at = parsedate_to_datetime(date_header)
    except (TypeError, ValueError, OverflowError):
        return None

    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=TZ)
    else:
        received_at = received_at.astimezone(TZ)

    body = extract_body(msg)
    if not body.strip():
        return None

    uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
    return EmailMessage(
        uid=uid_str,
        sender=msg.get("From", ""),
        subject=msg.get("Subject", ""),
        received_at=received_at,
        body=body,
    )


def _sender_matches(message_sender: str, allowed_sender: str) -> bool:
    """Case-insensitive check that the allowed sender appears in the From header."""
    return allowed_sender.lower() in message_sender.lower()


class GmailClient:
    def __init__(
        self,
        address: str | None = None,
        app_password: str | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self.address = (address or os.environ.get("GMAIL_ADDRESS") or "").strip()
        self.app_password = (
            app_password or os.environ.get("GMAIL_APP_PASSWORD") or ""
        ).strip()
        self._now = now or (lambda: datetime.now(TZ))
        self._conn: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        if not self.address or not self.app_password:
            raise ValueError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set")
        conn = imaplib.IMAP4_SSL("imap.gmail.com")
        conn.login(self.address, self.app_password)
        conn.select("INBOX")
        self._conn = conn

    def disconnect(self) -> None:
        if not self._conn:
            return
        try:
            self._conn.close()
        except imaplib.IMAP4.error:
            pass
        try:
            self._conn.logout()
        except imaplib.IMAP4.error:
            pass
        self._conn = None

    def __enter__(self) -> GmailClient:
        self.connect()
        return self

    def __exit__(self, *_args) -> None:
        self.disconnect()

    @property
    def now(self) -> datetime:
        return self._now()

    @property
    def conn(self) -> imaplib.IMAP4_SSL:
        if not self._conn:
            raise RuntimeError("GmailClient is not connected")
        return self._conn

    def reconnect(self) -> None:
        """Drop any existing session and open a fresh IMAP connection."""
        self.disconnect()
        self.connect()

    def _run_imap(self, action):
        """Run an IMAP operation; reconnect once on a dropped connection."""
        try:
            return action()
        except (imaplib.IMAP4.abort, OSError) as exc:
            print(f"IMAP connection lost ({exc}); reconnecting...", file=sys.stderr)
            self.reconnect()
            return action()

    def fetch_from_senders(
        self,
        senders: list[str],
        lookback_hours: int | None = None,
    ) -> list[EmailMessage]:
        """Fetch inbox messages from allowlisted senders within the lookback window."""

        def _fetch() -> list[EmailMessage]:
            hours = lookback_hours if lookback_hours is not None else default_lookback_hours()
            now = self._now()
            cutoff = lookback_cutoff(now, hours)
            since_str = imap_since_date(cutoff)

            seen_uids: set[str] = set()
            results: list[EmailMessage] = []

            for sender in senders:
                status, data = self.conn.uid(
                    "search",
                    None,
                    f'(FROM "{sender}" SINCE {since_str})',
                )
                if status != "OK" or not data or not data[0]:
                    continue

                uids = data[0].split()
                for uid in uids:
                    uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
                    if uid_str in seen_uids:
                        continue

                    status, fetched = self.conn.uid("fetch", uid, "(RFC822)")
                    if status != "OK" or not fetched or not fetched[0]:
                        continue

                    raw = fetched[0][1]
                    if not isinstance(raw, (bytes, bytearray)):
                        continue

                    parsed = parse_raw_message(uid_str, bytes(raw))
                    if not parsed:
                        continue
                    if not _sender_matches(parsed.sender, sender):
                        continue
                    if not within_lookback(parsed.received_at, cutoff):
                        continue

                    seen_uids.add(uid_str)
                    results.append(parsed)

            results.sort(key=lambda m: m.received_at)
            return results

        return self._run_imap(_fetch)

    def mark_as_read(self, uids: list[str]) -> None:
        """Mark the given message UIDs as read (\\Seen)."""

        def _mark() -> None:
            for uid in uids:
                self.conn.uid("store", uid, "+FLAGS", "(\\Seen)")

        self._run_imap(_mark)

    def append_to_inbox(self, message: bytes) -> None:
        """Append a raw RFC822 message directly to INBOX (avoids self-send Sent-folder behavior)."""
        import time

        def _append() -> None:
            self.conn.append(
                "INBOX",
                None,
                imaplib.Time2Internaldate(time.time()),
                message,
            )

        self._run_imap(_append)
