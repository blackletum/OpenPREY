#!/usr/bin/env python3
"""Regression checks for Linux ARM64 CI coverage."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"Missing {needle!r} in {context}")


def reject(haystack: str, needle: str, context: str) -> None:
    if needle in haystack:
        raise AssertionError(f"Unexpected {needle!r} in {context}")


def require_count(haystack: str, needle: str, expected: int, context: str) -> None:
    actual = haystack.count(needle)
    if actual != expected:
        raise AssertionError(f"Expected {expected} occurrence(s) of {needle!r} in {context}, found {actual}")


def lane_entry(source: str, platform: str) -> str:
    marker = f"          - platform: {platform}\n"
    require_count(source, marker, 1, "openPR06 validation unified-gamelib matrix")
    entry = source[source.index(marker) :]
    end = entry.find("\n          - platform:", 1)
    if end == -1:
        end = entry.index("\n\n    steps:")
    return entry[:end]


def step_block(source: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    require_count(source, marker, 1, "workflow steps")
    block = source[source.index(marker) + len(marker) :]
    end = block.find("\n      - name:")
    return block if end == -1 else block[:end]


def validate_validation_workflow() -> None:
    # openPR06: no push-verification/commit-validation workflows. Linux ARM64
    # builds natively in openpr06-validation.yml's unified-gamelib matrix.
    source = read(".github/workflows/openpr06-validation.yml")

    arm64 = lane_entry(source, "Linux ARM64")
    for token in (
        "os: ubuntu-24.04-arm\n",
        "arch: arm64\n",
        "module: game_arm64.so\n",
        "client: openPR06-client_arm64\n",
        "dedicated: openPR06-ded_arm64\n",
        "renderer_gl: renderer-gl_arm64.so\n",
        "renderer_vk: renderer-vk_arm64.so\n",
    ):
        require(arm64, token, "Linux ARM64 unified-gamelib lane")
    reject(arm64, "game-sp_", "Linux ARM64 unified-gamelib lane")
    reject(arm64, "game-mp_", "Linux ARM64 unified-gamelib lane")

    dependencies = step_block(source, "Install Linux native dependencies")
    require(dependencies, "if: runner.os == 'Linux'", "Linux dependency gate")
    for package in ("binutils", "libgl1-mesa-dri", "libglx-mesa0", "libwayland-dev", "libdecor-0-dev"):
        require(dependencies, f"{package} \\\n", "Linux native dependencies")

    build = step_block(source, "Configure, build, and stage (Linux)")
    require(build, "if: runner.os == 'Linux'", "Linux build gate")
    require(build, "bash tools/build/meson_setup.sh setup --wipe builddir", "Linux Meson setup")
    require(build, "-Dbuild_games=true", "Linux unified game module build")
    require(build, "install -C builddir --no-rebuild --skip-subprojects", "Linux staging")

    payload = step_block(source, "Verify unified staged payload")
    require(payload, 'test -f ".install/basepr/${{ matrix.module }}"', "staged unified game module")
    require(payload, 'test -f ".install/${{ matrix.dedicated }}"', "staged dedicated server")
    require(payload, "openPR06 ships one game_<arch> module.", "split game-module rejection")

    # openPR06: no lane runs the Xvfb/Wayland assetless runtime smoke. PREY's
    # game module does not define g_allowAssetlessStartup, so the client cannot
    # start without retail PREY assets (see manual-release.yml's header).
    require(
        read(".github/workflows/manual-release.yml"),
        "PREY's game module does not define g_allowAssetlessStartup",
        "documented assetless runtime-smoke boundary",
    )


def validate_linux_hardening_contract() -> None:
    meson = read("meson.build")
    validator = read("tools/validation/openq4_validate.py")

    require(meson, "linux_compile_hardening_args", "Linux compile hardening")
    require(meson, "-fstack-protector-strong", "Linux compile hardening")
    require(meson, "-D_FORTIFY_SOURCE=2", "Linux compile hardening")
    require(meson, "linux_link_hardening_args", "Linux link hardening")
    require(meson, "-Wl,-z,relro", "Linux link hardening")
    require(meson, "-Wl,-z,now", "Linux link hardening")
    require(meson, "-Wl,-z,noexecstack", "Linux link hardening")
    require(meson, "linux_executable_pie", "Linux executable PIE")
    require(meson, "pie: linux_executable_pie", "Linux executable PIE")
    require(meson, "'Linux executable PIE': linux_executable_pie", "Meson hardening summary")

    require(validator, "validate_linux_binary_hardening", "Linux staged hardening validation")
    require(validator, "readelf", "Linux staged hardening validation")
    require(validator, "GNU_RELRO", "Linux staged hardening validation")
    require(validator, "GNU_STACK", "Linux staged hardening validation")
    require(validator, "BIND_NOW", "Linux staged hardening validation")
    require(validator, "Linux binary is not PIE/ET_DYN", "Linux staged hardening validation")
    require(validator, '"arm64": ("ELF64", "AArch64")', "Linux staged ARM64 ELF validation")
    require(validator, '["--wide", "--dyn-syms"]', "Linux dynamic module export validation")
    require(validator, 'fields[4] in {"GLOBAL", "WEAK", "UNIQUE"}', "Linux public symbol binding validation")
    require(validator, 'fields[5] in {"DEFAULT", "PROTECTED"}', "Linux public symbol visibility validation")
    require(validator, 'expected_game_exports = {"GetGameAPI", "openQ4_Mem_GetModuleStats"}', "Linux exact game module export set")
    require(validator, "len(public_symbols) == len(expected_game_exports)", "no extra public Linux module export")
    require(validator, 'symbol[:3] == ("FUNC", "GLOBAL", "DEFAULT")', "Linux game module export binding validation")
    require(validator, "Linux game module must expose exactly the GLOBAL/DEFAULT/FUNC GetGameAPI", "Linux game module export validation")


def validate_runtime_flags() -> None:
    renderer = read("tools/tests/renderer_validation_matrix.py")
    runner = read("tools/validation/openq4_validate.py")

    require(renderer, '"id": "sdl3-wayland-window-lifecycle"', "renderer validation Wayland window lifecycle case")
    require(renderer, "native Wayland SDL3 window lifecycle smoke", "renderer validation Wayland window lifecycle case")
    require(renderer, '"SDL3: current video driver: wayland"', "renderer validation Wayland driver assertion")
    # openPR06: the lifecycle and stress cases resize windowed only; they check fullscreen=no.
    require(renderer, '["fullscreen=no"]', "renderer validation Wayland windowed-state assertion")
    require(renderer, '"SDL3: native Wayland window state after windowed change"', "renderer validation Wayland windowed assertion")
    require(renderer, '"+vid_restart"', "renderer validation window lifecycle restart command")
    require(renderer, '"id": "sdl3-wayland-window-stress"', "renderer validation Wayland window stress case")
    require(renderer, "native Wayland SDL3 repeated windowed-resize stress", "renderer validation Wayland window stress case")
    require(renderer, '"r_windowWidth",\n                "1280"', "renderer validation Wayland window stress width change")
    require(renderer, '"id": "sdl3-wayland-mouse-capture"', "renderer validation Wayland mouse capture case")
    require(renderer, "native Wayland SDL3 relative mouse capture smoke", "renderer validation Wayland mouse capture case")
    require(renderer, '"+sdl3MouseCaptureDiagnostics"', "renderer validation mouse capture command")
    require(renderer, '"SDL3 mouse capture diagnostics after activate:"', "renderer validation mouse capture activation assertion")
    require(renderer, '"relative=on"', "renderer validation relative mouse assertion")
    require(renderer, '"captured=yes"', "renderer validation relative mouse assertion")
    require(renderer, '"id": "sdl3-wayland-mouse-capture-stress"', "renderer validation Wayland mouse capture stress case")
    require(renderer, "native Wayland SDL3 repeated relative mouse capture stress", "renderer validation Wayland mouse capture stress case")
    require(renderer, '"SDL3 mouse capture diagnostics: begin repeat=4"', "renderer validation mouse capture repeat assertion")
    require(renderer, '"SDL3 mouse capture diagnostics: iteration 4/4"', "renderer validation mouse capture repeat assertion")
    require(renderer, '"id": "sdl3-wayland-display-diagnostics"', "renderer validation Wayland display diagnostics case")
    require(renderer, "native Wayland SDL3 display diagnostics smoke", "renderer validation Wayland display diagnostics case")
    require(renderer, '"+listDisplays"', "renderer validation display diagnostics command")
    require(renderer, '"SDL3: detected"', "renderer validation display enumeration assertion")
    require(renderer, '"contentScale"', "renderer validation display scale assertion")
    require(renderer, '"orientation"', "renderer validation display orientation assertion")
    require(renderer, '"selected display"', "renderer validation selected-display assertion")
    require(renderer, '"id": "sdl3-x11-display-diagnostics"', "renderer validation X11 display diagnostics case")
    require(renderer, "SDL3 X11/Xvfb fallback display diagnostics smoke", "renderer validation X11 display diagnostics case")
    require(renderer, '"SDL3: current video driver: x11"', "renderer validation X11 driver assertion")
    require(renderer, '"id": "sdl3-force-x11-display-diagnostics"', "renderer validation OPENQ4_FORCE_X11 display diagnostics case")
    require(renderer, "openPR06 XWayland fallback diagnostics smoke", "renderer validation OPENQ4_FORCE_X11 display diagnostics case")
    require(renderer, '"OPENQ4_FORCE_X11=1"', "renderer validation OPENQ4_FORCE_X11 environment assertion")
    require(renderer, '"videoDriver": "x11"', "renderer validation X11 driver-specific metadata")
    require(renderer, '"videoDriver": "wayland"', "renderer validation Wayland driver-specific metadata")
    require(renderer, "filter_driver_specific_cases", "renderer validation default driver-specific filter")
    require(renderer, "--skip-official-pak-validation", "renderer validation matrix assetless option")
    require(renderer, '"fs_validateOfficialPaks"', "renderer validation matrix startup cvar")
    require(renderer, '"g_allowAssetlessStartup"', "renderer validation matrix assetless game guard")
    require(renderer, "skipOfficialPakValidation", "renderer validation matrix report metadata")
    require(runner, "--runtime-skip-official-pak-validation", "validation profile assetless option")
    require(runner, '"--skip-official-pak-validation"', "validation profile renderer handoff")


def validate_renderer_selftest_object_lifetime() -> None:
    planner = read("src/renderer/ModernShadowPlanner.cpp")
    executor = read("src/renderer/ModernGLExecutor.cpp")

    for source, context in (
        (planner, "modern shadow planner self-tests"),
        (executor, "modern GL executor self-tests"),
    ):
        reject(source, "memset( lightDefs, 0, sizeof( lightDefs ) );", context)
    reject(planner, "memset( &lightDef, 0, sizeof( lightDef ) );", "projected shadow diagnostic self-test")


def validate_assetless_renderer_bootstrap() -> None:
    source = read("src/renderer/RenderSystem_init.cpp")

    require(source, 'FindMaterial( "_default", false )', "renderer default material stock lookup")
    require(source, "using generated internal fallback", "renderer default material assetless fallback")
    require(source, 'FindMaterial( "_default" )', "renderer default material generated fallback lookup")
    require(source, "_default material fallback not available", "renderer default material fallback fatal guard")


# openPR06: PREY's game module has no assetless AAS startup (g_allowAssetlessStartup);
# validate_validation_workflow checks that the boundary stays documented.


def validate_release_note() -> None:
    # openPR06: the release completion list and the unreleased notes record the
    # ARM64 preview lane and the native ARM64 CI lanes.
    completion = read("docs/dev/release-completion.md")
    unreleased = read("docs/dev/releases/unreleased.md")

    require(completion, "Linux x64 and ARM64 (preview) with AppImages", "release completion notes")
    require(
        unreleased,
        "The ARM64 lanes build natively on the same `windows-11-arm` and `ubuntu-24.04-arm` runners as the release",
        "unreleased CI notes",
    )


def load_evidence_helper():
    path = ROOT / "tools" / "build" / "verify_linux_arm64_release_evidence.py"
    spec = importlib.util.spec_from_file_location("verify_linux_arm64_release_evidence", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_linux_arm64_release_claim_policy() -> None:
    # openPR06: manual-release.yml ships Linux ARM64 as a preview and has no
    # first-class selector or evidence inputs yet (TODO-RELEASE-LANES). Run its
    # release-matrix script and check the preview names it publishes, and that
    # the evidence verifier accepts the archive name a first-class release uses.
    workflow = read(".github/workflows/manual-release.yml")
    evidence = read("docs/dev/linux-arm64-signoff-evidence.md")
    evidence_template = read("docs/dev/linux-arm64-first-class-evidence.toml")
    evidence_helper = read("tools/build/verify_linux_arm64_release_evidence.py")

    matrix_step = step_block(workflow, "Build release matrix")
    heredoc_start_marker = "          python - <<'PY' >> \"${GITHUB_OUTPUT}\"\n"
    heredoc_end_marker = "\n          PY\n"
    require_count(matrix_step, heredoc_start_marker, 1, "manual release matrix script")
    heredoc_start = matrix_step.index(heredoc_start_marker) + len(heredoc_start_marker)
    heredoc_end = matrix_step.index(heredoc_end_marker, heredoc_start)
    embedded_python = textwrap.dedent(matrix_step[heredoc_start:heredoc_end])
    compile(embedded_python, ".github/workflows/manual-release.yml:release-matrix", "exec")

    with tempfile.TemporaryDirectory(prefix="openpr06-linux-arm64-release-policy-") as temp_dir:
        summary = Path(temp_dir) / "summary.md"
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("MACOS_")
        }
        environment["OPENPR06_RELEASE_VERSION_TAG"] = "9.9.9"
        environment["GITHUB_STEP_SUMMARY"] = str(summary)
        result = subprocess.run(
            [sys.executable, "-c", embedded_python],
            cwd=temp_dir,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise AssertionError("manual release matrix script failed:\n" + result.stdout + result.stderr)
    outputs = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    matrix = json.loads(outputs["release_matrix"])["include"]
    linux = {entry["binary_arch"]: entry for entry in matrix if entry["platform"] == "linux"}
    if sorted(linux) != ["arm64", "x64"]:
        raise AssertionError(f"manual release must build Linux x64 and ARM64, got {sorted(linux)}")
    if linux["x64"]["package_suffix"] != "":
        raise AssertionError("Linux x64 release must not inherit the ARM64 preview suffix")
    if linux["arm64"]["package_suffix"] != "-preview":
        raise AssertionError("preview Linux ARM64 archive must use the -preview suffix")
    if linux["arm64"]["label"] != "Linux ARM64 (preview)":
        raise AssertionError("preview Linux ARM64 matrix label is not explicit")
    if linux["arm64"]["os"] != "ubuntu-24.04-arm":
        raise AssertionError("Linux ARM64 release must build on the native ubuntu-24.04-arm runner")

    expected_assets = set(json.loads(outputs["expected_assets"]))
    for asset in (
        "openpr06-9.9.9-linux-arm64-preview.tar.xz",
        "openpr06-9.9.9-linux-arm64-preview-debugsymbols.tar.xz",
        "openpr06-9.9.9-preview-aarch64.AppImage",
        "openpr06-9.9.9-preview-aarch64.AppImage.zsync",
        "openpr06-9.9.9-linux-x64.tar.xz",
    ):
        if asset not in expected_assets:
            raise AssertionError(f"manual release does not expect {asset}")
    require(
        outputs["linux_arm64_release_reason"],
        "First-class publication needs real-hardware",
        "Linux ARM64 preview release reason",
    )

    helper = load_evidence_helper()
    for archive in ("openpr06-9.9.9-linux-arm64.tar.xz", "openpr06-9.9.9-linux-arm64-preview.tar.xz"):
        helper.require_package_filename(archive, "Linux ARM64 release archive")
    try:
        helper.require_package_filename("openq4-9.9.9-linux-arm64.tar.xz", "Linux ARM64 release archive")
    except RuntimeError:
        pass
    else:
        raise AssertionError("evidence verifier accepted an openQ4 archive name")
    runtime_paths = {key: path.as_posix() for key, path in helper.ARM64_RUNTIME_PATHS.items()}
    if runtime_paths != {
        "client": "openPR06-client_arm64",
        "dedicated": "openPR06-ded_arm64",
        "game": "basepr/game_arm64.so",
    }:
        raise AssertionError(f"evidence verifier hashes the wrong ARM64 runtime files: {runtime_paths}")

    require(evidence, "Required Two-Pass Workflow", "Linux ARM64 signoff evidence")
    require(evidence, "linux_arm64_evidence_ref", "Linux ARM64 signoff evidence")
    require(evidence, "generate_linux_arm64_evidence_candidate", "Linux ARM64 signoff evidence")
    require(evidence, "same triggering openPR06 commit", "Linux ARM64 signoff evidence")
    require(evidence, "Fast-forward the exact tested candidate commit", "Linux ARM64 signoff evidence")
    require(evidence, "creates no tag or GitHub release", "Linux ARM64 signoff evidence")
    require(evidence, "SOURCE_DATE_EPOCH", "Linux ARM64 signoff evidence")
    require(evidence, "hard failure", "Linux ARM64 signoff evidence")
    require(evidence, "physical 64-bit little-endian AArch64", "Linux ARM64 signoff evidence")
    require(evidence, "desktop OpenGL compatibility driver", "Linux ARM64 signoff evidence")
    require(evidence, "representative single-player gameplay", "Linux ARM64 signoff evidence")
    require(evidence, "stock multiplayer map", "Linux ARM64 signoff evidence")
    require(evidence, "stock map with the packaged dedicated server", "Linux ARM64 signoff evidence")
    require(evidence, "Verify keyboard, relative mouse, controller", "Linux ARM64 signoff evidence")
    require(evidence, "SHA-256", "Linux ARM64 signoff evidence")
    require(evidence, "schema version 2", "Linux ARM64 signoff evidence")
    require(evidence, "TODO-RELEASE-LANES", "Linux ARM64 signoff evidence release-lane boundary")
    require(
        evidence,
        "human audible playback",
        "Linux ARM64 manual audio evidence boundary",
    )
    for token in (
        "schema_version = 2",
        'status = "pending"',
        "[review]",
        "[runtime_reports]",
        "[candidate]",
        "[sha256]",
        'openpr06_commit = "pending"',
        'package_filename = "pending"',
        'archive = "pending"',
        'client = "pending"',
        'dedicated = "pending"',
        'game = "pending"',
        'stock_sp = "pending"',
    ):
        require(evidence_template, token, "Linux ARM64 evidence TOML template")
    for token in ("openq4_commit", "openq4_game_commit", "game_sp", "game_mp"):
        reject(evidence_template, token, "Linux ARM64 evidence TOML template")
    for token in (
        "GIT_SHA_RE",
        "SHA256_RE",
        "ROOT_KEYS",
        "REVIEW_KEYS",
        "CANDIDATE_KEYS",
        "SHA256_KEYS",
        "RUNTIME_REPORT_KEYS",
        "RuntimeReportPaths",
        "validate_evidence_manifest",
        "validate_runtime_reports",
        "read_runtime_report",
        "verify_release_evidence",
        "write_candidate",
        "files_equal",
        "require_regular_file",
        "MAX_MANIFEST_BYTES",
        "MAX_RUNTIME_REPORT_BYTES",
        "require_review_value",
        "REVIEW_PLACEHOLDER_VALUES",
        "REVIEW_MINIMUM_LENGTHS",
        "--print-archive-sha256",
    ):
        require(evidence_helper, token, "Linux ARM64 candidate evidence verifier")
    require(
        read("tools/validation/openq4_validate.py"),
        '"linux_arm64_release_evidence.py"',
        "validation runner ARM64 evidence fixture wiring",
    )

    for path, token in (
        ("README.md", "the ARM64 preview"),
        ("docs/user/getting-started.md", "Linux ARM64 and macOS are previews"),
        ("assets/release/README.html", "ARM64 as a preview"),
        ("docs/dev/releases/v0.15.0.md", "ARM64 is a preview"),
        (".github/scripts/announce-release-discord.mjs", "linux-arm64-preview.tar.xz"),
    ):
        require(read(path), token, f"Linux ARM64 preview claim in {path}")

    require(
        read("docs/dev/linux-arm64-cross-compilation.md"),
        "linux-arm64-signoff-evidence.md",
        "Linux ARM64 evidence link in docs/dev/linux-arm64-cross-compilation.md",
    )


def main() -> None:
    validate_validation_workflow()
    validate_linux_hardening_contract()
    validate_runtime_flags()
    validate_renderer_selftest_object_lifetime()
    validate_assetless_renderer_bootstrap()
    validate_release_note()
    validate_linux_arm64_release_claim_policy()
    print("linux_arm64_ci_coverage: ok")


if __name__ == "__main__":
    main()
