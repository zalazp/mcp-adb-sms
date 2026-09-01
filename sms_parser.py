"""SMS body parsing and OTP extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered by specificity — first match wins.
OTP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"验证码[：:\s]*(\d{4,8})", re.IGNORECASE),
    re.compile(r"校验码[：:\s]*(\d{4,8})", re.IGNORECASE),
    re.compile(r"动态码[：:\s]*(\d{4,8})", re.IGNORECASE),
    re.compile(r"(?:code|otp|pin)[：:\s]+(\d{4,8})", re.IGNORECASE),
    re.compile(r"\b(\d{6})\b"),
    re.compile(r"\b(\d{4})\b"),
]

_ROW_DATE_RE = re.compile(r",\s*date=(\d+)\s*$")
_ROW_FIELDS_RE = re.compile(r"^(?:_id=\d+,\s*)?address=([^,]+),\s*body=(.*)$", re.DOTALL)


@dataclass
class SmsRecord:
    address: str
    body: str
    date: int  # epoch ms

    def extract_otp(self, custom_pattern: str | None = None) -> str | None:
        if custom_pattern:
            match = re.search(custom_pattern, self.body, re.IGNORECASE)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
            return None

        for pattern in OTP_PATTERNS:
            match = pattern.search(self.body)
            if match:
                return match.group(1)
        return None


def parse_content_query_rows(raw: str) -> list[dict[str, str]]:
    """Parse `adb shell content query` output into list of field dicts."""
    rows: list[dict[str, str]] = []

    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("Row:"):
            continue

        payload = line.split(":", 1)[1].strip()
        # Strip leading row index e.g. "0 address=1, body=..."
        prefix, _, remainder = payload.partition(" ")
        if prefix.isdigit() and remainder:
            payload = remainder

        date_match = _ROW_DATE_RE.search(payload)
        if not date_match:
            continue

        date = date_match.group(1)
        head = payload[: date_match.start()]
        fields_match = _ROW_FIELDS_RE.match(head)
        if not fields_match:
            continue

        rows.append(
            {
                "address": fields_match.group(1).strip(),
                "body": fields_match.group(2).strip(),
                "date": date,
            }
        )

    return rows


def parse_content_query_output(raw: str) -> list[SmsRecord]:
    """Parse SMS query output into SmsRecord list."""
    return [_row_to_record(row) for row in parse_content_query_rows(raw)]


def _row_to_record(row: dict[str, str]) -> SmsRecord:
    return SmsRecord(
        address=row.get("address", row.get("Address", "")),
        body=row.get("body", row.get("Body", "")),
        date=int(row.get("date", row.get("Date", "0")) or "0"),
    )
