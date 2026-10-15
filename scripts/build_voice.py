#!/usr/bin/env python3
"""Assemble the voice track from an EDL (spec §6.1).

Cuts are declicked with a short fade in/out on every segment instead of an
overlapping crossfade: a real `acrossfade` shortens the audio by
(n-1) * fade, which desynchronises it from the video track, while micro-fades
remove the click and keep the duration exact.

Usage:
  build_voice.py <source.mp4> <edl.json> <voice.wav> [--fade 0.012] [--rate 48000]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("edl")
    ap.add_argument("out")
    ap.add_argument("--fade", type=float, default=0.012, help="declick fade per edge, s (spec: 10-20 ms)")
    ap.add_argument("--rate", type=int, default=48000)
    args = ap.parse_args()

    src = Path(args.source).resolve()
    edl = json.loads(Path(args.edl).read_text(encoding="utf-8-sig"))
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    chains, labels = [], []
    for i, seg in enumerate(edl):
        a, b = float(seg["in"]), float(seg["out"])
        dur = b - a
        f = min(args.fade, dur / 4)
        # even-indexed voice parts get the fade; keep the fade small relative to the clip
        chains.append(
            f"[0:a]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS,"
            f"aformat=sample_fmts=fltp:sample_rates={args.rate}:channel_layouts=mono,"
            f"afade=t=in:st=0:d={f:.4f},afade=t=out:st={dur - f:.4f}:d={f:.4f}[a{i}]"
        )
        labels.append(f"[a{i}]")
    chains.append(f"{''.join(labels)}concat=n={len(edl)}:v=0:a=1[cat]")
    chains.append(f"[cat]aformat=sample_fmts=s16:sample_rates={args.rate}[out]")

    graph = ";\n".join(chains)
    if len(graph) > 30000:
        raise SystemExit(f"filter graph too long for the command line ({len(graph)} chars)")

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-filter_complex", graph, "-map", "[out]",
         "-c:a", "pcm_s16le", str(out)],
        check=True,
    )

    expected = sum(float(s["out"]) - float(s["in"]) for s in edl)
    got = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True).stdout.strip())
    print(f"Voice: {out}")
    print(f"  clips {len(edl)}  declick fade {args.fade * 1000:.0f} ms per edge")
    print(f"  duration {got:.3f}s  expected {expected:.3f}s  delta {got - expected:+.3f}s")
    return 0 if abs(got - expected) < 0.05 else 1


if __name__ == "__main__":
    raise SystemExit(main())
