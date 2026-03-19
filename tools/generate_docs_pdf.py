from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (  # type: ignore
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _try_register_windows_fonts() -> tuple[str, str, str]:
    """Регистрирует шрифты с поддержкой кириллицы.

    Возвращает (family_regular, family_bold, family_mono).

    На Windows обычно доступны Arial/Arial Bold.
    """

    fonts_dir = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts"
    candidates = [
        (fonts_dir / "arial.ttf", fonts_dir / "arialbd.ttf", "Arial"),
        (fonts_dir / "calibri.ttf", fonts_dir / "calibrib.ttf", "Calibri"),
    ]

    # Моноширинный шрифт для inline-кода
    mono_candidates = [
        (fonts_dir / "consola.ttf", "Consolas"),
        (fonts_dir / "cour.ttf", "CourierNew"),
    ]

    mono_font_name: str | None = None
    for mono_path, mono_family in mono_candidates:
        if mono_path.exists():
            mono_font_name = f"{mono_family}-Regular"
            pdfmetrics.registerFont(TTFont(mono_font_name, str(mono_path)))
            break

    for regular_path, bold_path, family in candidates:
        if regular_path.exists() and bold_path.exists():
            pdfmetrics.registerFont(TTFont(f"{family}-Regular", str(regular_path)))
            pdfmetrics.registerFont(TTFont(f"{family}-Bold", str(bold_path)))
            # Если моно не нашли — используем встроенный Courier
            return f"{family}-Regular", f"{family}-Bold", (mono_font_name or "Courier")

    # Фолбэк: пробуем DejaVuSans, если вдруг установлен
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "DejaVuSans-Bold.ttf"))
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSansMono", "DejaVuSansMono.ttf"))
            mono = "DejaVuSansMono"
        except Exception:
            mono = "Courier"
        return "DejaVuSans", "DejaVuSans-Bold", mono
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "Не удалось найти шрифт с поддержкой кириллицы. "
            "Установите Arial/Calibri (Windows) или DejaVuSans (Linux) и повторите."
        ) from e


@dataclass
class Block:
    kind: str
    text: str


def _parse_markdown_simple(md: str) -> List[Block]:
    """Минимальный парсер Markdown для нужд документации.

    Поддерживает:
    - Заголовки #, ##, ###
    - Маркированные списки ("- ")
    - Нумерованные списки ("1)" или "1.") как обычный текст
    - Код-блоки ```
    - Горизонтальные линии ---

    Это намеренно простой парсер (без полной спецификации Markdown).
    """

    lines = md.replace("\r\n", "\n").split("\n")
    blocks: List[Block] = []

    in_code = False
    code_lines: List[str] = []

    def flush_paragraph(par_lines: List[str]) -> None:
        text = "\n".join(par_lines).strip()
        if text:
            blocks.append(Block("p", text))

    paragraph_lines: List[str] = []

    for raw in lines:
        line = raw.rstrip("\n")

        if line.strip().startswith("```"):
            if not in_code:
                flush_paragraph(paragraph_lines)
                paragraph_lines = []
                in_code = True
                code_lines = []
            else:
                in_code = False
                blocks.append(Block("code", "\n".join(code_lines).rstrip()))
            continue

        if in_code:
            code_lines.append(line)
            continue

        if line.strip() == "---":
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            blocks.append(Block("hr", ""))
            continue

        if line.startswith("### "):
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            blocks.append(Block("h3", line[4:].strip()))
            continue

        if line.startswith("## "):
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            blocks.append(Block("h2", line[3:].strip()))
            continue

        if line.startswith("# "):
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            blocks.append(Block("h1", line[2:].strip()))
            continue

        if line.strip().startswith("- "):
            # Копим список как отдельный блок для более аккуратного вывода
            flush_paragraph(paragraph_lines)
            paragraph_lines = []

            items: List[str] = []
            items.append(line.strip()[2:].strip())

            # соберём последующие пункты списка
            # (делаем «ручной» lookahead, поэтому обработаем через итератор ниже)
            blocks.append(Block("li", "\n".join(items)))
            continue

        if line.strip() == "":
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            continue

        paragraph_lines.append(line)

    flush_paragraph(paragraph_lines)

    # Сольём последовательные li-блоки в один ul
    merged: List[Block] = []
    ul_items: List[str] = []
    for b in blocks:
        if b.kind == "li":
            ul_items.append(b.text)
            continue
        if ul_items:
            merged.append(Block("ul", "\n".join(ul_items)))
            ul_items = []
        merged.append(b)
    if ul_items:
        merged.append(Block("ul", "\n".join(ul_items)))

    return merged


def build_pdf(input_md: Path, output_pdf: Path) -> None:
    regular_font, bold_font, mono_font = _try_register_windows_fonts()

    styles = getSampleStyleSheet()

    base = ParagraphStyle(
        "Base",
        parent=styles["Normal"],
        fontName=regular_font,
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )

    h1 = ParagraphStyle(
        "H1",
        parent=base,
        fontName=bold_font,
        fontSize=18,
        leading=22,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "H2",
        parent=base,
        fontName=bold_font,
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=8,
    )

    h3 = ParagraphStyle(
        "H3",
        parent=base,
        fontName=bold_font,
        fontSize=12,
        leading=16,
        spaceBefore=8,
        spaceAfter=6,
    )

    code_style = ParagraphStyle(
        "Code",
        parent=base,
        fontName=mono_font,
        fontSize=10,
        leading=13,
        backColor=colors.whitesmoke,
        borderPadding=6,
        leftIndent=6,
        rightIndent=6,
        spaceBefore=6,
        spaceAfter=8,
    )

    ul_style = ParagraphStyle(
        "UL",
        parent=base,
        leftIndent=14,
        bulletIndent=6,
        spaceBefore=2,
        spaceAfter=2,
    )

    md_text = input_md.read_text(encoding="utf-8")
    blocks = _parse_markdown_simple(md_text)

    story = []

    # Верхняя «шапка» (аккуратно отделяем от основного текста)
    story.append(Spacer(1, 2 * mm))

    for b in blocks:
        if b.kind == "h1":
            story.append(Paragraph(_escape(b.text), h1))
        elif b.kind == "h2":
            story.append(Paragraph(_escape(b.text), h2))
        elif b.kind == "h3":
            story.append(Paragraph(_escape(b.text), h3))
        elif b.kind == "p":
            story.append(Paragraph(_inline_format(b.text, mono_font=mono_font), base))
        elif b.kind == "code":
            # Preformatted сохраняет переносы строк
            story.append(Preformatted(b.text, code_style))
        elif b.kind == "hr":
            story.append(_hr_table())
            story.append(Spacer(1, 3 * mm))
        elif b.kind == "ul":
            for item in [x.strip() for x in b.text.split("\n") if x.strip()]:
                story.append(Paragraph(f"• {_inline_format(item, mono_font=mono_font)}", ul_style))
            story.append(Spacer(1, 2 * mm))

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=input_md.stem,
        author="1xBet TJ Bot",
        subject="Документация и инструкция",
        creator="tools/generate_docs_pdf.py",
    )

    doc.build(story)


def _hr_table() -> Table:
    t = Table([[""]], colWidths=[170 * mm])
    t.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, -1), 1, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inline_format(text: str, mono_font: str) -> str:
    """Форматирует inline Markdown для Paragraph.

    Поддерживается:
    - **жирный** -> <b>...</b>
    - `код` -> <font face="...">...</font>
    - переносы строк -> <br/>

    Остальные символы экранируются.
    """

    segments: list[tuple[str, str]] = []
    i = 0
    buf: list[str] = []
    mode: str = "plain"  # plain | bold | code

    def flush() -> None:
        nonlocal buf
        if buf:
            segments.append((mode, "".join(buf)))
            buf = []

    while i < len(text):
        ch = text[i]

        # Inline code: `...`
        if ch == "`":
            flush()
            mode = "plain" if mode == "code" else "code"
            i += 1
            continue

        # Bold: **...** (не внутри code)
        if mode != "code" and text.startswith("**", i):
            flush()
            mode = "plain" if mode == "bold" else "bold"
            i += 2
            continue

        buf.append(ch)
        i += 1

    flush()

    out: list[str] = []
    for seg_mode, seg_text in segments:
        if seg_text == "":
            continue
        escaped = _escape(seg_text)
        if seg_mode == "bold":
            out.append(f"<b>{escaped}</b>")
        elif seg_mode == "code":
            out.append(f"<font face=\"{mono_font}\">{escaped}</font>")
        else:
            out.append(escaped)

    return "".join(out).replace("\n", "<br/>")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate PDF from project documentation Markdown")
    parser.add_argument(
        "--input",
        default=str(Path("docs") / "Документация_и_инструкция.md"),
        help="Path to input .md file",
    )
    parser.add_argument(
        "--output",
        default=str(Path("docs") / "1xBetTJ_Документация_и_инструкция.pdf"),
        help="Path to output .pdf file",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    input_md = Path(args.input)
    output_pdf = Path(args.output)

    if not input_md.exists():
        raise FileNotFoundError(f"Input markdown not found: {input_md}")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    build_pdf(input_md=input_md, output_pdf=output_pdf)

    print(f"OK: generated {output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
