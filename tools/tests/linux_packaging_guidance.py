#!/usr/bin/env python3
"""Regression checks for Linux packaging and audit-status guidance."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"Missing {needle!r} in {context}")


def validate_building_packager_notes() -> None:
    source = read("BUILDING.md")

    require(source, "## Building on Linux / macOS", "BUILDING Linux build section")
    meson_floor = re.search(r"meson_version: '>=([0-9.]+)'", read("meson.build"))
    if meson_floor is None:
        raise AssertionError("meson.build no longer declares a meson_version floor")
    require(source, f"{meson_floor.group(1)} or newer", "BUILDING Meson floor")
    require(source, "libglew-dev", "BUILDING OpenGL development dependency")
    require(source, "libopenal-dev", "BUILDING OpenAL development dependency")
    require(source, "OPENPR06_FORCE_X11=1", "BUILDING project XWayland fallback")
    require(source, "`src/game/`, `src/Prey/` and `src/preyengine/`", "BUILDING canonical game source paths")
    require(source, "openq4_game_sources.json", "BUILDING canonical source inventory")
    require(source, "tools/build/meson_setup.sh", "BUILDING canonical Linux wrapper")
    require(source, "install -C builddir --no-rebuild --skip-subprojects", "BUILDING package staging command")
    require(source, "openpr06-<version-tag>-linux-x64.tar.xz", "BUILDING Linux archive identity")
    require(source, "openpr06-<version-tag>-x86_64.AppImage", "BUILDING Linux AppImage identity")
    require(source, "basepr/game_<arch>.(dll|so|dylib)", "BUILDING unified game module layout")


def validate_platform_support() -> None:
    source = read("docs/dev/platform-support.md")

    require(source, "Linux x64", "platform support Linux lane")
    require(source, "Retail gameplay validation pending", "platform support runtime boundary")
    require(source, "SDL3 may use Wayland or X11", "platform support display stack")
    require(source, "OPENPR06_FORCE_X11=1", "platform support XWayland fallback")
    require(source, "OPENPR06_WAYLAND_DISABLE_LIBDECOR=1", "platform support libdecor fallback")
    require(source, "Legacy `OPENQ4_*` names remain temporary migration aliases only", "platform support migration boundary")


def validate_plan_status() -> None:
    source = read("docs/dev/prey-rebase/status-ledger.md")

    require(source, "## Explicit deferral register", "rebase status ledger")
    require(source, "TODO-RELEASE-LANES", "rebase release-lane deferral")
    require(source, "OpenPrey-game", "rebase release-lane companion contract")
    require(source, "basepr", "rebase release-lane runtime layout")
    require(source, "one `game_<arch>` module", "rebase release-lane module contract")


def validate_ci_wiring() -> None:
    # openPR06: no push-verification/commit-validation workflows; openq4_validate.py is the runner.
    runner = read("tools/validation/openq4_validate.py")

    require(runner, "linux_packaging_guidance.py", "validation runner")


def validate_release_note() -> None:
    source = read("docs/dev/release-completion.md")

    require(source, "Archive/AppImage tooling is rebranded for openPR06", "release completion notes")
    require(source, "Wayland/X11 runtime boundaries", "release completion notes")
    require(source, "nightly publication lane", "release completion notes")


def main() -> None:
    validate_building_packager_notes()
    validate_platform_support()
    validate_plan_status()
    validate_ci_wiring()
    validate_release_note()
    print("linux_packaging_guidance: ok")


if __name__ == "__main__":
    main()
