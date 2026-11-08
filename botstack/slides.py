"""Render a BotStack deck to a real .pptx the student can open in PowerPoint, Keynote or Google Slides."""

from __future__ import annotations

import io
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

INK = RGBColor(0x1B, 0x1F, 0x3B)
ACCENT = RGBColor(0xFF, 0x6B, 0x4A)
PAPER = RGBColor(0xFF, 0xF8, 0xEE)


def _background(slide, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _text(slide, text: str, left, top, width, height, size: int, color: RGBColor, bold=False):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    run = frame.paragraphs[0].add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return frame


def deck_to_pptx(deck: dict[str, Any]) -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]

    cover = prs.slides.add_slide(blank)
    _background(cover, INK)
    _text(cover, deck["title"], Inches(0.9), Inches(2.4), Inches(11.5), Inches(1.6), 54, PAPER, bold=True)
    _text(cover, deck.get("subtitle", ""), Inches(0.9), Inches(4.1), Inches(11.5), Inches(0.8), 24, ACCENT)

    for i, s in enumerate(deck["slides"], start=1):
        slide = prs.slides.add_slide(blank)
        _background(slide, PAPER)
        _text(slide, f"{i:02d}", Inches(0.9), Inches(0.5), Inches(2), Inches(0.5), 16, ACCENT, bold=True)
        _text(slide, s.get("heading", ""), Inches(0.9), Inches(0.9), Inches(11.5), Inches(1.2), 38, INK, bold=True)
        frame = _text(slide, "", Inches(0.9), Inches(2.3), Inches(11.5), Inches(4.6), 24, INK)
        for j, bullet in enumerate(s.get("bullets", [])):
            para = frame.paragraphs[0] if j == 0 else frame.add_paragraph()
            run = para.add_run()
            run.text = f"•  {bullet}"
            run.font.size = Pt(24)
            run.font.color.rgb = INK
            para.space_after = Pt(14)
        slide.notes_slide.notes_text_frame.text = s.get("speaker_notes", "")

    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()
