from __future__ import annotations

import html
import io
import re
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout


class PDFExporter:
    def __init__(self, css_path: str | Path = "config/templates/base.css") -> None:
        self.css_path = Path(css_path)

    def export_pdf(self, title: str, markdown_content: str, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        html_string = self.convert_markdown_to_html(title, markdown_content)

        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                from weasyprint import HTML

                HTML(string=html_string, base_url=str(Path.cwd())).write_pdf(output)
            return output
        except Exception:
            try:
                self._export_reportlab_pdf(title, markdown_content, output)
                return output
            except Exception as exc:
                fallback = output.with_suffix(".html")
                fallback.write_text(html_string, encoding="utf-8")
                raise RuntimeError(
                    f"PDF export failed. A reviewable HTML fallback was written to {fallback}. Original error: {exc}"
                ) from exc

    def _export_reportlab_pdf(self, title: str, markdown_content: str, output: Path) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        styles["Title"].fontSize = 22
        styles["Title"].leading = 27
        styles["Title"].textColor = colors.HexColor("#0f172a")
        styles["Heading1"].fontSize = 15
        styles["Heading1"].leading = 19
        styles["Heading1"].spaceBefore = 12
        styles["Heading1"].spaceAfter = 7
        styles["Heading1"].textColor = colors.HexColor("#0f172a")
        styles["Heading2"].fontSize = 13
        styles["Heading2"].leading = 16
        styles["Heading2"].spaceBefore = 10
        styles["Heading2"].spaceAfter = 6
        styles["Heading2"].textColor = colors.HexColor("#0f172a")
        styles["Heading3"].fontSize = 11
        styles["Heading3"].leading = 14
        styles["Heading3"].spaceBefore = 7
        styles["Heading3"].spaceAfter = 4
        styles["Heading3"].textColor = colors.HexColor("#0f172a")
        styles["BodyText"].fontSize = 9.2
        styles["BodyText"].leading = 12.2
        styles["BodyText"].spaceAfter = 4
        styles["BodyText"].wordWrap = "CJK"

        table_cell_style = ParagraphStyle(
            "TableCell",
            parent=styles["BodyText"],
            fontSize=7.2,
            leading=9,
            wordWrap="CJK",
            splitLongWords=1,
        )
        table_header_style = ParagraphStyle(
            "TableHeader",
            parent=table_cell_style,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#0f172a"),
        )
        doc = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=title,
        )

        display_title, body_markdown = self._split_leading_title(markdown_content, title)
        story = [
            Paragraph(display_title, styles["Title"]),
            Spacer(1, 4 * mm),
        ]
        pending_bullets: list[str] = []
        pending_table: list[list[str]] = []

        def flush_bullets() -> None:
            if pending_bullets:
                story.append(
                    ListFlowable(
                        [ListItem(Paragraph(item, styles["BodyText"])) for item in pending_bullets],
                        bulletType="bullet",
                    )
                )
                pending_bullets.clear()

        def flush_table() -> None:
            if pending_table:
                normalized_table = self._normalize_table(pending_table)
                col_widths = self._column_widths(normalized_table[0], len(normalized_table[0]), doc.width)
                table_data = []
                for row_index, row in enumerate(normalized_table):
                    style = table_header_style if row_index == 0 else table_cell_style
                    table_data.append([Paragraph(self._escape_pdf_text(cell), style) for cell in row])
                table = Table(table_data, colWidths=col_widths, repeatRows=1, splitByRow=1, hAlign="LEFT")
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 4 * mm))
                pending_table.clear()

        for raw_line in body_markdown.splitlines():
            line = raw_line.strip()
            if not line:
                flush_bullets()
                flush_table()
                continue
            image_match = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            if image_match:
                flush_bullets()
                flush_table()
                image_alt = image_match.group(1).strip()
                image_path = Path(image_match.group(2).strip().strip("<>"))
                if not image_path.is_absolute():
                    image_path = Path.cwd() / image_path
                if image_path.exists():
                    image_height = 32 * mm if self._is_compact_product_visual(image_alt, image_path) else 58 * mm
                    story.append(Image(str(image_path), width=doc.width, height=image_height, kind="proportional"))
                    story.append(Spacer(1, 2 * mm))
                else:
                    story.append(Paragraph(f"Image evidence missing: {self._escape_pdf_text(image_match.group(2))}", styles["BodyText"]))
                continue
            if self._is_markdown_table_line(line):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if all(cell and set(cell) <= {"-", ":"} for cell in cells):
                    continue
                pending_table.append(cells)
                continue
            flush_table()
            if line.startswith("# "):
                flush_bullets()
                story.append(Paragraph(line[2:], styles["Heading1"]))
            elif line.startswith("## "):
                flush_bullets()
                story.append(Paragraph(line[3:], styles["Heading2"]))
            elif line.startswith("### "):
                flush_bullets()
                story.append(Paragraph(line[4:], styles["Heading3"]))
            elif line.startswith("#### "):
                flush_bullets()
                story.append(Paragraph(line[5:], styles["Heading3"]))
            elif line.startswith("- "):
                pending_bullets.append(line[2:])
            else:
                flush_bullets()
                story.append(Paragraph(line, styles["BodyText"]))
        flush_bullets()
        flush_table()
        doc.build(story, onFirstPage=self._draw_reportlab_frame, onLaterPages=self._draw_reportlab_frame)

    @staticmethod
    def _draw_reportlab_frame(canvas, doc) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm

        canvas.saveState()
        width, height = A4
        canvas.setFillColor(colors.HexColor("#0f172a"))
        canvas.rect(0, height - 10 * mm, width, 10 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#0d9488"))
        canvas.rect(0, height - 11.5 * mm, width, 1.5 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(width / 2, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    @staticmethod
    def _is_markdown_table_line(line: str) -> bool:
        return line.startswith("|") and line.endswith("|") and line.count("|") >= 2

    @staticmethod
    def _escape_pdf_text(text: str) -> str:
        escaped = html.escape(str(text).strip())
        return escaped.replace("\n", "<br/>")

    @staticmethod
    def _normalize_table(rows: list[list[str]]) -> list[list[str]]:
        column_count = max(len(row) for row in rows)
        return [row + [""] * (column_count - len(row)) for row in rows]

    @staticmethod
    def _column_widths(header: list[str], column_count: int, available_width: float) -> list[float]:
        header_text = " ".join(header).lower()
        if column_count == 2:
            weights = [0.28, 0.72]
        elif column_count == 3 and "step" in header_text and "acceptance" in header_text:
            weights = [0.09, 0.51, 0.40]
        elif column_count == 3 and "why it matters" in header_text:
            weights = [0.15, 0.22, 0.63]
        elif column_count == 3 and "operator notes" in header_text:
            weights = [0.17, 0.41, 0.42]
        elif column_count == 3 and "manual interpretation" in header_text:
            weights = [0.16, 0.25, 0.59]
        elif column_count == 3:
            weights = [0.22, 0.28, 0.50]
        elif column_count == 4:
            weights = [0.18, 0.24, 0.29, 0.29]
        elif column_count == 5:
            weights = [0.15, 0.20, 0.20, 0.22, 0.23]
        else:
            weights = [1 / column_count] * column_count
        total = sum(weights)
        return [(weight / total) * available_width for weight in weights]

    def export_html(self, title: str, markdown_content: str, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.convert_markdown_to_html(title, markdown_content), encoding="utf-8")
        return output

    def convert_markdown_to_html(self, title: str, markdown_content: str) -> str:
        display_title, body_markdown = self._split_leading_title(markdown_content, title)
        body = self._markdown_to_semantic_html(body_markdown)
        css = self.css_path.read_text(encoding="utf-8") if self.css_path.exists() else ""
        safe_title = html.escape(display_title)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{safe_title}</title>
  <style>{css}</style>
</head>
<body>
  <header class="top-bar">
    <h1>{safe_title}</h1>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""

    @staticmethod
    def _split_leading_title(markdown_content: str, fallback_title: str) -> tuple[str, str]:
        lines = markdown_content.splitlines()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("# "):
                title = stripped[2:].strip() or fallback_title
                remaining = lines[:index] + lines[index + 1 :]
                return title, "\n".join(remaining).lstrip()
            break
        return fallback_title, markdown_content

    @staticmethod
    def _is_compact_product_visual(alt_text: str, image_path: Path) -> bool:
        text = f"{alt_text} {image_path.stem}".lower()
        return any(
            token in text
            for token in (
                "feature overview",
                "product callout",
                "architecture",
                "ecosystem",
                "advanced_ev",
                "controller_callouts",
                "stacked_architecture",
                "charging_ecosystem",
            )
        )

    def _markdown_to_semantic_html(self, markdown_content: str) -> str:
        try:
            import markdown

            safe_markdown = html.escape(markdown_content, quote=False)
            return markdown.markdown(safe_markdown, extensions=["tables", "fenced_code"])
        except Exception:
            return self._minimal_markdown_to_html(markdown_content)

    @staticmethod
    def _minimal_markdown_to_html(markdown_content: str) -> str:
        blocks: list[str] = []
        list_items: list[str] = []

        def flush_list() -> None:
            if list_items:
                blocks.append("<ul>" + "".join(list_items) + "</ul>")
                list_items.clear()

        for raw_line in markdown_content.splitlines():
            line = raw_line.strip()
            if not line:
                flush_list()
                continue
            if line.startswith("# "):
                flush_list()
                blocks.append(f"<h2>{html.escape(line[2:])}</h2>")
            elif (image_match := re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line)):
                flush_list()
                alt = html.escape(image_match.group(1))
                src = html.escape(image_match.group(2).strip().strip("<>"))
                blocks.append(f'<img src="{src}" alt="{alt}">')
            elif line.startswith("## "):
                flush_list()
                blocks.append(f"<h2>{html.escape(line[3:])}</h2>")
            elif line.startswith("### "):
                flush_list()
                blocks.append(f"<h3>{html.escape(line[4:])}</h3>")
            elif line.startswith("- "):
                list_items.append(f"<li>{html.escape(line[2:])}</li>")
            else:
                flush_list()
                blocks.append(f"<p>{html.escape(line)}</p>")
        flush_list()
        return "\n".join(blocks)
