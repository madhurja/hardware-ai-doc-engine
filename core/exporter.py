from __future__ import annotations

import html
import io
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
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            str(output),
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=20 * mm,
            bottomMargin=18 * mm,
            title=title,
        )

        story = [Paragraph(title, styles["Title"]), Paragraph("Automated Engineering Delivery", styles["Normal"]), Spacer(1, 8 * mm)]
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
                table = Table(pending_table, repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 4 * mm))
                pending_table.clear()

        for raw_line in markdown_content.splitlines():
            line = raw_line.strip()
            if not line:
                flush_bullets()
                flush_table()
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

    def export_html(self, title: str, markdown_content: str, output_path: str | Path) -> Path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.convert_markdown_to_html(title, markdown_content), encoding="utf-8")
        return output

    def convert_markdown_to_html(self, title: str, markdown_content: str) -> str:
        body = self._markdown_to_semantic_html(markdown_content)
        css = self.css_path.read_text(encoding="utf-8") if self.css_path.exists() else ""
        safe_title = html.escape(title)
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{safe_title}</title>
  <style>{css}</style>
</head>
<body>
  <header class="top-bar">
    <div class="eyebrow">Automated Engineering Delivery</div>
    <h1>{safe_title}</h1>
  </header>
  <main>
    {body}
  </main>
</body>
</html>
"""

    def _markdown_to_semantic_html(self, markdown_content: str) -> str:
        try:
            import markdown

            return markdown.markdown(markdown_content, extensions=["tables", "fenced_code"])
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
