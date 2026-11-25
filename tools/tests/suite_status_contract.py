#!/usr/bin/env python3
"""Keep tools/tests/suite_status.json honest.

Every listed script must exist and sit in one group, the groups must say why
they are listed, and the full-suite runner and BUILDING.md must describe the
same list. A stale entry hides nothing; it just makes the next full run fail
to tell new drift from old.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "tools" / "tests" / "suite_status.json"
RUNNER = ROOT / "tools" / "validation" / "run_test_suite.py"
EXPECTED_GROUPS = {"deferred-release-lane", "pending-source-port", "needs-arguments", "needs-runtime"}


def main() -> int:
    data = json.loads(STATUS.read_text(encoding="utf-8"))
    groups = data["groups"]
    if set(groups) != EXPECTED_GROUPS:
        raise AssertionError(f"suite_status.json groups changed: {sorted(groups)}; update this contract and BUILDING.md")
    for group, entry in groups.items():
        if len(entry.get("reason", "")) < 40:
            raise AssertionError(f"group {group} needs a reason")
        if entry["tests"] != sorted(entry["tests"]):
            raise AssertionError(f"group {group} must list its scripts in sorted order")

    spec = importlib.util.spec_from_file_location("run_test_suite_under_test", RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {RUNNER}")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    listed, timeouts = runner.load_status()  # raises on missing or duplicated scripts
    if Path(__file__).stem in listed:
        raise AssertionError("this contract must not list itself")
    slow_and_skipped = sorted(set(listed) & set(timeouts))
    if slow_and_skipped:
        raise AssertionError(f"skipped scripts need no slow limit: {slow_and_skipped}")

    building = (ROOT / "BUILDING.md").read_text(encoding="utf-8")
    for needle in ("tools/validation/run_test_suite.py", "tools/tests/suite_status.json"):
        if needle not in building:
            raise AssertionError(f"BUILDING.md must describe the full-suite run ({needle})")

    print(f"suite_status_contract: ok ({len(listed)} listed, {len(timeouts)} slow)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
