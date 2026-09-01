"""Unit tests for SMS content-query parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sms_parser import parse_content_query_output


def test_parse_body_with_commas():
    raw = (
        "Row: 0 address=106830670063681621, "
        "body=【农信数智】您正在使用验证码登录,验证码:178637,请于10分钟内输入,重发会刷新验证码, "
        "date=1788164240529"
    )
    records = parse_content_query_output(raw)
    assert len(records) == 1
    assert records[0].address == "106830670063681621"
    assert "验证码:178637" in records[0].body
    assert records[0].extract_otp() == "178637"


def test_parse_multiple_rows():
    raw = """Row: 0 address=10086, body=hello, date=100
Row: 1 address=10658612, body=推广,带逗号,测试, date=200"""
    records = parse_content_query_output(raw)
    assert len(records) == 2
    assert records[1].body == "推广,带逗号,测试"


if __name__ == "__main__":
    test_parse_body_with_commas()
    test_parse_multiple_rows()
    print("ok")
