#!/usr/bin/env python3
"""Focused contracts for resilient libvorbisfile sample decoding."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_SOURCE = ROOT / "src" / "sound" / "OpenAL" / "AL_SoundSample.cpp"


def cxx_function_body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start == -1:
        raise AssertionError(f"Missing function {signature!r}")
    open_brace = source.index("{", start)
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : index]
    raise AssertionError(f"Unclosed function {signature!r}")


class OpenALOggDecodeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SAMPLE_SOURCE.read_text(encoding="utf-8", errors="replace")
        # openPR06: LoadOgg forwards to BeginOggLoad, which decodes with stb_vorbis and
        # falls back to libvorbisfile here; the loop and its error handling moved with it.
        cls.load_ogg = cxx_function_body(cls.source, "static short* SoundSample_DecodeOggWithVorbisFile(")
        cls.begin_ogg = cxx_function_body(cls.source, "bool idSoundSample_OpenAL::BeginOggLoad(")

    def test_holes_are_recoverable_but_bounded(self) -> None:
        self.assertIn("static const int OGG_MAX_HOLE_RETRIES = 16;", self.source)
        self.assertIn("if( chunk == OV_HOLE )", self.load_ogg)
        self.assertIn("++holeRetries > OGG_MAX_HOLE_RETRIES", self.load_ogg)
        self.assertIn("continue;", self.load_ogg)
        self.assertLess(
            self.load_ogg.index("if( chunk == OV_HOLE )"),
            self.load_ogg.index("if( chunk < 0"),
        )

    def test_eof_shortfall_is_silence_padded_to_declared_timeline(self) -> None:
        self.assertIn("if( chunk == 0 )", self.load_ogg)
        self.assertIn("reachedEof = true;", self.load_ogg)
        self.assertIn("reachedEof && offset > 0 && offset < capacityBytes", self.load_ogg)
        self.assertIn(
            "memset( reinterpret_cast<byte*>( pcm ) + offset, 0, static_cast<size_t>( capacityBytes - offset ) );",
            self.load_ogg,
        )
        self.assertIn("offset = capacityBytes;", self.load_ogg)
        self.assertIn("const uint64 capacityBytes = static_cast<uint64>( totalFrames ) * bytesPerFrame;", self.load_ogg)
        self.assertNotIn("offset != capacityBytes", self.load_ogg)

    def test_fatal_negatives_and_invalid_pcm_geometry_fail(self) -> None:
        self.assertIn("if( chunk < 0 || static_cast<uint64>( chunk ) % bytesPerFrame != 0 )", self.load_ogg)
        self.assertIn("ov_streams( &vorbisFile ) != 1", self.load_ogg)
        self.assertIn("FreeBuffer( pcm );", self.load_ogg)
        self.assertIn("return NULL;", self.load_ogg)
        self.assertIn("libvorbisfile could not decode it either", self.begin_ogg)
        self.assertIn("FreeData();", self.begin_ogg)

if __name__ == "__main__":
    unittest.main(verbosity=2)
