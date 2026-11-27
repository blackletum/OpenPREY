#!/usr/bin/env python3
"""Run every tools/tests/*.py script and separate new failures from known ones.

tools/tests/suite_status.json lists the scripts a bare run cannot judge
(deferred openQ4 release-lane fixtures, helpers that need arguments, runtime
checks that need a build or device), the slow scripts that need a longer
limit, and the prerequisites (a JDK, Python modules, commands, a platform) some
scripts need. Listed groups are skipped unless named with --include, and a
script whose prerequisites are missing is reported as skipped with what to
install; everything else must pass, so the exit status is 1 only for drift
outside the list.

Run from anywhere:

    python tools/validation/run_test_suite.py
    python tools/validation/run_test_suite.py --jobs 6 --include deferred-release-lane
    python tools/validation/run_test_suite.py docs_link_integrity source_charset_integrity

On Windows, run it from a Visual Studio developer environment
(tools/build/openpr06_devcmd.cmd) so the C++ harness tests find a compiler.
Each script's output goes to .tmp/test-suite/<name>.log.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tools" / "tests"
STATUS = TESTS / "suite_status.json"


def load_status() -> tuple[dict[str, str], dict[str, int]]:
    groups, timeouts, _ = load_status_with_requirements()
    return groups, timeouts


def load_status_with_requirements() -> tuple[dict[str, str], dict[str, int], dict[str, dict]]:
    data = json.loads(STATUS.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise SystemExit(f"{STATUS}: unsupported schema {data.get('schema')!r}")
    groups: dict[str, str] = {}
    for group, entry in data["groups"].items():
        for name in entry["tests"]:
            if name in groups:
                raise SystemExit(f"{STATUS}: {name} is listed in both {groups[name]} and {group}")
            groups[name] = group
    timeouts = {name: int(seconds) for name, seconds in data["slow"]["timeouts"].items()}
    requires = data.get("requires", {}).get("tests", {})
    for name, needs in requires.items():
        unknown = sorted(set(needs) - {"jdk", "modules", "commands", "platforms"})
        if unknown:
            raise SystemExit(f"{STATUS}: {name} has unknown prerequisites: {', '.join(unknown)}")
    stale = sorted(name for name in [*groups, *timeouts, *requires] if not (TESTS / f"{name}.py").is_file())
    if stale:
        raise SystemExit(f"{STATUS}: listed scripts do not exist: {', '.join(stale)}")
    return groups, timeouts, requires


def missing_prerequisites(needs: dict) -> list[str]:
    """What a script listed under "requires" lacks on this machine, if anything."""
    missing: list[str] = []
    platforms = needs.get("platforms")
    if platforms and not any(sys.platform.startswith(prefix) for prefix in platforms):
        missing.append("platform " + " or ".join(platforms))
        return missing
    if needs.get("jdk"):
        java_home = os.environ.get("JAVA_HOME")
        javac = "javac.exe" if os.name == "nt" else "javac"
        if not shutil.which("javac") and not (java_home and (Path(java_home) / "bin" / javac).is_file()):
            missing.append("a JDK (javac on PATH or JAVA_HOME)")
    for module in needs.get("modules", []):
        if importlib.util.find_spec(module) is None:
            missing.append(f"Python module {module}")
    commands = needs.get("commands", [])
    if isinstance(commands, dict):
        commands = [command for prefix, listed in commands.items() if sys.platform.startswith(prefix) for command in listed]
    for command in commands:
        if not shutil.which(command):
            missing.append(f"command {command}")
    return missing


def first_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if "Error" in line or "error:" in line or "FAIL" in line:
            return line[:200]
    return lines[-1][:200] if lines else ""


def run_script(name: str, timeout: int, log_dir: Path, env: dict[str, str]) -> tuple[str, str, float, str]:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(TESTS / f"{name}.py")],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        status = "pass" if proc.returncode == 0 else f"fail ({proc.returncode})"
        output = proc.stdout
    except subprocess.TimeoutExpired as exc:
        status = f"timeout ({timeout}s)"
        output = exc.stdout or b""
    text = output.decode("utf-8", "replace")
    (log_dir / f"{name}.log").write_text(text, encoding="utf-8")
    return name, status, time.monotonic() - start, "" if status == "pass" else first_error(text)


def main() -> int:
    groups, timeouts, requires = load_status_with_requirements()
    known_groups = sorted(set(groups.values()))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="run only these scripts (names without .py)")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    parser.add_argument("--timeout", type=int, default=600, help="per-script limit in seconds (slow scripts get their listed limit)")
    parser.add_argument("--include", action="append", default=[], choices=known_groups,
                        help="also run a listed group; its results are reported but never fail the run")
    parser.add_argument("--log-dir", type=Path, default=ROOT / ".tmp" / "test-suite")
    args = parser.parse_args()

    all_names = sorted(path.stem for path in TESTS.glob("*.py"))
    if args.names:
        missing = sorted(set(args.names) - set(all_names))
        if missing:
            parser.error("no such script: " + ", ".join(missing))
        selected = list(args.names)
    else:
        selected = [name for name in all_names if groups.get(name) is None or groups[name] in args.include]
    skipped = [] if args.names else [name for name in all_names if name not in selected]
    unmet = {name: missing for name in selected if (missing := missing_prerequisites(requires.get(name, {})))}
    selected = [name for name in selected if name not in unmet]
    for name, missing in sorted(unmet.items()):
        print(f"{'skip':<16} {0.0:7.1f}s  {name}  needs {', '.join(missing)}", flush=True)

    args.log_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # Nothing in the suite should open a window or an audio device.
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    results: list[tuple[str, str, float, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [
            pool.submit(run_script, name, max(args.timeout, timeouts.get(name, 0)), args.log_dir, env)
            for name in selected
        ]
        for future in concurrent.futures.as_completed(futures):
            name, status, seconds, error = future.result()
            results.append((name, status, seconds, error))
            tag = f" [{groups[name]}]" if name in groups else ""
            print(f"{status:<16} {seconds:7.1f}s  {name}{tag}{('  ' + error) if error else ''}", flush=True)

    new_failures = sorted(r for r in results if r[1] != "pass" and r[0] not in groups)
    known_failures = sorted(r for r in results if r[1] != "pass" and r[0] in groups)
    now_passing = sorted(r[0] for r in results if r[1] == "pass" and r[0] in groups)

    print()
    print(f"{len(results)} run, {len(results) - len(new_failures) - len(known_failures)} passed, "
          f"{len(new_failures)} new failures, {len(known_failures)} known failures, {len(skipped)} listed scripts skipped"
          + (f" (groups: {', '.join(g for g in known_groups if g not in args.include)})" if skipped else "")
          + (f", {len(unmet)} skipped for missing prerequisites" if unmet else ""))
    if now_passing:
        print("Listed in suite_status.json but passing now (take them off the list): " + ", ".join(now_passing))
    for name, status, _, error in new_failures:
        print(f"NEW FAILURE {name}: {status}: {error}")
    print(f"Logs: {args.log_dir}")
    return 1 if new_failures else 0


if __name__ == "__main__":
    sys.exit(main())
