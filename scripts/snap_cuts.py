#!/usr/bin/env python3
"""Snap EDL cut points to the speech envelope (spec MONTAGE-PROMPT-v4 §4).

Transcript timestamps lie on tails: the spec requires cuts on the waveform, not on
word times. This script:

  * extracts a 16 kHz mono envelope of the source once (cached),
  * snaps every segment `in` to (first speech onset - pre-roll) and `out` to
    (last speech offset + post-roll), searching a bounded window,
  * splits segments at internal pauses longer than `--max-pause`, keeping only
    `--keep-pause` seconds of the pause (spec: >0.3 s compressed to 0.1-0.15 s).

Usage:
  snap_cuts.py <source.mp4> <edl_in.json> <edl_out.json> [--data data.json]
               [--fps 30] [--search 0.30] [--max-pause 0.30] [--keep-pause 0.12]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HOP = 0.010      # envelope frame step, s
WIN = 0.025      # envelope window, s
SMOOTH = 3       # moving-average frames


def envelope(src: Path, cache: Path) -> tuple[np.ndarray, float]:
    """Return (rms envelope, hop) for the source audio."""
    if not cache.exists():
        raw = cache.with_suffix(".raw")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
             "-ar", "16000", "-f", "f32le", str(raw)],
            check=True,
        )
        raw.replace(cache)
    x = np.fromfile(cache, dtype=np.float32)
    step = int(HOP * 16000)
    win = int(WIN * 16000)
    if len(x) < win:
        raise SystemExit("audio too short")
    n = (len(x) - win) // step + 1
    idx = np.arange(win)[None, :] + step * np.arange(n)[:, None]
    frames = x[idx]
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    if SMOOTH > 1:
        k = np.ones(SMOOTH) / SMOOTH
        rms = np.convolve(rms, k, mode="same")
    return rms, HOP


def threshold(rms: np.ndarray) -> float:
    peak = float(np.percentile(rms, 95))
    floor = float(np.percentile(rms, 20))
    return max(floor + 0.08 * (peak - floor), 0.10 * peak, 1e-4)


def first_onset(rms: np.ndarray, thr: float, a: float, b: float) -> float | None:
    i0, i1 = max(0, int(a / HOP)), min(len(rms), int(b / HOP))
    above = rms[i0:i1] > thr
    for i in range(len(above)):
        if above[i]:
            return (i0 + i) * HOP
    return None


def last_offset(rms: np.ndarray, thr: float, a: float, b: float) -> float | None:
    i0, i1 = max(0, int(a / HOP)), min(len(rms), int(b / HOP))
    above = rms[i0:i1] > thr
    for i in range(len(above) - 1, -1, -1):
        if above[i]:
            return (i0 + i + 1) * HOP
    return None


def silence_runs(rms: np.ndarray, thr: float, a: float, b: float, min_len: float):
    i0, i1 = max(0, int(a / HOP)), min(len(rms), int(b / HOP))
    runs, start = [], None
    for i in range(i0, i1):
        if rms[i] <= thr:
            if start is None:
                start = i
        elif start is not None:
            if (i - start) * HOP >= min_len:
                runs.append((start * HOP, i * HOP))
            start = None
    if start is not None and (i1 - start) * HOP >= min_len:
        runs.append((start * HOP, i1 * HOP))
    return runs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("edl_in")
    ap.add_argument("edl_out")
    ap.add_argument("--data", default=None, help="data.json to update 'segments' in sync")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--search", type=float, default=0.30, help="search window around a cut, s")
    ap.add_argument("--pre-roll", type=float, default=0.08, help="lead before speech onset, s")
    ap.add_argument("--post-roll", type=float, default=0.06, help="tail after speech offset, s")
    ap.add_argument("--max-pause", type=float, default=0.30, help="pause longer than this is compressed")
    ap.add_argument("--keep-pause", type=float, default=0.12, help="pause kept after compression, s")
    ap.add_argument("--min-clip", type=float, default=0.25, help="drop clips shorter than this, s")
    ap.add_argument("--tail-hold", type=float, default=0.0,
                    help="keep this much footage after the last word, so the speech "
                         "and a beat of silence survive before the end card")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    edl = json.loads(Path(args.edl_in).read_text(encoding="utf-8-sig"))
    tmp = Path(tempfile.mkdtemp())
    cache = tmp / "env.f32"
    rms, _ = envelope(src, cache)
    thr = threshold(rms)
    total = float(rms.shape[0]) * HOP

    out: list[dict] = []
    n_snap_in = n_snap_out = n_split = n_drop = 0

    for seg in edl:
        text = seg.get("text", "")
        src_name = seg.get("source", src.name)
        a, b = float(seg["in"]), float(seg["out"])

        on = first_onset(rms, thr, max(0.0, a - args.search), min(total, b))
        if on is not None and abs(on - a) > 0.001:
            a = max(0.0, on - args.pre_roll)
            n_snap_in += 1
        off = last_offset(rms, thr, a, min(total, b + args.search))
        if off is not None and abs(off - b) > 0.001:
            b = min(total, off + args.post_roll)
            n_snap_out += 1
        if b - a < args.min_clip:
            n_drop += 1
            continue

        # split at internal pauses, keeping a short pause
        cuts: list[tuple[float, float]] = [(a, b)]
        for (s, e) in silence_runs(rms, thr, a + 0.15, b - 0.15, args.max_pause):
            if (e - s) <= args.keep_pause:
                continue
            cuts = _split(cuts, s + args.keep_pause / 2, e - args.keep_pause / 2)
        if len(cuts) > 1:
            n_split += len(cuts) - 1

        for k, (ca, cb) in enumerate(cuts):
            if cb - ca < args.min_clip:
                n_drop += 1
                continue
            out.append({
                "text": text if k == 0 else "",
                "source": src_name,
                "in": round(ca, 3),
                "out": round(cb, 3),
                "reason": ("waveform onset/offset snap" if k == 0 else "continuation after pause trim")
                          + (f" (part {k + 1}/{len(cuts)})" if len(cuts) > 1 else ""),
            })

    if args.tail_hold > 0 and out:
        last = out[-1]
        want = min(total, last["out"] + args.tail_hold)
        if want > last["out"]:
            last["out"] = round(want, 3)
            last["reason"] += " + tail hold (let the closing words land)"

    Path(args.edl_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.data:
        dp = Path(args.data)
        d = json.loads(dp.read_text(encoding="utf-8-sig"))
        d["segments"] = out
        dp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    dur_in = sum(float(s["out"]) - float(s["in"]) for s in edl)
    dur_out = sum(s["out"] - s["in"] for s in out)
    print(f"segments: {len(edl)} -> {len(out)}  "
          f"(snap in {n_snap_in}, snap out {n_snap_out}, splits {n_split}, dropped {n_drop})")
    print(f"duration: {dur_in:.2f}s -> {dur_out:.2f}s  (threshold {thr:.4f})")
    print(f"written: {args.edl_out}")
    return 0


def _split(cuts: list[tuple[float, float]], at1: float, at2: float):
    res = []
    for (a, b) in cuts:
        if a < at1 < b and a < at2 < b and at1 > a and at2 < b:
            res.append((a, at1))
            res.append((at2, b))
        else:
            res.append((a, b))
    return res


if __name__ == "__main__":
    raise SystemExit(main())
