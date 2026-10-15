#!/usr/bin/env python3
"""Measure the eye line in a take (does the speaker look into the lens?).

Why this exists
---------------
"Keep the eyes on the camera" is a *shooting* problem, not an editing one: on this
take the teleprompter column sat at 80 % of the screen height while the webcam sat
at the top of the monitor, so the reader looked down and off-axis, and the screen's
violet glow reflected in the lower half of both lenses. Post cannot fix a gaze, so
the fix is the prompter layout (`build_teleprompter.py --eyeline`) - and this tool
is how the fix is verified instead of guessed.

How it measures
---------------
For N evenly spaced frames it looks at the face band and finds

  * the screen reflection: pixels that are clearly violet/blue (the prompter is the
    only blue-violet source in a daylight talking-head shot),
  * the eye centre: the centroid of the darkest pixels in the band (the glasses
    frame and the pupils dominate the dark tail).

`offset` is the reflection centroid minus the eye centre, in per cent of frame
height. A screen placed above the lens paints the reflection above the eye centre
(offset < 0); a screen below the eye line - the usual mistake - gives offset > 0.

Usage:
  check_eyeline.py <take.mp4> [--frames 12] [--lens-percent 9]
                   [--band-top 22 --band-bottom 62] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

W, H = 480, 270          # analysis resolution
VIOLET_B_MIN = 95
VIOLET_BR_MIN = 22
VIOLET_BG_MIN = 16
DARK_PCT = 3.0
LENS_TOL_PCT = 1.5       # |offset| beyond this is a real eye-line error
BAND_X = (0.30, 0.72)


def frames_of(src: Path, count: int, duration: float) -> list[np.ndarray]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(count):
            t = duration * (i + 0.5) / count
            raw = Path(tmp) / f"f{i}.rgb"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src),
                            "-frames:v", "1", "-vf", f"scale={W}:{H}", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", str(raw)], check=True)
            if raw.is_file() and raw.stat().st_size >= W * H * 3:
                out.append(np.frombuffer(raw.read_bytes()[: W * H * 3], dtype=np.uint8)
                           .reshape(H, W, 3))
    return out


def probe_duration(src: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(src)], capture_output=True, text=True,
                         check=True).stdout.strip()
    return float(out or 0.0)


def measure(frame: np.ndarray, band_top: float, band_bottom: float) -> dict | None:
    y0, y1 = int(H * band_top / 100), int(H * band_bottom / 100)
    x0, x1 = int(W * BAND_X[0]), int(W * BAND_X[1])
    band = frame[y0:y1, x0:x1].astype(np.int16)
    r, g, b = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    violet = (b > VIOLET_B_MIN) & ((b - r) > VIOLET_BR_MIN) & ((b - g) > VIOLET_BG_MIN)
    if violet.sum() < 12:
        return None
    ys, xs = np.nonzero(violet)
    lum = band.mean(axis=2)
    thr = np.percentile(lum, DARK_PCT)
    dark = lum <= thr
    dys, _dxs = np.nonzero(dark)
    if len(dys) < 12:
        return None
    refl_y = (y0 + ys.mean()) / H * 100.0
    eye_y = (y0 + dys.mean()) / H * 100.0
    return {"reflection_y_pct": round(float(refl_y), 2), "eye_y_pct": round(float(eye_y), 2),
            "offset_pct": round(float(refl_y - eye_y), 2),
            "violet_share_pct": round(float(violet.mean() * 100.0), 2),
            "reflection_x_pct": round(float((x0 + xs.mean()) / W * 100.0), 2)}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Measure the speaker's eye line in a take")
    ap.add_argument("take")
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--lens-percent", type=float, default=9.0,
                    help="where the lens sits in the frame, %% of height (a webcam on top ≈ 8-11)")
    ap.add_argument("--band-top", type=float, default=22.0)
    ap.add_argument("--band-bottom", type=float, default=62.0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    src = Path(args.take).resolve()
    if not src.is_file():
        raise SystemExit(f"take not found: {src}")
    duration = probe_duration(src)
    frames = frames_of(src, args.frames, duration)
    if not frames:
        raise SystemExit("no frame could be decoded")
    rows = [m for m in (measure(f, args.band_top, args.band_bottom) for f in frames) if m]
    if not rows:
        raise SystemExit("no violet screen reflection found - is the prompter in the shot?")

    offs = np.array([r["offset_pct"] for r in rows])
    refl = float(np.mean([r["reflection_y_pct"] for r in rows]))
    eye = float(np.mean([r["eye_y_pct"] for r in rows]))
    mean_off = float(offs.mean())
    spread = float(offs.max() - offs.min())
    if abs(mean_off) <= LENS_TOL_PCT:
        verdict = "OK"
        note = "экран стоит на линии глаз: взгляд идёт в объектив"
    elif mean_off > 0:
        verdict = "GAZE DOWN"
        note = (f"экран ниже линии глаз на {mean_off:.1f} % высоты кадра — диктор смотрит вниз. "
                f"Поднять строку чтения в суфлёре (--eyeline --lens-percent "
                f"{max(4.0, args.lens_percent):.0f}) и опустить объектив на эту линию")
    else:
        verdict = "GAZE UP"
        note = (f"экран выше линии глаз на {abs(mean_off):.1f} % высоты кадра — диктор смотрит вверх. "
                f"Опустить строку чтения к линии объектива")

    print(f"eye line: {src.name}")
    print(f"  кадров проанализировано      : {len(rows)}/{len(frames)} "
          f"({duration:.0f} с, {duration / max(1, len(frames)):.0f} с шаг)")
    print(f"  отражение суфлёра в очках    : y = {refl:.2f} % высоты кадра, "
          f"x = {np.mean([r['reflection_x_pct'] for r in rows]):.2f} %")
    print(f"  центр глаз (тёмный слой)     : y = {eye:.2f} % высоты кадра")
    print(f"  смещение отражение − глаз    : {mean_off:+.2f} % "
          f"(разброс {spread:.2f} %) при допуске ±{LENS_TOL_PCT:.1f} %")
    print(f"  доля фиолетового в кадре     : "
          f"{np.mean([r['violet_share_pct'] for r in rows]):.2f} %")
    print(f"  линия объектива в этом кадре : {args.lens_percent:.1f} % высоты")
    print(f"  ВЕРДИКТ                      : {verdict} — {note}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"take": str(src), "frames": rows, "mean_offset_pct": round(mean_off, 2),
             "reflection_y_pct": round(refl, 2), "eye_y_pct": round(eye, 2),
             "lens_percent": args.lens_percent, "verdict": verdict},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  отчёт: {args.json}")
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
