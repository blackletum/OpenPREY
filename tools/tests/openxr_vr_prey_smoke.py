#!/usr/bin/env python3
"""Play PREY in VR against the OpenXR test runtime (requires Pillow, a client
built with OpenXR, and retail PREY assets).

openPR06's half of openQ4's VR smoke (openQ4 tools/tests/openxr_vr_smoke.py),
cut down to what PREY's game module does: hhPlayerView renders the
first-person view once per eye (src/Prey/game_playerview.cpp), and the weapon
hand holds the view weapon (hhPlayer::GetVRWeaponTransform).

The test runtime (tools/tests/openxr/OpenXRTestRuntime.cpp, built beside the
client) simulates a stereo headset with off-axis eyes and two controllers. It
is selected for this process only through XR_RUNTIME_JSON, so no system-wide
OpenXR registration is read or changed. No keyboard or mouse input is
synthesised: a cfg drives the game, and the runtime's frame script follows it
through marker files the engine writes with condump.

Checks:
- the session presents, and gameplay submits a stereo projection layer plus
  the HUD quad;
- both eyes are lit and differ (parallax), and a scripted head turn changes
  what they see;
- with game time stopped and the controller aiming, the aim marker
  (vr_aimLaser) is the only difference between captures: a small red dot in
  each eye, at the same height in both, whose disparity puts it in front of
  the player at a plausible range, and a beam (vr_aimLaser 2) that adds more;
- the gun in the hand: moving the controller 15 cm to the right, with game
  time stopped and no marker, moves the drawn gun (and only what it covers)
  by the same distance in the head's frame (vr_debug 2 logs the held gun);
- the trigger fires the rifle through its default binding, and each shot
  pulses the weapon hand's controller (a 40 ms vibration on the right hand);
- the comfort vignette: a smooth turn at full strength darkens the eyes' top
  corners and leaves their centres clear;
- the rifle's zoom magnifies the eyes;
- PREY's gravity: flipped onto the ceiling (setPlayerGravity), the drawn head
  turns upside down with the player's frame, the gun stays in the hand the
  same way, and both eyes still see the world;
- the log carries no errors.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]

# The test runtime's eyes (OpenXRTestRuntime.cpp EyeFov, TR_IPD): signed
# angles of each frustum (left, right, up, down), and their separation.
EYE_FOV = {"left": (-0.94, 0.78, 0.86, -0.92), "right": (-0.78, 0.94, 0.86, -0.92)}
EYE_SEPARATION_M = 0.064
# The weapon hand aims 10 degrees down from 0.35 m below the eyes, and the
# gun in it fires from the hand, so the shot meets the floor some metres ahead.
LASER_HAND_POSE = "0.2 1.25 -0.35 0 -10 0"
# The same aim from 15 cm further right: the held gun follows the controller.
SHIFTED_HAND_POSE = "0.35 1.25 -0.35 0 -10 0"
HAND_SHIFT_M = 0.15
WORLD_SCALE = 39.37  # vr_worldScale: game units per metre
LEVEL_HAND_POSE = "0.2 1.25 -0.35 0 0 0"
DEFAULT_BASEPATH = Path(r"C:\Program Files (x86)\Human Head Studios\Prey")


def read_events(path: Path) -> list[dict]:
    events = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def frame_guarded(commands: list[str]) -> list[str]:
    """Lets frames run before every marker and after every real-time wait
    (openQ4's openxr_vr_smoke.py explains the races on a busy machine)."""
    guarded = []
    for command in commands:
        if command.startswith("condump vr_marker_"):
            guarded.append("wait 2")
        guarded.append(command)
        if command.startswith("waitMsec "):
            guarded.append("wait 3")
    return guarded


def changed_box(before, after, threshold=48):
    """The bounding box and count of pixels whose largest channel changed by more than threshold."""
    from PIL import ImageChops
    difference = ImageChops.difference(before, after)
    mask = difference.split()[0].point(lambda v: 255 if v > threshold else 0)
    for channel in difference.split()[1:]:
        mask = ImageChops.lighter(mask, channel.point(lambda v: 255 if v > threshold else 0))
    return mask.getbbox(), mask.histogram()[255]


def eye_tangents(eye: str, x: float, y: float, width: int, height: int) -> tuple[float, float]:
    """A pixel position on an eye image as tangents right and up of that eye's axis."""
    left, right, up, down = (math.tan(a) for a in EYE_FOV[eye])
    u = (x + 0.5) / width
    v = (y + 0.5) / height
    return left + u * (right - left), up - v * (up - down)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--basepath", type=Path, default=Path(os.environ.get("OPENPR06_PREY_BASEPATH", DEFAULT_BASEPATH)),
                        help="installed retail PREY (the directory holding base/)")
    parser.add_argument("--runtime-dir", type=Path, default=ROOT / "builddir",
                        help="a complete runtime: builddir, or a staged .install")
    parser.add_argument("--build-dir", type=Path, default=ROOT / "builddir",
                        help="build directory holding openq4_xr_test_runtime.json")
    parser.add_argument("--executable-name")
    parser.add_argument("--map", default="game/feedingtowerb")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--render-api", choices=("gl", "vulkan"), default="gl")
    parser.add_argument("--eye-size", default="960x1056")
    options = parser.parse_args(argv)
    from PIL import Image, ImageChops, ImageStat

    runtime = options.runtime_dir.resolve()
    executable = options.executable_name or ("openPR06-client_x64.exe" if os.name == "nt" else "openPR06-client_x64")
    manifest = (options.build_dir / "openq4_xr_test_runtime.json").resolve()
    if not (runtime / executable).is_file():
        parser.error(f"no client at {runtime / executable}")
    if not (options.basepath / "base").is_dir():
        parser.error(f"no retail PREY assets under {options.basepath}")
    if not manifest.is_file():
        parser.error(f"the OpenXR test runtime is not built: {manifest}")

    output = (options.output_dir or ROOT / ".tmp/openxr-vr-prey-smoke").resolve()
    profile = output / options.render_api
    game = profile / "basepr"
    game.mkdir(parents=True, exist_ok=True)
    for stale in list(game.glob("vr_marker_*.txt")) + list(profile.glob("xr_*.tga")):
        stale.unlink()
    xr_log = profile / "xr.jsonl"
    xr_log.unlink(missing_ok=True)
    game_log = game / "qconsole.log"
    game_log.unlink(missing_ok=True)

    def marker(name: str) -> str:
        return str(game / f"vr_marker_{name}.txt")

    # The runtime acts on the frame after each marker appears.
    script = [
        f"when {marker('gameplay')} capture {profile / 'xr_gameplay'}",
        f"when {marker('turn')} head 40 0 0",
        f"when {marker('turned')} capture {profile / 'xr_turned'}",
        f"when {marker('turn_back')} head 0 0 0",
        f"when {marker('laser_aim')} hand right {LASER_HAND_POSE}",
        f"when {marker('laser_off')} capture {profile / 'xr_laser_off'}",
        f"when {marker('laser_dot')} capture {profile / 'xr_laser_dot'}",
        f"when {marker('laser_beam')} capture {profile / 'xr_laser_beam'}",
        f"when {marker('hand_shift')} hand right {SHIFTED_HAND_POSE}",
        f"when {marker('hand_moved')} capture {profile / 'xr_hand_moved'}",
        f"when {marker('hand_back')} hand right {LASER_HAND_POSE}",
        f"when {marker('smooth')} stick right 1 0",
        f"when {marker('vignette')} capture {profile / 'xr_vignette'}",
        f"when {marker('smooth_stop')} stick right 0 0",
        f"when {marker('laser_done')} hand right {LEVEL_HAND_POSE}",
        f"when {marker('fire')} button right trigger 1",
        f"when {marker('fire_release')} button right trigger 0",
        f"when {marker('zoom_off')} capture {profile / 'xr_zoom_off'}",
        f"when {marker('zoom_on')} capture {profile / 'xr_zoom_on'}",
        f"when {marker('flipped')} capture {profile / 'xr_flipped'}",
        f"when {marker('exit')} exit",
    ]
    (profile / "xr_script.txt").write_text("\n".join(script) + "\n", encoding="utf-8")

    commands = [
        "waitMsec 4000", "echo VR_GAMEPLAY_ACTIVE", "vr_status",
        # the profile persists between runs: start from the default trigger binding
        "bind JOY15 _attack",
        "give weapon_rifle", "waitMsec 2500",
        "condump vr_marker_gameplay.txt", "waitMsec 800",
        # a head turn changes what the eyes see
        "condump vr_marker_turn.txt", "waitMsec 800",
        "condump vr_marker_turned.txt", "waitMsec 500",
        "condump vr_marker_turn_back.txt", "waitMsec 800",
        # the aim marker against a frozen world: only the marker may change
        "condump vr_marker_laser_aim.txt", "waitMsec 800", "g_stopTime 1", "vr_aimLaser 0", "waitMsec 800",
        "condump vr_marker_laser_off.txt", "waitMsec 500", "vr_aimLaser 1", "waitMsec 500",
        "condump vr_marker_laser_dot.txt", "waitMsec 500", "vr_aimLaser 2", "waitMsec 500",
        "condump vr_marker_laser_beam.txt", "waitMsec 500",
        # the gun in the hand, still against the frozen world and with no
        # marker: the controller moves right, and the drawn gun with it
        "vr_aimLaser 0", "vr_debug 2", "waitMsec 300", "vr_debug 1", "echo VR_HAND_AT_REST",
        "condump vr_marker_hand_shift.txt", "waitMsec 800",
        "vr_debug 2", "waitMsec 300", "vr_debug 1", "echo VR_HAND_SHIFTED",
        "condump vr_marker_hand_moved.txt", "waitMsec 500",
        "condump vr_marker_hand_back.txt", "waitMsec 800", "vr_aimLaser 1", "waitMsec 300",
        # comfort: a smooth turn darkens each eye's edges around a clear centre
        "vr_turnMode 1", "vr_comfortVignette 1", "condump vr_marker_smooth.txt", "waitMsec 600",
        "condump vr_marker_vignette.txt", "waitMsec 300",
        "condump vr_marker_smooth_stop.txt", "waitMsec 300", "vr_turnMode 0", "vr_comfortVignette 0.5",
        "g_stopTime 0", "condump vr_marker_laser_done.txt", "waitMsec 800",
        # the right trigger's default binding fires the rifle from the hand
        "echo VR_FIRE", "condump vr_marker_fire.txt", "waitMsec 400",
        "condump vr_marker_fire_release.txt", "waitMsec 1000",
        # the rifle's scope magnifies each eye
        "g_stopTime 1", "waitMsec 300", "condump vr_marker_zoom_off.txt", "waitMsec 400", "g_stopTime 0",
        'script "entity w = $player1.getWeaponEntity(); w.zoomIn();"', "waitMsec 1500", "g_stopTime 1",
        "waitMsec 300", "condump vr_marker_zoom_on.txt", "waitMsec 400", "g_stopTime 0",
        'script "entity w = $player1.getWeaponEntity(); w.zoomOut();"', "waitMsec 1000",
        # PREY's gravity: flipped, the player stands on the ceiling and the eyes
        # turn with the player's frame (vr_debug 2 logs the drawn head's up)
        "vr_debug 2", "waitMsec 300", "vr_debug 1", "echo VR_GRAVITY_NORMAL",
        "setPlayerGravity 0 0 1066", "waitMsec 3500",
        "vr_debug 2", "waitMsec 300", "vr_debug 1", "echo VR_GRAVITY_FLIPPED",
        "condump vr_marker_flipped.txt", "waitMsec 600",
        "setPlayerGravity 0 0 -1066", "waitMsec 3000",
        "condump vr_marker_exit.txt", "waitMsec 1500",
        "echo VR_AFTER_EXIT", "vr_status",
        "echo VR_SMOKE_COMPLETE", "quit",
    ]
    (game / "openxr_vr_prey_smoke.cfg").write_text("\n".join(frame_guarded(commands)) + "\n", encoding="utf-8")

    settings = {
        "logFile": "2", "developer": "1",
        "in_mouse": "0", "in_joystick": "0",
        "r_fullscreen": "0", "r_borderless": "0", "r_borderlessDefaultMigrated": "1",
        "r_windowWidth": "1280", "r_windowHeight": "720",
        "r_swapInterval": "0", "com_maxfps": "60",
        "win_allowMultipleInstances" if os.name == "nt" else "sys_allowMultipleInstances": "1",
        "s_volume": "0", "s_musicVolume": "0",
        "fs_basepath": str(options.basepath.resolve()),
        "fs_savepath": str(profile), "fs_game": "basepr",
        "si_gameType": "singleplayer",
        "com_skipLoadingContinue": "1", "com_loadingContinueAutoAdvance": "1", "com_allowConsole": "1",
        "vr_enable": "1", "vr_debug": "1", "vr_aimMode": "1", "vr_aimLaser": "1", "vr_turnMode": "0",
        "vr_leftHanded": "0", "vr_comfortVignette": "0.5",
        "r_renderApi": options.render_api,
    }
    args = []
    for key, value in settings.items():
        args += ["+set", key, value]
    # the map loads within its command, so the cfg runs once it has
    args += ["+map", options.map, "+exec", "openxr_vr_prey_smoke.cfg"]
    command = [str(runtime / executable), *args]
    (profile / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")

    environment = dict(os.environ)
    environment.update({
        "XR_RUNTIME_JSON": str(manifest),
        "OPENQ4_XR_TEST_LOG": str(xr_log),
        "OPENQ4_XR_TEST_SCRIPT": str(profile / "xr_script.txt"),
        "OPENQ4_XR_TEST_EYE_SIZE": options.eye_size,
        "OPENQ4_XR_TEST_RATE": "90",
    })
    timed_out = False
    result = None
    with (profile / "process.log").open("w", encoding="utf-8") as log:
        try:
            result = subprocess.run(command, cwd=runtime, stdout=log, stderr=subprocess.STDOUT,
                                    env=environment, timeout=options.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True

    text = game_log.read_text(encoding="utf-8", errors="replace") if game_log.is_file() else ""
    events = read_events(xr_log)
    (profile / "xr_events.json").write_text(json.dumps(events, indent=2), encoding="utf-8")

    assert "VR_GAMEPLAY_ACTIVE" in text, f"gameplay not reached (log: {game_log})"
    assert "OpenXR: presenting to the headset" in text, "the session never began"
    assert not timed_out, f"the client did not finish within {options.timeout} s"
    assert result.returncode == 0, result.returncode
    assert "VR_SMOKE_COMPLETE" in text, "script did not complete"
    errors = [line for line in text.splitlines() if re.search(r"FATAL|ERROR:|OpenXR: .* failed|Unknown command", line)]
    assert not errors, "errors in the log:\n" + "\n".join(errors[:10])

    frames = [e for e in events if e.get("event") == "end_frame"]
    stereo = [f for f in frames if [layer["type"] for layer in f["layers"]] == ["projection", "quad"]]
    assert stereo, "gameplay never presented a stereo projection layer with the HUD"
    assert not any(e.get("event") in ("end_frame_invalid", "create_session_rejected", "create_swapchain_rejected")
                   for e in events), "the runtime rejected a submission"

    stages = ("gameplay", "turned", "laser_off", "laser_dot", "laser_beam", "hand_moved", "vignette", "zoom_off",
              "zoom_on", "flipped")
    captures = {}
    for e in events:
        if e.get("event") == "capture":
            name = Path(e["path"]).name
            stage = next((s for s in stages if name.startswith(f"xr_{s}_")), None)
            if stage:
                captures[f"{stage}_{e['layer']}"] = e
    for stage in stages:
        for eye in ("left", "right"):
            name = f"{stage}_{eye}"
            assert name in captures and captures[name]["written"], f"missing capture {name}: {sorted(captures)}"
    for name in ("gameplay_left", "gameplay_right", "turned_left", "turned_right"):
        assert captures[name]["lit_fraction"] > 0.2, f"eye capture {name} is mostly black: {captures[name]}"

    def image(prefix: str, layer: str):
        return Image.open(profile / f"{prefix}_{layer}.tga").convert("RGB")

    results = {}
    left, right = image("xr_gameplay", "left"), image("xr_gameplay", "right")
    results["eye_difference"] = max(ImageStat.Stat(ImageChops.difference(left, right)).mean)
    assert results["eye_difference"] > 1.0, f"the eyes are identical: no parallax ({results['eye_difference']:.3f})"
    results["turn_difference"] = max(ImageStat.Stat(ImageChops.difference(left, image("xr_turned", "left"))).mean)
    assert results["turn_difference"] > 4.0, f"a 40 degree head turn barely changed the view ({results['turn_difference']:.3f})"

    # the aim marker: the same dot in both eyes, fusing in front of the player
    dots = {}
    for eye in ("left", "right"):
        off, dot, beam = image("xr_laser_off", eye), image("xr_laser_dot", eye), image("xr_laser_beam", eye)
        box, dot_pixels = changed_box(off, dot)
        assert box is not None, f"the aim marker changed nothing in the {eye} eye"
        assert box[2] - box[0] <= 24 and box[3] - box[1] <= 24, \
            f"the {eye} eye changed beyond a small dot with game time stopped: {box}"
        red = sum(1 for r, g, b in dot.crop(box).getdata() if r > 150 and r > g + 60 and r > b + 60)
        assert red >= 4, f"the {eye} eye's marker is not a red dot ({red} red pixels in {box})"
        # the beam leaves the gun in the hand, below the eyes, for the dot
        beam_box, beam_pixels = changed_box(off, beam)
        assert beam_pixels > dot_pixels * 2, f"the {eye} eye's beam adds too little ({beam_pixels} vs {dot_pixels} pixels)"
        assert beam_box[3] > box[3] + 20, f"the {eye} eye's beam should rise from the gun below the dot ({beam_box} vs {box})"
        results[f"beam_pixels_{eye}"] = beam_pixels
        x, y = (box[0] + box[2] - 1) / 2.0, (box[1] + box[3] - 1) / 2.0
        dots[eye] = eye_tangents(eye, x, y, dot.width, dot.height)
    (left_x, left_y), (right_x, right_y) = dots["left"], dots["right"]
    assert abs(left_y - right_y) < 0.01, f"the marker sits at different heights in the two eyes ({left_y:.4f} vs {right_y:.4f})"
    disparity = left_x - right_x
    assert disparity > 0.0, f"the marker's disparity puts it behind the eyes ({disparity:.5f})"
    results["marker_depth_m"] = EYE_SEPARATION_M / disparity
    assert 1.0 < results["marker_depth_m"] < 40.0, f"the marker fuses at {results['marker_depth_m']:.2f} m"

    # the gun in the hand: the held gun moves with the controller, in the
    # head's own axes (forward, left, up), by what the controller moved
    def held_weapon(tag: str) -> tuple[float, float, float]:
        found = re.findall(r"VR held weapon \d+ \([^)]*\) head-relative \(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)",
                           text.partition(tag)[0])
        assert found, f"vr_debug 2 logged no held weapon before {tag}: the gun is not in the hand"
        return tuple(float(v) for v in found[-1])
    rest, shifted = held_weapon("VR_HAND_AT_REST"), held_weapon("VR_HAND_SHIFTED")
    results["held_weapon_rest"], results["held_weapon_shifted"] = rest, shifted
    expected = HAND_SHIFT_M * WORLD_SCALE
    assert abs((rest[1] - shifted[1]) - expected) < 0.5, \
        f"moving the controller {HAND_SHIFT_M} m right should move the held gun {expected:.2f} units right: {rest} -> {shifted}"
    assert abs(rest[0] - shifted[0]) < 0.5 and abs(rest[2] - shifted[2]) < 0.5, \
        f"a sideways controller move should move the held gun only sideways: {rest} -> {shifted}"
    for eye in ("left", "right"):
        rest_image, moved_image = image("xr_laser_off", eye), image("xr_hand_moved", eye)
        box, pixels = changed_box(rest_image, moved_image)
        assert box is not None and pixels > 400, \
            f"moving the controller barely changed the {eye} eye with game time stopped ({pixels} pixels): the gun did not follow"
        height = rest_image.height
        assert box[3] > height // 2, f"the {eye} eye changed only above its centre, not where the gun hangs: {box}"
        results[f"hand_moved_pixels_{eye}"] = pixels

    # a shot pulses the weapon hand, and only it (a hit would pulse both, for 90 ms)
    assert "VR_FIRE" in text, "the fire stage never ran"
    pulses = [e for e in events if e.get("event") == "haptic" and e.get("duration_ns") == 40_000_000]
    assert pulses, "firing the rifle did not vibrate a controller"
    assert all(e.get("hand") == "/user/hand/right" and 0.4 <= e["amplitude"] <= 1.0 for e in pulses), \
        f"a shot must pulse only the right (weapon) hand: {pulses}"
    results["fire_pulses"] = len(pulses)

    # the vignette: the eyes' top corners go dark, their centres stay clear
    for eye in ("left", "right"):
        vignette, plain = image("xr_vignette", eye), image("xr_laser_dot", eye)
        w, h = vignette.size
        corner = (0, 0, w // 8, h // 8)
        centre = (w * 7 // 16, h * 7 // 16, w * 9 // 16, h * 9 // 16)
        corner_luma = max(ImageStat.Stat(vignette.crop(corner)).mean)
        assert corner_luma < 12.0, f"the {eye} eye's corner stayed lit under the vignette ({corner_luma:.1f})"
        centre_vignette = max(ImageStat.Stat(vignette.crop(centre)).mean)
        assert centre_vignette > 4.0, f"the {eye} eye's centre went dark under the vignette ({centre_vignette:.1f})"
        results[f"vignette_{eye}"] = {"corner": round(corner_luma, 2), "centre": round(centre_vignette, 2),
                                      "centre_plain": round(max(ImageStat.Stat(plain.crop(centre)).mean), 2)}

    results["zoom_difference"] = max(ImageStat.Stat(ImageChops.difference(image("xr_zoom_off", "left"),
                                                                          image("xr_zoom_on", "left"))).mean)
    assert results["zoom_difference"] > 4.0, f"zooming the rifle barely changed the view ({results['zoom_difference']:.3f})"

    # gravity: the drawn head stands up in the world, then upside down on the
    # ceiling once gravity points up, and both eyes still see the world
    def head_up(tag: str) -> float:
        # the last frame vr_debug 2 logged before the tag's echo
        found = re.findall(r"VR drawn head \d+ \([^)]*\) up \(\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\)",
                           text.partition(tag)[0])
        assert found, f"vr_debug 2 logged no drawn head before {tag}"
        return float(found[-1][2])
    results["head_up_z_normal"] = head_up("VR_GRAVITY_NORMAL")
    results["head_up_z_flipped"] = head_up("VR_GRAVITY_FLIPPED")
    assert results["head_up_z_normal"] > 0.9, f"the head should stand up in normal gravity ({results['head_up_z_normal']})"
    assert results["head_up_z_flipped"] < -0.9, \
        f"with gravity flipped the head should turn with the player's frame ({results['head_up_z_flipped']})"
    # the hand hangs off the same gravity frame as the head, so the gun sits
    # where it did relative to the head, upside down with it
    held_normal, held_flipped = held_weapon("VR_GRAVITY_NORMAL"), held_weapon("VR_GRAVITY_FLIPPED")
    results["held_weapon_flipped"] = held_flipped
    assert all(abs(a - b) < 0.5 for a, b in zip(held_normal, held_flipped)), \
        f"on the ceiling the gun should stay in the hand relative to the head: {held_normal} -> {held_flipped}"
    for eye in ("left", "right"):
        assert captures[f"flipped_{eye}"]["lit_fraction"] > 0.2, f"the {eye} eye went dark on the ceiling"
    results["flipped_eye_difference"] = max(ImageStat.Stat(ImageChops.difference(
        image("xr_flipped", "left"), image("xr_flipped", "right"))).mean)
    assert results["flipped_eye_difference"] > 1.0, \
        f"the eyes lost their parallax on the ceiling ({results['flipped_eye_difference']:.3f})"

    (profile / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "profile": str(profile), **results}, indent=2))


if __name__ == "__main__":
    main()
