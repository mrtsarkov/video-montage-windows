#!/usr/bin/env python3
"""Machine part of the pre-delivery acceptance checklist (MONTAGE-PROMPT-v4.md, sec. 12).

Verifies the rendered `runs/<label>/out/final.mp4` and the `edit/` inputs against the
spec requirements: video format, BT.709 `tv` colour tags, video bitrate, audio loudness
and true peak (sec. 6.1), subtitles-off rule (sec. 5), graphics-layer alpha (sec. 9.3,
11.3) and non-black first/last frames.

Usage:
  py -3 scripts/verify_final.py <final.mp4> [--edit <runs/<label>/edit>]
        [--source <source.mp4>] [--json <out.json>]
        [--lufs -14] [--tp -1.0] [--min-bitrate-mbps 24]
        [--fps 30] [--width 1920] [--height 1080]

Exit codes: 0 - every check passed (skipped checks do not fail), 1 - at least one FAIL,
2 - missing/unreadable input or usage error.

Console output is deliberately ASCII-only (Windows codepage safety); files are written
as UTF-8. Dependencies: stdlib + numpy + ffmpeg/ffprobe in PATH.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from html.parser import HTMLParser
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------- #
# Constants: thresholds come from the spec / acceptance checklist
# --------------------------------------------------------------------------- #
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

EDL_DUR_TOL_S = 0.15         # sec. 12.15: final duration == edit duration
LUFS_TOL = 0.5               # sec. 6.1: ~ -14 LUFS
TP_TOL_DB = 0.15             # true-peak measurement slack on top of the target
MARGIN_W_PCT = 3.5           # sec. 9.3: frame margins, % of width
MARGIN_H_PCT = 7.0           # sec. 9.3: frame margins, % of height
ALPHA_VISIBLE = 0.12         # sec. 12.3: alpha above this counts as visible graphics
BLACK_MEAN_LIMIT = 8.0       # mean luma (0..255) above which a frame is "not black"
LAYER_MIN_SAMPLES = 12       # checklist: at least 12 evenly spaced frames
LAYER_SAMPLE_STEP_S = 4.0    # aim at one sample every ~4 s of layer time
LAYER_SAMPLE_MIN = 24        # never fewer than this
LAYER_SAMPLE_MAX = 120       # upper bound, keeps the check fast on long layers
FORMAT_GRAY = "format=gray"

# spec sec. 11.3 / 11.4: all four tags are mandatory
COLOR_TAGS = (
    ("color_range", "color_range", "tv"),
    ("color_space", "color_space", "bt709"),
    ("color_primaries", "color_primaries", "bt709"),
    ("color_trc", "color_transfer", "bt709"),
)

# tolerant EDL shapes: the montage list is a flat list of cuts in every run so far
SEG_KEYS = ("segments", "clips", "cuts", "items", "edl", "entries", "timeline", "shots")
IN_KEYS = ("in", "src_in", "source_in", "t_in", "start", "from", "start_s")
OUT_KEYS = ("out", "src_out", "source_out", "t_out", "end", "to", "end_s")
DUR_KEYS = ("duration", "dur", "length", "len")

# pixel formats that really carry an alpha plane
ALPHA_PIX_FMT_PREFIXES = (
    "yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya8", "ya16", "pal8",
)

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}


# --------------------------------------------------------------------------- #
# Small result containers
# --------------------------------------------------------------------------- #
class Check:
    """One reported row: status + measured value + target (+ optional sub-rows)."""

    __slots__ = ("name", "status", "measured", "target", "note", "details")

    def __init__(self, name, status, measured, target, note="", details=None):
        self.name = name
        self.status = status
        self.measured = measured
        self.target = target
        self.note = note
        self.details = list(details or [])

    def to_dict(self):
        out = {
            "check": self.name,
            "status": self.status,
            "measured": self.measured,
            "target": self.target,
            "note": self.note,
        }
        if self.details:
            out["details"] = [d.to_dict() for d in self.details]
        return out


def make_group(name, details, target, measured=None, note=""):
    """Roll sub-checks up into one reported check (FAIL wins, else SKIP if all skipped)."""
    if any(d.status == FAIL for d in details):
        status = FAIL
    elif details and all(d.status == SKIP for d in details):
        status = SKIP
    else:
        status = PASS
    if measured is None:
        measured = "; ".join(f"{d.name}: {d.measured}" for d in details) or "n/a"
    return Check(name, status, measured, target, note, details)


class ToolMissing(RuntimeError):
    pass


class ProbeError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# Process / probe helpers
# --------------------------------------------------------------------------- #
def run_text(cmd, timeout=None):
    """Run a command, capture stdout/stderr as text (ffmpeg output is ASCII)."""
    try:
        return subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except FileNotFoundError as exc:
        raise ToolMissing(str(cmd[0])) from exc


def run_bytes(cmd, timeout=None):
    """Run a command and capture raw binary stdout (rawvideo pipes)."""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ToolMissing(str(cmd[0])) from exc


def ffprobe_json(path):
    proc = run_text(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    )
    if proc.returncode != 0:
        raise ProbeError((proc.stderr or "").strip() or f"ffprobe failed: {path}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe gave no JSON for {path}: {exc}") from exc


def stream_of(probe, codec_type, index=0):
    found = [s for s in probe.get("streams", []) if s.get("codec_type") == codec_type]
    return found[index] if len(found) > index else None


def parse_rate(value):
    """'30/1' -> 30.0, '29.97' -> 29.97, junk -> None."""
    if value is None:
        return None
    text = str(value).strip()
    if "/" in text:
        num, _, den = text.partition("/")
        try:
            num_f, den_f = float(num), float(den)
        except ValueError:
            return None
        return num_f / den_f if den_f else None
    try:
        return float(text)
    except ValueError:
        return None


_TIME_RE = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)$")


def parse_time(value):
    """Accept seconds (int/float/str) or 'HH:MM:SS.mmm' / 'MM:SS.mmm'."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    match = _TIME_RE.match(text)
    if not match:
        return None
    parts = [float(p) for p in match.groups() if p is not None]
    total = 0.0
    for part in parts:
        total = total * 60.0 + part
    return total


def first_key(mapping, keys):
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def fmt(value, digits=3):
    return "n/a" if value is None else f"{value:.{digits}f}"


def fmt_signed(value, digits=3):
    """Signed value with a clean zero (no '-0.000')."""
    if value is None:
        return "n/a"
    if abs(value) < 0.5 * 10 ** (-digits):
        value = 0.0
    return f"{value:+.{digits}f}"


def pix_fmt_has_alpha(pix):
    probe = (pix or "").lower()
    return any(probe.startswith(prefix) for prefix in ALPHA_PIX_FMT_PREFIXES)


# --------------------------------------------------------------------------- #
# EDL (edit/edl.json)
# --------------------------------------------------------------------------- #
def edl_segments(data):
    if isinstance(data, dict):
        for key in SEG_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        if any(k in data for k in IN_KEYS):
            return [data]
        for value in data.values():  # last resort: first list of dicts
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def edl_duration(path):
    """-> (total edited seconds, usable segments, unparsable segments)."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    total, usable, broken = 0.0, 0, 0
    for seg in edl_segments(data):
        start = parse_time(first_key(seg, IN_KEYS))
        end = parse_time(first_key(seg, OUT_KEYS))
        if end is None:
            length = parse_time(first_key(seg, DUR_KEYS))
            if start is not None and length is not None:
                end = start + length
        if start is None or end is None:
            broken += 1
            continue
        total += max(0.0, end - start)
        usable += 1
    return total, usable, broken


# --------------------------------------------------------------------------- #
# Composition HTML: subtitle markers, clip intervals, occlusion allowance
# --------------------------------------------------------------------------- #
class CompParser(HTMLParser):
    """Collect clip time intervals and `data-layout-allow-occlusion` elements.

    An element without its own data-start/data-duration inherits them from the nearest
    open ancestor (approximation: nested HyperFrames compositions may use their own
    time base, in which case the interval is only indicative).
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []          # [{"tag", "start", "dur"}]
        self.clips = []          # (start, end, label)
        self.occlusion = []      # (start, end, label, explicit_timing)

    def handle_starttag(self, tag, attrs):
        attr = {}
        for key, value in attrs:
            attr[key.lower()] = "" if value is None else value

        start = length = None
        explicit = "data-start" in attr and "data-duration" in attr
        if explicit:
            try:
                start = float(attr["data-start"])
                length = float(attr["data-duration"])
            except ValueError:
                start = length = None
        elif self.stack and self.stack[-1]["start"] is not None:
            start = self.stack[-1]["start"]
            length = self.stack[-1]["dur"]

        element_id = (attr.get("id") or "").strip()
        classes = " ".join((attr.get("class") or "").split())
        if element_id or classes:
            label = ("#" + element_id if element_id else "") + (
                "." + classes.replace(" ", ".") if classes else ""
            )
        else:
            label = tag

        if start is not None and length is not None and length > 0:
            end = start + length
            class_list = classes.split()
            if "clip" in class_list:
                self.clips.append((start, end, label))
            flag = attr.get("data-layout-allow-occlusion", "").strip().lower()
            if flag and flag not in ("false", "0", "no", "off"):
                self.occlusion.append((start, end, label, explicit))

        if tag not in VOID_TAGS:
            self.stack.append({"tag": tag, "start": start, "dur": length})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for pos in range(len(self.stack) - 1, -1, -1):
            if self.stack[pos]["tag"] == tag:
                del self.stack[pos:]
                return

    # -- queries ----------------------------------------------------------- #
    def in_occlusion(self, t):
        return any(a <= t <= b for a, b, _label, _explicit in self.occlusion)

    def occlusion_labels(self):
        return sorted({label for _a, _b, label, _explicit in self.occlusion})

    def full_span_labels(self, total):
        """Labels of clips covering (almost) the whole layer - containers/roots."""
        if total <= 0:
            return set()
        return {
            label
            for start, end, label in self.clips
            if start <= 0.05 * total and end >= 0.95 * total
        }

    def active_labels(self, t, total):
        containers = self.full_span_labels(total)
        return sorted(
            {label for start, end, label in self.clips if start <= t <= end and label not in containers}
        )


def parse_comp(html_path):
    parser = CompParser()
    parser.feed(Path(html_path).read_text(encoding="utf-8-sig", errors="replace"))
    parser.close()
    return parser


# --------------------------------------------------------------------------- #
# Measurement helpers
# --------------------------------------------------------------------------- #
def measure_loudness(path, timeout=None):
    """-> (integrated LUFS or None, true peak dBTP or None) via ffmpeg ebur128."""
    proc = run_text(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-",
        ],
        timeout=timeout,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    lufs = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", blob)
    peaks = re.findall(r"\bPeak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", blob)
    return (
        float(lufs[-1]) if lufs else None,
        float(peaks[-1]) if peaks else None,
    )


def measure_video_bitrate_mbps(path, stream, duration):
    """Container-reported stream bitrate, with a packet-sum fallback."""
    raw = stream.get("bit_rate")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value / 1e6, "ffprobe stream bit_rate"
        except (TypeError, ValueError):
            pass
    if not duration:
        return None, "unavailable"
    proc = run_text(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "packet=size", "-of", "csv=p=0", str(path),
        ]
    )
    total = 0
    for token in (proc.stdout or "").split():
        token = token.strip().rstrip(",")
        if token.isdigit():
            total += int(token)
    if total <= 0:
        return None, "unavailable"
    return total * 8.0 / duration / 1e6, "packet size sum"


def alpha_frame(layer, t, width, height):
    """One alpha plane (uint8, HxW) from the graphics layer at time t, or None."""
    proc = run_bytes(
        [
            "ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(layer),
            "-vf", "alphaextract", "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ]
    )
    buf = proc.stdout or b""
    if len(buf) < width * height:
        return None
    return np.frombuffer(buf[: width * height], dtype=np.uint8).reshape(height, width)


def gray_frames(path, in_args, out_args, width, height):
    """Decode gray frames (list of HxW uint8 arrays) with the given input options."""
    proc = run_bytes(
        ["ffmpeg", "-v", "error", *in_args, "-i", str(path),
         "-vf", FORMAT_GRAY, *out_args, "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    )
    buf = proc.stdout or b""
    count = len(buf) // (width * height)
    if count <= 0:
        return []
    arr = np.frombuffer(buf[: count * width * height], dtype=np.uint8)
    return list(arr.reshape(count, height, width))


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def check_video(probe, args, edl_state):
    video = stream_of(probe, "video")
    target = (
        f"h264 / yuv420p / {args.width}x{args.height} / {args.fps:g} fps / "
        f"duration = EDL sum +- {EDL_DUR_TOL_S:.2f} s"
    )
    if video is None:
        return Check("video", FAIL, "no video stream", target, "final.mp4 has no video stream")

    details = []
    codec = video.get("codec_name")
    details.append(Check("codec", PASS if codec == "h264" else FAIL, codec or "n/a", "h264"))

    pix = video.get("pix_fmt")
    details.append(Check("pix_fmt", PASS if pix == "yuv420p" else FAIL, pix or "n/a", "yuv420p"))

    width, height = video.get("width"), video.get("height")
    size_ok = width == args.width and height == args.height
    details.append(
        Check("size", PASS if size_ok else FAIL, f"{width}x{height}", f"{args.width}x{args.height}")
    )

    rate = parse_rate(video.get("avg_frame_rate")) or parse_rate(video.get("r_frame_rate"))
    fps_ok = rate is not None and abs(rate - args.fps) <= 0.005
    details.append(
        Check(
            "fps",
            PASS if fps_ok else FAIL,
            f"{fmt(rate, 3)} fps (r_frame_rate {video.get('r_frame_rate') or 'n/a'})",
            f"{args.fps:g} fps",
        )
    )

    duration = parse_time(video.get("duration"))
    if duration is None:
        duration = parse_time((probe.get("format") or {}).get("duration"))
    edl_dur = edl_state.get("duration")
    state = edl_state.get("status")
    if state == "no-edit":
        details.append(
            Check(
                "duration",
                SKIP,
                f"{fmt(duration)} s",
                f"EDL sum +- {EDL_DUR_TOL_S:.2f} s",
                "no --edit given: edited duration not verified",
            )
        )
    elif state != "ok":
        details.append(
            Check("duration", FAIL, f"{fmt(duration)} s", f"readable EDL sum +- {EDL_DUR_TOL_S:.2f} s",
                  f"edit/edl.json {state}")
        )
    else:
        delta = None if duration is None else duration - edl_dur
        ok = delta is not None and abs(delta) <= EDL_DUR_TOL_S
        details.append(
            Check(
                "duration",
                PASS if ok else FAIL,
                f"{fmt(duration)} s vs EDL {fmt(edl_dur)} s "
                f"({edl_state.get('segments', 0)} segments, delta {fmt_signed(delta)} s)",
                f"EDL sum +- {EDL_DUR_TOL_S:.2f} s",
            )
        )

    measured = (
        f"{codec or 'n/a'} / {pix or 'n/a'} / {width}x{height} / {fmt(rate, 3)} fps / "
        f"duration {fmt(duration)} s"
    )
    note = ""
    if state == "no-edit":
        note = "duration not verified: --edit not given"
    elif state != "ok":
        note = f"duration not verifiable: edit/edl.json {state}"
    return make_group("video", details, target, measured, note)


def check_color_tags(probe):
    video = stream_of(probe, "video")
    target = "tv / bt709 / bt709 / bt709 (all four tags mandatory)"
    if video is None:
        return Check("color_tags", FAIL, "no video stream", target)
    details, values = [], []
    for shown, key, want in COLOR_TAGS:
        got = video.get(key)
        values.append(f"{shown}={got or 'missing'}")
        details.append(
            Check(shown, PASS if got == want else FAIL, got or "missing", want)
        )
    return make_group("color_tags", details, target, " / ".join(values))


def check_bitrate(path, probe, args):
    video = stream_of(probe, "video")
    target = f">= {args.min_bitrate_mbps:g} Mbps (target ~30 Mbps)"
    if video is None:
        return Check("bitrate", FAIL, "no video stream", target)
    duration = parse_time(video.get("duration")) or parse_time(
        (probe.get("format") or {}).get("duration")
    )
    mbps, how = measure_video_bitrate_mbps(path, video, duration)
    if mbps is None:
        return Check("bitrate", FAIL, "unavailable", target, f"bitrate not measurable ({how})")
    ok = mbps >= args.min_bitrate_mbps
    detail = Check(
        "video bitrate",
        PASS if ok else FAIL,
        f"{mbps:.2f} Mbps ({how})",
        f">= {args.min_bitrate_mbps:g} Mbps",
    )
    return make_group("bitrate", [detail], target, f"{mbps:.2f} Mbps")


def check_audio(path, probe, args):
    tp_limit = args.tp + TP_TOL_DB
    target = f"aac / {args.lufs:g} LUFS +- {LUFS_TOL:g} LU / true peak <= {tp_limit:.2f} dBTP"
    audio = stream_of(probe, "audio")
    if audio is None:
        return Check("audio", FAIL, "no audio stream", target, "final.mp4 has no audio stream")

    details = []
    codec = audio.get("codec_name")
    layout = f"{audio.get('sample_rate') or '?'} Hz, {audio.get('channels') or '?'} ch"
    details.append(
        Check("stream", PASS if codec == "aac" else FAIL, f"{codec or 'n/a'} ({layout})", "aac")
    )

    lufs, peak = measure_loudness(path)
    if lufs is None:
        details.append(
            Check("loudness", FAIL, "unmeasurable", f"{args.lufs:g} +- {LUFS_TOL:g} LU",
                  "ffmpeg ebur128 gave no integrated loudness")
        )
    else:
        ok = abs(lufs - args.lufs) <= LUFS_TOL
        details.append(
            Check("loudness", PASS if ok else FAIL, f"{lufs:.2f} LUFS",
                  f"{args.lufs:g} +- {LUFS_TOL:g} LU (delta {lufs - args.lufs:+.2f} LU)")
        )
    if peak is None:
        details.append(
            Check("true_peak", FAIL, "unmeasurable", f"<= {tp_limit:.2f} dBTP",
                  "ffmpeg ebur128 gave no true peak")
        )
    else:
        ok = peak <= tp_limit
        details.append(
            Check("true_peak", PASS if ok else FAIL, f"{peak:.2f} dBTP", f"<= {tp_limit:.2f} dBTP")
        )

    measured = f"{codec or 'n/a'} / {fmt(lufs, 2)} LUFS / true peak {fmt(peak, 2)} dBTP"
    return make_group("audio", details, target, measured)


def check_subtitles(edit):
    target = 'no class="subs", no class="sub clip", no edit/subtitles.json (spec sec. 5)'
    if edit is None:
        return Check(
            "subtitles", SKIP, "not checked", target, "no --edit given: subtitle rule not verified"
        )

    details = []
    subs_re = re.compile(r"""class\s*=\s*["'][^"']*\bsubs\b""", re.I)
    sub_clip_re = re.compile(r"""class\s*=\s*["'][^"']*\bsub\b[^"']*\bclip\b""", re.I)

    html_path = Path(edit) / "comp" / "index.html"
    if not html_path.is_file():
        details.append(
            Check("comp/index.html", PASS, "absent", 'no class="subs" / "sub clip"',
                  "no composition in edit/: nothing to scan")
        )
    else:
        html = html_path.read_text(encoding="utf-8-sig", errors="replace")
        n_subs = len(subs_re.findall(html))
        n_clip = len(sub_clip_re.findall(html))
        ok = n_subs == 0 and n_clip == 0
        details.append(
            Check(
                "comp/index.html",
                PASS if ok else FAIL,
                f'{n_subs}x class="subs", {n_clip}x class="sub clip"',
                'no class="subs" and no class="sub clip"',
            )
        )

    subs_json = Path(edit) / "subtitles.json"
    details.append(
        Check(
            "edit/subtitles.json",
            FAIL if subs_json.exists() else PASS,
            "present" if subs_json.exists() else "absent",
            "absent",
        )
    )

    note = ""
    data_json = Path(edit) / "data.json"
    if data_json.is_file():
        try:
            flag = json.loads(data_json.read_text(encoding="utf-8-sig", errors="replace")).get("subtitles")
            note = f"info: edit/data.json has subtitles={flag!r} (spec sec. 5 expects false)"
        except (json.JSONDecodeError, OSError):
            note = "info: edit/data.json is not readable JSON"
    return make_group("subtitles", details, target, note=note)


def check_layer_alpha(edit, args):
    target = (
        f">= 1 empty frame (max alpha == 0); graphics present (max alpha > {ALPHA_VISIBLE:g}); "
        f"opaque bbox >= {MARGIN_W_PCT:g}% of width and >= {MARGIN_H_PCT:g}% of height from the edges"
    )
    layer = None if edit is None else Path(edit) / "layer-front.mov"
    if layer is None or not layer.is_file():
        return Check(
            "layer_alpha", SKIP, "layer-front.mov not found", target,
            "no --edit or no layer file: alpha checks skipped",
        )

    try:
        probe = ffprobe_json(layer)
    except ProbeError as exc:
        return Check("layer_alpha", FAIL, "unreadable", target, str(exc))
    video = stream_of(probe, "video")
    if video is None:
        return Check("layer_alpha", FAIL, "no video stream", target, "layer-front.mov has no video")

    width = int(video.get("width") or args.width)
    height = int(video.get("height") or args.height)
    duration = parse_time(video.get("duration")) or parse_time(
        (probe.get("format") or {}).get("duration")
    )
    details = []

    pix = video.get("pix_fmt") or "n/a"
    has_alpha = pix_fmt_has_alpha(pix)
    details.append(
        Check(
            "alpha_channel",
            PASS if has_alpha else FAIL,
            pix,
            "pixel format with alpha (ProRes 4444, e.g. yuva444p12le)",
        )
    )

    if not duration or duration <= 0:
        details.append(Check("sampling", FAIL, "unknown duration", f">= {LAYER_MIN_SAMPLES} frames"))
        return make_group("layer_alpha", details, target, note="layer duration unknown")

    count = max(LAYER_SAMPLE_MIN, min(LAYER_SAMPLE_MAX, int(round(duration / LAYER_SAMPLE_STEP_S))))
    times = [duration * (i + 0.5) / count for i in range(count)]
    frames = [(t, alpha_frame(layer, t, width, height)) for t in times]
    decoded = [(t, a) for t, a in frames if a is not None]
    details.append(
        Check(
            "sampling",
            PASS if len(decoded) >= LAYER_MIN_SAMPLES else FAIL,
            f"{len(decoded)}/{count} frames decoded via ffmpeg alphaextract",
            f">= {LAYER_MIN_SAMPLES} frames evenly spaced over {fmt(duration)} s",
            f"one sample every {duration / count:.1f} s of layer time",
        )
    )
    if not decoded:
        return make_group("layer_alpha", details, target, note="no alpha frame could be decoded")

    thr = int(round(ALPHA_VISIBLE * 255))
    empty = sum(1 for _t, a in decoded if int(a.max()) == 0)
    empty_note = ""
    if empty == 0:
        empty_note = (
            "every sampled frame carries graphics: look for a full-length element "
            "(e.g. burned-in subtitles or a background layer)"
        )
    details.append(
        Check(
            "empty_frames",
            PASS if empty >= 1 else FAIL,
            f"{empty}/{len(decoded)} frames with max(alpha) == 0",
            ">= 1 (alpha is 0 outside the graphics)",
            empty_note,
        )
    )

    visible = [(t, a) for t, a in decoded if int(a.max()) > thr]
    details.append(
        Check(
            "graphics_present",
            PASS if visible else FAIL,
            f"{len(visible)}/{len(decoded)} frames with max(alpha) > {ALPHA_VISIBLE:g}",
            f">= 1 frame with max(alpha) > {ALPHA_VISIBLE:g}",
        )
    )

    comp = None
    comp_path = Path(edit) / "comp" / "index.html"
    if comp_path.is_file():
        try:
            comp = parse_comp(comp_path)
        except OSError:
            comp = None

    worst = [float("inf")] * 4  # L, R, T, B in %
    violations, exempt = [], []
    measured_frames = 0
    for t, a in visible:
        mask = a > thr
        rows, cols = np.nonzero(mask)
        left = float(cols.min()) / width * 100.0
        right = float(width - 1 - cols.max()) / width * 100.0
        top = float(rows.min()) / height * 100.0
        bottom = float(height - 1 - rows.max()) / height * 100.0
        margins = (left, right, top, bottom)
        bad = (
            left < MARGIN_W_PCT or right < MARGIN_W_PCT
            or top < MARGIN_H_PCT or bottom < MARGIN_H_PCT
        )
        if comp is not None and comp.in_occlusion(t):
            if bad:
                exempt.append((t, margins))
            continue
        measured_frames += 1
        worst = [min(w, m) for w, m in zip(worst, margins)]
        if bad:
            violations.append((t, margins))

    if not visible or measured_frames == 0:
        details.append(
            Check("frame_margins", SKIP, "n/a", f">= {MARGIN_W_PCT:g}% W / {MARGIN_H_PCT:g}% H",
                  "no sampled frame with graphics outside the occlusion exemption")
        )
    else:
        shown = "/".join("n/a" if w == float("inf") else f"{w:.2f}" for w in worst)
        details.append(
            Check(
                "frame_margins",
                FAIL if violations else PASS,
                f"min margins L/R/T/B = {shown} % of frame; {len(violations)} violating frames",
                f">= {MARGIN_W_PCT:g}% of width, >= {MARGIN_H_PCT:g}% of height",
                "; ".join(
                    f"t={t:.2f}s L={m[0]:.2f} R={m[1]:.2f} T={m[2]:.2f} B={m[3]:.2f}"
                    for t, m in violations[:6]
                ),
            )
        )

    labels = comp.occlusion_labels() if comp is not None else []
    notes = []
    if labels:
        notes.append(
            "occlusion exemption (data-layout-allow-occlusion): elements "
            + ", ".join(labels)
            + f"; applied to {len(exempt)}/{len(visible)} sampled frames"
            + (" at t=" + ", ".join(f"{t:.2f}s" for t, _m in exempt[:8]) if exempt else "")
        )
        if exempt:
            notes.append(
                "exemption is frame-level: other elements active at those timestamps are "
                "not attributed separately"
            )
    else:
        notes.append("no data-layout-allow-occlusion element found in comp/index.html")

    measured = (
        f"empty {empty}/{len(decoded)} frames; visible {len(visible)}/{len(decoded)} frames; "
        f"min margins " + "/".join("n/a" if w == float("inf") else f"{w:.2f}" for w in worst) + " %"
    )
    if len(decoded) != count:
        notes.append(f"{count - len(decoded)} sampled frames could not be decoded")
    return make_group("layer_alpha", details, target, measured, " | ".join(notes))


def check_black_frames(path, probe):
    target = f"first and last frame mean luma > {BLACK_MEAN_LIMIT:g}/255"
    video = stream_of(probe, "video")
    if video is None:
        return Check("black_frames", FAIL, "no video stream", target)
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        return Check("black_frames", FAIL, "unknown frame size", target)

    details = []
    head = gray_frames(path, [], ["-frames:v", "1"], width, height)
    if head:
        mean = float(head[0].mean())
        details.append(
            Check("first_frame", PASS if mean > BLACK_MEAN_LIMIT else FAIL,
                  f"mean luma {mean:.2f}/255", f"> {BLACK_MEAN_LIMIT:g}/255")
        )
    else:
        details.append(Check("first_frame", FAIL, "undecodable", f"> {BLACK_MEAN_LIMIT:g}/255"))

    tail = gray_frames(path, ["-sseof", "-0.25"], [], width, height)
    if not tail:
        tail = gray_frames(path, ["-sseof", "-1.0"], [], width, height)
    if not tail:
        tail = gray_frames(path, [], [], width, height)  # last resort: decode everything
    if tail:
        mean = float(tail[-1].mean())
        details.append(
            Check("last_frame", PASS if mean > BLACK_MEAN_LIMIT else FAIL,
                  f"mean luma {mean:.2f}/255", f"> {BLACK_MEAN_LIMIT:g}/255")
        )
    else:
        details.append(Check("last_frame", FAIL, "undecodable", f"> {BLACK_MEAN_LIMIT:g}/255"))

    measured = "; ".join(f"{d.name} {d.measured}" for d in details)
    return make_group("black_frames", details, target, measured)


def check_source(source, probe_final, final_duration):
    """Optional cross-check of the source file, run only when --source is given."""
    target = "readable; source duration >= final duration; colour tags consistent"
    try:
        probe = ffprobe_json(source)
    except ProbeError as exc:
        return Check("source", FAIL, "unreadable", target, str(exc))

    details = [Check("readable", PASS, str(source), "readable")]
    video = stream_of(probe, "video")
    src_dur = None
    if video is not None:
        src_dur = parse_time(video.get("duration"))
    if src_dur is None:
        src_dur = parse_time((probe.get("format") or {}).get("duration"))

    if src_dur is None or final_duration is None:
        details.append(
            Check("duration", SKIP, f"source {fmt(src_dur)} s, final {fmt(final_duration)} s",
                  "source >= final", "duration of one of the files is unknown")
        )
    else:
        ok = src_dur + EDL_DUR_TOL_S >= final_duration
        details.append(
            Check("duration", PASS if ok else FAIL,
                  f"source {fmt(src_dur)} s vs final {fmt(final_duration)} s",
                  "source >= final - 0.15 s")
        )

    final_video = stream_of(probe_final, "video") or {}
    mismatched = []
    for shown, key, _want in COLOR_TAGS:
        src_val = (video or {}).get(key)
        fin_val = final_video.get(key)
        if src_val and src_val != "unknown" and fin_val and src_val != fin_val:
            mismatched.append(f"{shown}: source {src_val} vs final {fin_val}")
    if not video:
        details.append(Check("color_tags", SKIP, "no video stream in source", "consistent"))
    elif mismatched:
        details.append(Check("color_tags", FAIL, "; ".join(mismatched), "final tags match source"))
    else:
        details.append(
            Check("color_tags", PASS, "source and final tags agree (or source tags are unset)",
                  "final tags match source")
        )

    return make_group("source", details, target, note="optional check requested with --source")


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def wrap_note(note, width=110, indent="    "):
    lines = textwrap.wrap(note, width=width) or [""]
    return [indent + "note     : " + lines[0]] + [indent + "           " + ln for ln in lines[1:]]


def print_report(checks, final, edit, source, args, verdict):
    print("verify_final.py - acceptance checks (MONTAGE-PROMPT-v4.md sec. 5/6.1/9.3/11.3/12)")
    print(f"file   : {final}")
    print(f"edit   : {edit if edit is not None else '-'}")
    print(f"source : {source if source is not None else '-'}")
    print(
        f"params : {args.width}x{args.height} @ {args.fps:g} fps, video bitrate >= "
        f"{args.min_bitrate_mbps:g} Mbps, audio {args.lufs:g} LUFS +- {LUFS_TOL:g} LU, "
        f"true peak <= {args.tp + TP_TOL_DB:.2f} dBTP"
    )
    print()
    for check in checks:
        print(f"[{check.status}] {check.name}")
        print(f"    measured : {check.measured}")
        print(f"    target   : {check.target}")
        if check.note:
            for line in wrap_note(check.note):
                print(line)
        for detail in check.details:
            print(
                f"      . {detail.name:<16} [{detail.status}] "
                f"measured: {detail.measured}"
            )
            print(f"        {'':<16}  target  : {detail.target}")
            if detail.note:
                print(f"        {'':<16}  note    : {detail.note}")
        print()

    passed = sum(1 for c in checks if c.status == PASS)
    failed = sum(1 for c in checks if c.status == FAIL)
    skipped = sum(1 for c in checks if c.status == SKIP)
    print("-" * 100)
    print(f"checks: {passed} passed, {failed} failed, {skipped} skipped (of {len(checks)})")
    print(f"VERDICT: {verdict}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="verify_final.py",
        description="Acceptance checks for the montage final.mp4 (MONTAGE-PROMPT-v4.md sec. 12).",
    )
    parser.add_argument("final", help="rendered final.mp4")
    parser.add_argument("--edit", default=None, help="runs/<label>/edit folder (edl.json, comp/, layer-front.mov)")
    parser.add_argument("--source", default=None, help="source footage for the optional cross-check")
    parser.add_argument("--json", dest="json_out", default=None, help="write the report as JSON")
    parser.add_argument("--lufs", type=float, default=-14.0, help="target integrated loudness, LUFS (default -14)")
    parser.add_argument("--tp", type=float, default=-1.0, help="true peak ceiling, dBTP (default -1.0)")
    parser.add_argument("--min-bitrate-mbps", type=float, default=24.0, help="minimum video bitrate (default 24)")
    parser.add_argument("--fps", type=float, default=30.0, help="expected frame rate (default 30)")
    parser.add_argument("--width", type=int, default=1920, help="expected width (default 1920)")
    parser.add_argument("--height", type=int, default=1080, help="expected height (default 1080)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    final = Path(args.final)
    edit = Path(args.edit) if args.edit else None
    source = Path(args.source) if args.source else None

    if not final.is_file():
        print(f"ERROR: final file not found: {final}", file=sys.stderr)
        return 2
    if edit is not None and not edit.is_dir():
        print(f"ERROR: edit folder not found: {edit}", file=sys.stderr)
        return 2
    if source is not None and not source.is_file():
        print(f"ERROR: source file not found: {source}", file=sys.stderr)
        return 2

    try:
        probe = ffprobe_json(final)
    except ProbeError as exc:
        print(f"ERROR: cannot probe {final}: {exc}", file=sys.stderr)
        return 2
    except ToolMissing as exc:
        print(f"ERROR: required tool not found in PATH: {exc}", file=sys.stderr)
        return 2

    # EDL duration (check 1) ------------------------------------------------- #
    edl_state = {"status": "no-edit", "duration": None, "segments": 0}
    if edit is not None:
        edl_path = edit / "edl.json"
        if not edl_path.is_file():
            edl_state["status"] = "missing"
        else:
            try:
                total, usable, _broken = edl_duration(edl_path)
                if usable > 0:
                    edl_state = {"status": "ok", "duration": total, "segments": usable}
                else:
                    edl_state["status"] = "has no parsable cut in/out pairs"
            except (json.JSONDecodeError, OSError, ValueError):
                edl_state["status"] = "unreadable"

    checks = []
    try:
        checks.append(check_video(probe, args, edl_state))
        checks.append(check_color_tags(probe))
        checks.append(check_bitrate(final, probe, args))
        checks.append(check_audio(final, probe, args))
        checks.append(check_subtitles(edit))
        checks.append(check_layer_alpha(edit, args))
        checks.append(check_black_frames(final, probe))
    except ToolMissing as exc:
        print(f"ERROR: required tool not found in PATH: {exc}", file=sys.stderr)
        return 2

    final_video = stream_of(probe, "video") or {}
    final_duration = parse_time(final_video.get("duration")) or parse_time(
        (probe.get("format") or {}).get("duration")
    )
    if source is not None:
        checks.append(check_source(source, probe, final_duration))

    failed = [c for c in checks if c.status == FAIL]
    verdict = "FAIL" if failed else "PASS"
    print_report(checks, final, edit, source, args, verdict)

    if failed:
        print()
        print("failed checks: " + ", ".join(c.name for c in failed))
        for check in failed:
            for detail in check.details:
                if detail.status == FAIL:
                    print(f"  - {check.name}.{detail.name}: {detail.measured} (target {detail.target})")

    if args.json_out:
        payload = {
            "file": str(final),
            "edit": str(edit) if edit is not None else None,
            "source": str(source) if source is not None else None,
            "params": {
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "lufs": args.lufs,
                "tp": args.tp,
                "min_bitrate_mbps": args.min_bitrate_mbps,
            },
            "checks": [c.to_dict() for c in checks],
            "passed": sum(1 for c in checks if c.status == PASS),
            "failed": len(failed),
            "skipped": sum(1 for c in checks if c.status == SKIP),
            "verdict": verdict,
        }
        out_path = Path(args.json_out)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            print(f"ERROR: cannot write JSON report {out_path}: {exc}", file=sys.stderr)
            return 2
        print(f"json report: {out_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
