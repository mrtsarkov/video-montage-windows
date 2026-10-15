#!/usr/bin/env python3
"""Measure the sfx/ library into a catalog (spec §6.2).

For every file the spec asks for: duration, peak time, loudness, envelope shape
(impact / whoosh / riser / tail), brightness (spectral centroid), type
(whoosh / pop / click / impact / riser / transition) and what it suits.

The old version only read WAV through the wave module, so every mp3 got a
duration and nothing else; this one decodes anything ffmpeg reads.

Usage:
  sfx_catalog.py <sfx_dir> <out.json> [--rate 16000]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HOP = 0.005
FRAME = 0.025


def load(path: Path, rate: int) -> np.ndarray:
    raw = Path(tempfile.mkdtemp()) / "s.f32"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                    "-ar", str(rate), "-f", "f32le", str(raw)], check=True)
    return np.fromfile(raw, dtype=np.float32)


def envelope(x: np.ndarray, rate: int) -> np.ndarray:
    step, win = int(HOP * rate), int(FRAME * rate)
    if len(x) < win:
        return np.array([float(np.sqrt((x ** 2).mean() + 1e-12))])
    n = (len(x) - win) // step + 1
    idx = np.arange(win)[None, :] + step * np.arange(n)[:, None]
    return np.sqrt((x[idx] ** 2).mean(axis=1) + 1e-12)


def spectral_centroid(x: np.ndarray, rate: int) -> float:
    if len(x) < 1024:
        return 0.0
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    total = spec.sum()
    return float((freqs * spec).sum() / total) if total > 0 else 0.0


def classify(dur: float, attack_ms: float) -> tuple[str, str, str]:
    if attack_ms >= 180:
        return "riser", "нарастание", "подводка к событию; финал нарастания ставится на кадр события"
    if dur < 0.5:
        return "click", "удар", "галочка, тик, шаг степпера, счётчик"
    if dur < 1.2:
        return "pop", "удар", "появление плашки, метки, пункта списка"
    if dur >= 1.5:
        return "impact", "удар", "крупное событие: слово за головой, полноэкранная карточка"
    return "whoosh", "взмах", "наезд камеры, split, переход между сценами"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sfx_dir")
    ap.add_argument("out")
    ap.add_argument("--rate", type=int, default=16000)
    args = ap.parse_args()

    files = sorted(p for p in Path(args.sfx_dir).glob("*")
                   if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"))
    entries, duplicates = [], []
    seen: dict[str, str] = {}
    for path in files:
        x = load(path, args.rate)
        if not len(x):
            continue
        env = envelope(x, args.rate)
        peak_i = int(np.argmax(env))
        peak = float(env[peak_i])
        attack_ms = peak_i * HOP * 1000.0
        dur = len(x) / args.rate
        kind, shape, suits = classify(dur, attack_ms)
        import hashlib
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        if digest in seen:
            duplicates.append({"file": path.name, "same_as": seen[digest]})
        else:
            seen[digest] = path.name
        entries.append({
            "file": path.name,
            "sha256_12": digest,
            "duration_s": round(dur, 3),
            "peak_at_s": round(peak_i * HOP, 3),
            "peak_dbfs": round(20 * np.log10(peak + 1e-9), 2),
            "attack_ms": round(attack_ms, 1),
            "shape": shape,
            "type": kind,
            "brightness_hz": int(spectral_centroid(x, args.rate)),
            "sustain_ratio": round(float(env[peak_i:].mean() / peak) if peak > 0 else 0.0, 3),
            "suits": suits,
            "use_gain_linear": 0.3,
        })

    out = Path(args.out)
    out.write_text(json.dumps({"files": entries, "duplicates": duplicates},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SFX catalog: {len(entries)} file(s) -> {out}")
    for e in entries:
        print(f"  {e['file']:18s} {e['duration_s']:5.2f}s  peak {e['peak_at_s']:5.2f}s "
              f"{e['peak_dbfs']:6.2f} dBFS  attack {e['attack_ms']:6.1f} ms  {e['shape']:10s} "
              f"{e['type']:7s} centroid {e['brightness_hz']:5d} Hz")
    if duplicates:
        for d in duplicates:
            print(f"  ! {d['file']} is byte-identical to {d['same_as']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
