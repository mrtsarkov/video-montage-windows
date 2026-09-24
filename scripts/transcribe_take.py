#!/usr/bin/env python3
"""Transcribe a take with faster-whisper large-v3, split on pauses >= 0.7s."""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np


def extract_wav(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)],
        check=True,
        capture_output=True,
    )


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if w.getnchannels() > 1:
        x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    return x, sr


def silence_segments(wav: Path, min_pause: float = 0.7, min_seg: float = 0.3) -> list[tuple[float, float]]:
    log = wav.with_suffix(".silence.log")
    subprocess.run(
        ["ffmpeg", "-i", str(wav), "-af", f"silencedetect=noise=-30dB:d={min_pause}", "-f", "null", "-"],
        stderr=open(log, "w", encoding="utf-8"),
        stdout=subprocess.DEVNULL,
        check=True,
    )
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    segments: list[tuple[float, float]] = []
    start = 0.0
    for line in lines:
        if "silence_start:" in line:
            end = float(line.split("silence_start:")[1].strip())
            if end - start >= min_seg:
                segments.append((start, end))
        elif "silence_end:" in line:
            start = float(line.split("silence_end:")[1].strip().split()[0])
    x, sr = read_wav(wav)
    dur = len(x) / sr
    if dur - start >= min_seg:
        segments.append((start, dur))
    return segments or [(0.0, dur)]


def transcribe(src: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = src.stem
    wav = out_dir / f"{base}.16k.wav"
    extract_wav(src, wav)
    segments = silence_segments(wav)
    print(f"Segments: {len(segments)}", flush=True)

    from faster_whisper import WhisperModel

    model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    all_words: list[dict] = []
    for i, (seg_start, seg_end) in enumerate(segments, 1):
        seg_wav = out_dir / f"{base}-seg-{i:03d}.wav"
        length = seg_end - seg_start
        subprocess.run(
            ["ffmpeg", "-y", "-ss", str(seg_start), "-t", str(length), "-i", str(wav), "-c", "copy", str(seg_wav)],
            check=True,
            capture_output=True,
        )
        segs, _ = model.transcribe(
            str(seg_wav),
            language="ru",
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        for s in segs:
            if not s.words:
                continue
            for w in s.words:
                all_words.append(
                    {
                        "word": w.word.strip(),
                        "start": round(w.start + seg_start, 3),
                        "end": round(w.end + seg_start, 3),
                    }
                )
        print(f"  seg {i}/{len(segments)}: +{len(all_words)} words total", flush=True)

    merged = out_dir / f"{base}-words.json"
    merged.write_text(json.dumps(all_words, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {merged} ({len(all_words)} words)")
    return merged


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: transcribe_take.py <take.mp4> [out_dir]", file=sys.stderr)
        return 1
    src = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else src.parent.parent / "runs" / "cursor" / "edit" / "transcripts"
    transcribe(src, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
