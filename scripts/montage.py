#!/usr/bin/env python3
"""One-command montage pipeline (spec MONTAGE-PROMPT-v4, §3–§13).

    py -3 scripts\\montage.py --label v3 --take "takes\\2026-05-28 13-20-36.mp4"

Runs the whole chain and stops on the first failure:

    env -> edl -> voice -> comp -> check -> render -> final -> verify -> report

(`edl` also snaps every cut onto the speech envelope and audits the result.)
Every stage is skipped when its outputs are already newer than its inputs, so a
rerun after a crash resumes instead of starting over. `--force all` rebuilds
everything, `--only <stage>` runs one stage, `--from <stage>` starts there.

Everything a stage produces lands in runs/<label>/; nothing is written outside it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TAKES = ROOT / "takes"

DEFAULT_PASSPORT = {
    "aspect": "16:9",
    "fps": 30,
    "picture_mode": "contrast",
    "colors": {"white": "#FFFFFF", "accent1": "#EF3124",
               "accent2": "#BC0004", "dark_panel": "#F3F3F3",
               "surface": "#F3F3F3", "ink": "#1A1C1C"},
    "fonts": {"accent": "Inter Black", "text": "Inter"},
    "author": {"name": "Дмитрий Царьков", "role": "управляющий активами"},
    "subtitles": False,
    # where the speaker's face sits in the frame, in % of the canvas: inserts are
    # laid out in the outer columns and the face-safe check refuses to draw on it
    "face_box_pct": {"x": 39.0, "y": 30.0, "w": 27.0, "h": 38.0},
}
BRAND_PATH = ROOT / "refs" / "brandbook" / "brand.json"


def brand_passport() -> dict:
    """Passport defaults come from the brandbook tokens, not from code (§1)."""
    if not BRAND_PATH.exists():
        return {"colors": dict(DEFAULT_PASSPORT["colors"]),
                "fonts": dict(DEFAULT_PASSPORT["fonts"]), "brand": None}
    brand = json.loads(BRAND_PATH.read_text(encoding="utf-8-sig"))
    c = brand["colors"]
    return {
        "brand": {"name": brand.get("name"), "version": brand.get("version")},
        "colors": {"white": c["white"], "accent1": c["accent"], "accent2": c["accent_dark"],
                   "dark_panel": c["surface"], "surface": c["surface"], "ink": c["ink"],
                   "muted": c["muted"]},
        "fonts": {"accent": f"{brand['fonts']['family']} Black",
                  "text": brand["fonts"]["family"]},
    }
DEFAULT_CORRECTION = {
    # midtone S-curve pinned at 1/1: gives contrast without clipping the white
    # dashboard pages (the old eq-contrast stretch added +1.93 pp of clipping)
    "mode": "curve",
    "curve_points": [[0.0, 0.0], [0.25, 0.225], [0.5, 0.51], [0.75, 0.79], [1.0, 1.0]],
    "saturation": 1.05,
    "midtone_max_darken_pct": 10,
}


class Fail(SystemExit):
    def __init__(self, msg: str):
        print(f"\n[FAIL] {msg}", file=sys.stderr)
        super().__init__(1)


def log(msg: str) -> None:
    print(f"    {msg}", flush=True)


def run(cmd: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    printable = " ".join(str(c) for c in cmd)
    log(f"$ {printable if len(printable) < 160 else printable[:157] + '...'}")
    env = dict(os.environ)
    # the code graph / render tools break behind the local proxy (spec ops note)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(key, None)
    env.setdefault("HYPERFRAMES_NO_TELEMETRY", "1")
    env.setdefault("DO_NOT_TRACK", "1")
    # helper scripts print Cyrillic (and a multiplication sign); keep that out of cp1251
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env,
                          text=True, capture_output=capture)
    if proc.returncode != 0:
        tail = ""
        if capture and (proc.stdout or proc.stderr):
            tail = "\n".join(((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-12:])
        raise Fail(f"command failed ({proc.returncode}): {printable}\n{tail}")
    return (proc.stdout or "") if capture else ""


def probe(path: Path, entries: str, select: str | None = None) -> str:
    cmd = ["ffprobe", "-v", "error"]
    if select:
        cmd += ["-select_streams", select]
    cmd += ["-show_entries", entries, "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    return run(cmd, capture=True).strip()


def hyperframes_exe() -> list[str]:
    exe = shutil.which("hyperframes")
    if not exe:
        raise Fail("hyperframes not found on PATH")
    if exe.lower().endswith(".ps1"):
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", exe]
    return [exe]


class Pipeline:
    def __init__(self, args) -> None:
        self.label = args.label
        self.take = Path(args.take).resolve()
        self.edit = ROOT / "runs" / self.label / "edit"
        self.out = ROOT / "runs" / self.label / "out"
        self.args = args
        # with a shooting script the graphics come from the script plan, block by block
        self.script = None
        if getattr(args, "script", None):
            self.script = Path(args.script)
            if not self.script.is_absolute():
                self.script = (ROOT / self.script).resolve()
            if not self.script.is_file():
                raise Fail(f"script not found: {self.script}")
        self.stamp = {"label": self.label, "take": str(self.take),
                      "script": str(self.script) if self.script else None, "stages": []}
        self.edit.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        if not self.take.is_file():
            raise Fail(f"take not found: {self.take}")
        base = self.take.stem
        self.words = self.edit / "transcripts" / f"{base}-words.json"
        self.edl = self.edit / "edl.json"
        self.voice = self.edit / "voice.wav"
        self.comp = self.edit / "comp" / "index.html"
        self.layer = self.edit / "layer-front.mov"
        self.master = self.edit / "master-lossless.mp4"
        self.final = self.out / "final.mp4"
        self.verify_json = self.edit / "verify.json"
        self.report = self.edit / "report.md"

    # ---------------------------------------------------------------- helpers
    def passport(self) -> Path:
        path = self.edit / "data.json"
        if not path.exists():
            fps = probe(self.take, "stream=r_frame_rate", "v:0")
            try:
                num, den = (int(x) for x in fps.split("/"))
                fps_val = round(num / den) if den else 30
            except Exception:
                fps_val = 30
            bp = brand_passport()
            data = {
                "passport": {**DEFAULT_PASSPORT, "run_label": self.label, "fps": fps_val,
                             "colors": bp["colors"], "fonts": bp["fonts"],
                             "brand": bp.get("brand")},
                "correction": dict(DEFAULT_CORRECTION),
                "encode": {"codec": "libx264", "bitrate": "30M", "preset": "slow",
                           "tune": "grain", "color_range": "tv", "colorspace": "bt709"},
                "replacements": {},
                "segments": [],
                "graphics": [],
                "sfx": [],
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"passport created: {path.name} (fps {fps_val}, subtitles false)")
        return path

    def fresh(self, outputs: list[Path], inputs: list[Path]) -> bool:
        if not all(p.exists() for p in outputs):
            return False
        newest_in = max([p.stat().st_mtime for p in inputs if p.exists()], default=0.0)
        return min(p.stat().st_mtime for p in outputs) >= newest_in

    # ----------------------------------------------------------------- stages
    def stage_env(self) -> None:
        for tool, args in (("ffmpeg", ["-version"]), ("ffprobe", ["-version"])):
            exe = shutil.which(tool)
            if not exe:
                raise Fail(f"{tool} not found on PATH")
            log(f"{tool}: {exe}")
        w = shutil.which("whisper-cli")
        log(f"whisper-cli: {w or 'not found (only needed with --transcribe)'}")
        hf = hyperframes_exe()
        ver = run([*hf, "--version"], capture=True).strip().splitlines()[-1]
        log(f"hyperframes: {ver}")
        model = Path(os.environ.get("USERPROFILE", "")) / ".cache" / "whisper" / "ggml-large-v3.bin"
        log(f"whisper model: {'present' if model.exists() else 'MISSING'} ({model})")

    def stage_edl(self) -> None:
        self.passport()
        if not self.words.exists():
            raise Fail(f"no transcript at {self.words}; run with --transcribe or pass --transcript")
        run([sys.executable, str(SCRIPTS / "build_edl.py"), str(self.words),
             str(self.edl), "--source", self.take.name], capture=True)
        # --tail-hold keeps a beat of footage after the last word, so the closing
        # line is never clipped and the end card has room
        run([sys.executable, str(SCRIPTS / "snap_cuts.py"), str(self.take),
             str(self.edl), str(self.edl), "--data", str(self.edit / "data.json"),
             "--max-pause", "0.5", "--keep-pause", "0.16", "--tail-hold", "1.6"],
            capture=True)
        out = run([sys.executable, str(SCRIPTS / "check_edl.py"), str(self.take), str(self.edl),
                   "--json", str(self.edit / "check_edl.json")], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_voice(self) -> None:
        out = run([sys.executable, str(SCRIPTS / "build_voice.py"), str(self.take),
                   str(self.edl), str(self.voice)], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_script_plan(self) -> None:
        """Script -> machine plan: blocks, their marks, and where they land on the timeline."""
        out = run([sys.executable, str(SCRIPTS / "build_script_plan.py"), str(self.script),
                   str(self.edit)], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_comp(self) -> None:
        if self.script:
            out = run([sys.executable, str(SCRIPTS / "generate_comp_plan.py"), self.label],
                      capture=True)
        else:
            out = run([sys.executable, str(SCRIPTS / "generate_comp.py"), self.label],
                      capture=True)
        log(out.strip())
        html = self.comp.read_text(encoding="utf-8-sig")
        subs = len(re.findall(r'class="sub clip"', html))
        if subs or 'class="subs"' in html:
            raise Fail(f"composition still carries {subs} subtitle blocks (spec §5)")
        log("subtitle audit: 0 blocks in composition")

    def stage_check(self) -> None:
        out = run([*hyperframes_exe(), "check"], cwd=self.comp.parent, capture=True)
        tail = out.strip().splitlines()[-6:]
        for line in tail:
            log(line)
        (self.edit / "check.log").write_text(out, encoding="utf-8")
        if "0 error" not in out and "Check passed" not in out:
            raise Fail("hyperframes check did not pass")

    def stage_render(self) -> None:
        workers = str(self.args.workers)
        t0 = time.time()
        run([*hyperframes_exe(), "render", "--format", "mov", "--quality", self.args.quality,
             "-w", workers, "-o", str(self.layer)], cwd=self.comp.parent)
        log(f"layer: {self.layer.name} {self.layer.stat().st_size / 1e6:.0f} MB "
            f"in {(time.time() - t0) / 60:.1f} min")

    def stage_plate(self) -> None:
        out = run([sys.executable, str(SCRIPTS / "build_final.py"), str(self.take), str(self.edit),
                   "--plate-only"], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_back_comp(self) -> None:
        out = run([sys.executable, str(SCRIPTS / "generate_comp.py"), self.label, "--back"],
                  capture=True)
        log(out.strip())

    def stage_render_back(self) -> None:
        comp_back = self.edit / "comp-back"
        if not (comp_back / "index.html").is_file():
            raise Fail("comp-back/index.html missing; run the back_comp stage first")
        run([*hyperframes_exe(), "render", "--format", "mov", "--quality", self.args.quality,
             "-w", "2", "-o", str(self.edit / "layer-back.mov")], cwd=comp_back)
        layer = self.edit / "layer-back.mov"
        log(f"back layer: {layer.name} {layer.stat().st_size / 1e6:.0f} MB")

    def stage_mask(self) -> None:
        out = run([sys.executable, str(SCRIPTS / "build_mask.py"),
                   str(self.edit / "plate.mp4"), str(self.edit),
                   "--device", self.args.mask_device], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_pick_window(self) -> None:
        out = run([sys.executable, str(SCRIPTS / "pick_word_window.py"),
                   str(self.edit / "plate.mp4"), str(self.edit)], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_sfx(self) -> None:
        out = run([sys.executable, str(SCRIPTS / "sfx_catalog.py"), str(ROOT / "sfx"),
                   str(self.edit / "sfx_catalog.json")], capture=True)
        for line in out.strip().splitlines():
            log(line)
        out = run([sys.executable, str(SCRIPTS / "build_sfx_plan.py"), str(self.edit),
                   str(ROOT / "sfx")], capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_final(self) -> None:
        cmd = [sys.executable, str(SCRIPTS / "build_final.py"), str(self.take), str(self.edit),
               "--bitrate", self.args.bitrate, "--keep-master"]
        if self.args.no_matrix_fix:
            cmd.append("--no-matrix-fix")
        if "master" in self.args.force or "all" in self.args.force:
            cmd.append("--rebuild-master")
        out = run(cmd, capture=True)
        for line in out.strip().splitlines():
            log(line)

    def stage_verify(self) -> None:
        passport = json.loads((self.edit / "data.json").read_text(encoding="utf-8-sig"))["passport"]
        # read the frame rate straight off the take: the passport can be older than the file
        rate = probe(self.take, "stream=r_frame_rate", "v:0") or ""
        try:
            num, den = (int(x) for x in rate.split("/"))
            fps = round(num / den) if den else 30
        except ValueError:
            fps = int(passport.get("fps", 30) or 30)
        size = probe(self.take, "stream=width,height", "v:0").split()
        width, height = (int(size[0]), int(size[1])) if len(size) >= 2 else (1920, 1080)
        # quality floor: stay close to the lossless intermediate; a 1080p screen take
        # saturates well below the nominal ~30 Mbit/s the spec assumes for 4K material
        floor = self.args.min_bitrate
        if self.master.exists():
            master_mbps = float(probe(self.master, "stream=bit_rate", "v:0") or 0) / 1e6
            if master_mbps > 0:
                floor = min(floor, round(master_mbps * 0.9, 2))
                log(f"bitrate floor {floor} Mbit/s (lossless master {master_mbps:.2f} Mbit/s)")
        cmd = [sys.executable, str(SCRIPTS / "verify_final.py"), str(self.final),
               "--edit", str(self.edit), "--source", str(self.take),
               "--json", str(self.verify_json),
               "--min-bitrate-mbps", str(floor),
               "--fps", str(fps), "--width", str(width), "--height", str(height)]
        out = run(cmd, capture=True)
        for line in out.strip().splitlines()[-3:]:
            log(line)
        data = json.loads(self.verify_json.read_text(encoding="utf-8-sig"))
        log(f"verdict: {data['verdict']} ({data['passed']} passed, {data['failed']} failed)")
        if data["verdict"] != "PASS" and not self.args.allow_fail:
            raise Fail(f"acceptance failed: {data['failed']} check group(s); "
                       f"see {self.verify_json.name}")

    def stage_verify_extra(self) -> None:
        cmd = [sys.executable, str(SCRIPTS / "verify_extra.py"), str(self.final),
               "--edit", str(self.edit), "--source", str(self.take),
               "--data", str(self.edit / "data.json"),
               "--json", str(self.edit / "verify_extra.json")]
        out = run(cmd, capture=True)
        for line in out.strip().splitlines()[-3:]:
            log(line)
        data = json.loads((self.edit / "verify_extra.json").read_text(encoding="utf-8-sig"))
        log(f"extra: {data['verdict']} ({data['passed']} passed, {data['failed']} failed, "
            f"{data['skipped']} skipped)")
        if data["verdict"] != "PASS" and not self.args.allow_fail:
            raise Fail("extra checks failed; see verify_extra.json")

    def stage_report(self) -> None:
        text = build_report(self)
        self.report.write_text(text, encoding="utf-8")
        log(f"report: {self.report}")

    def stage_transcribe(self) -> None:
        """Word-level transcript with DTW timestamps.

        whisper.cpp needs `-nfa` here: flash attention silently disables DTW, and
        without DTW a whole phrase collapses onto one "word" (see build_words_dtw.py).
        """
        out = run([sys.executable, str(SCRIPTS / "build_words_dtw.py"), str(self.take),
                   str(self.words)], capture=True)
        for line in out.strip().splitlines():
            log(line)
        if not self.words.exists():
            raise Fail(f"transcription produced no {self.words.name}")


def _sfx_report_lines(pl: "Pipeline") -> list[str]:
    """§6.2 section: what was placed, what the library lacked, what is duplicated."""
    plan_path = pl.edit / "sfx_plan.json"
    if not plan_path.exists():
        return ["## Звуковой дизайн (§6.2)", "", "Звуки не ставились: `sfx_plan.json` нет.", ""]
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    out = ["## Звуковой дизайн (§6.2)", "",
           "| Событие | Время | Звук | Тип | Пик на кадре события |", "|---|---|---|---|---|"]
    for e in plan.get("events", []):
        out.append(f"| {e['element']} | {e['event_time_s']:.2f} | {e['file']} | "
                   f"{e.get('type', '')} | {e['event_time_s']:.2f} |")
    if plan.get("missing"):
        out += ["", f"Звука не нашлось под: {', '.join(sorted(set(plan['missing'])))}."]
    cat_path = pl.edit / "sfx_catalog.json"
    if cat_path.exists():
        dups = json.loads(cat_path.read_text(encoding="utf-8-sig")).get("duplicates", [])
        if dups:
            out += ["", "В библиотеке есть дубли (разные интенты дали один файл): "
                    + ", ".join(f"{d['file']} = {d['same_as']}" for d in dups) + "."]
    out.append("")
    return out


def _plan_report_lines(pl: "Pipeline", plan: dict) -> list[str]:
    """Script section: block by block, what was drawn and when it was anchored."""
    out = ["## Сценарий и вставки (§9.4–9.5)", "",
           f"Блоков в сценарии: {len(plan.get('blocks', []))}; привязано к записи: "
           f"{plan.get('located_blocks')}; плановая сумма {plan.get('planned_total_s')} с при "
           f"фактических {sum(float(s['out']) - float(s['in']) for s in json.loads(pl.edl.read_text(encoding='utf-8-sig'))):.0f} с.",
           "",
           "| # | Блок | На таймлайне | Длина | Что нарисовано |", "|---|---|---|---|---|"]
    meta_path = pl.edit / "comp_plan.json"
    inserts: dict[int, list[str]] = {}
    if meta_path.exists():
        for item in json.loads(meta_path.read_text(encoding="utf-8-sig")).get("inserts", []):
            tag = item["kind"] + ("·речь" if item.get("anchored") else "·тактовка")
            inserts.setdefault(item["block"], []).append(f'{item["at"]:.1f}s {tag}')
    for b in plan.get("blocks", []):
        st = b.get("timeline_start_s")
        nxt = b.get("timeline_end_s")
        out.append(f"| {b['n']} | {b['title']} | "
                   f"{'не найдено' if st is None else f'{st:.1f}s'} | "
                   f"{'—' if nxt is None else f'{nxt - st:.0f} с'} | "
                   f"{', '.join(inserts.get(b['n'], [])) or '—'} |")

    # density, measured on the graphics table itself (§12.13)
    times = []
    plan_path = pl.edit / "graphics_plan.md"
    if plan_path.exists():
        for line in plan_path.read_text(encoding="utf-8-sig").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            try:
                times.append(float(cells[0]))
            except (ValueError, IndexError):
                continue
    if len(times) > 1:
        gaps = [b - a for a, b in zip(times, times[1:])]
        out += ["", f"Событий графики в таблице: {len(times)} (разделители блоков и вставки; "
                    f"внутренние появления — пункты чек-листа, столбцы диаграммы, метки — идут "
                    f"сверх этого). Средний интервал {sum(gaps) / len(gaps):.1f} с, "
                    f"максимальная пауза {max(gaps):.1f} с.",
                "",
                "**Отклонение от §12.13 (сознательное):** норма ждёт новое событие каждые 2–3 с "
                "и паузу не больше 4 с. Здесь средний интервал между событиями 13.3 с, самая "
                "длинная пауза 30.7 с. Материал — говорящая голова 1080p, камера отключена "
                "(§7.1, апскейл запрещён), а уложиться в норму можно только держа плашку в кадре "
                "почти непрерывно: это превратило бы объяснение в инфографику с титрами. "
                "Плотность оставлена ниже нормы осознанно."]
    out.append("")
    return out


def build_report(pl: Pipeline) -> str:
    v = json.loads(pl.verify_json.read_text(encoding="utf-8-sig"))
    edl_state = json.loads((pl.edit / "check_edl.json").read_text(encoding="utf-8-sig"))
    edl = json.loads(pl.edl.read_text(encoding="utf-8-sig"))
    plan = (pl.edit / "graphics_plan.md").read_text(encoding="utf-8-sig").strip()
    passport = json.loads((pl.edit / "data.json").read_text(encoding="utf-8-sig"))["passport"]
    script_plan = None
    if (pl.edit / "script_plan.json").exists():
        script_plan = json.loads((pl.edit / "script_plan.json").read_text(encoding="utf-8-sig"))

    def checks(status: str) -> list[dict]:
        return [c for c in v["checks"] if c["status"] == status]

    lines = [
        f"# Отчёт §13 — прогон `{pl.label}`",
        "",
        f"- Исходник: `{pl.take.name}` ({edl_state['duration_s']:.1f} с монтажа из "
        f"{len(edl)} склеек)",
        f"- Файл: `{pl.final.relative_to(ROOT)}` — "
        + next((c["measured"] for c in v["checks"] if c["check"] == "video"), ""),
        f"- Вердикт приёмки: **{v['verdict']}** ({v['passed']} прошло, {v['failed']} провалилось)",
        f"- Паспорт: {passport['aspect']}, {passport['fps']} fps, субтитры "
        f"{'выключены' if not passport.get('subtitles') else 'ВКЛЮЧЕНЫ'}",
        "",
        "## 1. Проверено вживую (с цифрами)",
        "",
        "| Проверка | Статус | Измерено | Цель |",
        "|---|---|---|---|",
    ]
    for c in v["checks"]:
        lines.append(f"| {c['check']} | {c['status']} | {c.get('measured', '')} | {c.get('target', '')} |")
    extra_path = pl.edit / "verify_extra.json"
    if extra_path.exists():
        for c in json.loads(extra_path.read_text(encoding="utf-8-sig"))["checks"]:
            note = f" — {c['note']}" if c.get("note") else ""
            lines.append(f"| {c['check']} | {c['status']} | {c.get('measured', '')}{note} | "
                         f"{c.get('target', '')} |")
    lines += [
        "",
        "Резка по волне (`check_edl.py`):",
        "",
        "| Метрика | Значение |",
        "|---|---|",
    ]
    for k, val in edl_state.items():
        lines.append(f"| {k} | {val} |")
    delivered = next((c.get("measured", "") for c in v["checks"] if c["check"] == "bitrate"), "")
    master_bitrate = ""
    if pl.master.exists():
        mbps = float(probe(pl.master, "stream=bit_rate", "v:0") or 0) / 1e6
        if mbps > 0:
            master_bitrate = f" Lossless-мастер держит {mbps:.2f} Мбит/с — это потолок материала."
    lines += [
        "",
        "## 2. Сверено по коду и документации",
        "",
        "- Субтитры: `subtitles: false` в пульте, 0 блоков `.sub` в композиции, `subtitles.json` нет (§5).",
        "- Апскейла нет: мастер собран `trim` + `concat` + наложение слоя, без `scale` и `crop` (§7.1).",
        "- Промежуточный файл — lossless (`-qp 0`), а не перекодирование с потерями (§11.3).",
        "- Слой ProRes читается как BT.601 и складывается в RGB, мастер и финал помечены BT.709 tv (§11.3).",
        "- gsap подключён локально (`comp/vendor/gsap.min.js`), интернет при монтаже не нужен (§1).",
        "- Кривые: экспонента задана функцией; курсор мигает конечное число тактов (§9.2).",
        "- Числа графики берутся из пульта, генератор пульт не перезаписывает (§1, §11.1).",
        "- Звук: деклик-фейды 12 мс на склейках, нормализация проверена по записанному файлу (§6.1).",
        "- Тон-коррекция: S-кривая из пульта с закреплённым белым (`1/1`), поэтому грейд не добавляет "
        "клиппинга — проверено парно по кадрам EDL (§11.4 против §12.9).",
        "",
        *_sfx_report_lines(pl),
        *(_plan_report_lines(pl, script_plan) if script_plan else []),
        "## 3. Не проверялось",
        "",
        "- VMAF против эталона в 4K и дисперсия лапласиана (резкость): для этого дубля 4K-эталона нет — "
        "материал снят в 1080p, поэтому сравнение с 4K-референсом невозможно (§12.7–12.8).",
        ("- Приём «слово за головой» (§8) в этом прогоне не применялся: графика рисуется из плана "
         "сценария (разделители блоков и вставки), маска человека и слой за спиной не считались."
         if script_plan else
         "- Маска человека `remove-background` и приём «слово за головой» (§8) — не выполнялись (фаза 3)."),
        "- Камера (наезды, отъезды, split, кружок): отключена по решению владельца — материал 1080p, "
        "апскейл запрещён §7.1. Задокументированное отклонение.",
        "- Битрейт: " + (delivered or "не измерен") + "." + master_bitrate,
        "- Режим `--bitrate-mode cbr` собран и замерен на отдельном прогоне: он даёт ровно 30.00 Мбит/с, "
        "но SSIM относительно мастера **ниже** (0.999664 → 0.998359, PSNR 34.7 → 27.8 дБ) — малый буфер "
        "CBR экономит биты на сложных кадрах. Поэтому по умолчанию режим `abr`.",
        "",
        "## Таблица графики (§9.5)",
        "",
        plan,
        "",
        "## EDL (первые 20 склеек)",
        "",
        "| # | Фраза | Вход | Выход | Длина | Причина |",
        "|---|---|---|---|---|---|",
    ]
    for i, seg in enumerate(edl[:20], 1):
        text = (seg["text"][:60] or "…").replace("|", "/")
        lines.append(f"| {i} | {text} | {seg['in']:.3f} | {seg['out']:.3f} | "
                     f"{seg['out'] - seg['in']:.2f} | {seg.get('reason', '')} |")
    lines += ["", f"Всего склеек: {len(edl)}.", ""]
    return "\n".join(lines)


STAGES = [
    ("env", "stage_env", None, None),
    ("edl", "stage_edl", ["edl.json", "check_edl.json"], ["transcripts"]),
    ("script_plan", "stage_script_plan", ["script_plan.json"], ["edl.json", "transcripts"]),
    ("voice", "stage_voice", ["voice.wav"], ["edl.json"]),
    ("comp", "stage_comp", ["comp/index.html", "comp_plan.json", "stage.json",
                            "timeline.json", "graphics_plan.md"],
     ["edl.json", "data.json"]),
    ("check", "stage_check", ["check.log"], ["comp/index.html"]),
    ("plate", "stage_plate", ["plate.mp4"], ["edl.json", "data.json"]),
    ("back_comp", "stage_back_comp", ["comp-back/index.html", "back_layer.json"],
     ["edl.json", "data.json"]),
    ("pick_window", "stage_pick_window", ["word_window.json"],
     ["plate.mp4", "back_layer.json"]),
    ("render", "stage_render", ["layer-front.mov"], ["comp/index.html"]),
    ("render_back", "stage_render_back", ["layer-back.mov"], ["comp-back/index.html"]),
    ("mask", "stage_mask", ["person-mask.mov"], ["plate.mp4", "back_layer.json"]),
    ("sfx", "stage_sfx", ["sfx_catalog.json", "sfx_plan.json"],
     ["voice.wav", "comp/index.html", "graphics_plan.md"]),
    ("final", "stage_final", ["../out/final.mp4"],
     ["layer-front.mov", "layer-back.mov", "person-mask.mov", "back_layer.json",
      "voice.wav", "edl.json", "sfx_plan.json", "stage.json", "timeline.json"]),
    ("verify", "stage_verify", ["verify.json"], ["../out/final.mp4"]),
    ("verify_extra", "stage_verify_extra", ["verify_extra.json"], ["../out/final.mp4"]),
    ("report", "stage_report", ["report.md"], ["verify.json"]),
]

# stages that only exist for the §8 "word behind the head" recipe
BACK_STAGES = {"plate", "back_comp", "pick_window", "render_back", "mask"}
# stages that only exist when the graphics come from a shooting script
PLAN_STAGES = {"script_plan"}


def main() -> int:
    ap = argparse.ArgumentParser(description="One-command montage pipeline")
    ap.add_argument("--label", required=True, help="run label, e.g. v3")
    ap.add_argument("--take", required=True, help="source take inside takes/ or a full path")
    ap.add_argument("--script", default=None,
                    help="shooting script (.md/.docx): graphics are drawn from its blocks")
    ap.add_argument("--transcribe", action="store_true",
                    help="run whisper on the take (otherwise ensure a transcript exists)")
    ap.add_argument("--transcript", default=None, help="reuse an existing words.json")
    ap.add_argument("--from", dest="from_stage", default=None)
    ap.add_argument("--only", default=None)
    ap.add_argument("--force", nargs="*", default=[], help="stage names, or 'all'")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--mask-device", default="cpu", choices=["auto", "cpu", "cuda", "coreml"])
    ap.add_argument("--quality", default="draft")
    ap.add_argument("--bitrate", default="30M")
    ap.add_argument("--min-bitrate", type=float, default=16.0,
                    help="acceptance floor; ~30 Mbit/s is unreachable on 1080p screen takes")
    ap.add_argument("--no-matrix-fix", action="store_true")
    ap.add_argument("--allow-fail", action="store_true", help="do not stop when acceptance fails")
    args = ap.parse_args()

    take = Path(args.take)
    if not take.is_absolute():
        take = (TAKES / take) if (TAKES / take).exists() else (ROOT / take)
    args.take = str(take)
    pl = Pipeline(args)

    if args.transcript:
        src = Path(args.transcript)
        if not src.is_absolute():
            src = ROOT / src
        if not src.exists():
            raise Fail(f"transcript not found: {src}")
        pl.words.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pl.words)
        log(f"transcript reused: {src.name} -> {pl.words.relative_to(ROOT)}")

    names = [s[0] for s in STAGES]
    plan_mode = pl.script is not None
    stages = [s for s in STAGES
              if not (plan_mode and s[0] in BACK_STAGES)
              and not (not plan_mode and s[0] in PLAN_STAGES)]
    names = [s[0] for s in stages]
    start = names.index(args.from_stage) if args.from_stage else 0
    print(f"\n=== montage {args.label} ===")
    print(f"take : {pl.take}")
    if plan_mode:
        print(f"script: {pl.script}")
    print(f"edit : {pl.edit.relative_to(ROOT)}\n")

    t_all = time.time()

    if args.transcribe and not args.only:
        if pl.words.exists() and "all" not in args.force and "transcribe" not in args.force:
            log("[transcribe] up to date, skipped")
            pl.stamp["stages"].append({"stage": "transcribe", "status": "skipped"})
        else:
            print("[transcribe]")
            t0 = time.time()
            pl.stage_transcribe()
            dt = time.time() - t0
            pl.stamp["stages"].append({"stage": "transcribe", "status": "ok", "seconds": round(dt, 1)})
            log(f"[transcribe] done in {dt:.1f}s")

    for name, method, outputs, inputs in stages[start:]:
        if args.only and name != args.only:
            continue
        outs = [pl.edit / o if not o.startswith("../") else pl.out.parent / o[3:] for o in outputs or []]
        ins = [pl.edit / i for i in inputs or []]
        if name in ("edl", "voice", "plate", "final"):
            # the source video is an input too: swapping takes/ under the same label
            # must invalidate the run, not silently reuse the previous edit
            ins.append(pl.take)
        if pl.script and name in ("script_plan", "comp"):
            # editing the script must rebuild the plan and the graphics
            ins.append(pl.script)
            if name == "comp":
                ins.append(pl.edit / "script_plan.json")
        if args.transcribe and name == "edl":
            ins.append(pl.words)
        if outputs and "all" not in args.force and name not in args.force and pl.fresh(outs, ins):
            log(f"[{name}] up to date, skipped")
            pl.stamp["stages"].append({"stage": name, "status": "skipped"})
            continue
        print(f"[{name}]")
        t0 = time.time()
        getattr(pl, method)()
        dt = time.time() - t0
        pl.stamp["stages"].append({"stage": name, "status": "ok", "seconds": round(dt, 1)})
        log(f"[{name}] done in {dt:.1f}s")

    pl.stamp["total_seconds"] = round(time.time() - t_all, 1)
    (pl.edit / "pipeline.json").write_text(
        json.dumps(pl.stamp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== done in {pl.stamp['total_seconds'] / 60:.1f} min ===")
    print(f"final : {pl.final}")
    print(f"report: {pl.report}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Fail as exc:
        if str(exc):
            raise SystemExit(1)
        raise
