#!/usr/bin/env python3
"""Lock the savegame's native-layout blocks (roadmap Q4-06 stage 1).

A save is portable only if every saved byte has an explicit width and byte order.
Typed writers (WriteInt, WriteFloat, WriteVec3, ...) already swap to little-endian;
what remains are calls that copy memory as the compiler laid it out. This test finds
every such call in both game trees and the GUI save code and requires each one to be
listed below with a class:

  bitfield        flag struct whose bit allocation is up to the compiler
  aggregate       struct or template with padding, bool/enum members or a layout
                  tied to the code (it has changed before)
  le-scalars      fixed-width ints and floats (arrays, vectors, rectangles) whose
                  bytes match on every 64-bit little-endian target
  script-storage  script values in host byte order; pointer-sized slots included
  bytes           strings and byte payloads with an explicit length
  legacy-reader   reads that serve only the v2/v3 historical decoders
  helper          the GUI byte/field helper definitions themselves

A new, removed or recounted raw call fails until this table is updated, so a change
to the save format is always reviewed. The SP and MP trees must stay identical.

Blocks already converted to explicit fields leave the table. Stage 2 converted
those whose bytes stay the same. Stage 3 converted the rest under payload version
5, so their raw reads remain only as legacy readers for versions 2 to 4. The flag
bitfields keep their old bytes only while each saved flag list follows its
struct's declaration order, so FLAG_LISTS checks that order as well.
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RAW = re.compile(r"\b(?:savefile|saveFile)\s*->\s*(?:Write|Read)\s*\(")
HELPER = re.compile(r"\bOpenQ4_(?:Write|Read)SaveGame(?:RawField|Bytes)\s*\(")
# Script globals are copied one byte at a time from the program's variable block.
SCRIPT_BYTES = re.compile(r"\bsavefile\s*->\s*(?:Write|Read)Byte\s*\(\s*variables\s*\[")

CLASSES = {"bitfield", "aggregate", "le-scalars", "script-storage", "bytes", "legacy-reader", "helper"}


def W(text: str) -> str:
    return "savefile->Write(" + text + ")"


def R(text: str) -> str:
    return "savefile->Read(" + text + ")"


# Relative path -> class -> calls. A call listed twice must occur twice.
# openPR06: Prey's single game library spans src/game, src/Prey and src/preyengine
# (no Quake 4 src/mpgame), so paths start at src/. Its saves keep the Prey SDK's
# native layout: the Q4-06 stage 2/3 conversions were Quake 4 game code.
GAME_TREES = ("game", "Prey", "preyengine")
GAME: dict[str, dict[str, list[str]]] = {
    # Flag bitfields copied after LittleBitField.
    "game/BrittleFracture.cpp": {"bitfield": [W("&flags,sizeof(flags)"), R("&fl,sizeof(fl)")]},
    "game/Entity.cpp": {"bitfield": [W("&flags,sizeof(flags)"), R("&fl,sizeof(fl)")]},
    "game/projectile.cpp": {"bitfield": [W("&flags,sizeof(flags)"), R("&projectileFlags,sizeof(projectileFlags)")]},
    "game/gamesys/Event.cpp": {"bytes": [W("str,MAX_STRING_LEN")] * 2 + [R("str,MAX_STRING_LEN")] * 2},
    # Script values in host byte order; every slot but string and vector is
    # intptr_t-sized in Prey (validate_script_slot_widths).
    "game/script/Script_Interpreter.cpp": {"script-storage": [W("&localstack,localstackUsed"), R("localstack,localstackUsed")]},
    "game/script/Script_Program.cpp": {
        "script-storage": [W("data,size"), R("data,savedSize"),
                           "savefile->WriteByte(variables[", "savefile->WriteByte(variables[",
                           "savefile->ReadByte(variables[", "savefile->ReadByte(variables["],
    },
    "Prey/game_arcadegame.cpp": {"bytes": [W("startingGrid,ARCADE_GRID_WIDTH*ARCADE_GRID_HEIGHT"),
                                           R("startingGrid,ARCADE_GRID_WIDTH*ARCADE_GRID_HEIGHT")]},
    # card_t pads its char members.
    "Prey/game_blackjack.cpp": {"aggregate": [W("&PlayerHand[i],sizeof(card_t)"), W("&DealerHand[i],sizeof(card_t)"),
                                              R("&PlayerHand[i],sizeof(card_t)"), R("&DealerHand[i],sizeof(card_t)")]},
    "Prey/game_cards.cpp": {"le-scalars": [W("&cards[i],sizeof(hhCard)"), R("&card,sizeof(hhCard)")]},
    "Prey/game_console.cpp": {"aggregate": [W("&transState,sizeof(transState)"), R("&transState,sizeof(transState)")]},
    # fxInfoFlags_s is a struct of plain bools.
    "Prey/game_fxinfo.cpp": {"aggregate": [W("&infoFlags,sizeof(infoFlags)"), R("&flags,sizeof(flags)")]},
    "Prey/game_handcontrol.cpp": {"le-scalars": [W("anims,sizeof(int)*HAND_MATRIX_WIDTH*HAND_MATRIX_HEIGHT"),
                                                 R("anims,sizeof(int)*HAND_MATRIX_WIDTH*HAND_MATRIX_HEIGHT")]},
    "Prey/game_inventory.cpp": {
        "le-scalars": [W("&maxSpirit,sizeof(maxSpirit)"), R("&maxSpirit,sizeof(maxSpirit)")],
        "bitfield": [W("&requirements,sizeof(requirements)"), R("&requirements,sizeof(requirements)")],
        "aggregate": [W("&altMode,sizeof(altMode)"), W("&weaponRaised,sizeof(weaponRaised)"),
                      R("&altMode,sizeof(altMode)"), R("&weaponRaised,sizeof(weaponRaised)")],
    },
    "Prey/game_player.cpp": {"le-scalars": [W("weaponInfo,sizeof(weaponInfo_t)*15"), W("altWeaponInfo,sizeof(weaponInfo_t)*15"),
                                            R("weaponInfo,sizeof(weaponInfo_t)*15"), R("altWeaponInfo,sizeof(weaponInfo_t)*15")]},
    "Prey/game_poker.cpp": {
        "le-scalars": [W("values,sizeof(suitHist_t)*NUM_SUITS"), W("suits,sizeof(valueHist_t)*NUM_CARD_VALUES"),
                       R("values,sizeof(suitHist_t)*NUM_SUITS"), R("suits,sizeof(valueHist_t)*NUM_CARD_VALUES"),
                       W("&cards[i],sizeof(hhCard)"), R("&card,sizeof(hhCard)")],
        "aggregate": [W("markedCards,sizeof(bool)*5"), R("markedCards,sizeof(bool)*5")],
    },
}

# Direct raw writes across the game trees. A new raw write fails here.
GAME_DIRECT_WRITES = 24


def field(op: str, name: str, context: str, label: str) -> str:
    return f'OpenQ4_{op}SaveGameRawField(savefile,{name},"{context}","{label}")'


# Flag bitfields written one bit per flag (SaveCodec_WriteFlagBytes). Each list
# in the save and restore code must follow its struct's declaration order, or
# the bytes would move: (source, save function, restore function, struct
# source, declaration marker, member).
# openPR06: Prey's flag bitfields are still raw LittleBitField copies (listed
# above); none is written one bit per flag yet.
FLAG_LISTS: list[tuple[str, str, str, str, str, str]] = []


UI: dict[str, dict[str, list[str]]] = {
    # Window layout fields go through the typed OpenQ4_*SaveGameField overloads
    # (same bytes as the raw copy). Version 5 writes the transition interpolator
    # through SaveCodec; these reads decode the raw records of versions 2 to 4.
    "Window.cpp": {
        "legacy-reader": [field("Read", "interp", "idWindow::ReadSaveGameTransition", "interpolatestate"),
                          field("Read", "saved", "idWindow::ReadSaveGameTransition", "interpolatestate")],
        "bytes": ['OpenQ4_WriteSaveGameBytes(savefile,string,len,"idWindow::WriteSaveGameString","string")',
                  'OpenQ4_ReadSaveGameBytes(savefile,&string[0],len,"idWindow::ReadSaveGameString","string")'],
    },
    "SimpleWindow.cpp": {
        "bytes":['OpenQ4_WriteSaveGameBytes(savefile,background->GetName(),stringLen,"idSimpleWindow::WriteToSaveGame","backgroundname")',
                  'OpenQ4_ReadSaveGameBytes(savefile,&(backName)[0],stringLen,"idSimpleWindow::ReadFromSaveGame","backgroundname")'],
    },
    "Winvar.h": {
        "helper": ["OpenQ4_WriteSaveGameBytes(idFile*savefile,constvoid*buffer,intlen,constchar*context,constchar*fieldName)",
                   "OpenQ4_ReadSaveGameBytes(idFile*savefile,void*buffer,intlen,constchar*context,constchar*fieldName)",
                   "OpenQ4_ReadSaveGameRawField(idFile*savefile,type&value,constchar*context,constchar*fieldName)",
                   "OpenQ4_ReadSaveGameBytes(savefile,&value,sizeof(value),context,fieldName)",
                   W("buffer,len"), R("buffer,len")],
        "bytes": ['OpenQ4_WriteSaveGameBytes(savefile,data.c_str(),len,"idWinStr::WriteToSaveGame","string")',
                  'OpenQ4_ReadSaveGameBytes(savefile,&data[0],len,"idWinStr::ReadFromSaveGame","string")',
                  'OpenQ4_WriteSaveGameBytes(savefile,data.c_str(),len,"idWinBackground::WriteToSaveGame","materialname")',
                  'OpenQ4_ReadSaveGameBytes(savefile,&data[0],len,"idWinBackground::ReadFromSaveGame","materialname")'],
    },
    "UserInterface.cpp": {"bytes": [W("string.c_str(),len"), R("buffer,len")]},
    "RegExp.cpp": {"bytes": [W("buffer,len"), R("buffer,len")]},
    # Doom 3 PDA minigames write typed fields (same bytes); these reads decode
    # their unversioned legacy format only.
    "GameBearShootWindow.cpp": {"legacy-reader": [R("&value,sizeof(value)")]},
    "GameBustOutWindow.cpp": {"legacy-reader": [R("&value,sizeof(value)")]},
    "GameSSDWindow.cpp": {"legacy-reader": [R("&value,sizeof(value)")] * 3 + [R("data,size")]},
}


def calls_in(text: str) -> collections.Counter:
    found: collections.Counter = collections.Counter()
    for pattern in (RAW, HELPER):
        for match in pattern.finditer(text):
            depth, index = 0, text.index("(", match.start())
            while True:
                depth += text[index] == "("
                depth -= text[index] == ")"
                index += 1
                if depth == 0:
                    break
            found[re.sub(r"\s+", "", text[match.start():index])] += 1
    for match in SCRIPT_BYTES.finditer(text):
        found[re.sub(r"\s+", "", match.group(0))] += 1
    return found


def scan(tree: Path) -> dict[str, collections.Counter]:
    result = {}
    for path in sorted(tree.rglob("*")):
        if path.suffix not in (".cpp", ".h"):
            continue
        relative = path.relative_to(tree).as_posix()
        found = calls_in(path.read_text(encoding="latin-1"))
        if found:
            result[relative] = found
    return result


def expected(manifest: dict[str, dict[str, list[str]]]) -> dict[str, collections.Counter]:
    result = {}
    for relative, classes in manifest.items():
        unknown = set(classes) - CLASSES
        assert not unknown, f"{relative}: unknown class {sorted(unknown)}"
        result[relative] = collections.Counter(call for calls in classes.values() for call in calls)
    return result


def compare(label: str, found: dict[str, collections.Counter], manifest: dict[str, dict[str, list[str]]]) -> list[str]:
    problems = []
    want = expected(manifest)
    for relative in sorted(set(found) | set(want)):
        have, need = found.get(relative, collections.Counter()), want.get(relative, collections.Counter())
        for call in sorted(set(have) | set(need)):
            if have[call] != need[call]:
                kind = "unclassified" if need[call] == 0 else "stale" if have[call] == 0 else "count changed"
                problems.append(f"{label}/{relative}: {kind} raw save call ({have[call]} found, {need[call]} listed): {call}")
    return problems


def summary(manifest: dict[str, dict[str, list[str]]]) -> dict[str, int]:
    totals: collections.Counter = collections.Counter()
    for classes in manifest.values():
        for name, calls in classes.items():
            totals[name] += len(calls)
    return dict(sorted(totals.items()))


def validate_script_slot_widths() -> None:
    # Script storage is saved raw. Its pointer-sized types are the only slots whose
    # width follows the target; the Q4-06 contract relies on them staying intptr_t
    # (8 bytes on every supported target) and on no other type changing width.
    source = (ROOT / "src/game/script/Script_Program.cpp").read_text(encoding="latin-1")
    # openPR06: Prey's script VM gives every slot but string and vector an intptr_t.
    slot = "sizeof( intptr_t )"
    for name, size in (("scriptevent", slot), ("namespace", slot),
                       ("string", "MAX_STRING_LEN"), ("float", slot), ("vector", "E_EVENT_SIZEOF_VEC"),
                       ("entity", slot), ("field", slot), ("function", slot),
                       ("virtual function", slot), ("pointer", slot),
                       ("object", slot), ("boolean", slot)):
        if not re.search(rf'"{re.escape(name)}",\s*{re.escape(size)},', source):
            raise AssertionError(f"script type '{name}' no longer has size {size}; reclassify script storage")


def body_after(text: str, marker: str) -> str:
    start = text.index(marker)
    return text[start:text.index("\n}", start)]


def validate_flag_lists(tree: str) -> list[str]:
    problems = []
    for source, save, restore, header, marker, member in FLAG_LISTS:
        text = (ROOT / "src" / tree / source).read_text(encoding="latin-1")
        declared_text = (ROOT / "src" / tree / header).read_text(encoding="latin-1")
        if marker == "struct {":
            block = re.search(r"struct\s*\{([^}]*)\}\s*" + member + r"\s*;", declared_text).group(1)
        else:
            start = declared_text.index(marker)
            block = declared_text[start:declared_text.index("}", start)]
        declared = re.findall(r"\bbool\s+(\w+)\s*:\s*1\s*;", block)
        saved_list = re.search(member + r"Bits\[\]\s*=\s*\{(.*?)\};", body_after(text, save), re.S)
        saved = re.findall(re.escape(member) + r"\.(\w+)", saved_list.group(1)) if saved_list else []
        restored = sorted((int(index), name) for name, index in re.findall(
            re.escape(member) + r"\.(\w+)\s*=\s*" + re.escape(member) + r"Bits\[\s*(\d+)\s*\]", body_after(text, restore)))
        if not declared or saved != declared or [name for _, name in restored] != declared or \
                [index for index, _ in restored] != list(range(len(declared))):
            problems.append(f"src/{tree}/{source}: {member} flag list does not follow {marker} in {header} "
                            f"(declared {declared}, saved {saved}, restored {[n for _, n in restored]})")
        if f"static_assert( sizeof( {member} ) == ( {len(declared)} + 7 ) / 8" not in body_after(text, save):
            problems.append(f"src/{tree}/{source}: {save} lacks the {member} layout assertion")
    return problems


def self_test() -> None:
    sample = "void f(idSaveGame *savefile){ savefile->Write( &newBlock, sizeof( newBlock ) ); savefile->WriteInt( x ); }"
    found = calls_in(sample)
    assert found == collections.Counter({W("&newBlock,sizeof(newBlock)"): 1}), found
    problems = compare("sample", {"New.cpp": found}, {})
    assert problems and "unclassified" in problems[0], problems


def main() -> None:
    self_test()
    validate_script_slot_widths()
    problems = []
    found = {f"{tree}/{relative}": calls for tree in GAME_TREES
             for relative, calls in scan(ROOT / "src" / tree).items()}
    problems += compare("src", found, GAME)
    problems += validate_flag_lists("game")
    problems += compare("src/ui", scan(ROOT / "src" / "ui"), UI)
    writes = sum(1 for classes in GAME.values() for name, calls in classes.items() if name != "legacy-reader"
                 for call in calls if "->Write(" in call)
    if writes != GAME_DIRECT_WRITES:
        problems.append(f"game trees: {writes} direct raw writes listed, expected {GAME_DIRECT_WRITES}")
    if problems:
        raise AssertionError("savegame raw inventory changed:\n  " + "\n  ".join(problems))
    print(f"savegame_raw_inventory: ok (game {summary(GAME)}, {GAME_DIRECT_WRITES} direct writes; "
          f"ui {summary(UI)})")


if __name__ == "__main__":
    main()
