#!/usr/bin/env python3
"""Place sfx on visual events (spec §6.2).

Rules taken from the spec:
  * a sound goes on a visual event: a panel/window appearing, a mark, a list item,
    the big word, a check mark, a counter;
  * the sound's PEAK lands on the event frame, so the clip starts at
    event_time - peak_at_s (measured, not guessed);
  * do not invent sounds that the library does not have.

Usage:
  build_sfx_plan.py <edit_dir> <sfx_dir> [--json out.json] [--target-peak-dbfs -14]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# element -> sfx type; sub-events come from the composition itself
ELEMENT_TYPE = {
    "hook": "pop",
    "word": "impact",
    "calendar": "pop",
    "checklist": "pop",
    "chat": "pop",
    "counter": "click",
    "scale": "pop",
    "stepper": "pop",
    # script-plan elements (generate_comp_plan.py)
    "title": "impact",
    "divider": "pop",
    "quotes": "pop",
    "chart": "pop",
    "table": "pop",
    "timeline": "pop",
    "funnel": "pop",
    "diagram": "pop",
    "steps": "pop",
    "chips": "pop",
    "stat": "click",
    "miners": "click",
    "premium": "pop",
    "quote": "pop",
    "scenario": "pop",
    "outro": "impact",
}


def parse_plan(edit: Path) -> list[tuple[float, str]]:
    plan = edit / "graphics_plan.md"
    rows: list[tuple[float, str]] = []
    if not plan.is_file():
        return rows
    for line in plan.read_text(encoding="utf-8-sig").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("время", "") or set(cells[0]) <= {"-"}:
            continue
        try:
            rows.append((float(cells[0]), cells[2]))
        except ValueError:
            continue
    return rows


def parse_sub_events(edit: Path) -> list[tuple[float, str]]:
    """List items / stepper steps / counter times, read from the composition."""
    html = edit / "comp" / "index.html"
    if not html.is_file():
        return []
    text = html.read_text(encoding="utf-8-sig")
    subs: list[tuple[float, str]] = []
    for m in re.finditer(r"tl\.fromTo\('#(cnt|i\d|s\d)'[^;]*?,\s*([0-9.]+)\);", text):
        sel, t = m.group(1), float(m.group(2))
        subs.append((t, "click" if sel != "cnt" else "click"))
    for m in re.finditer(r"tl\.call\([^;]*?'#(i\d|s\d)'[^;]*?,\s*null,\s*([0-9.]+)\);", text):
        subs.append((float(m.group(2)), "click"))
    # de-duplicate timings that came from both patterns
    seen, out = set(), []
    for t, kind in sorted(subs):
        key = round(t, 3)
        if key in seen:
            continue
        seen.add(key)
        out.append((t, kind))
    return out


def pick(catalog: dict, kind: str) -> dict | None:
    for entry in catalog.get("files", []):
        if entry.get("type") == kind:
            return entry
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("edit_dir")
    ap.add_argument("sfx_dir")
    ap.add_argument("--json", default=None)
    ap.add_argument("--target-peak-dbfs", type=float, default=-14.0,
                    help="peak level each placed sound should reach (spec: 0.2-0.4 linear)")
    args = ap.parse_args()

    edit = Path(args.edit_dir)
    sfx_dir = Path(args.sfx_dir)
    catalog_path = edit / "sfx_catalog.json"
    if not catalog_path.is_file():
        print(f"no catalog at {catalog_path}; run sfx_catalog.py first")
        return 1
    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))

    events: list[dict] = []
    missing: list[str] = []
    for t, element in parse_plan(edit):
        # "divider7", "e3_1" and friends: the base name carries the intent
        kind = ELEMENT_TYPE.get(element) or ELEMENT_TYPE.get(re.sub(r"[\d_]+$", "", element))
        if not kind:
            continue
        entry = pick(catalog, kind)
        if not entry:
            missing.append(f"{element} ({kind})")
            continue
        events.append(_event(t, element, entry, args.target_peak_dbfs, "появление элемента"))
    for t, kind in parse_sub_events(edit):
        entry = pick(catalog, kind)
        if not entry:
            missing.append(f"sub-event ({kind})")
            continue
        events.append(_event(t, "item", entry, args.target_peak_dbfs, "пункт / шаг / счётчик"))

    events.sort(key=lambda e: e["event_time_s"])
    plan = {
        "source": str(sfx_dir),
        "target_peak_dbfs": args.target_peak_dbfs,
        "missing": missing,
        "events": events,
    }
    out = Path(args.json) if args.json else edit / "sfx_plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"SFX plan: {len(events)} event(s) -> {out}")
    for e in events:
        print(f"  {e['event_time_s']:7.2f}s  {e['element']:9s} {e['file']:18s} "
              f"start {e['start_s']:7.2f}s  gain {e['gain_db']:+6.2f} dB  peak {e['peak_dbfs']:6.2f} dBFS")
    if missing:
        print(f"  ! no matching sound for: {', '.join(sorted(set(missing)))}")
    return 0


def _event(t: float, element: str, entry: dict, target_peak: float, note: str) -> dict:
    peak_at = float(entry.get("peak_at_s", 0.0))
    return {
        "event_time_s": round(t, 3),
        "element": element,
        "file": entry["file"],
        "type": entry.get("type", ""),
        "note": note,
        "peak_at_s": peak_at,
        "start_s": round(max(0.0, t - peak_at), 3),
        "gain_db": round(target_peak - float(entry.get("peak_dbfs", -14.0)), 2),
        "peak_dbfs": float(entry.get("peak_dbfs", 0.0)),
    }


if __name__ == "__main__":
    raise SystemExit(main())
