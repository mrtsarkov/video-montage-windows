#!/usr/bin/env python3
"""Measure a flat brand colour in a rendered frame (spec §11.3/§11.4 colour path).

The graphics layer is ProRes 4444 tagged BT.601, so it has to be read with an
explicit matrix and composited in RGB. This checker proves the round trip: it
finds the pixels closest to the expected colour in a frame and reports the
median of that cluster plus per-channel error.

Usage:
  check_color.py <video> --at 1.0 --hex f97316 [--tol 90] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def frame(video: Path, t: float, w: int = 1920, h: int = 1080) -> np.ndarray:
    tmp = Path(tempfile.mkdtemp()) / "f.raw"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                    "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                    "-pix_fmt", "rgb24", str(tmp)], check=True)
    return np.fromfile(tmp, dtype=np.uint8).reshape(h, w, 3).astype(np.int16)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--at", type=float, required=True)
    ap.add_argument("--hex", required=True, dest="hex_color")
    ap.add_argument("--tol", type=float, default=40.0,
                    help="max euclidean distance for the cluster (keep it tight: wide tolerances "
                         "pull anti-aliased edges and soft shadows into the median)")
    ap.add_argument("--tol-ok", type=float, default=12.0, help="pass threshold, mean channel error")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    want = np.array([int(args.hex_color[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.int32)
    img = frame(Path(args.video).resolve(), args.at)
    flat = img.reshape(-1, 3).astype(np.int32)
    dist = np.sqrt(((flat - want) ** 2).sum(axis=1).astype(np.float64))
    sel = flat[dist <= args.tol]
    if len(sel) < 50:
        print(f"FAIL: only {len(sel)} pixels within tolerance {args.tol} of #{args.hex_color}")
        return 1
    med = np.median(sel, axis=0)
    err = np.abs(med - want)
    ok = bool(err.mean() <= args.tol_ok)
    res = {
        "video": str(args.video),
        "at_s": args.at,
        "expected_hex": args.hex_color.lower(),
        "expected_rgb": want.tolist(),
        "measured_rgb": [int(v) for v in med],
        "mean_channel_error": round(float(err.mean()), 2),
        "max_channel_error": int(err.max()),
        "pixels_in_cluster": int(len(sel)),
        "threshold": args.tol_ok,
        "status": "PASS" if ok else "FAIL",
    }
    print(f"colour @ {args.at:.2f}s  expected #{args.hex_color.lower()} {want.tolist()}  "
          f"measured {res['measured_rgb']}  mean err {res['mean_channel_error']}  "
          f"({res['pixels_in_cluster']} px)  -> {res['status']}")
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
