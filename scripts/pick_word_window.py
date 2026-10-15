#!/usr/bin/env python3
"""Choose where the big word goes so it can actually hide behind the speaker (spec §8).

The semantic trigger names the moment the phrase is spoken, but in a screen-recording
take that moment often shows the screen with only a small PiP: measured person coverage
was 1.4% there against 25.3% on the nearest camera close-up. So the trigger position is
only a hint — this step scores candidate moments by how much of the frame the person
occupies and moves the window to the best one near the trigger.

Usage:
  pick_word_window.py <plate.mp4> <edit_dir> [--span 25] [--samples 9] [--min-person-pct 5]
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

GW, GH = 480, 270


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def hf_exe() -> list[str]:
    exe = shutil.which("hyperframes")
    if not exe:
        raise SystemExit("hyperframes not found on PATH")
    if exe.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", exe]
    return [exe]


def coverage(frame: np.ndarray) -> float:
    return float((frame > 128).mean() * 100) if frame.size else 0.0


def person_share(plate: Path, t: float, work: Path) -> float:
    """Person share of the frame at time t, via the same model used for the matte."""
    png = work / f"f_{t:07.2f}.png"
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(plate),
         "-frames:v", "1", str(png)], capture_output=True)
    out = work / f"m_{t:07.2f}.png"
    try:
        run([*hf_exe(), "remove-background", str(png), "-o", str(out), "--device", "cpu"],
            capture_output=True)
    except subprocess.CalledProcessError:
        return 0.0
    raw = work / f"a_{t:07.2f}.raw"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf", f"alphaextract,scale={GW}:{GH}",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", str(raw)], capture_output=True)
    return coverage(np.fromfile(raw, dtype=np.uint8))


def duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plate")
    ap.add_argument("edit_dir")
    ap.add_argument("--span", type=float, default=25.0, help="seconds around the trigger to search")
    ap.add_argument("--samples", type=int, default=9, help="candidate moments inside the span")
    ap.add_argument("--min-person-pct", type=float, default=5.0)
    args = ap.parse_args()

    plate = Path(args.plate).resolve()
    edit = Path(args.edit_dir).resolve()
    meta_path = edit / "back_layer.json"
    if not plate.is_file():
        raise SystemExit(f"plate not found: {plate}")
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    trigger = float(meta["start_s"])
    length = float(meta["duration_s"])
    total = duration(plate)
    if total <= length + 1:
        print(f"plate is only {total:.1f}s; leaving the window at {trigger:.2f}s")
        return 0

    lo = max(0.5, trigger - args.span)
    hi = min(total - length - 0.5, trigger + args.span)
    candidates = sorted({round(lo + (hi - lo) * i / max(1, args.samples - 1), 2)
                         for i in range(args.samples)} | {round(trigger, 2)})
    work = Path(tempfile.mkdtemp())
    scored = []
    for t in candidates:
        share = person_share(plate, t, work)
        scored.append((share, t))
        print(f"  t={t:7.2f}s  person {share:5.2f}%")

    scored.sort(key=lambda x: (-x[0], abs(x[1] - trigger)))
    best_share, best_t = scored[0]
    if best_share < args.min_person_pct:
        raise SystemExit(f"no candidate within +-{args.span:.0f}s of the trigger has a person "
                         f"(best {best_share:.2f}% at {best_t:.2f}s) — record the key phrase on camera "
                         f"or pass a manual back_layer.json")
    chosen = max(0.5, min(best_t, total - length - 0.5))
    meta["start_s"] = round(chosen, 3)
    meta["chosen_by"] = "pick_word_window.py (person coverage)"
    meta["trigger_s"] = round(trigger, 3)
    meta["candidates"] = [{"t": t, "person_pct": round(s, 2)} for s, t in sorted(scored, key=lambda x: x[1])]
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (edit / "word_window.json").write_text(json.dumps({
        "trigger_s": round(trigger, 3), "chosen_s": round(chosen, 3),
        "person_pct_at_trigger": next((s for s, t in scored if abs(t - trigger) < 0.01), None),
        "person_pct_at_chosen": round(best_share, 2),
        "candidates": meta["candidates"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"word window: {trigger:.2f}s -> {chosen:.2f}s (person {best_share:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
