#!/usr/bin/env python3
"""SetupTrmModel must reuse one scratch trace model, as Doom 3's did.

PREY's game code (idClipModel::Handle, idClip::GetModelContactFeature) calls
collisionModelManager->SetupTrmModel for trace-model clip models every frame
and never frees what it gets back: Doom 3's manager filled one scratch model.
openQ4's ModelFromTrm makes a new standalone model each call, so the shim has
to free the previous scratch model or every call leaks one.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8", errors="replace")


def setup_trm_model_body(header: str) -> str:
    start = header.find("idCollisionModel *SetupTrmModel( const idTraceModel &trm, const idMaterial *material ) {")
    if start == -1:
        raise AssertionError("CollisionModel.h no longer defines the SetupTrmModel shim")
    depth = 0
    for index in range(header.index("{", start), len(header)):
        if header[index] == "{":
            depth += 1
        elif header[index] == "}":
            depth -= 1
            if depth == 0:
                return header[start : index + 1]
    raise AssertionError("unterminated SetupTrmModel body")


def validate_shim(header: str) -> None:
    body = setup_trm_model_body(header)
    scratch = re.search(r"static idCollisionModel \*(\w+) = NULL;", body)
    if scratch is None:
        raise AssertionError("SetupTrmModel must keep one static scratch model")
    name = scratch.group(1)
    free = body.find(f"FreeModel( {name} );")
    make = body.find(f"{name} = ModelFromTrm(")
    if free == -1 or make == -1 or free > make:
        raise AssertionError("SetupTrmModel must free the previous scratch model before making the next one")
    if f"return {name};" not in body:
        raise AssertionError("SetupTrmModel must return the scratch model it keeps")


def validate_callers() -> None:
    # The callers rely on the scratch semantics: they use the handle at once
    # and never free it. If one starts freeing it, the shim would free it twice.
    for relative in ("src/game/physics/Clip.cpp",):
        source = read(relative)
        if "collisionModelManager->SetupTrmModel(" not in source:
            raise AssertionError(f"{relative} no longer calls SetupTrmModel; revisit this contract")
        if re.search(r"FreeModel\(\s*[^)]*SetupTrmModel", source):
            raise AssertionError(f"{relative} frees a SetupTrmModel result, which the shim owns")


def validate_self_test() -> None:
    leaking = """
	idCollisionModel *SetupTrmModel( const idTraceModel &trm, const idMaterial *material ) {
		return ModelFromTrm( NULL, "_legacy_trm_model_", trm, material );
	}
"""
    try:
        validate_shim(leaking)
    except AssertionError:
        pass
    else:
        raise AssertionError("the shim check accepted a SetupTrmModel that leaks a model per call")


def main() -> None:
    validate_shim(read("src/cm/CollisionModel.h"))
    validate_callers()
    validate_self_test()
    print("collision_trm_scratch_model: ok")


if __name__ == "__main__":
    main()
