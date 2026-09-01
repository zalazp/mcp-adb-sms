#!/usr/bin/env python3
"""ADB SMS OTP MCP server for Cursor Agent."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# Ensure local imports work when launched as script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from adb_client import AdbClient, load_device_profile
from sms_parser import SmsRecord

mcp = FastMCP("adb-sms")
client = AdbClient()


def _resolve_serial(serial: str | None) -> str | None:
    if serial:
        return serial
    devices = client.list_devices()
    ready = [d for d in devices if d.state == "device"]
    return ready[0].serial if ready else None


def _load_sms(serial: str | None, limit: int = 10) -> list[SmsRecord]:
    try:
        records = client.read_recent_sms(limit=limit, serial=serial)
        if records:
            return records
        return client.read_sms_fallback(limit=limit, serial=serial)
    except RuntimeError:
        return client.read_sms_fallback(limit=limit, serial=serial)


@mcp.tool()
def adb_list_devices() -> str:
    """List ADB-connected Android devices with serial, state, and model."""
    devices = client.list_devices()
    return json.dumps(
        {
            "adb_path": client.adb_path,
            "count": len(devices),
            "devices": [
                {
                    "serial": d.serial,
                    "state": d.state,
                    "model": d.model,
                    "product": d.product,
                }
                for d in devices
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def adb_get_sim_numbers(serial: str | None = None) -> str:
    """Get phone numbers for the connected device from devices.json (user-configured)."""
    target = _resolve_serial(serial)
    if not target:
        return json.dumps({"error": "No device in 'device' state", "numbers": []}, ensure_ascii=False)

    sims = client.get_phone_numbers(serial=target)
    has_config = load_device_profile(target) is not None
    return json.dumps(
        {
            "serial": target,
            "sim_cards": [
                {
                    "slot": s.slot,
                    "number": s.number,
                    "display_name": s.display_name,
                    "available": s.available,
                }
                for s in sims
            ],
            "source": "devices.json" if has_config else "missing",
            "hint": (
                "Phone numbers are user-configured in devices.json keyed by adb serial. "
                f"Add entry for serial {target} if empty."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def adb_read_recent_sms(limit: int = 10, serial: str | None = None) -> str:
    """Read recent SMS messages from device inbox (newest first)."""
    target = _resolve_serial(serial)
    if not target:
        return json.dumps({"error": "No device in 'device' state", "messages": []}, ensure_ascii=False)

    messages = _load_sms(target, limit=limit)
    return json.dumps(
        {
            "serial": target,
            "count": len(messages),
            "messages": [
                {
                    "sender": m.address,
                    "body": m.body,
                    "date_ms": m.date,
                    "otp_guess": m.extract_otp(),
                }
                for m in messages
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def adb_wait_for_otp(
    timeout: int = 90,
    sender_filter: str | None = None,
    pattern: str | None = None,
    serial: str | None = None,
) -> str:
    """Poll device SMS until a new OTP arrives. Use after triggering send-code on web."""
    target = _resolve_serial(serial)
    if not target:
        return json.dumps({"error": "No device in 'device' state"}, ensure_ascii=False)

    baseline = _load_sms(target, limit=5)
    baseline_max_date = max((m.date for m in baseline if m.date), default=0)
    baseline_bodies = {m.body for m in baseline}

    sender_re = re.compile(sender_filter, re.IGNORECASE) if sender_filter else None

    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = _load_sms(target, limit=10)
        for msg in messages:
            is_new = (msg.date and msg.date > baseline_max_date) or (
                msg.body and msg.body not in baseline_bodies
            )
            if not is_new:
                continue
            if sender_re and msg.address and not sender_re.search(msg.address):
                # Also check body for sender name (e.g. 【美的】)
                if not sender_re.search(msg.body):
                    continue

            code = msg.extract_otp(pattern)
            if code:
                return json.dumps(
                    {
                        "serial": target,
                        "code": code,
                        "sender": msg.address,
                        "body": msg.body,
                        "date_ms": msg.date,
                    },
                    ensure_ascii=False,
                    indent=2,
                )

        time.sleep(2)

    return json.dumps(
        {
            "error": "OTP timeout",
            "timeout_seconds": timeout,
            "hint": "Check SMS arrived, increase timeout, or relax sender_filter.",
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def adb_shell(command: str, serial: str | None = None) -> str:
    """Run a restricted adb shell command (content/dumpsys/getprop only)."""
    target = _resolve_serial(serial)
    output = client.allowed_shell(command, serial=target)
    return output or "(empty output)"


@mcp.tool()
def adb_health_check(serial: str | None = None) -> str:
    """Run ADB connectivity, SMS readability, and SIM number diagnostics."""
    report = client.health_check(serial=serial)
    return json.dumps(report, ensure_ascii=False, indent=2)


@mcp.tool()
def adb_grant_sms_permission(serial: str | None = None) -> str:
    """Try granting READ_SMS to adb shell (needed on some Android 11+ devices)."""
    target = _resolve_serial(serial)
    if not target:
        return json.dumps({"error": "No device in 'device' state"}, ensure_ascii=False)
    result = client.try_grant_sms_permission(serial=target)
    return json.dumps({"serial": target, "result": result}, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
