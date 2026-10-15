#!/usr/bin/env python3
"""Check an EDL against the audio envelope (spec §4): dead air, truncated speech,
untrimmed internal pauses. Transcript-free — the waveform is the ground truth.

Usage:
  check_edl.py <source.mp4> <edl.json> [--json out.json] [--max-pause 0.30]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HOP, WIN, SMOOTH = 0.010, 0.025, 3


def envelope(src: Path, cache: Path):
    if not cache.exists():
        raw = cache.with_suffix(".raw")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
                        "-ar", "16000", "-f", "f32le", str(raw)], check=True)
        raw.replace(cache)
    x = np.fromfile(cache, dtype=np.float32)
    step, win = int(HOP * 16000), int(WIN * 16000)
    n = (len(x) - win) // step + 1
    idx = np.arange(win)[None, :] + step * np.arange(n)[:, None]
    rms = np.sqrt((x[idx] ** 2).mean(axis=1) + 1e-12)
    return np.convolve(rms, np.ones(SMOOTH) / SMOOTH, mode="same")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("edl")
    ap.add_argument("--json", default=None)
    ap.add_argument("--max-pause", type=float, default=0.30)
    args = ap.parse_args()

    src = Path(args.source).resolve()
    edl = json.loads(Path(args.edl).read_text(encoding="utf-8-sig"))
    tmp = Path(tempfile.mkdtemp())
    rms = envelope(src, tmp / "env.f32")
    peak, floor = float(np.percentile(rms, 95)), float(np.percentile(rms, 20))
    thr = max(floor + 0.08 * (peak - floor), 0.10 * peak, 1e-4)

    lead, tail, dead_total, long_pauses = [], [], 0.0, 0
    cut_in_on_speech = cut_out_on_speech = 0
    for s in edl:
        a, b = float(s["in"]), float(s["out"])
        i0, i1 = int(a / HOP), int(b / HOP)
        seg = rms[i0:i1]
        above = seg > thr
        # dead air at the head: frames before first speech
        first = int(np.argmax(above)) if above.any() else len(above)
        lead.append(first * HOP)
        # dead air at the tail
        last = len(above) - 1 - int(np.argmax(above[::-1])) if above.any() else 0
        tail.append((len(above) - 1 - last) * HOP)
        if above.any():
            dead_total += first * HOP + (len(above) - 1 - last) * HOP
        # a cut that lands while speech is still going chops the word
        at_in = rms[max(0, i0 - 1):i0 + 2].max() > thr if i0 < len(rms) else False
        at_out = rms[max(0, i1 - 1):i1 + 2].max() > thr if i1 < len(rms) else False
        if at_in:
            cut_in_on_speech += 1
        if at_out:
            cut_out_on_speech += 1
        # internal pauses that spec wants compressed
        run = 0
        for v in above:
            if not v:
                run += 1
            else:
                if run * HOP > args.max_pause:
                    long_pauses += 1
                run = 0

    dur = sum(float(s["out"]) - float(s["in"]) for s in edl)
    report = {
        "segments": len(edl),
        "duration_s": round(dur, 3),
        "threshold_rms": round(thr, 5),
        "dead_air_total_s": round(dead_total, 3),
        "dead_air_lead_median_s": round(float(np.median(lead)), 3),
        "dead_air_lead_max_s": round(float(np.max(lead)), 3),
        "dead_air_tail_median_s": round(float(np.median(tail)), 3),
        "dead_air_tail_max_s": round(float(np.max(tail)), 3),
        "cut_in_lands_on_speech": cut_in_on_speech,
        "cut_out_lands_on_speech": cut_out_on_speech,
        "internal_pauses_over_max": long_pauses,
    }
    print(f"EDL: {args.edl}")
    for k, v in report.items():
        print(f"  {k:44s} {v}")
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
