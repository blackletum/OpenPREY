# Release status

**The latest release is [0.15.0, the First Contact Edition](https://github.com/themuffinator/openPR06/releases/tag/v0.15.0)**,
openPR06's first. Status checked on 22 November 2026.

The nightly builds from April 2026 further down the
[Releases page](https://github.com/themuffinator/openPR06/releases) predate
openPR06's move onto the openQ4 engine and the in-tree PREY game library, so
they don't match these guides. Please don't report bugs against them.

## Getting openPR06 today

1. Keep your legitimate copy of **PREY (2006)** where it is installed. openPR06
   ships no PREY game data.
2. Download the [latest release](https://github.com/themuffinator/openPR06/releases/latest)
   for your platform: the Windows installer (`-setup.exe`) or zip, the Linux
   `.tar.xz` or AppImage, or the macOS `openPR06.app` archive (see the table
   below). Install or extract it into a folder of its own: the client, the
   dedicated server, the renderer modules, and `basepr/` with the unified
   `game_<arch>` module and openPR06's own packs. To build it yourself instead, follow
   [BUILDING.md](../../BUILDING.md); the staged package lands in `.install/`.
3. Launch `openPR06-client_x64` (`.exe` on Windows, `_arm64` on ARM64), the
   AppImage, or `openPR06.app`. openPR06
   finds a CD-era or other retail install through the registry, App Paths and
   uninstall entries and the usual install folders. If it doesn't, point it at
   the folder that contains `base`:

   ```text
   openPR06-client_x64 +set r_fullscreen 0 +set fs_basepath "C:\path\to\Prey"
   ```

[Getting Started](getting-started.md) covers the details.

## Platforms

Active CI (`.github/workflows/openpr06-validation.yml`) builds the engine,
dedicated server, OpenGL and Vulkan renderers and the unified game module on
Windows x64, Linux x64, macOS Apple silicon (OpenGL and Metal bridge) and macOS
Intel on every push. Releases come from
`.github/workflows/manual-release.yml`, adapted from openQ4's, on openQ4's
platform set. Every release lane builds, stages, validates and packages the
unified `game_<arch>` module and `basepr/`, but only Windows x64 has had real
PREY play-testing. openQ4's Android APK and signed update channel are not part
of openPR06 releases.

| Platform | Build | Runtime testing | Package |
|---|---|---|---|
| Windows x64 | Built in CI | Deepest testing: representative campaign maps, save/load and a two-client listen server | Installer (`-setup.exe`) and zip, with PDB symbols |
| Windows ARM64 | Release lane (`windows-11-arm`) | None yet | Installer and zip, with PDB symbols |
| Linux x64 | Built in CI | Retail gameplay validation still pending | `.tar.xz` and `x86_64` AppImage, with detached debug symbols |
| Linux ARM64 (preview) | Release lane (`ubuntu-24.04-arm`) | None yet on real hardware | `-preview` `.tar.xz` and `aarch64` AppImage, with detached debug symbols |
| Steam Deck / SteamOS | `openPR06-steamdeck` launcher staged by Linux builds | Inherited from openQ4, not yet checked with PREY | In the Linux x64 package |
| macOS, Apple silicon (preview) | Built in CI; release lane (`macos-15`), OpenGL and Metal-bridge variants | None yet | Unsigned, unnotarized `openPR06.app` in `-unsigned.tar.gz`, with dSYM symbols. See [macOS Support Data](macos-support-data.md) to report a run |
| Android | Inherited openQ4 sources; the GLES renderer and Android host aren't ported to PREY | None | Not supported |

The [platform support roadmap](../dev/platform-support.md) lists the evidence a
platform needs before openPR06 claims it.

## What works and what doesn't

**Landed**

- PREY install discovery for CD-era installs, without depending on Steam or GOG.
- One `game_x64` module, built from the in-tree PREY SDK game library, for
  single-player and multiplayer.
- Retail base-pack validation. The consolidated retail layout is
  checksum-verified; CD-era numbered packs are checked for presence until their
  checksums are recorded.
- OpenGL rendering on PREY's original interaction stages, and baked
  [light grids](light-grids.md).

**Tested, but not signed off**

- Single-player: the stock menu and representative maps, including Roadhouse,
  Feeding Tower, the deathwalk, Shuttle and portal gameplay, plus save/load.
- Multiplayer: a listen server with two clients. See
  [Multiplayer Networking](multiplayer-networking.md).
- Vulkan (`r_renderApi vulkan`): reaches gameplay on focused Roadhouse and
  Biolabs runs, without full PREY feature parity.
- Multiplayer bots, which are experimental. See the
  [bot guide](../dev/mp-bots.md).

**Not yet claimed**

- Full single-player campaign completion on stock assets.
- Multiplayer parity with the retail game.
- Retail parity for the restored Doom 3/PREY-era particle, FX and beam paths.

**Unavailable in the current baseline**

- Multi-view demos and voice chat need game-API calls PREY's v7 game module
  doesn't have. See [Multi-View Demos](multiview-demos.md) and
  [Multiplayer Chat](multiplayer-chat.md).
- Mods built for the original proprietary PREY game DLLs don't load.

## About the other guides

Most guides in this directory describe engine features carried over from
openQ4: shadow maps, cel shading, temporal AA, screen-space lighting, PBR
materials, DDS texture replacements, the level-load cache, VR, controller
support and the server tools. Each one opens with a note saying it has not yet
been checked against PREY. They describe what the engine code does; PREY
behaviour stays validation-pending until the
[rebase status ledger](../dev/prey-rebase/status-ledger.md) records evidence
for it.

The [Technical Reference](../../TECHNICAL.md) holds the full compatibility
status, and the [release completion list](../dev/release-completion.md)
collects work for the first release's changelog. Neither announces a release.
