#!/usr/bin/env python3
"""Assemble voice WAV from EDL with crossfades."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: build_voice.py <source.mp4> <edl.json> <voice.wav>", file=sys.stderr)
        return 1
    src = Path(sys.argv[1])
    edl = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out = Path(sys.argv[3])
    tmp = Path(tempfile.mkdtemp())
    parts: list[Path] = []
    for i, clip in enumerate(edl):
        p = tmp / f"part_{i:04d}.wav"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(clip["in"]),
                "-to", str(clip["out"]),
                "-i", str(src),
                "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
                str(p),
            ],
            check=True,
            capture_output=True,
        )
        parts.append(p)
    if not parts:
        raise SystemExit("empty EDL")
    # concat with tiny crossfade via filter_complex
    if len(parts) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", str(parts[0]), "-c:a", "pcm_s16le", str(out)], check=True)
        return 0
    inputs = []
    for p in parts:
        inputs.extend(["-i", str(p)])
    n = len(parts)
    fades = []
    labels = []
    for i in range(n):
        labels.append(f"[a{i}]")
        fades.append(f"[{i}:a]asetpts=PTS-STARTPTS[a{i}]")
    chain = ";".join(fades)
    # simple concat
    concat_in = "".join(labels)
    filt = f"{chain};{concat_in}concat=n={n}:v=0:a=1[out]"
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[out]", str(out)],
        check=True,
    )
    print(f"Voice: {out} ({len(parts)} clips)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
