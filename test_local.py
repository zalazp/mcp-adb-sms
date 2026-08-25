"""Quick local test for adb-sms modules (no MCP stdio)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adb_client import AdbClient


def main() -> None:
    client = AdbClient()
    print("ADB path:", client.adb_path)
    report = client.health_check()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
