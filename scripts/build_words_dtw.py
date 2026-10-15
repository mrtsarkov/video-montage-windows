#!/usr/bin/env python3
"""Word-level transcript with DTW timestamps (whisper.cpp).

Why this exists
---------------
`tools/transcribe.ps1` ran whisper-cli per silence segment and took the
*segment* offsets as word times, so a whole phrase landed on one "word" (on this
take "сентября" spanned 13.4 s). Graphics anchored to those times appear early or
late, and a retake cannot be told from a normal phrase.

whisper.cpp computes real per-token timestamps with DTW, but **flash attention
silently disables it** ("dtw_token_timestamps is not supported with flash_attn -
disabling"), so the flag alone changes nothing. This script therefore always runs
with `-nfa -dtw <preset>`; `t_dtw` is in centiseconds, so it is multiplied by 10.

Usage:
  build_words_dtw.py <take.mp4|wav> <out-words.json> [--raw raw.json]
                     [--model PATH] [--lang ru] [--dtw large.v3] [--threads N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKIP_TOKEN = re.compile(r"^\[_[A-Z0-9_]*\]$")
PUNCT_ONLY = re.compile(r"^[^\w]+$", re.UNICODE)


def run(cmd: list[str]) -> None:
    print("    $ " + " ".join(str(c) for c in cmd[:6]) + (" ..." if len(cmd) > 6 else ""),
          flush=True)
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-15:])
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(str(c) for c in cmd)}\n{tail}")


def to_wav(src: Path, dst: Path) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(dst)])


def dtw_preset(model: Path, explicit: str | None) -> str:
    if explicit:
        return explicit
    name = model.stem.lower()
    if "large-v3" in name or "large_v3" in name:
        return "large.v3"
    if "large-v2" in name:
        return "large.v2"
    if "large-v1" in name:
        return "large.v1"
    if "medium" in name:
        return "medium"
    if "small" in name:
        return "small"
    if "base" in name:
        return "base"
    return "tiny"


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", (w or "").lower().replace("ё", "е"))


def _same(a: str, b: str) -> bool:
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])


def _timed_ratio(words: list[dict], start: int, n: int) -> float:
    """How much of a copy carries real timestamps (a whisper loop carries none)."""
    spans = [words[k]["end"] - words[k]["start"] for k in range(start, start + n)]
    return sum(1 for s in spans if s >= 0.05) / max(1, len(spans))


def clean_repeats(words: list[dict], min_n: int = 3, max_n: int = 12,
                  lookahead: int = 18) -> tuple[list[dict], list[dict]]:
    """Remove whispered loops and spoken retakes from the word stream.

    whisper.cpp sometimes falls into a decoding loop and emits the same phrase up
    to eight times, each copy with a zero-length timestamp (this take produced
    "Второй, это спотовый дискорд." x8 inside two seconds). A speaker also aborts
    a sentence and starts it again. Both look the same from here: an n-gram repeats
    inside a short window. Which copy goes:

      * a copy with no real timestamps is the artefact - drop it, keep the timed one;
      * when both copies are timed, the earlier one is the aborted attempt - drop it.

    Token comparison is by five-character prefix, because a retake rarely repeats
    word for word ("посчитайте" / "посчитать").

    Every removal is returned so the run can report it.
    """
    removed: list[dict] = []
    while True:
        toks = [_norm(w["word"]) for w in words]
        best = None
        for i in range(len(toks)):
            for n in range(min(max_n, len(toks) - i), min_n - 1, -1):
                pat = toks[i:i + n]
                if not all(pat):
                    continue
                hit = None
                for j in range(i + n, min(len(toks), i + n + lookahead)):
                    if all(_same(x, y) for x, y in zip(pat, toks[j:j + n])):
                        hit = j
                        break
                if hit is not None and (best is None or n > best[0]):
                    best = (n, i, hit)
                if best is not None and best[0] == n and best[1] == i:
                    break
        if best is None:
            break
        n, i, j = best
        timed_i, timed_j = _timed_ratio(words, i, n), _timed_ratio(words, j, n)
        if timed_i > timed_j + 0.15:
            span, rule = list(range(j, j + n)), "whisper-loop"
        elif timed_j > timed_i + 0.15:
            span, rule = list(range(i, i + n)), "whisper-loop"
        else:
            span, rule = list(range(i, i + n)), "retake"
        drop = set(span)
        removed.append({
            "rule": rule,
            "text": " ".join(words[k]["word"].strip() for k in sorted(drop))[:120],
            "start": round(float(words[min(drop)]["start"]), 3),
            "kept": " ".join(words[k]["word"].strip() for k in range(j, min(j + n, len(words))))[:120],
        })
        words = [w for k, w in enumerate(words) if k not in drop]
    return words, removed


def words_from_json(raw: dict, total_s: float) -> tuple[list[dict], dict]:
    """tokens -> words. A token that starts with a space opens a new word."""
    words: list[dict] = []
    stats = {"segments": 0, "tokens": 0, "dtw_tokens": 0, "no_time": 0}
    for seg in raw.get("transcription") or []:
        stats["segments"] += 1
        seg_from = float(seg.get("offsets", {}).get("from") or 0) / 1000.0
        seg_to = float(seg.get("offsets", {}).get("to") or 0) / 1000.0
        pending: list[tuple[float | None, str]] = []   # (time_s or None, text)

        def flush(boundary: float | None) -> None:
            if not pending:
                return
            text = "".join(t for _t, t in pending).strip()
            times = [t for t, _x in pending if t is not None]
            if not text:
                pending.clear()
                return
            start = min(times) if times else seg_from
            end = (boundary if boundary is not None and boundary > start else None)
            if end is None:
                end = max(times) if times else seg_from
                end = max(end, start) + 0.18
            if PUNCT_ONLY.match(text) and words:
                words[-1]["word"] = (words[-1]["word"] + text).strip()
                words[-1]["end"] = max(float(words[-1]["end"]), round(min(end, total_s), 3))
                pending.clear()
                return
            words.append({"word": text, "start": round(min(start, total_s), 3),
                          "end": round(min(max(end, start + 0.02), total_s), 3)})
            pending.clear()

        for tok in seg.get("tokens") or []:
            text = tok.get("text") or ""
            if SKIP_TOKEN.match(text.strip()):
                continue
            stats["tokens"] += 1
            t_dtw = tok.get("t_dtw", -1)
            t = None
            if t_dtw is not None and t_dtw >= 0:
                stats["dtw_tokens"] += 1
                t = float(t_dtw) / 100.0          # centiseconds -> seconds
            else:
                stats["no_time"] += 1
            if text.startswith(" ") or not pending:
                flush(t)
            pending.append((t, text))
        flush(None)
    # no word may start after the next one
    for a, b in zip(words, words[1:]):
        if b["start"] < a["end"]:
            a["end"] = round(max(a["start"] + 0.02, b["start"]), 3)
    stats["words"] = len(words)
    stats["last_word_end_s"] = words[-1]["end"] if words else 0.0
    return words, stats


def main() -> int:
    ap = argparse.ArgumentParser(description="DTW word-level transcription (whisper.cpp)")
    ap.add_argument("source", nargs="?", help="take (.mp4/.mov) or a 16 kHz mono wav")
    ap.add_argument("out", help="words.json to write")
    ap.add_argument("--raw", default=None, help="keep the raw whisper JSON here")
    ap.add_argument("--model", default=str(Path(os.environ.get("USERPROFILE", ""))
                                           / ".cache" / "whisper" / "ggml-large-v3.bin"))
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--dtw", default=None, help="DTW preset, e.g. large.v3")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--from-json", default=None,
                    help="reuse a whisper --output-json-full file instead of running whisper")
    args = ap.parse_args()

    if args.from_json:
        raw_path = Path(args.from_json)
        if not raw_path.is_file():
            raise SystemExit(f"raw whisper JSON not found: {raw_path}")
        raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
        ends = [float((s.get("offsets") or {}).get("to") or 0) / 1000.0
                for s in raw.get("transcription") or []]
        total_s = max(ends) if ends else 0.0
        words, stats = words_from_json(raw, total_s)
        if not words:
            raise SystemExit("no words recovered from the whisper output")
        words, dropped = clean_repeats(words)
        stats["words"] = len(words)
        stats["repeats_removed"] = len(dropped)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
        (out.parent / f"{out.stem}-repeats.json").write_text(
            json.dumps({"removed": dropped}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{out.name}: {stats['words']} words from {raw_path.name}; "
              f"{stats['dtw_tokens']}/{stats['tokens']} tokens carry a DTW time; "
              f"audio {total_s:.1f} s, last word {stats['last_word_end_s']:.1f} s")
        print(f"    repeats removed: {len(dropped)} "
              f"({sum(1 for d in dropped if d['rule'] == 'whisper-loop')} whisper loop(s), "
              f"{sum(1 for d in dropped if d['rule'] == 'retake')} retake(s))")
        for d in dropped[:10]:
            print(f"      - [{d['rule']} @{d['start']:.1f}s] «{d['text'][:70]}»")
        (out.parent / f"{out.stem}-meta.json").write_text(
            json.dumps({"source": str(raw_path), "dtw": args.dtw or "from-json",
                        "audio_s": round(total_s, 3), **stats}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return 0

    exe = shutil.which("whisper-cli")
    if not exe:
        raise SystemExit("whisper-cli not found on PATH")
    model = Path(args.model)
    if not model.is_file():
        raise SystemExit(f"whisper model not found: {model}")
    src = Path(args.source).resolve()
    if not src.is_file():
        raise SystemExit(f"source not found: {src}")

    tmp = Path(tempfile.mkdtemp(prefix="dsh-dtw-"))
    wav = src if src.suffix.lower() == ".wav" else tmp / "take.16k.wav"
    if wav is not src:
        print(f"[1/3] audio -> {wav.name} (16 kHz mono)", flush=True)
        to_wav(src, wav)
    total_s = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(wav)],
        capture_output=True, text=True).stdout.strip() or 0.0)

    preset = dtw_preset(model, args.dtw)
    raw_base = Path(args.raw).with_suffix("") if args.raw else tmp / "take-whisper"
    cmd = [exe, "-m", str(model), "-l", args.lang, "-nfa", "-dtw", preset,
           "-oj", "-ojf", "-of", str(raw_base)]
    if args.threads:
        cmd += ["-t", str(args.threads)]
    cmd.append(str(wav))
    print(f"[2/3] whisper-cli: DTW preset '{preset}', flash-attn off, {total_s:.1f} s of audio",
          flush=True)
    run(cmd)

    raw_path = raw_base.with_suffix(".json")
    if not raw_path.is_file():
        raise SystemExit(f"whisper produced no JSON at {raw_path}")
    raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    words, stats = words_from_json(raw, total_s)
    if not words:
        raise SystemExit("no words recovered from the whisper output")
    words, dropped = clean_repeats(words)
    stats["words"] = len(words)
    stats["repeats_removed"] = len(dropped)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")
    (out.parent / f"{out.stem}-repeats.json").write_text(
        json.dumps({"removed": dropped}, ensure_ascii=False, indent=2), encoding="utf-8")
    cover = (stats["last_word_end_s"] / total_s * 100.0) if total_s else 0.0
    print(f"[3/3] {out.name}: {stats['words']} words, "
          f"{stats['dtw_tokens']}/{stats['tokens']} tokens carry a DTW time, "
          f"last word at {stats['last_word_end_s']:.1f} s of {total_s:.1f} s ({cover:.1f} %)")
    print(f"      repeats removed: {len(dropped)} "
          f"({sum(1 for d in dropped if d['rule'] == 'whisper-loop')} whisper loop(s), "
          f"{sum(1 for d in dropped if d['rule'] == 'retake')} retake(s))")
    for d in dropped[:10]:
        print(f"        - [{d['rule']} @{d['start']:.1f}s] «{d['text'][:70]}»")
    meta = {"source": str(src), "model": str(model), "dtw": preset, "audio_s": round(total_s, 3),
            **stats}
    (out.parent / f"{out.stem}-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.raw:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"      raw whisper JSON: {raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
