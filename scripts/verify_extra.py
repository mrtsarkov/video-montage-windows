#!/usr/bin/env python3
"""Extra machine checks for spec §12 that verify_final.py does not cover.

  frame_sheet  — a still of every graphic element at its fullest moment (§12.16, §13)
  audio_sync   — lag between the muxed audio and the assembled voice, ±5 ms (§12.11)
  levels       — luma percentiles, clipping, and paired against the source (§12.9)
  jitter       — alpha centroid drift frame-to-frame while an element holds, ≤0.25 px (§12.4)
  determinism  — static audit of the composition for time/random sources

`levels` is paired: sampling a file on a fixed grid compares different moments,
so it walks the EDL and reads the same instant in the source and in the final.
The pass criterion is "the grade adds no clipping", because the source of a
screen recording already pins a few percent of pixels at 255 (white pages).

Usage:
  verify_extra.py <final.mp4> --edit <edit_dir> [--source <take.mp4>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

RATE = 8000
CLIP_ADD_LIMIT_PP = 0.3     # allowed clipping added by the grade
CLIP_HARD_PCT = 2.0         # absolute ceiling when no source is available
GRAPHICS_SKIP_PCT = 0.02    # frames with this much visible graphics are not a grade sample
JITTER_LIMIT_PX = 0.25      # §12.4
SYNC_LIMIT_MS = 5.0         # §12.11
PROHIBITED = ["infinite", "Math.random", "Date.now", "performance.now"]
GW, GH = 480, 270


def ff(cmd: list[str], binary: bool = False):
    p = subprocess.run(cmd, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd)}\n{p.stderr.decode('utf-8', 'replace')[-300:]}")
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


def to_pcm(path: Path, rate: int = RATE) -> np.ndarray:
    raw = Path(tempfile.mkdtemp()) / "a.f32"
    ff(["ffmpeg", "-y", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
        "-ar", str(rate), "-f", "f32le", str(raw)])
    return np.fromfile(raw, dtype=np.float32)


def gray_frame(path: Path, t: float) -> np.ndarray | None:
    raw = ff(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
              "-vf", f"scale={GW}:{GH},format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
             binary=True)
    if len(raw) < GW * GH:
        return None
    return np.frombuffer(raw[: GW * GH], dtype=np.uint8)


def alpha_frame(layer: Path, t: float, w: int, h: int) -> np.ndarray | None:
    buf = ff(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", str(layer),
              "-vf", "alphaextract", "-frames:v", "1", "-f", "rawvideo",
              "-pix_fmt", "gray", "-"], binary=True)
    if len(buf) < w * h:
        return None
    return np.frombuffer(buf[: w * h], dtype=np.uint8).reshape(h, w)


def parse_plan(edit: Path) -> list[tuple[float, str, str]]:
    plan = edit / "graphics_plan.md"
    if not plan.is_file():
        return []
    rows = []
    for line in plan.read_text(encoding="utf-8-sig").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("время", "") or set(cells[0]) <= {"-"}:
            continue
        try:
            t = float(cells[0])
        except ValueError:
            continue
        rows.append((t, cells[2], cells[3] if len(cells) > 3 else ""))
    return rows


def comp_timeline(edit: Path) -> list[tuple[str, float, float]]:
    html = edit / "comp" / "index.html"
    if not html.is_file():
        return []
    text = html.read_text(encoding="utf-8-sig")
    return [(m.group(1), float(m.group(2)), float(m.group(3)))
            for m in re.finditer(r'id="([^"]+)"[^>]*data-start="([\d.]+)"[^>]*data-duration="([\d.]+)"', text)]


def edl_of(edit: Path) -> list[dict]:
    path = edit / "edl.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else data.get("segments", [])


def check_frame_sheet(final: Path, edit: Path, sheet_dir: Path) -> dict:
    rows = parse_plan(edit)
    if not rows:
        return {"check": "frame_sheet", "status": "SKIP", "measured": "no graphics_plan.md",
                "target": "one still per element"}
    sheet_dir.mkdir(parents=True, exist_ok=True)
    made, missing = [], []
    for i, (t, element, _note) in enumerate(rows, 1):
        at = t + 0.6
        out = sheet_dir / f"{i:02d}_{element}_{at:.1f}s.jpg"
        try:
            ff(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.3f}", "-i", str(final),
                "-frames:v", "1", "-q:v", "2", str(out)])
        except RuntimeError:
            missing.append(f"{element}@{at:.1f}")
            continue
        (made if out.exists() and out.stat().st_size > 1000 else missing).append(out.name)
    return {"check": "frame_sheet",
            "status": "PASS" if made and not missing else "FAIL",
            "measured": f"{len(made)}/{len(rows)} stills in {sheet_dir.name}/"
                        + (f"; missing {', '.join(missing[:4])}" if missing else ""),
            "target": "one still per graphics element, after it settled"}


def check_audio_sync(final: Path, edit: Path) -> dict:
    # compare against the actual audio master that was muxed: voice-norm.wav has the
    # same limiting as the final, while the pre-limiter mix decorrelates under it
    voice = edit / "voice-norm.wav"
    if not voice.is_file():
        voice = edit / "voice-mix.wav"
    if not voice.is_file():
        voice = edit / "voice.wav"
    if not voice.is_file():
        return {"check": "audio_sync", "status": "SKIP", "measured": "no voice track",
                "target": f"|lag| <= {SYNC_LIMIT_MS} ms"}
    a, b = to_pcm(final), to_pcm(voice)
    n = min(len(a), len(b))
    span = min(n, 60 * RATE)
    if span < RATE:
        return {"check": "audio_sync", "status": "SKIP", "measured": "audio too short",
                "target": f"|lag| <= {SYNC_LIMIT_MS} ms"}
    off = n // 2
    a_win = a[off: off + span]
    pad = int(0.05 * RATE)
    best_lag, best = 0, -1.0
    for lag in range(-pad, pad + 1):
        s = off + lag
        if s < 0 or s + span > len(b):
            continue
        seg = b[s: s + span]
        den = np.linalg.norm(a_win) * np.linalg.norm(seg)
        score = float(np.dot(a_win, seg) / den) if den > 0 else -1.0
        if score > best:
            best, best_lag = score, lag
    lag_ms = best_lag / RATE * 1000.0
    return {"check": "audio_sync",
            "status": "PASS" if abs(lag_ms) <= SYNC_LIMIT_MS else "FAIL",
            "measured": f"lag {lag_ms:+.2f} ms (correlation {best:.4f})",
            "target": f"|lag| <= {SYNC_LIMIT_MS} ms"}


def layer_coverage(edit: Path, t: float, thr: int = 31) -> float | None:
    """Share of the frame covered by visible graphics at timeline time t.

    §12.9 measures what the *grade* does to the picture. Brand plates are white
    on purpose, so a frame that carries graphics is not a fair sample of the
    grade: those frames are reported and skipped instead of counted as clipping.
    """
    layer = edit / "layer-front.mov"
    if not layer.is_file():
        return None
    raw = ff(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(layer), "-frames:v", "1",
              "-vf", f"alphaextract,scale={GW}:{GH}:flags=area,format=gray", "-f", "rawvideo",
              "-pix_fmt", "gray", "-"], binary=True)
    if len(raw) < GW * GH:
        return None
    return float((np.frombuffer(raw[: GW * GH], dtype=np.uint8) > thr).mean())


def check_levels(final: Path, edit: Path, source: Path | None, samples: int = 24) -> dict:
    edl = edl_of(edit)
    paired = bool(source and Path(source).is_file() and edl)
    src_clip, fin_clip, luma_diff = [], [], []
    graphics_skipped = 0
    if paired:
        step = max(1, len(edl) // samples)
        t_line = 0.0
        for i, seg in enumerate(edl):
            a, b = float(seg["in"]), float(seg["out"])
            mid, line_mid = (a + b) / 2, t_line + (b - a) / 2
            t_line += b - a
            if i % step:
                continue
            cov = layer_coverage(edit, line_mid)
            if cov is not None and cov > GRAPHICS_SKIP_PCT:
                graphics_skipped += 1
                continue
            gs, gf = gray_frame(Path(source), mid), gray_frame(final, line_mid)
            if gs is None or gf is None:
                continue
            src_clip.append(float((gs == 255).mean() * 100))
            fin_clip.append(float((gf == 255).mean() * 100))
            luma_diff.append(float(np.abs(gs.astype(np.int16) - gf.astype(np.int16)).mean()))

    grid_clip0 = grid_clip255 = 0.0
    p50s = []
    dur = float(ff(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(final)]).strip())
    for i in range(12):
        t = dur * (i + 0.5) / 12
        cov = layer_coverage(edit, t)
        if cov is not None and cov > GRAPHICS_SKIP_PCT:
            graphics_skipped += 1
            continue
        g = gray_frame(final, t)
        if g is None:
            continue
        grid_clip0 = max(grid_clip0, float((g == 0).mean() * 100))
        grid_clip255 = max(grid_clip255, float((g == 255).mean() * 100))
        p50s.append(float(np.percentile(g, 50)))

    note = (f"{graphics_skipped} frame(s) skipped: graphics on screen (§9.3 plates are white "
            f"by design)" if graphics_skipped else "")
    if paired and src_clip:
        add = float(np.mean(fin_clip) - np.mean(src_clip))
        ok = add <= CLIP_ADD_LIMIT_PP
        return {"check": "levels", "status": "PASS" if ok else "FAIL",
                "measured": f"paired on {len(fin_clip)} EDL frames: source {np.mean(src_clip):.2f}% "
                            f"-> final {np.mean(fin_clip):.2f}% clipped at 255 "
                            f"(grade adds {add:+.2f} pp); p50 {min(p50s):.0f}-{max(p50s):.0f}; "
                            f"mean luma change {np.mean(luma_diff):.2f}/255",
                "target": f"grade adds <= {CLIP_ADD_LIMIT_PP} pp of clipping",
                "note": note}
    ok = grid_clip0 <= CLIP_HARD_PCT and grid_clip255 <= CLIP_HARD_PCT
    return {"check": "levels", "status": "PASS" if ok else "FAIL",
            "measured": f"no source given: clipped at 0 {grid_clip0:.3f}%, at 255 {grid_clip255:.3f}%",
            "target": f"<= {CLIP_HARD_PCT}% both ends (or pass --source for a paired test)",
            "note": note}


def check_jitter(edit: Path, elements: int = 4, frames: int = 12) -> dict:
    layer = edit / "layer-front.mov"
    if not layer.is_file():
        return {"check": "jitter", "status": "SKIP", "measured": "no layer-front.mov",
                "target": f"<= {JITTER_LIMIT_PX} px/frame on hold"}
    tl = [e for e in comp_timeline(edit) if e[2] > 3.0 and e[0] not in ("root", "main")][:elements]
    if not tl:
        return {"check": "jitter", "status": "SKIP", "measured": "no element interval",
                "target": f"<= {JITTER_LIMIT_PX} px/frame on hold"}
    worst, detail, measured_elements = 0.0, "", 0
    for name, start, dur in tl:
        hold0 = start + max(1.6, dur * 0.6)
        if start + dur - 0.5 - hold0 < frames / 30:
            continue
        ys, xs = [], []
        for i in range(frames):
            a = alpha_frame(layer, hold0 + i / 30.0, 1920, 1080)
            if a is None:
                continue
            mask = a > 31
            if not mask.any() or mask.mean() > 0.5:      # skip whole-frame layers
                continue
            idx = np.nonzero(mask)
            ys.append(idx[0].mean()); xs.append(idx[1].mean())
        if len(xs) < 3:
            continue
        measured_elements += 1
        d = float(np.hypot(np.diff(xs), np.diff(ys)).max())
        if d > worst:
            worst, detail = d, f"worst on #{name}"
    if measured_elements == 0:
        return {"check": "jitter", "status": "SKIP",
                "measured": "no element held long enough with alpha",
                "target": f"<= {JITTER_LIMIT_PX} px/frame on hold"}
    return {"check": "jitter", "status": "PASS" if worst <= JITTER_LIMIT_PX else "FAIL",
            "measured": f"max centroid drift {worst:.3f} px/frame per element "
                        f"({measured_elements} element(s), {detail})",
            "target": f"<= {JITTER_LIMIT_PX} px/frame on hold"}


def check_sfx_placement(edit: Path) -> dict:
    """Did the planned sounds actually land? Compares voice.wav with voice-mix.wav
    inside each event window: the mix must be louder exactly there."""
    plan_path = edit / "sfx_plan.json"
    voice = edit / "voice.wav"
    mix = edit / "voice-mix.wav"
    if not (plan_path.is_file() and voice.is_file() and mix.is_file()):
        return {"check": "sfx_placement", "status": "SKIP",
                "measured": "no sfx_plan.json / voice-mix.wav",
                "target": "every planned event raises the level in its window"}
    events = json.loads(plan_path.read_text(encoding="utf-8-sig")).get("events", [])
    if not events:
        return {"check": "sfx_placement", "status": "SKIP", "measured": "plan is empty",
                "target": "every planned event raises the level in its window"}
    a, b = to_pcm(mix), to_pcm(voice)
    n = min(len(a), len(b))
    rises, missing = [], []
    for e in events:
        t0 = float(e["event_time_s"])
        i0, i1 = int(t0 * RATE), min(n, int((t0 + 0.35) * RATE))
        if i1 - i0 < RATE // 20:
            continue
        rms_mix = float(np.sqrt(np.mean(a[i0:i1] ** 2) + 1e-12))
        rms_voice = float(np.sqrt(np.mean(b[i0:i1] ** 2) + 1e-12))
        rise = 20 * np.log10(rms_mix / rms_voice)
        if rise > 0.5:
            rises.append(rise)
        else:
            missing.append(f"{e['element']}@{t0:.1f}s ({rise:+.1f} dB)")
    ok = len(missing) == 0
    return {"check": "sfx_placement",
            "status": "PASS" if ok else "FAIL",
            "measured": f"{len(rises)}/{len(rises) + len(missing)} events raise the level "
                        f"(median +{np.median(rises):.1f} dB)" if rises
                        else "no event raised the level",
            "target": "each planned event louder than the voice-only track in its window",
            "note": ("; ".join(missing[:5]) if missing else "")}


def check_determinism(edit: Path) -> dict:
    html = edit / "comp" / "index.html"
    if not html.is_file():
        return {"check": "determinism", "status": "SKIP", "measured": "no composition",
                "target": "no time/random sources"}
    text = html.read_text(encoding="utf-8-sig")
    found = [p for p in PROHIBITED if p in text]
    calls = text.count("tl.call(")
    return {"check": "determinism", "status": "PASS" if not found else "FAIL",
            "measured": "no infinite animation, no random/time source"
                        + (f"; {calls} deterministic tl.call steps" if calls else ""),
            "target": "no " + ", ".join(PROHIBITED)}


def check_copy_quality(edit: Path) -> dict:
    """No ellipsis, every card text measured against the width it has.

    The first version finished a too-long line with "…", so cards looked like
    someone forgot to finish typing. `insert_copy.py` measures with the real Inter
    font and rewrites instead; this check fails if any ellipsis reaches the screen.
    """
    html = edit / "comp" / "index.html"
    if not html.is_file():
        return {"check": "copy_quality", "status": "SKIP", "measured": "no composition",
                "target": "no ellipsis in any on-screen text"}
    text = html.read_text(encoding="utf-8-sig")
    body = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    nodes = [m.group(1).strip() for m in re.finditer(r">([^<>]+)<", body) if m.group(1).strip()]
    bad = [n for n in nodes if "…" in n or n.endswith("...")]
    fit = edit / "copy_fit.json"
    fitted = 0
    if fit.is_file():
        try:
            fitted = len(json.loads(fit.read_text(encoding="utf-8-sig")).get("fitted", []))
        except json.JSONDecodeError:
            fitted = 0
    mark = edit / "script_plan.json"
    source = "автогенерация"
    copy_path = edit / "comp_plan.json"
    if copy_path.is_file():
        try:
            src = json.loads(copy_path.read_text(encoding="utf-8-sig")).get("copy_source")
            if src:
                source = Path(src).name
        except json.JSONDecodeError:
            pass
    measured = (f"{len(nodes)} text node(s), {len(bad)} with an ellipsis; "
                f"{fitted} line(s) rewritten to fit; copy: {source}")
    return {"check": "copy_quality", "status": "PASS" if not bad else "FAIL",
            "measured": measured + ("; " + "; ".join(b[:48] for b in bad[:4]) if bad else ""),
            "target": "0 ellipses on screen; long lines are rewritten, not cut short"}


def check_retakes(edit: Path, window: int = 6, sim: float = 0.72) -> dict:
    """Did any repeated or aborted phrase survive the cut?

    Two neighbouring clips that say the same thing (or where the earlier one is a
    prefix of the later) are a retake the editor missed.
    """
    edl = edl_of(edit)
    if not edl:
        return {"check": "retakes", "status": "SKIP", "measured": "no EDL",
                "target": "no repeated or aborted phrase left in the cut"}
    def norm(t):
        t = t.lower().replace("ё", "е")
        t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
        return re.sub(r"\s+", " ", t).strip()
    hits = []
    for i in range(len(edl)):
        a = norm(edl[i].get("text") or "")
        if len(a.split()) < 3:
            continue
        for j in range(i + 1, min(len(edl), i + window + 1)):
            b = norm(edl[j].get("text") or "")
            if len(b.split()) < 3:
                continue
            if a and b.startswith(a) and len(a) > 12:
                hits.append((i + 1, j + 1, "префикс"))
                continue
            r = SequenceMatcher(None, a, b).ratio()
            if r >= sim:
                hits.append((i + 1, j + 1, f"{r:.2f}"))
    # repeats inside one clip are a whisper decoding loop, not the speaker
    return {"check": "retakes", "status": "PASS" if not hits else "FAIL",
            "measured": (f"{len(edl)} clips checked; {len(hits)} duplicate pair(s) left"
                         + (": " + ", ".join(f"#{a}/#{b} ({why})" for a, b, why in hits[:6])
                            if hits else "")),
            "target": "0 repeated or aborted phrases (build_edl.py + build_words_dtw.py remove them)"}


def check_face_safe(edit: Path, data: Path | None = None, samples: int = 24) -> dict:
    """Does any graphic land on the speaker's face?

    The requirement is literal: an insert may sit beside the head or behind the
    liquid-glass cover, never on the face. Cards are measured in the outer columns
    and the two full-frame moments are declared as stage windows, so they are
    exempt exactly while they are on screen.
    """
    layer = edit / "layer-front.mov"
    if not layer.is_file():
        return {"check": "face_safe", "status": "SKIP", "measured": "no layer-front.mov",
                "target": "no graphic pixel inside the face box outside the glass stage"}
    # the face itself, measured on this take (eyes at y 36.6 %, cheeks to x 61 %):
    # deliberately not the hair silhouette, so the soft brand shadow may graze the
    # temple without this check firing on a frame where nothing covers the face
    box = {"x": 45.0, "y": 28.0, "w": 16.5, "h": 38.0}
    dp = data or (edit / "data.json")
    if dp and Path(dp).is_file():
        try:
            got = (json.loads(Path(dp).read_text(encoding="utf-8-sig"))
                   .get("passport", {}).get("face_box_pct"))
            if got:
                box = got
        except json.JSONDecodeError:
            pass
    stage_path = edit / "stage.json"
    windows = []
    if stage_path.is_file():
        try:
            windows = json.loads(stage_path.read_text(encoding="utf-8-sig")).get("windows") or []
        except json.JSONDecodeError:
            windows = []
    duration = float(ff(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", str(layer)]).strip() or 0.0)
    if duration <= 0:
        return {"check": "face_safe", "status": "SKIP", "measured": "undecodable layer",
                "target": "no graphic pixel inside the face box outside the glass stage"}
    x0, y0 = int(1920 * box["x"] / 100.0), int(1080 * box["y"] / 100.0)
    x1, y1 = int(1920 * (box["x"] + box["w"]) / 100.0), int(1080 * (box["y"] + box["h"]) / 100.0)
    bad, checked, exempt = [], 0, 0
    for i in range(samples):
        t = duration * (i + 0.5) / samples
        if any(w["start"] <= t <= w["end"] for w in windows):
            exempt += 1
            continue
        a = alpha_frame(layer, t, 1920, 1080)
        if a is None:
            continue
        checked += 1
        share = float((a[y0:y1, x0:x1] > 31).mean() * 100.0)
        if share > 0.25:
            bad.append(f"t={t:.1f}s {share:.1f}%")
    return {"check": "face_safe",
            "status": "PASS" if not bad else "FAIL",
            "measured": (f"face box x{box['x']:.0f}% y{box['y']:.0f}% "
                         f"{box['w']:.0f}×{box['h']:.0f}%; {checked} frame(s) measured, "
                         f"{exempt} exempt (liquid-glass stage); "
                         + (f"{len(bad)} frame(s) with graphics on the face: " + ", ".join(bad[:5])
                            if bad else "no graphics on the face")),
            "target": "0 frames with a graphic over the face outside the declared glass stage"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("final")
    ap.add_argument("--edit", required=True)
    ap.add_argument("--source", default=None)
    ap.add_argument("--data", default=None, help="data.json (face box and passport)")
    ap.add_argument("--json", default=None)
    ap.add_argument("--sheet-dir", default=None)
    args = ap.parse_args()

    final = Path(args.final).resolve()
    edit = Path(args.edit).resolve()
    sheet_dir = Path(args.sheet_dir).resolve() if args.sheet_dir else edit / "frames"
    checks = [
        check_frame_sheet(final, edit, sheet_dir),
        check_audio_sync(final, edit),
        check_levels(final, edit, Path(args.source).resolve() if args.source else None),
        check_jitter(edit),
        check_sfx_placement(edit),
        check_determinism(edit),
        check_copy_quality(edit),
        check_retakes(edit),
        check_face_safe(edit, Path(args.data).resolve() if args.data else None),
    ]
    print("verify_extra.py - additional checks (§12)")
    print(f"file : {final}")
    print(f"edit : {edit}\n")
    for c in checks:
        print(f"[{c['status']}] {c['check']}")
        print(f"    measured : {c['measured']}")
        print(f"    target   : {c['target']}")
    failed = [c["check"] for c in checks if c["status"] == "FAIL"]
    skipped = [c["check"] for c in checks if c["status"] == "SKIP"]
    print(f"\nchecks: {sum(1 for c in checks if c['status'] == 'PASS')} passed, "
          f"{len(failed)} failed, {len(skipped)} skipped (of {len(checks)})")
    print(f"VERDICT: {'FAIL' if failed else 'PASS'}")
    result = {"checks": checks, "passed": sum(1 for c in checks if c["status"] == "PASS"),
              "failed": len(failed), "skipped": len(skipped),
              "verdict": "FAIL" if failed else "PASS"}
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"json report: {args.json}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
