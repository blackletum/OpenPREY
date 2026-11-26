# Building openPR06 from Source

This guide covers building openPR06 on Windows and Linux, the two x64 platforms CI builds. The build files also cover macOS hosts, but macOS isn't supported yet: nothing builds or tests it for openPR06.

> [!NOTE]
> openPR06 has no published release yet, so building from source is currently the only way to run it. You also need your own copy of Prey (2006); see [Getting Started](docs/user/getting-started.md).

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [In-tree Game Sources](#in-tree-game-sources)
- [Build Setup](#build-setup)
- [Build Options](#build-options)
- [Validation Scripts](#validation-scripts)
- [Building on Windows](#building-on-windows)
- [Building on Linux / macOS](#building-on-linux--macos)
- [Output Files](#output-files)
- [Packaging a Distributable](#packaging-a-distributable)

---

## Prerequisites

### Compiler

| Platform | Minimum | Notes |
|---|---|---|
| **Windows x64** | MSVC 19.46+ (Visual Studio 2026+) | Use the Developer PowerShell or run `tools/build/openpr06_devcmd.cmd` to initialise the environment |
| **Linux x64** | GCC 13+ or Clang 17+ | Distro packages are fine |

### Build Tools

- **[Meson](https://mesonbuild.com/)** 1.6.0 or newer
- **[Ninja](https://ninja-build.org/)** (recommended backend)
- **Python 3** (used by the build wrapper scripts, `tools/build/sync_icons.py`, the `basepr/pak0.pk4` and `basepr/pak1.pk4` pack builds, and the code generators)

### Linux System Packages

The engine links against the system OpenGL and OpenAL libraries, and SDL3, which builds from its Meson subproject, needs the usual Linux desktop development headers for X11, Wayland, input and audio. On Ubuntu 24.04 this is the set the Linux CI lane installs:

```bash
sudo apt-get install binutils libasound2-dev libdbus-1-dev libdecor-0-dev libdrm-dev libegl1-mesa-dev libfribidi-dev libgbm-dev libgl1-mesa-dri libgl1-mesa-dev libglx-mesa0 libibus-1.0-dev libjack-dev libopenal-dev libpipewire-0.3-dev libpulse-dev libsndio-dev libthai-dev libudev-dev libwayland-dev libx11-dev libxcursor-dev libxext-dev libxfixes-dev libxi-dev libxkbcommon-dev libxrandr-dev libxss-dev libxtst-dev libxxf86dga-dev libxxf86vm-dev
```

A Wayland-only build (`-Dlinux_x11=disabled`) can do without the X11 packages. Other distributions package the same libraries under their own names.

### Windows Note

On Windows, always invoke Meson through `tools/build/meson_setup.ps1` rather than calling `meson` directly from an arbitrary shell. The wrapper ensures MSVC tools (`cl.exe`, `link.exe`, etc.) are on `PATH` and synchronises the icon set before setup, compile, and install steps.

```powershell
# Open a regular PowerShell window and use the wrapper:
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 <meson-command> [args...]
```

Alternatively, open `tools/build/openpr06_devcmd.cmd` first to initialise the Visual Studio environment, then call `meson` directly.

### Windows OpenAL Runtime

Windows builds link against OpenAL, so the client needs `OpenAL32.dll` beside it. The DLL isn't in the repository. After `compile` and `install`, the `meson_setup.ps1` wrapper copies it into `builddir/` and `.install/`, and stops with "OpenAL32.dll runtime not found" when it has none. It takes the DLL from `<OPENPR06_OPENAL_ROOT>\bin\OpenAL32.dll` when that environment variable is set, and from `src\external\openal-soft\bin\win64\OpenAL32.dll` otherwise.

Prepare one once per checkout, the way CI does:

```powershell
# Downloads and builds OpenAL Soft 1.25.2 into .tmp\openal-soft-windows-x64\ (bin\, lib\ and include\).
# Needs network access and the Visual Studio C++ tools, including CMake.
powershell -ExecutionPolicy Bypass -File tools/build/prepare_windows_openal.ps1 -Architecture x64

# Point the wrapper at it in each shell you build from...
$env:OPENPR06_OPENAL_ROOT = (Resolve-Path .tmp\openal-soft-windows-x64).Path

# ...or copy the DLL to the location the wrapper checks by default.
New-Item -ItemType Directory -Force src\external\openal-soft\bin\win64 | Out-Null
Copy-Item .tmp\openal-soft-windows-x64\bin\OpenAL32.dll src\external\openal-soft\bin\win64\
```

To link against a different OpenAL package, pass `-Dopenal_root_override=<path>` (a folder with `include\` and `lib\`) at configure time, and set `OPENPR06_OPENAL_ROOT` to the same folder so its `bin\OpenAL32.dll` is staged.

---

## In-tree Game Sources

openPR06's game library builds from this checkout. The SDK-derived trees are
`src/game/`, `src/Prey/` and `src/preyengine/`; they compile into the unified
`game_<arch>` module against the engine headers in the rest of `src/`. Clone
**openPR06 only**: no companion checkout, staging step or environment variable
is needed. The former `OpenPrey-game` companion repository is historical; its
history is a merge parent of the import commit.

The game trees stay under the PREY SDK EULA while the engine is GPLv3. See
[LICENSING.md](LICENSING.md) for the boundary and
[docs/dev/game-source-provenance.md](docs/dev/game-source-provenance.md) for the
import record.

Meson compiles the game sources directly. Before each build, the wrappers
compare `builddir/openq4_game_sources.json` with the source tree. Adding or
removing a game source file reconfigures Meson; editing one, or committing,
only refreshes the snapshot's hashes and Git identity in place, since Ninja
already rebuilds edited files. The module is built into `builddir/basepr/` and
staged into `.install/basepr/`. The `build_game_sp` and `build_game_mp` options
are accepted for compatibility only: the one module always provides both
single-player and multiplayer.

---

## Build Setup

Third-party libraries come from Meson subprojects (`subprojects/`) and vendored sources (`src/external/`): SDL3, GLEW, libogg, libvorbis, stb_vorbis, zlib-ng, glslang, RmlUi, JsonCpp, libtess2 and the OpenXR SDK, plus a prebuilt OpenAL Soft runtime on Windows. With `--wrap-mode=forcefallback`, the first configure step unpacks and builds the subprojects, so Windows needs nothing installed beyond the compiler, the build tools and the [OpenAL runtime](#windows-openal-runtime). Linux also needs the [system packages](#linux-system-packages) above.

On Linux the default SDL3 backend always uses the bundled GLEW. SDL3 must be at least 3.4.4; the bundled wrap is SDL3 3.4.18. `-Dlinux_x11=disabled` builds the native Wayland/EGL-only path without SDL's X11 driver, and an explicit `enabled` or `disabled` value forces the bundled SDL so the requested driver set is honoured; `auto` may use a suitable system SDL. The transitional `-Dplatform_backend=native` path needs the X11 and VidMode (`libxxf86vm-dev`) development packages and can use a system GLEW (`libglew-dev`) instead of the bundled one.

Meson copies a wrap's `patch_directory` only when it first extracts that subproject. After pulling changes under `subprojects/packagefiles/sdl3/`, an existing ignored `subprojects/SDL3-*` tree can therefore keep stale build definitions even after `setup --wipe`. Refresh that extraction before rebuilding; this matters most when validating `-Dlinux_x11=disabled`, because stale SDL definitions can silently keep the X11 libraries:

```bash
bash tools/build/meson_setup.sh subprojects purge --confirm sdl3
```

```powershell
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 subprojects purge --confirm sdl3
```

Then rerun the normal `setup --wipe`, compile, and install steps. The purge removes the generated SDL source extraction, not `subprojects/packagefiles/sdl3/` or the configured build directory.

The same holds for the `diff_files` patches Meson applies at extraction, such as `subprojects/packagefiles/jsoncpp/subnormal-numbers.patch`. When a wrap file changes, Meson only warns that the subproject "may be out of date", and the existing `subprojects/jsoncpp-1.9.8` tree keeps its old sources. Re-extract it in place through the same wrapper with `subprojects update --reset jsoncpp` before rebuilding.

---

## Build Options

Pass any of these with `-D<option>=<value>` on the `meson setup` command line:

| Option | Default | Description |
|---|---|---|
| `build_engine` | `true` | Build `openPR06-client_<arch>` and `openPR06-ded_<arch>` |
| `build_games` | `true` | Build the unified game module from the in-tree game sources |
| `build_renderer_gl` | `true` | Build the OpenGL renderer module (`renderer-gl_<arch>`) |
| `build_renderer_vk` | `true` | Build the Vulkan renderer module (`renderer-vk_<arch>`) |
| `openxr` | `auto` | Build OpenXR VR support into the SDL3 client on Windows and Linux |
| `platform_backend` | `sdl3` | `sdl3`; or `legacy_win32` on Windows and `native` on Linux, both transitional |
| `linux_x11` | `auto` | SDL3's X11/XWayland driver on Linux; `disabled` gives a Wayland-only build |
| `use_pch` | `true` | Use precompiled headers |
| `idlib_asserts` | `false` | Compile idlib `assert()`/`verify()` into live checks on GCC/Clang; a firing assert stops the process |
| `version_track` | `dev` | Build track label (`stable`, `dev`, `beta`, `rc`) |
| `version_iteration` | *(empty)* | Dot-separated iteration counter for pre-release builds |
| `version_base_override` | *(empty)* | Override the generated version without editing `meson.build` |
| `enforce_msvc_2026` | `false` | Fail configure if MSVC is older than 19.46+ (Windows only) |

`meson_options.txt` lists the rest. Options for Android, OpenGL ES and macOS are carried over from openQ4 and aren't used by openPR06.

---

## Validation Scripts

openPR06 includes local validation profiles under `tools/validation/`. They share one Python runner, `tools/validation/openq4_validate.py` (the file keeps its upstream name as a compatibility entry point), and use the platform build wrappers so Windows validation still goes through `tools/build/meson_setup.ps1`.

The Python checks are independent and run concurrently, as many at once as the machine has CPUs, with each check's output printed in list order. Pass `--python-jobs N` to change that, and `--python-jobs 1` to run them one at a time. Inherited checks that still encode openQ4-only contracts (split game modules, openQ4 release lanes, macOS policy) are excluded from the list, as are the `deferred-release-lane` and `pending-source-port` scripts in `tools/tests/suite_status.json`.

GitHub Actions runs `.github/workflows/openpr06-validation.yml` on every push, pull request and manual dispatch. Its **Scaffold and Content Contracts** job compiles the build scripts, checks the icon set, the game source inventory and the content pack table, runs the rebase, video-menu, sanitizer and source-charset contracts, checks the full-suite skip list, and builds `pak0.pk4` and `pak1.pk4` from `content/basepr/`. Its **Unified GameLib** jobs build a debug engine, dedicated server, both renderer modules and the `game_<arch>` module on Windows x64 and Linux x64, stage `.install/`, and check the staged payload. CI does not run the `tools/validation/` profiles, and no job starts the client or the dedicated server. The workflows inherited from openQ4 are named `DISABLED`, can only be dispatched manually, and every job in them is gated off; see `.github/workflows/README.md`.

### Full Test-Suite Run

To run every script in `tools/tests/` and see only new breakage, use `tools/validation/run_test_suite.py`. It runs the scripts concurrently (half the CPUs by default; `--jobs N`), writes each one's output to `.tmp/test-suite/<name>.log`, and exits non-zero only when a script outside `tools/tests/suite_status.json` fails:

```powershell
cmd /c "call tools\build\openpr06_devcmd.cmd >nul && python tools\validation\run_test_suite.py"
```

```bash
python tools/validation/run_test_suite.py
```

Run it from a Visual Studio developer environment on Windows so the C++ harness tests find a compiler; a full run takes about half an hour. Pass script names to run only those. `suite_status.json` lists the scripts a bare run cannot judge, in groups that are skipped unless named with `--include`:

- `deferred-release-lane`: inherited openQ4 macOS, packaging and release-lane fixtures kept for the lane rebuild (`TODO-RELEASE-LANES` in `docs/dev/prey-rebase/status-ledger.md`).
- `pending-source-port`: tests that are right to fail because openPR06's source still lacks the upstream change they check; the group's reason names the gap.
- `needs-arguments`: Meson build helpers and harness drivers that take arguments.
- `needs-runtime`: checks that need a staged build, retail assets, a device or another platform.

It also gives a handful of slow mutation tests a longer limit than the default 600 seconds. When you port a listed script, take it off the list (the runner names listed scripts that pass); `tools/tests/suite_status_contract.py` checks that every entry still exists. Run scripts without `python -I`: many import their siblings. Tests that read Quake 4 game code, Quake 4 content or openQ4-only workflows are deleted rather than listed (issue #62).

### IPv4 Networking Self-Test

After building the engine, run the no-argument `netIPv4SelfTest` command from the openPR06 console:

```text
netIPv4SelfTest
```

This developer diagnostic checks strict numeric IPv4 parsing, DNS-enabled
`localhost`, invalid ports, and isolated network-CVar handling. It binds an
explicit `127.0.0.1` high port plus an ephemeral sender, verifies initialized
counters and bidirectional payloads, accepts an exact-capacity datagram, rejects
an oversized datagram without losing the following marker, and exercises socket
close/reopen. A successful run ends with `IPv4 network self-test: passed`; any
failed check ends with `IPv4 network self-test: FAILED` and should be treated as
a validation failure.

The self-test is local and non-destructive. It does not prove public
reachability, router NAT or firewall configuration, external DNS records,
master-server availability, or end-to-end internet play; validate those
separately when they are relevant to a change.

### IPv6 Networking Self-Test

Run the no-argument `netIPv6SelfTest` command from the openPR06 console:

```text
netIPv6SelfTest
```

This developer diagnostic checks bracketed and unbracketed IPv6 literals,
rejected malformed endpoints, IPv4-mapped normalization, canonical RFC 5952
text and its round-trip through the parser, and LAN classification of loopback
and link-local addresses. It then binds an IPv6-only receiver and sender on
`::1` so every datagram provably crosses the IPv6 socket, verifying initialized
counters and bidirectional payloads, an exact-capacity datagram, rejection of an
oversized datagram without losing the following marker, and socket
close/reopen. A final dual-stack check binds one port and confirms it receives
over both families. A successful run ends with
`IPv6 network self-test: passed`; any failed check ends with
`IPv6 network self-test: FAILED` and should be treated as a validation failure.

A host with IPv6 disabled is a supported configuration: the parsing and
formatting checks still run, and the transport section reports that it was
skipped rather than failing.

The same limitations apply as for IPv4: the IPv6 self-test is local and
non-destructive, and does not prove public reachability, firewall
configuration, external DNS records, or end-to-end internet play.

### macOS Static Validation

The `macos-static` profile is carried over from openQ4. It runs the same Python checks as the push profile, a `bash -n` syntax check of the build wrapper, the validation wrappers and the macOS helper scripts, and dry runs of the push and PR profiles. It does not run openPR06 on macOS, and because the macOS policy checks it was built around are excluded in openPR06, it says little about macOS.

```powershell
powershell -ExecutionPolicy Bypass -File tools/validation/validate_macos_static.ps1
```

```bash
bash tools/validation/validate_macos_static.sh
```

You can also call the shared runner directly:

```bash
python tools/validation/openq4_validate.py macos-static
```

When shared renderer code changed, renderer self-test binaries may be run only on an available non-macOS host after a local build/stage:

```bash
python tools/validation/openq4_validate.py macos-static --runtime --runtime-cases renderer-default-safety-selftest --runtime-tiers auto --runtime-basepath "" --runtime-skip-official-pak-validation
```

### Push Validation

Use this before pushing local work. It runs the Python checks, reconfigures/reuses `builddir/` as a debug build, compiles the engine plus the game module, and runs the Meson native tests.

```powershell
powershell -ExecutionPolicy Bypass -File tools/validation/validate_push.ps1
```

```bash
bash tools/validation/validate_push.sh
```

The Python checks run before Meson setup, and a few native UI checks compile the jsoncpp and libtess2 wrap sources. On a fresh checkout they fetch those with `meson subprojects download` (`tools/tests/wrap_sources.py`), and they re-extract a tree whose wrap file has changed since Meson extracted it, so Meson must be installed even for `--skip-build` runs.

### PR Validation

Use this before opening or updating a pull request. It performs a clean debug build in `.tmp/validation/pr-builddir`, stages `.install/`, and verifies the staged runtime payload: the `openPR06-client_<arch>` and `openPR06-ded_<arch>` executables, one unified `basepr/game_<arch>` module and no split `game-sp`/`game-mp` modules, `basepr/mod.json` and every pack in `tools/build/content_packs.json`, no loose content in `basepr/` that belongs in a PK4, Windows diagnostic PDBs, no build-only linker artifacts and, on Linux, the launcher and desktop metadata, ELF hardening and runtime dependencies.

```powershell
powershell -ExecutionPolicy Bypass -File tools/validation/validate_pr.ps1
```

```bash
bash tools/validation/validate_pr.sh
```

Useful options:

- Add `--runtime` to run the safe renderer startup validation matrix (`tools/tests/renderer_validation_matrix.py`) after the staged install. Pass `--runtime-basepath <path>` to point it at a Prey (2006) install.
- Add `--runtime-skip-official-pak-validation` with a targeted no-map runtime case when intentionally running an assetless engine-startup smoke without the retail Prey PK4s.
- The game module builds with the engine; the old `--build-gamelibs` switch is accepted only for command-line continuity.
- Validation defaults to the current checkout. `--game-libs-repo` is retained for isolated source fixtures.
- Use `--build-dir <path>` plus `--no-clean` to validate a specific existing build tree.

### Linux Sanitizer Validation

On Linux, use this ASan+UBSan build when touching memory-sensitive code, SDL event normalization, display/window geometry, staged source handling, or parser/launcher logic:

```bash
bash tools/validation/validate_pr.sh \
  --skip-python-tests \
  --no-install \
  --build-dir .tmp/validation/linux-sanitizer-builddir \
  --buildtype debugoptimized \
  --jobs 4 \
  --skip-test-suite locales \
  --extra-setup-arg=-Duse_pch=false \
  --extra-setup-arg=-Db_sanitize=address,undefined
```

Stage the instrumented client, then run the assetless native Wayland window lifecycle case from a Wayland session:

```bash
bash tools/build/meson_setup.sh install \
  -C .tmp/validation/linux-sanitizer-builddir \
  --no-rebuild \
  --skip-subprojects

ASAN_OPTIONS=halt_on_error=1:detect_leaks=0 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
SDL_VIDEO_DRIVER=wayland \
SDL_VIDEODRIVER=wayland \
LIBGL_ALWAYS_SOFTWARE=1 \
OPENPR06_WAYLAND_DISABLE_LIBDECOR=1 \
python tools/tests/renderer_validation_matrix.py \
  --cases sdl3-wayland-window-lifecycle \
  --tiers auto \
  --timeout 120 \
  --basepath "" \
  --skip-official-pak-validation \
  --output-dir .tmp/renderer-validation/sanitizer
```

No retail Prey assets are required, and the matrix forces windowed mode. The build still needs the normal [Linux system packages](#linux-system-packages). Sanitizer failures stop the run immediately. CI does not run this lane for openPR06: the inherited openQ4 sanitizer job is gated off, and `openpr06-validation.yml` runs only the platform-independent `tools/tests/linux_sanitizer_source_contract.py`.

Linux engine and game translation units disable only UBSan's `vptr` check. The runtime-loaded modules consume polymorphic engine interfaces, while engine code also consumes game interfaces whose key functions and RTTI are owned by those modules; instrumenting either side for `vptr` creates link-time RTTI references that cannot be resolved without changing the executable/module ABI or weakening the modules' `-z defs` contract. AddressSanitizer and all other requested UBSan checks stay enabled.

---

## Building on Windows

> [!NOTE]
> Windows builds use Meson's `b_vscrt=static_from_buildtype` policy, so openPR06 itself does not require a separate Visual C++ Redistributable install.

### VS Code Fast Build

Use **Build openPR06 (Meson Debug)**, the default build task in `.vscode/tasks.json`. It runs `.vscode/meson-task.ps1 fastbuild`: the Meson compile of `builddir/` through the wrapper, which lets Ninja skip unaffected code and pack targets, then `tools/build/check_staged_content_edits.py` to prune stale loose `basepr` content, then `tools/build/stage_fast_install.py` to copy only changed runtime files into `.install/` for the launch configurations.

`builddir/` is configured `debug`, the same build type the push validation profile uses, so the two share one tree without reconfiguring each other. The compile task reconfigures an existing `builddir/` whose build type has drifted from `debug`. `tools/tests/vscode_fast_build.py` pins this behaviour.

Use **Full Build and Stage openPR06 (Meson Debug)** when you intentionally need the full configure + compile + `meson install --no-rebuild --skip-subprojects` path. If you add or remove files under `content/basepr/pak0/` or `pak1/`, run **Configure openPR06 (Meson Debug)** once so Meson refreshes the pack dependency list; edits to existing content files are picked up by the fast build.

### VS Code Launch Configurations

The Run and Debug list has the main menu on OpenGL and on Vulkan, every single-player map, the multiplayer maps (each started as a deathmatch listen server with `+devmap`), and a dedicated server on `game/dmescher`. Each runs the client or dedicated server the build task stages into `.install/` and keeps its configuration, saves and logs in `.home/`.

Every launch sets `+set r_fullscreen 0`, `fs_game basepr`, `fs_savepath` to `.home/`, `fs_devpath` to `.install/`, and `logFile 2` with a per-mode log name. Only the two main-menu entries choose a renderer (`r_renderApi gl` or `vulkan`); the map entries use whatever the saved configuration selects. No launch sets `fs_basepath`: the engine's install discovery finds Prey (2006).

`.vscode/launch.json` is generated. Edit the map table in `.vscode/prey-maps.json`, then run the **Regenerate openPR06 Launch Configurations** task (`.vscode/generate-launch.ps1`). `tools/tests/vscode_fast_build.py` fails if a launch configuration stops forcing windowed mode, stops selecting `basepr`, or sets `fs_basepath`.

### Debug Build

```powershell
# 1. Configure
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 setup --wipe builddir . --backend ninja --buildtype=debug --wrap-mode=forcefallback

# 2. Compile
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 compile -C builddir

# 3. Run directly from builddir
builddir\openPR06-client_x64.exe +set r_fullscreen 0
```

### Optimized Build

```powershell
# 1. Configure
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 setup builddir . --backend ninja --buildtype=release --wrap-mode=forcefallback

# 2. Compile
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 compile -C builddir

# 3. Stage the runtime package into .install/
powershell -ExecutionPolicy Bypass -File tools/build/meson_setup.ps1 install -C builddir --no-rebuild --skip-subprojects
```

### From a Visual Studio Developer Command Prompt

Once the MSVC environment is initialised via `tools/build/openpr06_devcmd.cmd` you can call `meson` directly:

```batch
meson setup builddir . --backend ninja --buildtype=release --wrap-mode=forcefallback
meson compile -C builddir
meson install -C builddir --no-rebuild --skip-subprojects
```

---

## Building on Linux / macOS

> [!NOTE]
> Linux defaults to the SDL3 backend, which uses native Wayland in a Wayland session, including through `openPR06-steamdeck`. XWayland is selected only when `OPENPR06_FORCE_X11=1` or an SDL X11 video-driver override is set. `-Dplatform_backend=native` remains available as a transitional comparison path on Linux.
>
> macOS on Apple silicon is a preview. The release workflow builds it on `macos-15` with `-Dplatform_backend=sdl3 -Dmacos_openal_provider=system` and `-Dmacos_graphics_bridge=opengl` or `metal`, after `tools/build/prepare_macos_openal_soft.sh` and with MoltenVK staged by `tools/build/prepare_macos_moltenvk.sh`; nobody has played PREY on it yet. In that code SDL3 is the default platform path and does not link Carbon, `-Dmacos_graphics_bridge=metal` is a Metal bridge that keeps the OpenGL renderer and is not a native Metal renderer, and `-Dplatform_backend=native` on macOS is comparison-only and not a supported release backend. The upstream policies behind those paths are kept for reference and describe openQ4's releases, not openPR06's: [support matrix](docs/dev/macos-support-matrix-policy.md), [renderer and backend](docs/dev/macos-renderer-backend-policy.md), [native backend containment](docs/dev/macos-native-backend-containment-policy.md) and [OpenAL Soft provider](docs/dev/macos-openal-provider-policy.md).

### Debug Build

```bash
# 1. Configure
bash tools/build/meson_setup.sh setup --wipe builddir . --backend ninja --buildtype=debug --wrap-mode=forcefallback

# 2. Compile
bash tools/build/meson_setup.sh compile -C builddir

# 3. Run directly from builddir
./builddir/openPR06-client_x64 +set r_fullscreen 0
```

Use `-Dplatform_backend=native` during setup if you need to compare against the legacy Linux X11/GLX backend; it needs the extra packages listed under [Build Setup](#build-setup).

### Linux Packager Notes

openPR06 releases Linux x64 and an ARM64 preview, as `.tar.xz` archives and AppImages. For a local or downstream package, the tested target is the Ubuntu 24.04 userspace the CI lane uses, with Meson 1.6.0 or newer, SDL3 3.4.4 or newer (the bundled wrap is 3.4.18) and the [system packages](#linux-system-packages) above.

Package the default SDL3 backend with OpenGL plus Wayland/EGL support, and keep X11 available where practical for fallback and diagnostics. Document both SDL spellings for explicit driver selection, because users and SDL documentation may use either form:

- Native Wayland: `SDL_VIDEODRIVER=wayland` or `SDL_VIDEO_DRIVER=wayland`.
- X11/XWayland: `SDL_VIDEODRIVER=x11`, `SDL_VIDEO_DRIVER=x11`, or the project-specific `OPENPR06_FORCE_X11=1`.
- Wayland decoration fallback: `OPENPR06_WAYLAND_DISABLE_LIBDECOR=1` when libdecor causes startup or window-decoration issues.
- Wayland decoration preference: `OPENPR06_WAYLAND_PREFER_LIBDECOR=1` when a compositor behaves better with libdecor.
- Wayland window-operation diagnostics: `OPENPR06_WAYLAND_SYNC_WINDOW_OPS=1`; use only for troubleshooting because some compositors can block during window animations.

Legacy `OPENQ4_*` spellings of these variables are still read as temporary migration aliases.

The game sources compile directly from `src/game/`, `src/Prey/` and `src/preyengine/`. `builddir/openq4_game_sources.json` records their hashes and the Git identity of the checkout; keep it with build evidence rather than copying source trees into runtime packages. The install step stages `openPR06-steamdeck`, the `openpr06.desktop` and `openpr06-steamdeck.desktop` entries under `share/applications/`, and the icons under `share/icons/`.

`tools/build/package_linux_appimage.py` turns a packaged Linux release directory and its matching detached-symbol directory into an `openpr06-<version-tag>-x86_64.AppImage` (or `-preview-aarch64` for the ARM64 preview) with a `.zsync` beside it, using pinned `linuxdeploy` and `appimagetool` binaries and a fixed type-2 runtime. `.github/workflows/manual-release.yml` produces those inputs (the debug-symbol split and `tools/build/verify_linux_release_artifacts.py`) and builds the AppImages for each release. On hosts where FUSE mounting is unavailable, `APPIMAGE_EXTRACT_AND_RUN=1` runs an AppImage by extracting it first.

Before shipping a downstream package, run at least:

```bash
bash tools/validation/validate_push.sh --install
bash tools/validation/validate_pr.sh --runtime --runtime-cases renderer-default-safety-selftest,sdl3-x11-display-diagnostics --runtime-tiers auto --runtime-basepath "" --runtime-skip-official-pak-validation
```

### Optimized Build

```bash
# 1. Configure
bash tools/build/meson_setup.sh setup builddir . --backend ninja --buildtype=release --wrap-mode=forcefallback

# 2. Compile
bash tools/build/meson_setup.sh compile -C builddir

# 3. Stage the runtime package into .install/
bash tools/build/meson_setup.sh install -C builddir --no-rebuild --skip-subprojects
```

---

## Output Files

### Build directory (`builddir/`)

| File | Description |
|---|---|
| `openPR06-client_x64[.exe]` | Main engine executable |
| `openPR06-ded_x64[.exe]` | Dedicated server |
| `renderer-gl_x64[.dll/.so]`, `renderer-vk_x64[.dll/.so]` | OpenGL and Vulkan renderer modules |
| `basepr/game_x64[.dll/.so]` | Unified game module |
| `basepr/pak0.pk4` | openPR06 core runtime content pack |
| `basepr/pak1.pk4` | openPR06 interface artwork pack (clients only) |
| `basepr/mod.json` | openPR06 game-directory manifest |
| `openq4_game_sources.json` | In-tree game source inventory |

- `content/basepr/pak0/` and `pak1/` are compiled into deterministic `pak0.pk4` and `pak1.pk4` before the engine is built, as listed in `tools/build/content_packs.json`, and are checked out without end-of-line conversion so every platform packs the same bytes. The pack checksums are embedded in the executable so startup can reject missing or modified openPR06 packs. A pack that passes is recorded under `fs_cachepath` and hashed again only when its file changes.
- On Windows, import libraries (`.lib`), program databases (`.pdb`), and export files (`.exp`) may be present beside the binaries, notably in debug builds; the `.lib` and `.exp` files are development-only artifacts.

### Install directory (`.install/`)

After the install step, `.install/` holds the runtime package. Windows stages its OpenAL runtime; the Linux client relies on the system OpenGL/EGL, OpenAL, Wayland or X11, input and audio libraries:

```
.install/
├── openPR06-client_x64[.exe]   # Main executable
├── openPR06-ded_x64[.exe]      # Dedicated server
├── *.pdb                       # (Windows) diagnostic symbols
├── renderer-gl_x64.dll/.so     # OpenGL renderer module (the default)
├── renderer-vk_x64.dll/.so     # Vulkan renderer module (r_renderApi vulkan)
├── OpenAL32.dll                # (Windows) OpenAL Soft runtime
├── openPR06-steamdeck          # (Linux) Steam Deck launcher
├── share/                      # (Linux) desktop entries and icons
├── openPR06.ico / openPR06.icns
├── LICENSE, LICENSING.md, CONTRIBUTORS.md
├── licenses/                   # Third-party notices and the PREY SDK EULA
└── basepr/
    ├── game_x64.dll/.so        # Unified game module
    ├── pak0.pk4                # openPR06 core runtime content
    ├── pak1.pk4                # openPR06 interface artwork (clients only)
    └── mod.json                # openPR06 game-directory manifest
```

> [!NOTE]
> Do not distribute raw `buildtype=debug` artifacts in public packages. MSVC import libraries (`*.lib`) are development-only artifacts and are not required in the package.

Repo-authored runtime content lives under `content/basepr/pak0/` and `pak1/`; development-only fixtures stay in `content/basepr/dev/` and are not packed. `mod.json` and the game module stay loose beside the PK4s.

On Linux desktops, you can create a user desktop shortcut for the staged runtime after the install step:

```bash
bash tools/linux/install_desktop_launcher.sh
```

If Prey (2006) is not in a location that openPR06 can auto-detect, pass the retail install root that contains `base/`:

```bash
bash tools/linux/install_desktop_launcher.sh --basepath "/path/to/Prey"
```

---

## Packaging a Distributable

openPR06's releases come from `.github/workflows/manual-release.yml`; this section is for building the same packages by hand. The `meson install` step (via the wrapper) stages everything into `.install/`, which is the input for packaging.

`tools/build/package_release.py` (a compatibility entry point for `tools/build/package_nightly.py`) copies `.install/` into a package directory, writes `VERSION.txt` and an offline HTML documentation site under `docs/`, and archives the result as `openpr06-<version-tag>-<platform>-<arch>`, for example `openpr06-<version-tag>-windows-x64.zip` or `openpr06-<version-tag>-linux-x64.tar.xz`. The documentation step needs the `markdown` module (`python -m pip install markdown`). Package contents:

- `basepr/game_<arch>.(dll|so|dylib)` stays a loose runtime module beside `basepr/pak0.pk4`, `basepr/pak1.pk4` and `basepr/mod.json`
- Linux packages include the `share/applications` and `share/icons` payloads
- macOS packages include an `openPR06.app` launcher bundle that carries `basepr/`, the game module and MoltenVK inside it, with dSYMs in a separate `-symbols.tar.xz`

```powershell
python tools/build/package_release.py --platform windows --arch x64 --version 0.0.1 --version-tag 0.0.1 --output-dir .tmp\release-artifacts
```

A Windows x64 archive built this way from `.install/` has been produced, inspected and launched in isolation. The release workflow builds and checks every other format (the Windows installer, the Linux archive and [AppImage](#linux-packager-notes), and the macOS app bundle) but doesn't launch them, because CI has no PREY install.

To build the Windows installer from an already-packaged Windows directory, install [Inno Setup](https://jrsoftware.org/isinfo.php) and run:

```powershell
python tools/build/build_windows_installer.py --package-dir .tmp\release-artifacts\openpr06-0.0.1-windows-x64 --version 0.0.1 --version-tag 0.0.1 --arch x64 --output-dir .tmp\release-artifacts
```

`manual-release.yml` is rebuilt for openPR06; the inherited nightly publishing workflow is still disabled, as it was written for openQ4's split game modules and Quake 4 content and not adapted to the `OpenPrey-game`, `basepr`, and the unified module changes. Active CI (`openpr06-validation.yml`) builds and stages Windows x64 and Linux x64 on every push and pull request, and uploads no packages.

Builds that do not pin `version_base_override` resolve their version through `tools/build/openq4_version.py`. It starts from the `meson.build` floor (`0.0.1`) and raises it to the newest non-withdrawn `v*` tag when Git history is available, so a checkout that has fetched upstream openQ4's tags reports a higher version than the floor. An exported tarball without Git history uses the floor as-is.

---

[← Back to README](README.md)
