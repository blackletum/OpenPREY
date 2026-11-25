# openPR06 platform and architecture roadmap

This document records the current platform policy for the Prey (2006)-focused rebase.
It is a roadmap, not a release-support claim.

## Current baseline

- Version line: `0.0.1`.
- Canonical build system: Meson + Ninja.
- Standard build output: `builddir/`.
- Standard staged runtime: `.install/`.
- Canonical game source: in-tree `src/game`, `src/Prey` and `src/preyengine`
  (Prey SDK EULA, `LICENSES/PREY-SDK-EULA.rtf`).
- Runtime game directory: `basepr/`.
- Module model: one `game_<arch>` module for SP and MP.
- Platform backend direction: SDL3 first; native/legacy backends are diagnostic
  fallbacks where they remain available.

## Support matrix

| Platform | Build status | Runtime status | Current claim |
|---|---|---|---|
| Windows x64 | Active | Deepest local validation target | Primary bring-up target; retail matrix still pending |
| Linux x64 | Active CI GameLib lane and packaging tooling | Retail gameplay validation pending | Build target, not yet a fully signed-off release |
| Windows ARM64 | Active CI debug lane and release lane (`windows-11-arm`): installer, zip and PDBs | Prey runtime evidence pending | Released package, not play-tested |
| Linux ARM64 | Active CI debug lane and release lane (`ubuntu-24.04-arm`): `-preview` archive, AppImage and debug symbols | Real-hardware Prey runtime evidence pending | Preview |
| macOS arm64 (OpenGL, Metal bridge) | Active CI debug lanes for both bridges; release lane (`macos-15`): unsigned `-unsigned.tar.gz` and dSYMs, or signed DMGs when the Apple secrets exist | Prey runtime and package evidence pending | Preview; experimental and gated for first-class |
| macOS x64/universal2 | Active CI debug lane for Intel x64 OpenGL (`macos-15-intel`); universal2 tooling inherited only | None | Not a release target |
| Android arm64 | `android-build.yml` builds and verifies the openPR06 APK (CI probe, `signing: ci`, 2026-11-22); active CI runs the Android host, touch and GLES checks; no release lane until the signing secrets exist ([android-build.md](android-build.md#release-signing)) | None: no APK installed on a device; the GLES module does not draw PREY's ARB interaction programs | Not released; experimental |

The active workflow is `.github/workflows/openpr06-validation.yml`. It validates
deterministic `pak0.pk4`/`pak1.pk4` inputs, one staged `game_<arch>` module,
`basepr/`, and openPR06 desktop/icon payloads on Windows x64, Linux x64, and, as
openQ4's push verification does, Windows ARM64 and Linux ARM64 (native
`windows-11-arm` and `ubuntu-24.04-arm` runners), macOS ARM64 (OpenGL and Metal
bridge) and macOS Intel x64 (OpenGL). The macOS lanes also run `openq4_validate.py --install` on the
staged tree, which checks install names, the exported game API and the bundled
OpenAL Soft.

`manual-release.yml` is rebuilt for openPR06 on openQ4's desktop release set:
Windows x64 and ARM64, Linux x64 and ARM64 (preview) with AppImages, and macOS
ARM64 OpenGL and Metal-bridge variants (preview). Each lane builds, stages and
validates the unified `game_<arch>` module and `basepr/`, and the release job checks
the exact asset set and every archive's contents. CI has no retail PREY install, so
none of these lanes run the game: that evidence has to come from real hardware.
The separate inherited OpenQ4 ARM64, macOS, Universal2 and signing workflows are
retained only as manual static-test/reference fixtures. Every job is unconditionally
false-gated because it asserts upstream OpenQ4's split `game-sp`/`game-mp` modules
and package contracts. Those gates must not be removed until the lanes are rebuilt around the
openPR06 contract and backed by runtime evidence.

## Linux and Steam Deck

SDL3 may use Wayland or X11 according to the available host. Preferred project
environment variables use the `OPENPR06_*` prefix:

- `OPENPR06_FORCE_X11=1`
- `OPENPR06_WAYLAND_DISABLE_LIBDECOR=1`
- `OPENPR06_WAYLAND_PREFER_LIBDECOR=1`
- `OPENPR06_WAYLAND_SYNC_WINDOW_OPS=1`
- `OPENPR06_STEAMDECK=1`

Legacy `OPENQ4_*` names remain temporary migration aliases only. The staged
`openPR06-steamdeck` launcher always forces windowed mode.

## macOS boundary

macOS code and packaging helpers are retained from upstream, but openPR06 currently
makes no signed-package or first-class runtime claim. One unified game module must be
used by any future app bundle. OpenGL is the first compatibility target; Vulkan through
MoltenVK and other backend parity remain explicit validation TODOs.

The inherited upstream policies,
[`docs/dev/macos-support-matrix-policy.md`](macos-support-matrix-policy.md) and
[`docs/dev/macos-renderer-backend-policy.md`](macos-renderer-backend-policy.md),
still describe openQ4's macOS preview and are the starting point if openPR06 ever
ungates macOS. In upstream terms: packages are `arm64 only`, signed off on the
`macOS 11` floor and the latest public macOS release; Intel Mac, universal2 and
Rosetta are not release targets; the two package variants are OpenGL and a
Metal bridge, which is not a native Metal renderer; and the legacy native backend is
comparison-only and not a supported release backend. None of this is an openPR06
claim until the macOS lanes are rebuilt and backed by PREY runtime evidence.

## Validation requirements

First-class support for a platform requires all of the following on real target
hardware:

1. clean configure, compile, and staged install;
2. architecture and runtime-dependency checks for client, dedicated server, renderer
   modules, and unified game module;
3. launch from `.install/` with a legitimate Prey installation;
4. SP map entry, MP listen/dedicated startup, save/load, input, audio, and clean shutdown;
5. logs free of new engine/game/parser/loader errors;
6. renderer validation using the engine `screenshot` command, never an OS capture;
7. package extraction/install and launcher/icon checks;
8. evidence tied to the exact source commit.

All agent-driven runtime validation must force `+set r_fullscreen 0`.

Current outstanding evidence is tracked in
[the rebase status ledger](prey-rebase/status-ledger.md#explicit-deferral-register).
