"""ADB command wrapper with SMS/SIM helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sms_parser import SmsRecord, parse_content_query_output

DEVICES_JSON = Path(__file__).resolve().parent / "devices.json"


def load_device_profile(serial: str | None) -> dict | None:
    if not serial or not DEVICES_JSON.exists():
        return None
    try:
        data = json.loads(DEVICES_JSON.read_text(encoding="utf-8"))
        return data.get(serial)
    except (OSError, json.JSONDecodeError):
        return None


def phone_numbers_from_config(serial: str | None) -> list["SimInfo"]:
    """Return phone numbers from devices.json for the connected device serial."""
    profile = load_device_profile(serial)
    if not profile:
        return []
    numbers = profile.get("phone_numbers") or []
    return [
        SimInfo(
            slot=idx,
            number=str(number).strip(),
            display_name=f"SIM{idx + 1}",
            icc_id="",
            available=bool(str(number).strip()),
        )
        for idx, number in enumerate(numbers)
        if str(number).strip()
    ]


@dataclass
class AdbDevice:
    serial: str
    state: str
    model: str = ""
    product: str = ""


@dataclass
class SimInfo:
    slot: int
    number: str
    display_name: str
    icc_id: str
    available: bool


class AdbClient:
    SHELL_ALLOWLIST = (
        "content query",
        "content read",
        "dumpsys telephony",
        "dumpsys notification",
        "getprop",
        "settings get",
        "appops set com.android.shell READ_SMS allow",
    )

    def __init__(self, adb_path: str | None = None) -> None:
        self.adb_path = adb_path or self.resolve_adb_path()

    @staticmethod
    def resolve_adb_path() -> str:
        env_path = os.environ.get("ADB_PATH")
        if env_path and Path(env_path).exists():
            return env_path

        found = shutil.which("adb")
        if found:
            return found

        candidates = [
            Path(r"C:\Windows\System32\adb.exe"),
            Path(r"C:\Windows\system32\adb.exe"),
            Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
            Path(r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        return "adb"

    def run(self, *args: str, serial: str | None = None, timeout: int = 30) -> str:
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"adb not found at '{self.adb_path}'. "
                "Set ADB_PATH in mcp.json env or add adb to PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"adb command timed out after {timeout}s: {' '.join(cmd)}") from exc

        if result.returncode != 0 and not result.stdout.strip():
            stderr = result.stderr.strip() or f"exit code {result.returncode}"
            raise RuntimeError(f"adb failed: {stderr}")

        return result.stdout

    def shell(self, command: str, serial: str | None = None, timeout: int = 30) -> str:
        return self.run("shell", command, serial=serial, timeout=timeout)

    def list_devices(self) -> list[AdbDevice]:
        output = self.run("devices", "-l")
        devices: list[AdbDevice] = []

        for line in output.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            serial, state = parts[0], parts[1]
            if state == "offline":
                continue

            model = ""
            product = ""
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1]
                elif part.startswith("product:"):
                    product = part.split(":", 1)[1]

            devices.append(AdbDevice(serial=serial, state=state, model=model, product=product))

        return devices

    def get_phone_numbers(self, serial: str | None = None) -> list[SimInfo]:
        """Phone numbers come from devices.json only (key = adb device serial)."""
        sims = phone_numbers_from_config(serial)
        if sims:
            return sims
        return [
            SimInfo(
                slot=0,
                number="",
                display_name="未配置",
                icc_id="",
                available=False,
            )
        ]

    def get_sim_numbers(self, serial: str | None = None) -> list[SimInfo]:
        """Alias for get_phone_numbers (backward compatible)."""
        return self.get_phone_numbers(serial=serial)

    def read_recent_sms(self, limit: int = 10, serial: str | None = None) -> list[SmsRecord]:
        """Read recent SMS. Some OEM builds reject `--limit`; slice in Python."""
        uris = (
            "content://sms/inbox",
            "content://sms",
        )
        records: list[SmsRecord] = []
        last_raw = ""

        for uri in uris:
            raw = self.shell(
                f"content query --uri {uri} "
                "--projection address,body,date "
                "--sort 'date DESC'",
                serial=serial,
                timeout=60,
            )
            last_raw = raw
            if _looks_like_content_query_error(raw):
                continue
            records = parse_content_query_output(raw)
            if records:
                break

        if not records and last_raw and not _looks_like_content_query_error(last_raw):
            # Permission OK but parser got nothing — surface a hint in logs via empty list.
            pass

        return records[:limit]

    def read_sms_fallback(self, limit: int = 10, serial: str | None = None) -> list[SmsRecord]:
        """Fallback via notification dump when content://sms is blocked or delayed."""
        records: list[SmsRecord] = []
        try:
            raw = self.shell("dumpsys notification --noredact", serial=serial, timeout=20)
        except RuntimeError:
            return records

        blocks = re.split(r"\n\s*NotificationRecord\(", raw)
        for block in blocks[1:]:
            title = _extract_field(block, "android.title")
            text = _extract_field(block, "android.text")
            big_text = _extract_field(block, "android.bigText")
            body = big_text or text or title
            if not body:
                continue
            when_match = re.search(r"\bwhen=(\d{10,})", block)
            date_ms = int(when_match.group(1)) if when_match else 0
            records.append(SmsRecord(address=title, body=body, date=date_ms))

        records.sort(key=lambda r: r.date, reverse=True)
        return records[:limit]

    def try_grant_sms_permission(self, serial: str | None = None) -> str:
        try:
            return self.shell(
                "appops set com.android.shell READ_SMS allow",
                serial=serial,
            )
        except RuntimeError as exc:
            return f"grant failed: {exc}"

    def allowed_shell(self, command: str, serial: str | None = None) -> str:
        normalized = command.strip()
        if not any(normalized.startswith(prefix) for prefix in self.SHELL_ALLOWLIST):
            allowed = ", ".join(self.SHELL_ALLOWLIST)
            raise ValueError(
                f"Command not allowed. Prefix must match one of: {allowed}"
            )
        return self.shell(normalized, serial=serial)

    def health_check(self, serial: str | None = None) -> dict:
        report: dict = {
            "adb_path": self.adb_path,
            "adb_exists": Path(self.adb_path).exists() if self.adb_path != "adb" else bool(shutil.which("adb")),
            "devices": [],
            "sms_readable": False,
            "sms_error": None,
            "sim_numbers": [],
            "recommendations": [],
        }

        try:
            devices = self.list_devices()
            report["devices"] = [
                {"serial": d.serial, "state": d.state, "model": d.model, "product": d.product}
                for d in devices
            ]
        except RuntimeError as exc:
            report["sms_error"] = str(exc)
            report["recommendations"].append("Install platform-tools or set ADB_PATH in mcp.json")
            return report

        target = serial
        if not target:
            ready = [d for d in devices if d.state == "device"]
            if ready:
                target = ready[0].serial

        if not target:
            report["recommendations"].append("Connect phone via USB, enable USB debugging, authorize PC")
            return report

        try:
            sms = self.read_recent_sms(limit=3, serial=target)
            report["sms_readable"] = bool(sms)
            report["sms_sample_count"] = len(sms)
            if not sms:
                fallback = self.read_sms_fallback(limit=3, serial=target)
                if fallback:
                    report["sms_readable"] = True
                    report["sms_source"] = "notification_fallback"
                    report["sms_sample_count"] = len(fallback)
                    report["recommendations"].append(
                        "content://sms 为空或延迟；已用通知栏降级。vivo 验证码通知可能打码 ******。"
                    )
                else:
                    report["recommendations"].append(
                        "adb 可读但无短信行：若刚改过 server.py，请在 Cursor MCP 面板 Reload adb-sms。"
                    )
        except RuntimeError as exc:
            report["sms_error"] = str(exc)
            report["recommendations"].append(
                "Try: adb shell appops set com.android.shell READ_SMS allow"
            )
            try:
                fallback = self.read_sms_fallback(limit=3, serial=target)
                if fallback:
                    report["sms_readable"] = True
                    report["sms_source"] = "notification_fallback"
                    report["sms_sample_count"] = len(fallback)
            except RuntimeError:
                pass

        sims = self.get_phone_numbers(serial=target)
        report["sim_numbers"] = [
            {
                "slot": s.slot,
                "number": s.number,
                "display_name": s.display_name,
                "available": s.available,
            }
            for s in sims
        ]
        profile = load_device_profile(target)
        if profile:
            report["device_profile"] = {
                "serial": target,
                "phone_numbers": profile.get("phone_numbers", []),
                "source": "devices.json",
            }
        else:
            report["recommendations"].append(
                f"在 devices.json 添加条目：\"{target}\": {{ \"phone_numbers\": [\"手机号1\", \"手机号2\"] }}"
            )

        return report


def _extract_field(block: str, field: str) -> str:
    match = re.search(rf"{re.escape(field)}=String\s*\(([^)]*)\)", block)
    if match:
        return match.group(1).strip()
    match = re.search(rf"{re.escape(field)}=([^,\n]+)", block)
    return match.group(1).strip() if match else ""


def _looks_like_content_query_error(raw: str) -> bool:
    text = raw.strip().lower()
    if not text:
        return True
    if "unsupported argument" in text or text.startswith("usage:"):
        return True
    if "usage: adb shell content" in text:
        return True
    return False
