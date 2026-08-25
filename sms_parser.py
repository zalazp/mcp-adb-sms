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
        # Strip leading row index e.g. "0 _id=1, number=138..."
        if " " in payload and "=" not in payload.split(" ", 1)[0]:
            payload = payload.split(" ", 1)[1]

        row: dict[str, str] = {}
        for part in payload.split(","):
            part = part.strip()
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            row[key.strip()] = value.strip()

        if row:
            rows.append(row)

    return rows


def parse_content_query_output(raw: str) -> list[SmsRecord]:
    """Parse SMS inbox query output into SmsRecord list."""
    return [_row_to_record(row) for row in parse_content_query_rows(raw)]


def _row_to_record(row: dict[str, str]) -> SmsRecord:
    return SmsRecord(
        address=row.get("address", row.get("Address", "")),
        body=row.get("body", row.get("Body", "")),
        date=int(row.get("date", row.get("Date", "0")) or "0"),
    )
