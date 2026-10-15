#!/usr/bin/env python3
"""Person matte for the «слово за головой» window (spec §8).

The model runs at ~2.5 fps on CPU, so the matte is computed for the word's window
only (3-4 s) and not for the whole film. Per §8 the plate supplies the colour and
this file supplies the alpha only, so the output is a ProRes 4444 clip whose alpha
is the person.

Usage:
  build_mask.py <plate.mp4> <edit_dir> [--backend hyperframes] [--device cpu]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kw)


def hf_exe() -> list[str]:
    exe = shutil.which("hyperframes")
    if not exe:
        raise SystemExit("hyperframes not found on PATH")
    if exe.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", exe]
    return [exe]


def probe(path: Path, entries: str) -> str:
    return run(["ffprobe", "-v", "error", "-show_entries", entries,
                "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
               capture_output=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plate")
    ap.add_argument("edit_dir")
    ap.add_argument("--meta", default="back_layer.json")
    ap.add_argument("--out", default="person-mask.mov")
    ap.add_argument("--device", default="cpu", choices=["auto", "cpu", "cuda", "coreml"])
    ap.add_argument("--lead", type=float, default=0.15, help="extra seconds before the word")
    ap.add_argument("--min-person-pct", type=float, default=5.0,
                    help="fail if the matte covers less than this share of the frame: "
                         "the word cannot hide behind a person who is not there (spec §8)")
    ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()

    plate = Path(args.plate).resolve()
    edit = Path(args.edit_dir).resolve()
    meta_path = edit / args.meta
    if not plate.is_file():
        raise SystemExit(f"plate not found: {plate}")
    if not meta_path.is_file():
        raise SystemExit(f"no back-layer metadata: {meta_path}; run generate_comp.py --back")
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    start = max(0.0, float(meta["start_s"]) - args.lead)
    dur = float(meta["duration_s"]) + args.lead
    out = edit / args.out

    tmp = Path(tempfile.mkdtemp())
    clip = tmp / "word-window.mp4"
    # lossless window so the matte is computed on untouched plate pixels (§8)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", str(plate), "-an", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p",
         str(clip)])

    print(f"mask window: {dur:.2f}s from {start:.2f}s ({meta['element']})")
    run([*hf_exe(), "remove-background", str(clip), "-o", str(out), "--device", args.device])

    if not out.is_file():
        raise SystemExit("remove-background produced no file")
    got_dur = float(probe(out, "format=duration"))
    pix = probe(out, "stream=pix_fmt")
    if "a" not in pix:
        raise SystemExit(f"mask has no alpha channel (pix_fmt={pix})")
    print(f"mask: {out.name} {out.stat().st_size / 1e6:.1f} MB, {got_dur:.3f}s, {pix}")

    # sanity: how much of the frame is the person, and does the matte actually vary
    raw = tmp / "a.raw"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf", "alphaextract,scale=480:270",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(raw)])
    frame = np.fromfile(raw, dtype=np.uint8)
    if frame.size:
        cover = float((frame > 128).mean() * 100)
        print(f"      person covers {cover:.1f}% of the frame (alpha > 0.5) on the first frame")
        (edit / "mask_info.json").write_text(json.dumps({
            "file": out.name, "window_start_s": round(start, 3),
            "window_duration_s": round(got_dur, 3), "pix_fmt": pix,
            "person_coverage_pct": round(cover, 2), "device": args.device,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        if cover < args.min_person_pct and not args.allow_empty:
            raise SystemExit(
                f"person covers only {cover:.1f}% of the frame in this window "
                f"(< {args.min_person_pct:g}%): «слово за головой» has nothing to hide behind.\n"
                f"Move the word window to a camera close-up "
                f"(back_layer.json start_s) or pass --allow-empty."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
