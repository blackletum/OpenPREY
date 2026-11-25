#!/usr/bin/env python3
"""Regression checks for the weapon wheel's transient slow-motion channel
(openPR06: PREY's wheel in src/Prey/game_weaponwheel.cpp)."""

from __future__ import annotations

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GAME_ROOT = Path(os.environ.get("OPENQ4_GAMELIBS_REPO", ROOT)).resolve()


def read(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def require(source: str, token: str, context: str) -> None:
    if token not in source:
        raise AssertionError(f"Missing {token!r} in {context}")


def function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start == -1:
        raise AssertionError(f"Missing function signature {signature!r}")

    depth = 0
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not find the end of {signature!r}")


def main() -> None:
    engine_header = read(ROOT / "src/framework/Common.h")
    require(engine_header, "SetGameTimeScale(float scale)", "idCommon transient time-scale API")
    require(engine_header, "GetGameTimeScale(void) const", "idCommon transient time-scale API")

    common = read(ROOT / "src/framework/Common.cpp")
    setter = function_body(common, "void idCommonLocal::SetGameTimeScale( float scale ) {")
    require(setter, "openQ4_gameTimeScale.store", "atomic transient time-scale publication")
    require(setter, "soundWorld->SetSlowmoSpeed( scale );", "transient audio slowdown")
    require(
        common,
        "com_timescale.GetFloat() * openQ4_gameTimeScale.load",
        "engine effective time-scale composition",
    )

    # openPR06: PREY's weapon wheel (src/Prey/game_weaponwheel.cpp) slows single
    # player through the transient channel and gives it back, never through
    # the player's own timescale CVar.
    wheel = read(GAME_ROOT / "src/Prey/game_weaponwheel.cpp")
    player = read(GAME_ROOT / "src/Prey/game_player.cpp")
    if re.search(r"SetCVar(?:Float|String|Integer)\s*\(\s*\"timescale\"", wheel + player):
        raise AssertionError("The weapon wheel must not write the public timescale CVar")

    effects = function_body(wheel, "void hhPlayer::UpdateWeaponWheelEffects( void ) {")
    require(effects, "gameLocal.isMultiplayer", "multiplayer keeps its normal speed")
    require(effects, "common->SetGameTimeScale( WheelLerp( 1.0f, WHEEL_TIME_SCALE,", "weapon-wheel transient time scale")
    require(effects, "common->SetGameTimeScale( 1.0f );", "weapon-wheel transient reset")
    require(effects, "wheelTimeScaled", "the wheel gives back only a slowdown it made")
    reset = function_body(wheel, "void hhPlayer::ResetWeaponWheel( bool instant ) {")
    require(reset, "UpdateWeaponWheelEffects();", "an instant reset restores the speed")
    destructor = function_body(player, "hhPlayer::~hhPlayer() {")
    require(destructor, "common->SetGameTimeScale( 1.0f );", "a removed player gives the speed back")

    handle_esc = function_body(read(GAME_ROOT / "src/game/Player.cpp"), "bool idPlayer::HandleESC( void ) {")
    require(handle_esc, "CancelWeaponWheel()", "Escape closes the wheel")

    print("weapon wheel transient time-scale checks passed")


if __name__ == "__main__":
    main()
