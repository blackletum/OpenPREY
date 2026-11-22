# Android and SigmaTouch integration

The Android platform layer and Quake 4 touch adapter were contributed by
[Emile Belanger (emileb)](https://github.com/emileb/openQ4/tree/android), building
on his [GLES shader variants](https://github.com/emileb/openQ4/tree/gles-shader-variants).
The imported openQ4 adapter sources use this repository's GPL-3.0-or-later
license. Their original attribution is retained in each source file.

Android builds default to a standalone SDL3 host and export `SDL_main` from
`libopenpr06.so`. An SDLActivity-based application must load SDL3 first, supply
the native library directory through `OPENQ4_NATIVE_LIBS`, and pass the folder
that holds the user's PREY `base/` with `+set fs_basepath`. Saves default to
SDL's app-private internal storage, or `USER_FILES/quake4` when supplied by a
host. The unified `libgame_<arch>.so` module serves single player and
multiplayer, with openPR06's content in `basepr/`.

`quake4_bridge.h` and `touch_interface_quake4.cpp` keep their names: the
`Quake4_*` functions are the C ABI the external SigmaTouch host links against,
and every action they post (`_attack`, `_zoom`, `_weaponWheel`, `_showScores`
and the movement buttons) exists in Prey's usercmd table
(`src/framework/UsercmdGen.cpp`). SigmaTouch builds still pass
`ENGINE_NAME="quake4"` to that host; an openPR06 SigmaTouch host would need its
own name and has not been built.

SigmaTouch is optional and selected with `OPENQ4_SIGMATOUCH` by the build system.
The host supplies Clibs_OpenTouch, MobileTouchControls, its existing touch art,
SDL3, OpenAL and SAF support. These third-party host sources and assets are not
included in openQ4. The adapter retains Emile's configurable touch layout and
action-based controls, so rebinding a physical key does not break touch buttons.
It synchronizes UI-thread callbacks with engine-thread input, releases held
touch controls on focus loss or queue overflow, and uses openQ4 language tables
for the touch editor's labels.

## External host licensing

[MobileTouchControls' license](https://github.com/emileb/MobileTouchControls/blob/master/License.txt)
states GPLv2 without an explicit later-version grant and directs users to Emile
Belanger for another license. That published grant does not establish
compatibility with this GPLv3 engine. The public
[Clibs_OpenTouch repository](https://github.com/emileb/Clibs_OpenTouch) also lacks
a top-level license grant. A combined SigmaTouch build therefore requires
separately obtained GPLv3-compatible grants for those host components and their
dependencies before redistribution. Merely enabling the build option does not
supply those rights. Standalone Android builds do not depend on either library.

`python tools/tests/android_touch_input.py` runs a native in-memory harness over
the adapter's actual input code. It does not launch the game or generate device
mouse, keyboard, or touch events. Android gameplay and host lifecycle validation
still require a device and an appropriately licensed host.
