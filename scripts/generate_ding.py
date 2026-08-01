#!/usr/bin/env python3
"""Synthesize a short Wunderlist-ish ding and write ding.wav."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "xong" / "static" / "sounds" / "ding.wav"


def synth(sample_rate: int = 22050) -> bytes:
    duration = 0.22
    n = int(sample_rate * duration)
    # Two partials: bright fundamental + soft fifth, short decay
    f1, f2 = 880.0, 1318.5  # A5 + E6
    samples: list[float] = []
    for i in range(n):
        t = i / sample_rate
        # Exponential envelope
        env = math.exp(-t * 14.0)
        # Soft attack
        attack = min(1.0, t / 0.008)
        s = (
            0.55 * math.sin(2 * math.pi * f1 * t)
            + 0.28 * math.sin(2 * math.pi * f2 * t)
            + 0.12 * math.sin(2 * math.pi * (f1 * 2) * t)
        )
        samples.append(s * env * attack)

    # Normalize
    peak = max(abs(x) for x in samples) or 1.0
    scale = 0.85 / peak
    pcm = bytearray()
    for x in samples:
        v = int(max(-1.0, min(1.0, x * scale)) * 32767)
        pcm += struct.pack("<h", v)
    return bytes(pcm)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = synth()
    with wave.open(str(OUT), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(data)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
