#!/usr/bin/env python3
"""Build background plate: EDL concat + per-segment zoom (ffmpeg)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def load_edl(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def timeline(edl: list[dict]) -> list[dict]:
    t = 0.0
    segs = []
    for c in edl:
        dur = c["out"] - c["in"]
        segs.append({**c, "timeline_start": t, "duration": dur})
        t += dur
    return segs


def segment_filter(si: int, dur: float, w: int, h: int) -> str:
    """Correction + alternating static crop (jump-cut friendly)."""
    corr = "eq=contrast=1.06:brightness=0.02:saturation=1.05"
    base_scale = 1.0 if si % 2 == 0 else 1.35
    if dur > 10 and si % 3 == 1:
        base_scale = 1.38
    cw = max(2, int(w / base_scale))
    ch = max(2, int(h / base_scale))
    # even dimensions for yuv420p
    cw -= cw % 2
    ch -= ch % 2
    x = int(w * 0.5 - cw / 2)
    y = int(h * 0.38 - ch / 2)
    x = max(0, min(w - cw, x))
    y = max(0, min(h - ch, y))
    x -= x % 2
    y -= y % 2
    return f"{corr},crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos"


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: build_plate.py <source.mp4> <edl.json> <plate.mp4>", file=sys.stderr)
        return 1
    src = Path(sys.argv[1]).resolve()
    edl = load_edl(Path(sys.argv[2]))
    out = Path(sys.argv[3]).resolve()
    segs = timeline(edl)
    tmp = Path(tempfile.mkdtemp())
    parts: list[Path] = []
    w, h = 1920, 1080
    for i, seg in enumerate(segs):
        part = tmp / f"seg_{i:04d}.mp4"
        vf = segment_filter(i, seg["duration"], w, h)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(seg["in"]),
                "-to", str(seg["out"]),
                "-i", str(src),
                "-vf", vf,
                "-an",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "50M",
                "-color_range", "tv", "-colorspace", "bt709",
                "-color_primaries", "bt709", "-color_trc", "bt709",
                str(part),
            ],
            check=True,
            capture_output=True,
        )
        parts.append(part)
    list_file = tmp / "list.txt"
    list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "50M",
            "-color_range", "tv", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            str(out),
        ],
        check=True,
    )
    dur = sum(s["duration"] for s in segs)
    print(f"Plate: {out} ({dur:.1f}s, {len(segs)} segments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
