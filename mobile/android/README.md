# Standalone Android application

This SDL3 Activity hosts Emile Belanger's Android/GLES port without SigmaTouch.
It supports the engine's SDL gamepad, mouse and keyboard input, menu touch input
and experimental first-party gameplay touch controls. The configurable
SigmaTouch overlay remains an optional, separately licensed host.

## Release download

openPR06 does not publish an APK yet. The Android workflow builds and verifies
`openpr06-<version>-android-arm64-experimental.apk` for PREY (2006), but
`manual-release.yml` gains its Android lane only once the maintainer supplies a
release signing key (see [Release automation and signing](#release-automation-and-signing)
and [docs/dev/android-build.md](../../docs/dev/android-build.md#openpr06-status)).
The APK needs an ARM64 device with Android 7.0/API 24 or later and OpenGL ES
3.0, plus your own PREY retail files as described below. It has not yet been
tested on a device. The application ID is `com.darkmatter.openpr06`, so it
installs beside openQ4 and never shares its data.

Published APKs will use one persistent certificate for updates. A local debug
APK uses a different certificate; back up its private saves before uninstalling
it to switch to a release APK. Do not clear app data to update a release APK.

## Build locally

Build the native Android targets and run Meson install first, following
[the Android build guide](../../docs/dev/android-build.md). The staging directory
must contain exactly `lib/libopenpr06.so`, `lib/libSDL3.so`,
`lib/librenderer-gles_arm64.so`, the unified `lib/libgame_arm64.so` and their
shared dependencies (`libopenal.so`, `libc++_shared.so`), plus
`basepr/pak0.pk4` and the remaining staged packs.

Use Java 17 or 21, Gradle 8.12, and Android SDK platform 35. Supply the same SDL3
source tree used for the native library (currently SDL 3.4.18):

```sh
gradle -p mobile/android \
  --project-cache-dir=/absolute/path/to/openPR06/.tmp/android-gradle-project \
  -Psdl3SourceRoot=/path/to/SDL3-3.4.18 \
  -Popenq4Stage=/path/to/openPR06/.install/android/arm64-v8a \
  assembleDebug
```

Set `ANDROID_HOME` to an installed Android SDK, or set `sdk.dir` in the ignored
`mobile/android/local.properties`. The APK is written under
`builddir/android-apk/app/outputs/apk/debug/`. Native compilation stays in Meson;
Gradle only packages staged libraries and openPR06-owned overlays. The phone
package targets `arm64-v8a` and API 24 or later. The Gradle `-Popenq4*`
property names, the `com.darkmatter.openq4` Java package and the
`OPENQ4_*` host environment variables keep their upstream names so openQ4's
host changes still merge; the application IDs, labels and files are openPR06's.

The separate [diagnostic emulator build](../../docs/dev/android-build.md#diagnostic-emulator-build)
uses `-Popenq4Abi=x86_64` and its matching stage. It produces a debug APK under
`builddir/android-apk-emulator/`, uses application ID
`com.darkmatter.openpr06.emulator` and keeps separate saves/data. Release packaging
is disabled for that ABI; it is not a published phone upgrade.

The experimental [Meta Quest flavor](../../docs/dev/android-build.md#meta-quest-flavor)
packages an arm64-v8a stage configured with `-Dandroid_headset=true`; add
`-Popenq4Quest=true`. It uses application ID `com.darkmatter.openpr06.quest`,
builds under `builddir/android-apk-quest/` and declares itself an immersive
OpenXR headset app: setup opens as a 2D panel and the game in VR. Gradle
refuses a Quest stage without the property and the property without a Quest
stage. The emulator alone accepts `-Popenq4XrTestRuntime=<built
libopenq4-xr-test-runtime.so>`, a headset-free OpenXR runtime for its VR check;
no stage or release carries it.

Gradle uses a 4 GiB heap and at most two workers. PK4 assets are already
compressed archives and are stored directly in the APK to avoid redundant
compression and intermittent heap exhaustion during release packaging.

Meson installation writes `android-build.json` beside `lib/`; the host requires
that metadata and uses its native API as the APK's minimum Android version.
The supplied SDL Java source version must match the staged native SDL library.
Do not mix Java classes and native libraries from different SDL releases.

The APK version name comes from the staged `basepr/mod.json`, and its default
version code is `major * 1000000 + minor * 1000 + patch` (for example, `0.13.1`
becomes `13001`). Distributors publishing multiple APKs with the same engine
version, including prereleases, can provide an increasing
`-Popenq4VersionCode=<integer>`; preserve increasing codes across later releases.

Use an absolute `--project-cache-dir` path: Gradle resolves a relative path
against `mobile/android`, which can otherwise place generated cache files in
the source tree. Compiler and APK intermediates remain under `builddir/`.

The APK retains the full openPR06 overlay packs. First launch also
copies those packs into private storage;
allow room for both the APK and extracted content, plus the retail installation
and saves.

Install the APK and open **openPR06 setup**. Choose English, German, Spanish or
French, then **Choose game folder** and select `base` from your own PREY
installation (or the install folder that contains it). Either retail layout
works: the CD/DVD set `pak000.pk4` to `pak004.pk4`, or the digital set
`pak_data.pk4`, `pak_sound.pk4`, `pak_en_v.pk4` and `pak_en_t.pk4`. A subfolder
inside Downloads or a connected USB drive can hold the source files. Android's
picker grants read access to that folder; openPR06 copies the archives to its
app-specific storage and preserves the originals. No retail game data is
included in the APK.

Setup verifies the archives of whichever layout is present against the same
checksums as the engine (`officialPk4s` in `src/framework/FileSystem.cpp`),
checks their contents, then prepares the bundled files with progress. Patch
packs (`pak005.pk4` and later, `game0N.pk4`) are accepted by presence. **Cancel**
keeps completed archives; **Retry last operation** checks them and restarts the
unfinished archive. If Android or the document provider loses the folder grant,
choose the folder again. Low-space messages show the next file's requirement
and available bytes. Once ready, choose **Single player** or **Multiplayer**.
Completing work in the background never launches the game automatically.

For development, manual data placement still works. Open the launcher and use
**Check installed files** afterward:

```sh
adb install builddir/android-apk/app/outputs/apk/debug/app-debug.apk
adb shell mkdir -p /sdcard/Android/data/com.darkmatter.openpr06/files/base
adb push /path/to/Prey/base/. /sdcard/Android/data/com.darkmatter.openpr06/files/base/
adb shell am start -n com.darkmatter.openpr06/com.darkmatter.openq4.LauncherActivity
```

The native game Activity is internal; external launches use the setup entry
point. Both play buttons keep `ui_autoJoin` explicitly `0`. A setup language
choice reaches the next native launch; subsequent ordinary launches preserve
the game's language setting. The normal gamepad and keyboard bindings work in
gameplay. The standalone overlay supports independent move/look/fire contacts,
jump/crouch, weapon tap/hold selection and weapon-dependent reload/zoom. Physical
mouse/controller settings do not change touch motion. See the
[player guide](https://github.com/themuffinator/openQ4/blob/main/docs/user/android-setup.md#play-with-touch-controls) for the
current controls and remaining layout/setup limitations.

The setup screen also exports saved games or diagnostic logs through Android's
file picker. It prepares a ZIP from private save/log folders, including setup
diagnostics and an integrity inventory, before copying it to the chosen new
document. Cancellation and failures preserve the originals; a partial destination
may need removal in Files. See the [player guide](https://github.com/themuffinator/openQ4/blob/main/docs/user/android-setup.md)
for backup contents, limits, cloud-provider completion and upgrade guidance.

Setup also provides touch controls presets, a touch layout editor that moves,
resizes, fades and hides each control per orientation (`TouchLayoutPage`, with
`TouchLayout` porting the engine's placement), and an Interface page for the
viewing profile, menu size and text size. The game's Settings can reopen setup
during play, and its Controls page opens the layout editor directly. See the
[player guide](https://github.com/themuffinator/openQ4/blob/main/docs/user/android-setup.md) for these pages.
Save/log exports to local Downloads and an exported-save restore round trip
pass on the recorded S25 debug package. Physical folder-import providers,
accessibility and visual qualification are still required; host fixtures do
not establish those results. Leaving single player writes the `Suspended`
save, which the emulator lifecycle probe and a Galaxy S25 check restore after
`am kill`.

The Android Back button or gesture follows the game's menu/pause navigation.
Fatal-error screens accept touch release on density-scaled Copy, Clear and Quit
buttons; Back dismisses the error screen. Dragging more than 8 dp or lifting
outside the pressed button cancels its action. The fatal screen does not open
the on-screen keyboard. These input paths remain subject to physical-device
qualification as part of the experimental Android package.

On Android 11 and later, the SDL surface stays inside the display cutout, with
a black strip beside the camera hole. Rendering and input therefore share the
same content coordinates. Density changes keep the existing native Activity
session. The game plays in either landscape orientation unless the player
chooses Landscape and portrait on the Interface setup page; the Activity
applies that choice itself, because SDL would otherwise request every
orientation when it creates the engine's resizable window. In portrait the
touch controls form the thumb deck below the view. Physical portrait,
cutout, rotation and input qualification remain in progress.

Saves/configuration/logs live in private `files/saves/basepr/`, and generated
texture caches live in the Android cache directory. With a debug APK, retrieve
the engine log using:

```sh
adb shell run-as com.darkmatter.openpr06 cat files/saves/basepr/logs/openpr06.log
```

When a native fatal error writes a diagnostic report, it is beside that log at
`files/saves/basepr/logs/fatal.txt`. The standalone host publishes
`OPENQ4_SAVE_ROOT` before native startup so early diagnostics use the same root
as `fs_savepath`. External hosts may publish their absolute save directory in
that variable; otherwise the existing `USER_FILES/quake4` or SDL private-storage
fallback remains in use. The setup screen's **Export logs** action includes
these reports without requiring a debug APK or ADB access.

Each packaged overlay revision extracts to its own private directory before
engine startup. A manifest verifies every extracted file on each launch; missing,
truncated or altered copies are repaired from the APK. Healthy files are not
recopied. An interrupted repair is retried, and a replacement is installed only
after its complete length and hash have been verified. Allow enough free storage
for a temporary replacement of a damaged file. Old generated revisions are
removed only after the current package is complete, so updates do not retain
another full copy indefinitely. Saves are kept separately. App data removal also removes
these copies and local saves. The native libraries must be extracted by the
package manager. Gradle's `useLegacyPackaging` setting writes the corresponding
`extractNativeLibs` attribute into the packaged manifest.

The custom Activity and build files are GPL-3.0-or-later engine-side sources
from openQ4, adapted for openPR06. SDL's
Android Java classes are referenced directly from the supplied source tree;
they retain [SDL's zlib license](https://github.com/libsdl-org/SDL/blob/release-3.4.10/LICENSE.txt).
The SDL Activity contract and Gradle versions follow
[SDL 3.4.10's Android project](https://github.com/libsdl-org/SDL/tree/release-3.4.10/android-project).
No SDL template source is copied into this repository.

## Release automation and signing

`.github/workflows/android-build.yml` builds the APK independently; openPR06's
Manual Releases does not call it yet. It uses NDK r30, Java 17, Gradle 8.12 and
SDK 35. SDL comes from the repository's checksum-pinned wrap with its patches, and
OpenAL Soft is the same 1.25.2 release the desktop packages use. The dependency source download
contains the actual patched SDL tree, the exact OpenAL archive and build
recipes. [SDL](https://github.com/libsdl-org/SDL) retains its zlib license and
[OpenAL Soft](https://github.com/kcat/openal-soft) its LGPL terms. Both libraries
are dynamically linked; rebuild with replacement libraries and sign your own
APK when modifying them.

The workflow builds an unsigned release APK, aligns it, signs it using
`apksigner`, then checks the signature against a pinned certificate. Its
`signing` input chooses the key:

- `release` (the default) needs four repository Actions secrets,
  `ANDROID_RELEASE_KEYSTORE_BASE64`, `ANDROID_RELEASE_STORE_PASSWORD`,
  `ANDROID_RELEASE_KEY_PASSWORD` and `ANDROID_RELEASE_KEY_ALIAS`, and the
  public certificate committed as `mobile/android/release-signing-cert.pem`.
  openPR06 has none of these yet, so this mode stops with an error.
- `ci` signs with a throwaway key generated for that job and verifies against
  its certificate. The artifact is named `...-ci-signed-not-for-distribution.apk`:
  it proves the package builds and verifies, but no installation can ever be
  updated from it, so never publish it.

Private keys and passwords never belong in Git or downloadable artifacts.
Preserve a secure independent backup of the signing key: future in-place
updates must retain the same signing identity. See Android's
[app signing guidance](https://developer.android.com/studio/publish/app-signing).
openQ4's certificate is not openPR06's; the verifier's unit tests keep it only
as a fixture (`tools/tests/android_fixture_signing_cert.pem`).

`verify_android_apk.py` also checks the application ID, version/API, non-debug
manifest, native-library extraction, 16 KiB alignment, all six libraries,
overlay bytes and license notices. APK publication is blocked if any check or
any desktop build fails. This packaging validation does not replace device
installation and gameplay testing.

The extraction manifest and its content revision are also checked against the
validated stage. The host rejects malformed metadata and unexpected links or
unlisted files in its private package tree. These checks do not replace the
engine's validation of the separately supplied retail PK4s.

## Validation

The standalone debug APK was assembled with Gradle 8.12, Android plugin 8.7.3,
SDK/build-tools 35 and the matching SDL 3.4.10 Java/native sources. Its APK v2
signature, ZIP alignment and packaged manifest were verified. All native
libraries, both overlay packs, mod metadata, contributor credits and dependency
notices match the Meson staging files. Device installation and gameplay have
not been tested as part of this integration.

The host's extraction/retry and upgrade cleanup are exercised by
`python tools/tests/android_host_storage.py` with a JDK. The test compiles the
actual Activity with minimal Android API substitutes and runs against temporary
filesystem fixtures; it does not require or control an Android device.

`python tools/tests/android_retail_data.py` checks the setup verifier against the
native PK4 checksum implementation and generated valid/damaged archives. It
requires a JDK and GCC or Clang; `--retail-root /path/to/Prey/base` additionally
performs a read-only full check of local retail media (passing on the digital
layout, 2026-11-22). The launcher uses this
verifier for imports and installed-data checks. The engine's own validation
also remains enabled.

`python tools/tests/android_retail_import.py` exercises verified replacement,
interruption/retry, low space, source failures and save preservation.
`python tools/tests/android_document_source.py` checks the read-only Android
document-provider adapter and its connection to the importer using host API
substitutes. Both require a JDK. Device folder-picker/grant behavior and the
player-facing setup flow remain separate physical acceptance work.

`python tools/tests/android_setup_task.py` checks retained operation delivery,
cancellation and native/setup storage ownership. `android_setup_flow.py` runs
the real provider/import/verification/extraction sequence, including cancellation
between stages and retry, and checks the four complete localized resource sets.
Neither needs a device. APK verification also compares the launcher's display
(`fonts/menu.ttf`) and Talon UI Condensed body faces with the exact faces inside
the staged `pak0.pk4`.

`python tools/tests/android_private_export.py` checks read-only save/log ZIPs,
manifest integrity, cancellation, source changes, bounds, storage ownership and
bounded setup diagnostics. `android_document_export.py` checks the actual
provider writer with controlled denied/disconnected/blocked providers, including
descriptor cleanup, cancellation, retry and byte-preserving output. These host
fixtures do not establish physical picker/provider or cloud-upload behavior.
