from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
NAVY, RED, OFFWHITE = HexColor("#102A43"), HexColor("#E50012"), HexColor("#FBFAF8")
GRAY, LIGHTBLUE, BLACK = HexColor("#777777"), HexColor("#9FB3C8"), HexColor("#181818")


def register_fonts() -> None:
    font_dir = ROOT / "assets/fonts"
    for name, filename in [("Pretendard", "Pretendard-Regular.ttf"), ("Pretendard-SemiBold", "Pretendard-SemiBold.ttf"), ("Pretendard-Bold", "Pretendard-Bold.ttf"), ("Pretendard-ExtraBold", "Pretendard-ExtraBold.ttf")]:
        pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))


def paragraph(canvas: Canvas, text: str, x: float, y_top: float, width: float, height: float, style: ParagraphStyle) -> None:
    p = Paragraph(text.replace("&", "&amp;"), style)
    _, h = p.wrap(width, height)
    p.drawOn(canvas, x, y_top - h)


def build_pdf(output: Path, articles: list, report_date: date, cfg: dict) -> None:
    register_fonts()
    output.parent.mkdir(parents=True, exist_ok=True)
    cards_per_page = cfg.get("cards_per_page", 5)
    section_order = list(cfg["sections"])
    pages: list[tuple[str, list]] = []
    for section in section_order:
        rows = [a for a in articles if a.section == section]
        if not rows:
            continue
        for start in range(0, len(rows), cards_per_page):
            pages.append((section, rows[start:start + cards_per_page]))

    w, h = A4
    c = Canvas(str(output), pagesize=A4, pageCompression=1)
    c.setTitle(f"{cfg['briefing_title']} {report_date:%Y.%m.%d}")
    total = len(pages)
    for page_no, (section, rows) in enumerate(pages, 1):
        c.setFillColor(NAVY); c.rect(0, 0, w, h, stroke=0, fill=1)
        c.setFillColor(LIGHTBLUE); c.setFont("Pretendard-SemiBold", 11); c.drawString(34, h - 47, "N E W S   C L I P P I N G")
        c.setFillColor(white); c.setFont("Pretendard-ExtraBold", 21); c.drawString(34, h - 75, cfg["briefing_title"])
        c.setFont("Pretendard-Bold", 15); c.drawRightString(w - 34, h - 58, f"{report_date:%Y.%m.%d}")
        c.setFillColor(LIGHTBLUE); c.setFont("Pretendard-SemiBold", 9); c.drawRightString(w - 34, h - 76, f"{page_no} / {total}")
        c.setFillColor(RED); c.roundRect(34, h - 104, 55, 18, 9, stroke=0, fill=1)
        c.setFillColor(white); c.setFont("Pretendard-Bold", 9); c.drawCentredString(61.5, h - 98, section)

        top, bottom, gap = h - 118, 62, 11
        card_h = (top - bottom - gap * (cards_per_page - 1)) / cards_per_page
        title_style = ParagraphStyle("title", fontName="Pretendard-Bold", fontSize=12.5, leading=15.5, textColor=BLACK, maxLines=2)
        body_style = ParagraphStyle("body", fontName="Pretendard", fontSize=9.2, leading=13.2, textColor=GRAY, maxLines=2)
        for idx, a in enumerate(rows):
            y = top - (idx + 1) * card_h - idx * gap
            c.setFillColor(OFFWHITE); c.roundRect(34, y, w - 68, card_h, 9, stroke=0, fill=1)
            c.setFillColor(RED); c.roundRect(50, y + card_h - 30, 43, 15, 7.5, stroke=0, fill=1)
            c.setFillColor(white); c.setFont("Pretendard-Bold", 7.7); c.drawCentredString(71.5, y + card_h - 25, section)
            c.setFillColor(HexColor("#9A9A9A")); c.setFont("Pretendard-SemiBold", 8.2); c.drawString(100, y + card_h - 25, a.publisher)
            c.setFillColor(NAVY); c.setFont("Pretendard-Bold", 8.2); c.drawRightString(w - 51, y + card_h - 25, "원문 보기  →")
            c.linkURL(a.url, (w - 116, y + card_h - 33, w - 48, y + card_h - 12), relative=0, thickness=0)
            paragraph(c, a.title, 50, y + card_h - 39, w - 100, 34, title_style)
            paragraph(c, a.summary, 50, y + card_h - 75, w - 100, 32, body_style)

        c.setFillColor(LIGHTBLUE); c.setFont("Pretendard", 8); c.drawString(34, 34, "본 자료는 임직원 내부 공유용입니다.")
        logo = ROOT / "assets/logo.png"
        if logo.exists():
            c.drawImage(ImageReader(str(logo)), w - 184, 24, width=150, height=21.4, mask="auto", preserveAspectRatio=True)
        c.showPage()
    c.save()

