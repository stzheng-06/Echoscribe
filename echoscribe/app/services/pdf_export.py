"""Formal, paginated PDF export for meeting summaries."""
from __future__ import annotations

import html
import os
import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QPageLayout,
    QPageSize,
    QPainter,
    QPalette,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrinter

from app.models import MeetingSummary
from app.ui.fonts import register_application_fonts


def export_summary_pdf(
    destination: Path,
    summary: MeetingSummary,
    *,
    record_title: str,
    source_file: str,
) -> int:
    """Export one summary version as an atomic A4 PDF and return its page count."""
    destination = Path(destination)
    register_application_fonts()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp.pdf")
    temporary.unlink(missing_ok=True)

    printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setResolution(96)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageMargins(
        QMarginsF(18, 17, 18, 16), QPageLayout.Unit.Millimeter
    )
    printer.setFullPage(True)
    printer.setOutputFileName(str(temporary))
    printer.setDocName(record_title or summary.title or "Meeting Summary")
    printer.setCreator("EchoScribe")

    page_rect = printer.pageLayout().paintRectPixels(printer.resolution())
    footer_height = 30.0
    content_size = QSizeF(page_rect.width(), page_rect.height() - footer_height)
    document = _build_document(summary, record_title, source_file)
    document.setPageSize(content_size)
    page_count = max(1, document.pageCount())

    painter = QPainter()
    try:
        if not painter.begin(printer):
            raise OSError(f"Could not create PDF: {destination}")
        for page_index in range(page_count):
            if page_index and not printer.newPage():
                raise OSError(f"Could not add PDF page: {destination}")
            _draw_document_page(
                painter, document, page_rect, content_size, page_index
            )
            _draw_footer(painter, page_rect, page_index + 1, page_count)
        painter.end()
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise OSError(f"PDF output was not created: {destination}")
        os.replace(temporary, destination)
    except Exception:
        if painter.isActive():
            painter.end()
        temporary.unlink(missing_ok=True)
        raise
    return page_count


def _build_document(
    summary: MeetingSummary, record_title: str, source_file: str
) -> QTextDocument:
    language = summary.language or "en"
    labels = _PDF_LABELS.get(language, _PDF_LABELS["en"])
    body_markdown = summary.markdown.strip()
    if not body_markdown:
        body_markdown = summary.overview.strip()
    elif summary.title and body_markdown.startswith("# "):
        _heading, _separator, remainder = body_markdown.partition("\n")
        body_markdown = remainder.lstrip()
    body_document = QTextDocument()
    body_document.setMarkdown(body_markdown)
    body_html = _body_fragment(body_document.toHtml())

    title = record_title or summary.title or labels["untitled"]
    subtitle = summary.title if summary.title and summary.title != title else ""
    metadata = (
        (labels["source"], source_file or labels["unknown"]),
        (labels["language"], language or labels["unknown"]),
        (labels["model"], summary.model or labels["unknown"]),
        (labels["length"], summary.length or labels["unknown"]),
        (labels["generated"], summary.generated_at or labels["unknown"]),
    )
    meta_html = "".join(
        f'<div class="meta"><span>{html.escape(label)}:</span>&nbsp;'
        f'{html.escape(value)}</div>'
        for label, value in metadata
    )
    subtitle_html = (
        f'<div class="subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
    )
    document = QTextDocument()
    document.setDefaultFont(QFont("Segoe UI", 11))
    document.setDocumentMargin(0)
    document.setDefaultStyleSheet(_DOCUMENT_CSS)
    document.setHtml(
        '<div class="document-header">'
        f'<div class="brand">EchoScribe · {html.escape(labels["minutes"])}</div>'
        f'<h1 class="record-title">{html.escape(title)}</h1>{subtitle_html}'
        f'<div class="meta-grid">{meta_html}</div></div>'
        f'<div class="summary-body" style="color:#35322d;">{body_html}</div>'
    )
    return document


def _body_fragment(value: str) -> str:
    match = re.search(r"<body[^>]*>(.*)</body>", value, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else value


def _draw_document_page(
    painter: QPainter,
    document: QTextDocument,
    page_rect,
    content_size: QSizeF,
    page_index: int,
) -> None:
    painter.save()
    # QAbstractTextDocumentLayout otherwise inherits the application's palette.
    # On Windows dark mode that can produce white text in an otherwise white PDF.
    painter.resetTransform()
    painter.setClipping(False)
    painter.fillRect(
        QRectF(0, 0, painter.viewport().width(), painter.viewport().height()),
        QColor("#ffffff"),
    )
    painter.translate(page_rect.left(), page_rect.top())
    painter.setClipRect(QRectF(0, 0, content_size.width(), content_size.height()))
    painter.translate(0, -page_index * content_size.height())
    context = QAbstractTextDocumentLayout.PaintContext()
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        context.palette.setColor(role, QColor("#35322d"))
    context.palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    context.palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    context.clip = QRectF(
        0,
        page_index * content_size.height(),
        content_size.width(),
        content_size.height(),
    )
    document.documentLayout().draw(painter, context)
    painter.restore()


def _draw_footer(
    painter: QPainter, page_rect, page_number: int, page_count: int
) -> None:
    painter.save()
    y = page_rect.bottom() - 18
    painter.setPen(QColor("#b1aaa0"))
    painter.drawLine(page_rect.left(), y - 8, page_rect.right(), y - 8)
    painter.setFont(QFont("Segoe UI", 8))
    painter.setPen(QColor("#756f67"))
    painter.drawText(
        QRectF(page_rect.left(), y, page_rect.width(), 16),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        "EchoScribe",
    )
    painter.drawText(
        QRectF(page_rect.left(), y, page_rect.width(), 16),
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        f"{page_number} / {page_count}",
    )
    painter.restore()


_DOCUMENT_CSS = """
body { color: #35322d; font-family: 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
       font-size: 11pt; line-height: 1.52; }
.summary-body, .summary-body p, .summary-body li,
.summary-body ul, .summary-body ol { color: #35322d; }
.document-header { margin-bottom: 26px; }
.brand { color: #827a70; font-size: 8.5pt; font-weight: 600;
         letter-spacing: 1.2px; text-transform: uppercase; margin-bottom: 9px; }
h1.record-title { color: #26231f; font-size: 25pt; font-weight: 650;
                  line-height: 1.12; margin: 0 0 6px 0; }
.subtitle { color: #625c54; font-size: 12pt; margin: 0 0 16px 0; }
.meta-grid { background: #f5f2ed; border-top: 1px solid #ded8cf;
             border-bottom: 1px solid #ded8cf; padding: 10px 12px; }
.meta { color: #4d4841; font-size: 8.8pt; margin: 3px 0; }
.meta span { color: #81796f; font-weight: 600; margin-right: 8px; }
.summary-body h1 { color: #2c2924; font-size: 18pt; margin: 20px 0 10px 0; }
.summary-body h2 { color: #2c2924; font-size: 13.5pt; font-weight: 650;
                   margin: 20px 0 7px 0; page-break-after: avoid; }
.summary-body h3 { color: #4d4841; font-size: 11.5pt; margin: 15px 0 6px 0;
                   page-break-after: avoid; }
.summary-body p { margin: 0 0 10px 0; }
.summary-body ul, .summary-body ol { margin: 5px 0 12px 0; padding-left: 22px; }
.summary-body li { margin: 0 0 7px 0; }
"""


_PDF_LABELS = {
    "en": {"minutes": "Meeting minutes", "source": "Source", "language": "Language",
           "model": "Model", "length": "Length", "generated": "Generated",
           "unknown": "Not recorded", "untitled": "Meeting summary"},
    "zh-CN": {"minutes": "会议纪要", "source": "源文件", "language": "语言",
              "model": "模型", "length": "长度", "generated": "生成时间",
              "unknown": "未记录", "untitled": "会议纪要"},
    "es": {"minutes": "Acta de reunión", "source": "Archivo fuente", "language": "Idioma",
           "model": "Modelo", "length": "Longitud", "generated": "Generado",
           "unknown": "No registrado", "untitled": "Resumen de la reunión"},
}
