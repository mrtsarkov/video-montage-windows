#!/usr/bin/env python3
"""Font glyph + width measurement for montage §3.5 / §10."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageFont


SAMPLE = "АБВабвЁё0123456789—«»…№%$₽→✓✕"


def check_glyphs(font_path: Path, size: int = 32) -> tuple[list[str], list[str]]:
    f = ImageFont.truetype(str(font_path), size)
    notdef = f.getmask("￿")
    nd_box = notdef.getbbox()
    missing = []
    present = []
    for ch in SAMPLE:
        if f.getmask(ch).getbbox() == nd_box:
            missing.append(ch)
        else:
            present.append(ch)
    return missing, present


def measure_width(font_path: Path, text: str, size: int) -> float:
    f = ImageFont.truetype(str(font_path), size)
    return float(f.getlength(text))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: measure_text.py <font.ttf> [text] [size]", file=sys.stderr)
        return 1
    font = Path(sys.argv[1])
    text = sys.argv[2] if len(sys.argv) > 2 else "HyperFrames — тест заголовка"
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 72
    missing, _ = check_glyphs(font)
    width = measure_width(font, text, size)
    print(f"Font: {font}")
    print(f"Missing glyphs: {''.join(missing) or '(none)'}")
    print(f'Width "{text}" @ {size}px: {width:.1f}px (+2.5% accent reserve: {width * 1.025:.1f}px)')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
