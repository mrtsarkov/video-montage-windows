#!/usr/bin/env python3
"""Analyze sfx/ files for montage §6.2 (agent cannot listen — metadata only)."""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        text=True,
    )
    return float(out.strip())


def analyze_wav(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if w.getnchannels() > 1:
        x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    env = np.abs(x)
    peak_i = int(np.argmax(env))
    peak_t = peak_i / sr
    rms = float(np.sqrt(np.mean(x**2) + 1e-12))
    peak = float(np.max(np.abs(x)) + 1e-12)
    # crude brightness via zero-crossing rate
    zcr = float(np.mean(np.abs(np.diff(np.sign(x)))) / 2)
    shape = "impact" if peak / (rms + 1e-6) > 8 else "tail"
    return {
        "duration_sec": len(x) / sr,
        "peak_time_sec": peak_t,
        "rms": rms,
        "peak": peak,
        "brightness_zcr": zcr,
        "envelope_shape": shape,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: sfx_catalog.py <sfx_dir> [out.json]", file=sys.stderr)
        return 1
    sfx_dir = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else sfx_dir / ".." / "runs" / "cursor" / "edit" / "sfx_catalog.json"
    items = []
    for p in sorted(sfx_dir.glob("*")):
        if p.suffix.lower() not in {".wav", ".mp3", ".ogg", ".flac", ".m4a"}:
            continue
        entry = {"file": p.name, "path": str(p.resolve())}
        try:
            entry["duration_sec"] = probe_duration(p)
            if p.suffix.lower() == ".wav":
                entry.update(analyze_wav(p))
        except Exception as e:
            entry["error"] = str(e)
        items.append(entry)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(items)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
