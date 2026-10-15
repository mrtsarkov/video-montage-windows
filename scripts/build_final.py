#!/usr/bin/env python3
"""Assemble the final cut (spec §11.3, §11.4, §6.1).

Pipeline:
  1. master  — EDL trims + concat + tone correction + graphics layers, encoded
               losslessly (spec §11.3: the intermediate must be lossless or 50+ Mbit/s;
               the old plate was a 10 Mbit/s H.264 re-encode, i.e. a generational loss).
  2. voice   — two-pass loudnorm to -14 LUFS / -1 dBTP (single-pass missed by 2.2 LU).
  3. final   — two-pass H.264 at the target bitrate, BT.709 tv tags.

The graphics layer is ProRes 4444 tagged BT.601 (spec §14.1), so it is read with an
explicit BT.601 matrix and composited in RGB with the BT.709 plate (spec §11.3).

Usage:
  build_final.py <source.mp4> <edit_dir> [--out final.mp4] [--bitrate 30M]
                 [--layers layer-front.mov,layer-back.mov] [--no-matrix-fix]
                 [--two-pass | --single-pass] [--keep-master]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kw)


def probe_duration(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)], capture_output=True).stdout.strip()
    return float(out)


def probe_bitrate(path: Path) -> int:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=bit_rate", "-of", "csv=p=0", str(path)],
              capture_output=True).stdout.strip()
    try:
        return int(out)
    except ValueError:
        return 0


def correction_filter(corr: dict) -> str:
    """Tone correction straight from the passport (spec §1: no numbers in code).

    The first version stretched [black_point, white_point] with `eq=contrast`;
    measured on this material that clipped the white dashboard pages hard
    (80 % of one frame at 255, +1.93 pp clipping on average over the EDL frames),
    because the pages already sit at the top of the range. A midtone S-curve that
    is pinned at 1/1 gives the same intent with no added clipping (-0.04 pp).
    """
    points = corr.get("curve_points")
    if not points:
        points = [[0.0, 0.0], [0.25, 0.225], [0.5, 0.51], [0.75, 0.79], [1.0, 1.0]]
    curve = " ".join(f"{float(x):g}/{float(y):g}" for x, y in points)
    sat = float(corr.get("saturation", 1.05))
    return f"curves=all={curve},eq=saturation={sat:.3f}"


def plate_graph(edl: list[dict], corr: dict, last_label: str = "vout") -> str:
    """Concat the cuts and grade them — the plate of §11.3, no graphics."""
    chains, labels = [], []
    for i, seg in enumerate(edl):
        a, b = float(seg["in"]), float(seg["out"])
        chains.append(f"[0:v]trim=start={a:.4f}:end={b:.4f},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    chains.append(f"{''.join(labels)}concat=n={len(edl)}:v=1:a=0[cut]")
    chains.append(f"[cut]{correction_filter(corr)}[{last_label}]")
    return ";\n".join(chains)


def build_plate(src: Path, edl: list[dict], corr: dict, out: Path) -> None:
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-filter_complex", plate_graph(edl, corr), "-map", "[vout]", "-an",
         "-c:v", "libx264", "-qp", "0", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", str(out)])


def build_master(src: Path, edl: list[dict], layers: list[Path], corr: dict,
                 out: Path, matrix_fix: bool, edit: Path | None = None) -> None:
    """Compose the plate with the graphics layers.

    §11.3 order: plate -> layer behind the speaker -> the speaker himself (plate
    pixels carrying the person matte as alpha) -> layer in front. The back layer is
    small (the word only) and is padded onto the timeline, so the person matte is
    needed for that window alone.
    """
    chains, labels = [], []
    for i, seg in enumerate(edl):
        a, b = float(seg["in"]), float(seg["out"])
        chains.append(f"[0:v]trim=start={a:.4f}:end={b:.4f},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    chains.append(f"{''.join(labels)}concat=n={len(edl)}:v=1:a=0[cut]")
    chains.append(f"[cut]{correction_filter(corr)}[vc]")

    dur = sum(float(s["out"]) - float(s["in"]) for s in edl)
    back = edit / "layer-back.mov" if edit else None
    mask = edit / "person-mask.mov" if edit else None
    meta_path = edit / "back_layer.json" if edit else None
    use_back = bool(back and back.exists() and mask and mask.exists()
                    and meta_path and meta_path.exists())

    if use_back:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        start = float(meta["start_s"])
        length = float(meta["duration_s"])
        tail = max(0.0, dur - start - length)
        pad_in = f"tpad=start_duration={start:.3f}:start_mode=add:color="
        pad_out = f":stop_mode=add:stop_duration={tail:.3f}"
        idx_back, idx_mask = 1, 2
        # the person keeps the plate's colour; the matte contributes alpha only (§8)
        chains.append("[vc]split=2[base][person_src]")
        if matrix_fix:
            chains.append(
                f"[{idx_back}:v]format=yuva444p10le,"
                f"scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=tv:out_range=tv,"
                f"format=gbrap,{pad_in}black@0{pad_out}[backg]")
        else:
            chains.append(f"[{idx_back}:v]format=gbrap,{pad_in}black@0{pad_out}[backg]")
        chains.append(f"[{idx_mask}:v]alphaextract,{pad_in}black{pad_out}[maskg]")
        chains.append("[base][backg]overlay=format=gbrp:eof_action=repeat[o1]")
        chains.append("[person_src][maskg]alphamerge[person]")
        chains.append(f"[o1][person]overlay=format=gbrp:eof_action=repeat:"
                      f"enable='between(t,{start:.3f},{start + length:.3f})'[o2]")
        last, first_layer_idx = "o2", 3
    else:
        last, first_layer_idx = "vc", 1
        if edit:
            print("      ! back layer or person matte missing: the word stays in front")

    for li, layer in enumerate(layers):
        idx = first_layer_idx + li
        if matrix_fix:
            chains.append(
                f"[{idx}:v]format=yuva444p10le,"
                f"scale=in_color_matrix=bt601:out_color_matrix=bt709:"
                f"in_range=tv:out_range=tv,format=gbrap[fg{li}]"
            )
        else:
            chains.append(f"[{idx}:v]format=gbrap[fg{li}]")
        chains.append(
            f"[{last}]format=gbrp[bg{li}];[bg{li}][fg{li}]"
            f"overlay=format=gbrp:eof_action=repeat[o{li}]"
        )
        last = f"o{li}"

    chains.append(
        f"[{last}]format=yuv420p,setparams=range=tv:color_primaries=bt709:"
        f"color_trc=bt709:colorspace=bt709[vout]"
    )

    graph = ";\n".join(chains)
    if len(graph) > 30000:
        raise SystemExit(f"filter graph too long for the command line ({len(graph)} chars)")

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if use_back:
        cmd += ["-i", str(back), "-i", str(mask)]
    for layer in layers:
        cmd += ["-i", str(layer)]
    cmd += ["-filter_complex", graph, "-map", "[vout]", "-an",
            "-c:v", "libx264", "-qp", "0", "-preset", "veryfast",
            "-pix_fmt", "yuv420p", "-color_range", "tv",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            str(out)]
    run(cmd)


def mix_sfx(edit: Path, voice: Path, out: Path) -> dict:
    """Voice + placed sfx into one track (spec §6.2).

    Each event starts at event_time - peak_at_s so the sound's measured peak lands
    on the event frame. Gains are normalised per file so every sound reaches the
    same peak level, then the whole mix is loudness-normalised again.
    """
    plan_path = edit / "sfx_plan.json"
    if not plan_path.is_file():
        shutil.copy2(voice, out)
        return {"events": 0, "note": "no sfx_plan.json"}
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    root = edit.parents[2]
    inputs, chains, labels, used = [], [], [], []
    idx = 1
    for event in plan.get("events", []):
        path = root / "sfx" / event["file"]
        if not path.is_file():
            path = edit / event["file"]
        if not path.is_file():
            continue
        inputs += ["-i", str(path)]
        ms = int(round(float(event["start_s"]) * 1000))
        chains.append(f"[{idx}:a]aformat=channel_layouts=mono,adelay=delays={ms}:all=1,"
                      f"volume={float(event['gain_db']):.2f}dB[s{idx}]")
        labels.append(f"[s{idx}]")
        used.append(event)
        idx += 1
    if not used:
        shutil.copy2(voice, out)
        return {"events": 0, "note": "no usable sfx file"}
    graph = (";".join(chains)
             + f";[0:a]{''.join(labels)}amix=inputs={len(labels) + 1}:normalize=0:duration=first,"
               "alimiter=limit=0.89:attack=5:release=50:level=disabled[out]")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(voice), *inputs,
         "-filter_complex", graph, "-map", "[out]", "-ar", "48000",
         "-c:a", "pcm_s16le", str(out)])
    return {"events": len(used), "files": sorted({e["file"] for e in used}),
            "types": sorted({e.get("type", "") for e in used})}


def measure_i_tp(path: Path) -> tuple[float, float]:
    """Integrated LUFS and true peak (dBFS) of a finished file (spec §6.1)."""
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    blob = proc.stdout or ""
    lufs = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", blob)
    peaks = re.findall(r"\bPeak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", blob)
    if not lufs or not peaks:
        raise SystemExit(f"could not measure loudness of {path}")
    return float(lufs[-1]), float(peaks[-1])


def normalize_voice(voice: Path, out: Path, lufs: float, tp: float, lra: float,
                    tol: float = 0.3, max_iter: int = 7) -> dict:
    """Iterative gain + limiter normalisation, verified on the written file.

    `loudnorm` alone undershoots badly on quiet, peak-limited speech: the input here
    measures -28.1 LUFS with -6 dBTP, and dynamic mode landed at -16.2 LUFS while a
    fixed +14 dB pre-gain plus limiter landed at -15.8. Gain is therefore corrected
    against the measured result until the file really sits on target.
    """
    start_i, start_tp = measure_i_tp(voice)
    gain = lufs - start_i
    # a sample-peak limiter cannot see inter-sample peaks: measured overshoot on this
    # mix is a constant ~1.4 dB, so the ceiling sits 3 dB under the true-peak target
    # (-4 dBFS for a -1 dBTP goal) and the gain loop makes up the loudness
    lim = min(0.95, 10 ** ((tp - 2.5) / 20.0))
    history = []
    got_i = got_tp = 0.0
    for _ in range(max_iter):
        run(["ffmpeg", "-y", "-v", "error", "-i", str(voice), "-af",
             f"volume={gain:.2f}dB,"
             f"alimiter=limit={lim:.4f}:attack=5:release=100:level=disabled",
             "-ar", "48000", "-c:a", "pcm_s16le", str(out)])
        got_i, got_tp = measure_i_tp(out)
        history.append({"gain_db": round(gain, 2), "I": got_i, "TP": got_tp})
        if abs(got_i - lufs) <= tol and got_tp <= tp + 0.15:
            break
        # the limiter eats part of every gain step, so overshoot the correction a little
        step = max(-6.0, min(6.0, (lufs - got_i) * 1.6))
        gain += step
    return {
        "input_i": start_i, "input_tp": start_tp, "gain_db": round(gain, 2),
        "final_i": got_i, "final_tp": got_tp, "iterations": len(history),
        "history": history,
    }


def encode_final(master: Path, voice: Path, out: Path, bitrate: str, two_pass: bool,
                 duration: float, passlog: Path, mode: str = "abr") -> None:
    """Encode the deliverable.

    `abr` spends what the picture needs and stops at the lossless ceiling; `cbr`
    pads up to the target bitrate, which is what the spec's "~30 Mbit/s" literally
    asks for on 1080p material that would otherwise saturate well below it.
    """
    common = ["-c:v", "libx264", "-b:v", bitrate, "-preset", "slow", "-tune", "grain",
              "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
              "-color_primaries", "bt709", "-color_trc", "bt709"]
    if mode == "cbr":
        common += ["-minrate", bitrate, "-maxrate", bitrate, "-bufsize", "2M",
                   "-x264-params", "nal-hrd=cbr:force-cfr=1"]
    if two_pass:
        run(["ffmpeg", "-y", "-v", "error", "-i", str(master), "-an", *common,
             "-pass", "1", "-passlogfile", str(passlog), "-f", "null", "-"])
        pass_args = ["-pass", "2", "-passlogfile", str(passlog)]
    else:
        pass_args = []
    run(["ffmpeg", "-y", "-v", "error", "-i", str(master), "-i", str(voice),
         "-map", "0:v", "-map", "1:a", *common, *pass_args,
         "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
         "-movflags", "+faststart", str(out)])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("edit_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--bitrate", default="30M")
    ap.add_argument("--bitrate-mode", default="abr", choices=["abr", "cbr"],
                    help="abr spends what the picture needs (stops at the lossless "
                         "ceiling); cbr pads up to the target the spec names")
    ap.add_argument("--layers", default="layer-front.mov",
                    help="comma-separated layer file names inside edit_dir, back to front")
    ap.add_argument("--no-matrix-fix", action="store_true")
    ap.add_argument("--single-pass", action="store_true")
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.0)
    ap.add_argument("--lra", type=float, default=11.0)
    ap.add_argument("--keep-master", action="store_true")
    ap.add_argument("--rebuild-master", action="store_true")
    ap.add_argument("--plate-only", action="store_true",
                    help="build only the graded plate (no graphics) and exit")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    edit = Path(args.edit_dir).resolve()
    out = Path(args.out).resolve() if args.out else edit.parent / "out" / "final.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    edl = json.loads((edit / "edl.json").read_text(encoding="utf-8-sig"))
    data = json.loads((edit / "data.json").read_text(encoding="utf-8-sig"))
    corr = data.get("correction", {})
    duration = sum(float(s["out"]) - float(s["in"]) for s in edl)

    layers = []
    for name in [n.strip() for n in args.layers.split(",") if n.strip()]:
        p = edit / name
        if p.exists():
            layers.append(p)
        else:
            print(f"  ! layer missing, skipped: {name}", file=sys.stderr)

    if args.plate_only:
        plate = edit / "plate.mp4"
        print(f"plate: {len(edl)} cuts, graded, lossless qp=0 -> {plate.name}")
        build_plate(src, edl, corr, plate)
        print(f"       {plate.stat().st_size / 1e6:.0f} MB, {probe_duration(plate):.3f}s")
        return 0

    master = edit / "master-lossless.mp4"
    newest_src = max([(edit / "edl.json").stat().st_mtime, (edit / "data.json").stat().st_mtime]
                     + [p.stat().st_mtime for p in layers])
    for extra in ("layer-back.mov", "person-mask.mov", "back_layer.json"):
        if (edit / extra).exists():
            newest_src = max(newest_src, (edit / extra).stat().st_mtime)
    if master.exists() and master.stat().st_mtime >= newest_src and not args.rebuild_master:
        print(f"[1/3] master: reusing {master.name} "
              f"({master.stat().st_size / 1e6:.0f} MB, --rebuild-master to force)")
    else:
        has_back = (edit / "layer-back.mov").exists() and (edit / "person-mask.mov").exists()
        print(f"[1/3] master: {len(edl)} cuts, {len(layers)} front layer(s)"
              + (", back layer + person matte" if has_back else "") + ", lossless qp=0")
        build_master(src, edl, layers, corr, master, not args.no_matrix_fix, edit)
    mdur = probe_duration(master)
    print(f"      {master.name} {master.stat().st_size / 1e6:.0f} MB, {mdur:.3f}s "
          f"(expect {duration:.3f}s, delta {mdur - duration:+.3f}s)")

    voice_src = edit / "voice.wav"
    if not voice_src.exists():
        raise SystemExit(f"missing {voice_src}; run build_voice.py first")
    voice_mix = edit / "voice-mix.wav"
    print("[2/3] audio: voice + sfx -> voice-mix.wav")
    mix_info = mix_sfx(edit, voice_src, voice_mix)
    if mix_info["events"]:
        print(f"      sfx: {mix_info['events']} event(s) from {', '.join(mix_info['files'])} "
              f"({', '.join(t for t in mix_info['types'] if t)})")
    else:
        print(f"      sfx: none ({mix_info.get('note', '')})")

    voice_norm = edit / "voice-norm.wav"
    print(f"      normalising the mix -> {args.lufs} LUFS / {args.tp} dBTP")
    meas = normalize_voice(voice_mix, voice_norm, args.lufs, args.tp, args.lra)
    print(f"      in I={meas['input_i']} TP={meas['input_tp']} -> "
          f"gain {meas['gain_db']} dB in {meas['iterations']} step(s) -> "
          f"out I={meas['final_i']} TP={meas['final_tp']}")

    print(f"[3/3] final: two-pass={not args.single_pass} {args.bitrate} mode={args.bitrate_mode}")
    passlog = Path(tempfile.mkdtemp()) / "x264pass"
    encode_final(master, voice_norm, out, args.bitrate, not args.single_pass,
                 duration, passlog, args.bitrate_mode)
    br = probe_bitrate(out) / 1e6
    print(f"      {out}  {out.stat().st_size / 1e6:.0f} MB  "
          f"video {br:.2f} Mbit/s  {probe_duration(out):.3f}s")

    if not args.keep_master:
        master.unlink(missing_ok=True)
        print("      master removed (use --keep-master to keep it)")
    shutil.rmtree(passlog.parent, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
