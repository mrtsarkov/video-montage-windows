#!/usr/bin/env python3
"""RMS envelope + speech attack detection for subtitle timing (MONTAGE §5)."""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if w.getnchannels() > 1:
        x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    return x, sr


def rms_db(x: np.ndarray, sr: int, win_ms: float = 10.0, hop_ms: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    win = max(1, int(sr * win_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    frames = []
    for i in range(0, len(x) - win, hop):
        chunk = x[i : i + win]
        rms = np.sqrt(np.mean(chunk**2) + 1e-12)
        frames.append(20 * np.log10(rms / 32768.0 + 1e-12))
    t = np.arange(len(frames)) * hop / sr
    db = np.array(frames)
    ref = np.percentile(db, 98)
    return t, db - ref


def find_attacks(t: np.ndarray, db: np.ndarray) -> list[dict]:
    attacks: list[dict] = []
    # A: rise above -20 dB after >=20 ms below
    below = db < -20
    for i in range(1, len(db)):
        if below[i - 1] and db[i] >= -20:
            attacks.append({"t": float(t[i]), "kind": "A"})
    # P: end of pause >=150 ms (simplified)
    silence = db < -35
    run = 0
    for i, s in enumerate(silence):
        run = run + 1 if s else 0
        if run == int(0.15 / (t[1] - t[0] if len(t) > 1 else 0.005)) and not s:
            attacks.append({"t": float(t[i]), "kind": "P"})
    return sorted(attacks, key=lambda a: a["t"])


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: subtitle_attacks.py <voice.wav> [out.json]", file=sys.stderr)
        return 1
    wav = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else wav.with_suffix(".attacks.json")
    x, sr = read_wav_mono(wav)
    t, db = rms_db(x, sr)
    attacks = find_attacks(t, db)
    payload = {"sample_rate": sr, "duration_sec": len(x) / sr, "attacks": attacks}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(attacks)} attacks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
