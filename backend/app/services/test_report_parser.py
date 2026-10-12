"""有界解析 pytest JUnit；不从 stdout 推测计数，也不执行 XML 实体。"""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from .repository_scanner import _is_link_or_reparse_point

MAX_REPORT_BYTES = 1_000_000


def read_test_report(path: Path) -> dict:
    base = {"version": 1, "format": "pytest_junit", "status": "missing",
            "sha256": None, "counts": None, "xml": None}
    try:
        if not path.exists():
            return base
        if _is_link_or_reparse_point(path) or not path.is_file():
            return {**base, "status": "invalid_path"}
        with path.open("rb") as stream:
            data = stream.read(MAX_REPORT_BYTES + 1)
    except OSError:
        return {**base, "status": "unreadable"}
    if len(data) > MAX_REPORT_BYTES:
        return {**base, "status": "too_large"}
    return parse_test_report(data)


def parse_test_report(data: bytes) -> dict:
    result = {"version": 1, "format": "pytest_junit", "status": "invalid",
              "sha256": None, "counts": None, "xml": None}
    if len(data) > MAX_REPORT_BYTES:
        return {**result, "status": "too_large"}
    result["sha256"] = hashlib.sha256(data).hexdigest()
    try:
        text = data.decode("utf-8")
        # 仅接受 pytest 的 UTF-8 输出，禁止 DTD/实体（包括内嵌实体扩展）。
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper() or "\x00" in text:
            return result
        result["xml"] = text
        root = ET.fromstring(text)
        if root.tag not in ("testsuite", "testsuites"):
            return result
        suites = [root] if root.tag == "testsuite" else list(root)
        if not suites or any(suite.tag != "testsuite" for suite in suites):
            return result
        counts = dict(passed=0, failed=0, errors=0, skipped=0)
        for suite in suites:
            local = dict.fromkeys(counts, 0)
            if suite.find("testsuite") is not None:
                return result
            cases = suite.findall("testcase")
            for case in cases:
                outcomes = [name for name in ("failure", "error", "skipped") if case.find(name) is not None]
                if len(outcomes) > 1:
                    return result
                outcome = {"failure": "failed", "error": "errors", "skipped": "skipped"}.get(
                    outcomes[0] if outcomes else "", "passed")
                local[outcome] += 1
            declared = {"tests": len(cases), "failures": local["failed"],
                        "errors": local["errors"], "skipped": local["skipped"]}
            if any(int(suite.attrib[name]) != number for name, number in declared.items()):
                return {**result, "status": "inconsistent"}
            for key in counts:
                counts[key] += local[key]
        return {**result, "status": "recorded", "counts": counts}
    except (UnicodeError, ET.ParseError, KeyError, ValueError):
        return result
