# openPR06 Release Completion List

Use this file as the source list for release changelog entries.

**Candidate release, 21 November 2026:** the first real release is being
curated as **0.15.0, the First Contact Edition**, numbered alongside openQ4
0.15.0, whose engine it ships. The player-facing draft is
[releases/v0.15.0.md](releases/v0.15.0.md); it draws on
[releases/unreleased.md](releases/unreleased.md) and supersedes the
[0.0.1 draft](releases/v0.0.1.md). Keep it in step with any entry added
before the release is cut. To cut it:

- `.github/workflows/manual-release.yml`, adapted from openQ4's on 22 November
  2026, builds and publishes openQ4's desktop platform set: Windows x64 and
  ARM64, Linux x64 and ARM64 (preview) with AppImages, and macOS ARM64 OpenGL
  and Metal-bridge variants (unsigned preview). Merge `release/0.15.0` into
  `main`, run the workflow from `main` with `version_override=0.15.0` and
  `draft=true`, check the draft's assets, then publish it.
- Android is not part of 0.15.0. Since 22 November 2026 the build works: the
  GLES module has its own ARB-program hooks, the host is openPR06's
  (`libopenpr06.so`, the unified `libgame_arm64.so`, `basepr/`, application
  ID `com.darkmatter.openpr06`, setup that checks a PREY `base/` in either
  retail layout), and a push-triggered CI probe ran the native build, Gradle
  `assembleRelease` and `verify_android_apk.py` on a CI-signed APK. What is
  left before `manual-release.yml` gets openQ4's "Android APK" lane
  (`uses: ./.github/workflows/android-build.yml`, `signing: release`):
  - **Signing (maintainer):** create an Android release key, keep an
    independent secure backup (every later update must use the same key), add
    the repository secrets `ANDROID_RELEASE_KEYSTORE_BASE64` (the PKCS#12
    keystore, base64), `ANDROID_RELEASE_STORE_PASSWORD`,
    `ANDROID_RELEASE_KEY_PASSWORD` and `ANDROID_RELEASE_KEY_ALIAS`, and commit
    its public certificate as `mobile/android/release-signing-cert.pem`
    (`keytool -exportcert -rfc`). The lane then passes the secrets with
    `secrets: inherit` and needs the release's content-pack artifact, as
    openQ4's does.
  - **Device testing:** no openPR06 APK has run on a device. Install, setup
    with a real PREY `base/` folder (CD and digital layouts), a single-player
    map, multiplayer, touch controls, suspend/resume and the GLES renderer's
    output on PREY maps all remain untested; the GLES module draws no retail
    ARB-program interaction stages yet.
  See [android-build.md](android-build.md#openpr06-status).
- Pass the version explicitly (`version_override=0.15.0`). The automatic bump
  gives `0.15.000`.
- A local clone that fetched the `openq4-upstream` remote carries openQ4's
  release tags (`v0.13.0` to `v0.14.1`), and the release tooling then takes
  `v0.14.1` as the previous openPR06 release. `origin` has no such tags, so a
  CI checkout is unaffected; check before running the tooling locally.
- [LICENSING.md](../../LICENSING.md) leaves the distribution of the linked
  GPL engine and SDK-EULA game module as an open question, and asserts no
  answer to it. The maintainer accepted publishing the binaries on that basis
  on 22 November 2026, as openQ4 does with its SDK-derived game code.
- The release is not announced on Discord: `discord-release.yml` stays off
  until the repository opts in.

Process:
1. Add completed work under "Ready For Changelog".
2. When cutting a release, move shipped items into release notes.
3. Keep remaining work in "Carry Forward".

## Ready For Changelog

- [x] Repository rebranded from OpenQ4 to openPR06 at Meson/project tooling level.
- [x] Canonical companion game sources now stage directly from `OpenPrey-game`; companion copies of engine/SDK headers are excluded.
- [x] Legacy external companion-repo build references removed from active build/docs/tooling paths.
- [x] VS Code tasks/launch settings refreshed for openPR06 naming.
- [x] Documentation set refreshed for openPR06 migration scope.
- [x] `fs_basepath` auto-discovery switched from Quake 4 Steam/GOG assumptions to Prey CD-era registry + legacy-path discovery.
- [x] Game-module loader/build updated to use a unified Prey module (`game_<arch>`) for both SP and MP paths.
- [x] Root Meson builds and stages one unified `game_<arch>` module from `src/game`, `src/Prey`, and `src/preyengine` in the companion repository.
- [x] Engine Session/Async `idGame` call sites aligned to current Prey game API signatures to unblock engine target compilation.
- [x] Meson build graph updated so `-Dbuild_games=false` no longer compiles game-idlib targets, allowing clean engine-only validation builds.
- [x] Runtime packaging keeps `basepr/game_<arch>` loose and assembles openPR06-owned content as `basepr/pak0.pk4` and `basepr/pak1.pk4`.
- [x] Archive/AppImage tooling is rebranded for openPR06 and retains explicit Wayland/X11 runtime boundaries.
- [x] Active validation builds the unified game-module layout on Windows x64 and Linux x64; inherited split-module workflow fixtures are manual-only and unconditionally disabled pending a clean openPR06 redesign.
- [x] Prey game library imported in-tree under `src/game`, `src/Prey`, and `src/preyengine` with its history, under the Prey SDK EULA (`LICENSES/PREY-SDK-EULA.rtf`); configure-time companion staging and its helper scripts removed.
- [x] Engine merged forward to current upstream OpenQ4 `main`.

## Carry Forward

- [ ] Validate default launch/map flow for Prey SP and MP in staged `.install/` runs.
- [ ] Finalize classic `pak000..pak004` checksum baseline (consolidated `pak_data/pak_sound/pak_en_*` baseline is now published).
- [ ] Continue reducing inherited Quake 4-specific assumptions in runtime/gameplay paths.
- [ ] Complete gameplay/runtime verification of the in-tree `src/Prey` and `src/preyengine` trees.
- [ ] Complete retail parity checks for the restored Doom 3/Prey particle, FX, and beam paths.
- [ ] Extend CI/runtime checks for openPR06-specific smoke tests.
- [ ] Rebuild the nightly publication lane (the manual release lane, AppImages included, was rebuilt for 0.15.0 on openQ4's desktop platform set). The AppImage still has no Wayland/X11 runtime smoke: it needs an assetless startup PREY's game module does not offer.
- [ ] Before any macOS package ships: macOS floor-version evidence is recorded for the documented `macOS 11` floor under the inherited `docs/dev/macos-support-matrix-policy.md`, and its notes do not imply native Metal or native Cocoa/OpenGL backend support (`docs/dev/macos-renderer-backend-policy.md`).
