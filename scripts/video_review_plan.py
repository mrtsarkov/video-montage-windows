#!/usr/bin/env python3
"""План выпуска видеообзора (dashboard plan.json) -> сцены, безопасные зоны, отчёт «план vs факт».

Формат нового видео: OBS пишет одно видео (сцены FACE/CIRCLE/CHARTS переключаются вживую),
монтаж НЕ перекомпоновывает камеру: только трим по EDL, звук, графика/вставки, sfx, финал.

Этот скрипт — мост между планом выпуска (генерирует дашборд) и монтажным пайплайном:
  1) сверяет блоки плана с блоками script_plan.json (порядок, длительности, границы);
  2) считает, где реально оказались блоки в таймлайне, и отчёт «план vs факт»;
  3) ищет возможные пересъёмки (повторные вхождения фраз в расшифровке);
  4) пишет карту сцен (кто в кадре / что на экране) и правила безопасных зон для графики.

Выходы (в edit/):
  video_plan.json    — нормализованный план: сцены, TV-layout'ы, mode, planned/actual, статусы
  plan_vs_fact.json  — машинный отчёт расхождений + найденные пересъёмки
  plan_report.md     — человеческий отчёт для агента монтажа

Использование:
    py -3 scripts/video_review_plan.py --plan script/<label>-plan.json --edit runs/<label>/edit \
        [--script script/<label>.md] [--words runs/<label>/edit/transcripts/<take>-words.json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STOPWORDS = {
    "и", "в", "во", "на", "с", "со", "по", "к", "ко", "о", "об", "от", "до", "за", "из",
    "для", "что", "как", "это", "не", "ни", "но", "а", "или", "ли", "же", "бы", "был",
    "была", "были", "есть", "у", "при", "про", "через", "после", "до", "так", "там",
    "тут", "вот", "мы", "вы", "он", "она", "они", "я", "ты", "его", "её", "их",
}

SAFE_ZONES = {
    "FACE": {
        "note": "Ведущий полностью в кадре: графика только в боковых колонках, центр/лицо не трогаем.",
        "zones": [
            {"name": "left_outer", "x_pct": 3, "w_pct": 24, "y_pct": 12, "h_pct": 70},
            {"name": "right_outer", "x_pct": 73, "w_pct": 24, "y_pct": 12, "h_pct": 70},
        ],
    },
    "CIRCLE": {
        "note": "Ведущий в кружке поверх графики: карточки в углах, которых не касается кружок; центр не занимать.",
        "zones": [
            {"name": "top_left", "x_pct": 3, "w_pct": 28, "y_pct": 6, "h_pct": 30},
            {"name": "top_right", "x_pct": 69, "w_pct": 28, "y_pct": 6, "h_pct": 30},
            {"name": "bottom_left", "x_pct": 3, "w_pct": 28, "y_pct": 64, "h_pct": 30},
        ],
    },
    "CHARTS": {
        "note": "Только графики: ведущего нет — можно шире, но не закрывать верхнюю панель TradingView и правую ось цен.",
        "zones": [
            {"name": "left_wide", "x_pct": 2, "w_pct": 34, "y_pct": 10, "h_pct": 78},
            {"name": "bottom_band", "x_pct": 10, "w_pct": 60, "y_pct": 76, "h_pct": 18},
            {"name": "top_right", "x_pct": 66, "w_pct": 26, "y_pct": 8, "h_pct": 30},
        ],
    },
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def norm_word(word: str) -> str:
    return re.sub(r"[^\w\-]", "", str(word or "").lower().replace("ё", "е"))


def significant(text: str, limit: int = 6) -> list[str]:
    words = [norm_word(w) for w in re.split(r"\s+", str(text or ""))]
    words = [w for w in words if len(w) >= 3 and w not in STOPWORDS]
    return words[:limit]


def find_occurrences(words: list[dict], needle: list[str]) -> list[float]:
    """Все вхождения последовательности значимых слов в расшифровке (для поиска пересъёмок)."""
    if not needle or not words:
        return []
    seq = [norm_word(w.get("word") or w.get("w")) for w in words]
    out: list[float] = []
    n = len(needle)
    for i in range(0, len(seq) - n + 1):
        if seq[i:i + n] == needle:
            item = words[i]
            t = item.get("start", item.get("t", 0)) or 0
            out.append(round(float(t), 2))
    return out


def block_planned_offsets(plan: dict) -> list[float]:
    offsets, t = [], 0.0
    for b in plan.get("blocks", []):
        offsets.append(round(t, 2))
        t += float(b.get("duration_sec") or b.get("duration_s") or 0)
    return offsets


def main() -> int:
    ap = argparse.ArgumentParser(description="video plan -> scene map + plan vs fact")
    ap.add_argument("--plan", required=True, help="план выпуска (plan.json из дашборда)")
    ap.add_argument("--edit", required=True, help="каталог runs/<label>/edit")
    ap.add_argument("--script", default="", help="script.md (для справки)")
    ap.add_argument("--words", default="", help="words.json расшифровки (для поиска пересъёмок)")
    ap.add_argument("--json", action="store_true", help="напечатать итоговый JSON")
    args = ap.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = ROOT / plan_path
    edit = Path(args.edit)
    if not edit.is_absolute():
        edit = ROOT / edit
    plan = read_json(plan_path)

    script_plan_path = edit / "script_plan.json"
    if not script_plan_path.exists():
        print(f"[video_plan] нет {script_plan_path} — сначала стадия script_plan")
        return 1
    script_plan = read_json(script_plan_path)

    plan_blocks = plan.get("blocks") or []
    sp_blocks = sorted(script_plan.get("blocks") or [], key=lambda b: b.get("n") or 0)
    warnings: list[str] = []
    if len(plan_blocks) != len(sp_blocks):
        warnings.append(
            f"Количество блоков не совпало: план {len(plan_blocks)}, script_plan {len(sp_blocks)}. "
            "Сверка по порядку до минимального количества."
        )

    words: list[dict] = []
    if args.words:
        wp = Path(args.words)
        if not wp.is_absolute():
            wp = ROOT / wp
        if wp.exists():
            raw = read_json(wp)
            words = raw.get("words") if isinstance(raw, dict) and "words" in raw else raw
            if isinstance(words, dict):
                words = [words[k] for k in sorted(words, key=lambda x: int(x)) if isinstance(words[k], dict)]
            words = [w for w in words if isinstance(w, dict)]
    if not words:
        warnings.append("Расшифровка не передана — поиск пересъёмок по фрагментам не выполнялся.")

    offsets = block_planned_offsets(plan)
    total_planned = round(sum(float(b.get("duration_sec") or 0) for b in plan_blocks), 2)
    rows = []
    scene_ranges = []
    retakes_all = []

    for i, pb in enumerate(plan_blocks):
        sb = sp_blocks[i] if i < len(sp_blocks) else None
        planned_s = float(pb.get("duration_sec") or 0)
        planned_start = offsets[i]
        actual_start = sb.get("timeline_start_s") if sb else None
        actual_s = sb.get("actual_s") if sb else None
        located = bool(sb and sb.get("timeline_first_word_s") is not None)
        shift = None
        if sb and actual_start is not None:
            shift = round(float(actual_start) - planned_start, 2)
        match = float(sb.get("match_score") or 0) if sb else 0.0
        need = significant((pb.get("read") or {}).get("text") or (pb.get("talking_points") or [""])[0])
        occurrences = find_occurrences(words, need) if words else []
        retake = len(occurrences) > 1
        if retake:
            retakes_all.append({"block": pb.get("index", i + 1), "title": pb.get("title"), "times_s": occurrences})

        scene = pb.get("scene") or "FACE"
        row = {
            "n": pb.get("index", i + 1),
            "title": pb.get("title"),
            "scene": scene,
            "tv_layout": pb.get("tv_layout"),
            "mode": pb.get("mode"),
            "planned_s": planned_s,
            "planned_start_s": round(planned_start, 2),
            "actual_start_s": actual_start,
            "actual_s": actual_s,
            "shift_s": shift,
            "match_score": match,
            "located": located,
            "possible_retake": retake,
            "retake_starts_s": occurrences,
            "read": bool(pb.get("read")),
            "talking_points": len(pb.get("talking_points") or []),
            "chart_cues": pb.get("chart_cues") or [],
            "rationale": pb.get("rationale") or "",
            "sources": pb.get("sources") or [],
        }
        rows.append(row)

        if sb and sb.get("timeline_start_s") is not None:
            scene_ranges.append({
                "n": row["n"], "scene": scene,
                "from_s": sb.get("timeline_start_s"),
                "to_s": sb.get("timeline_end_s"),
                "tv_layout": pb.get("tv_layout"),
            })
        if not located:
            warnings.append(f"Блок {row['n']} «{row['title']}» не найден в расшифровке — проверьте пересъёмку/текст.")
        if actual_s is not None and planned_s:
            delta = float(actual_s) - planned_s
            if abs(delta) > max(15.0, planned_s * 0.3):
                warnings.append(
                    f"Блок {row['n']}: фактическая длина {float(actual_s):.0f} с против плана {planned_s:.0f} с "
                    f"({delta:+.0f} с) — при монтаже резать по смыслу."
                )
        if match and match < 5:
            warnings.append(f"Блок {row['n']}: низкое совпадение с текстом сценария (match {match:.1f}).")
        if retake:
            warnings.append(f"Блок {row['n']}: возможно несколько дублей (фраза встречается {len(occurrences)} раза).")

    total_actual_speech = round(sum(float(r["actual_s"] or 0) for r in rows), 2)
    shift_stats = [r["shift_s"] for r in rows if r["shift_s"] is not None]
    by_scene: dict[str, float] = {}
    for r in rows:
        by_scene[r["scene"]] = round(by_scene.get(r["scene"], 0) + float(r["actual_s"] or r["planned_s"]), 2)

    video_plan = {
        "meta": {
            "label": (plan.get("meta") or {}).get("label"),
            "title": (plan.get("meta") or {}).get("title"),
            "format": (plan.get("meta") or {}).get("format"),
            "date": (plan.get("meta") or {}).get("date"),
            "duration_min": (plan.get("meta") or {}).get("duration_min"),
            "thesis": (plan.get("meta") or {}).get("thesis"),
            "tv_layouts": (plan.get("meta") or {}).get("tv_layouts"),
            "assembled": True,
            "graphics_mode": "scene_safe_zones",
        },
        "blocks": rows,
        "scene_ranges": scene_ranges,
        "scene_time_s": by_scene,
        "safe_zones": SAFE_ZONES,
        "warnings": warnings,
        "script": str(Path(args.script)) if args.script else None,
        "source_plan": str(plan_path),
    }
    plan_vs_fact = {
        "label": video_plan["meta"]["label"],
        "planned_total_s": total_planned,
        "timeline_total_s": script_plan.get("timeline_total_s"),
        "actual_speech_s": total_actual_speech,
        "located_blocks": sum(1 for r in rows if r["located"]),
        "blocks_total": len(rows),
        "boundary_shift_avg_s": round(sum(shift_stats) / len(shift_stats), 2) if shift_stats else None,
        "boundary_shift_max_s": max(shift_stats) if shift_stats else None,
        "scene_time_s": by_scene,
        "possible_retakes": retakes_all,
        "warnings": warnings,
        "blocks": rows,
    }

    edit.mkdir(parents=True, exist_ok=True)
    (edit / "video_plan.json").write_text(json.dumps(video_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (edit / "plan_vs_fact.json").write_text(json.dumps(plan_vs_fact, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------- человеческий отчёт ----------------
    lines = [
        "# План выпуска и «план vs факт» (video-review)",
        "",
        f"- Выпуск: **{video_plan['meta'].get('title') or video_plan['meta'].get('label') or '—'}**",
        f"- Формат: `{video_plan['meta'].get('format')}` · дата: {video_plan['meta'].get('date')} · "
        f"план {video_plan['meta'].get('duration_min')} мин",
        f"- Режим: **assembled** (OBS-композит: сцены FACE/CIRCLE/CHARTS уже сведены, камеру не перекомпоновываем)",
        f"- Тезис: {video_plan['meta'].get('thesis') or '—'}",
        "",
        "## Блоки: план vs факт",
        "",
        "| # | Блок | Сцена | TV | План | Факт | Сдвиг | Match | Дубли |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        fact = f"{r['actual_s']:.1f} с" if r["actual_s"] is not None else ("не найден" if not r["located"] else "—")
        shift = f"{r['shift_s']:+.1f} с" if r["shift_s"] is not None else "—"
        lines.append(
            f"| {r['n']} | {str(r['title'])[:52]} | {r['scene']} | {r['tv_layout'] or '—'} | "
            f"{r['planned_s']:.0f} с | {fact} | {shift} | {r['match_score']:.1f} | "
            f"{len(r['retake_starts_s']) if r['possible_retake'] else 0} |"
        )
    lines += [
        "",
        f"Итого: план {total_planned:.0f} с, таймлайн {script_plan.get('timeline_total_s') or '—'} с, "
        f"речь {total_actual_speech:.0f} с; найдено блоков {plan_vs_fact['located_blocks']}/{plan_vs_fact['blocks_total']}.",
        "",
        "## Сцены (OBS) и безопасные зоны графики",
        "",
        "| Сцена | Время, с | Где можно рисовать |",
        "|---|---|---|",
    ]
    for scene, seconds in by_scene.items():
        zones = SAFE_ZONES.get(scene, {})
        note = zones.get("note", "")
        names = ", ".join(z["name"] for z in zones.get("zones", []))
        lines.append(f"| {scene} | {seconds:.0f} | {names} — {note} |")
    lines += [
        "",
        "## Пересъёмки/дубли",
        "",
    ]
    if retakes_all:
        for rt in retakes_all:
            lines.append(f"- Блок {rt['block']} «{rt['title']}»: фраза встречается в расшифровке в "
                         f"{rt['times_s']} с — вероятны дубли, в монтаж брать последний удачный.")
    else:
        lines.append("- Дублей по фрагментам не найдено (или расшифровка не передана).")
    lines += ["", "## Предупреждения", ""]
    lines += [f"- {w}" for w in warnings] if warnings else ["- нет"]
    lines += [
        "",
        "## Как это использовать при монтаже",
        "",
        "1. Блоки с `scene=CHARTS` — ведущего в кадре нет: вставки можно ставить шире (левая колонка/нижняя полоса), "
        "но не закрывать верхнюю панель TradingView и правую ось цен.",
        "2. `scene=FACE` — только боковые колонки, лицо/центр не трогать. `scene=CIRCLE` — углы, не центр.",
        "3. Границы блоков — из EDL/script_plan; сдвиг >15 с означает, что на записи блок длиннее плана "
        "(импровизация) — при монтаже подрезать по смыслу, а не по плановой длительности.",
        "4. `possible_retake` — проверить указанные таймкоды, в монтаж брать последний удачный дубль.",
        "",
    ]
    if args.script:
        lines.append(f"Сценарий: `{args.script}`")
    (edit / "plan_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[video_plan] blocks: {len(rows)}, located: {plan_vs_fact['located_blocks']}/{len(rows)}, "
          f"planned {total_planned:.0f}s, actual speech {total_actual_speech:.0f}s, warnings: {len(warnings)}")
    for w in warnings[:8]:
        print(f"[video_plan] warning: {w}")
    print(f"[video_plan] -> {edit / 'video_plan.json'}")
    print(f"[video_plan] -> {edit / 'plan_vs_fact.json'}")
    print(f"[video_plan] -> {edit / 'plan_report.md'}")
    if args.json:
        print(json.dumps(plan_vs_fact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
