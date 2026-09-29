import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

import markdown
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])


def _render_pipeline(source):
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
    )
    normalized = MarkdownViewer._dedent_fenced_blocks(source)
    normalized = MarkdownViewer._normalize_list_indent(normalized)
    normalized = MarkdownViewer._inject_anchors(normalized)
    normalized = MarkdownViewer._preserve_indent(normalized)
    body = md.convert(normalized)
    body = MarkdownViewer._apply_indent(body, 14.0)
    body = MarkdownViewer._style_blockquotes(body)
    doc = QTextDocument()
    doc.setHtml(MarkdownViewer.wrap_html(body))
    return doc


class TestAnchorPipeline(unittest.TestCase):
    def test_lines_monotonic_and_fenced_table_skipped(self):
        source = (
            "# 标题\n\n"
            "段落一\n\n"
            "- 列表项\n\n"
            "```\ncode\n```\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
            "> 引用\n"
        )
        doc = _render_pipeline(source)
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, sorted(lines))
        self.assertTrue(all(y <= ys[i + 1] for i, y in enumerate(ys[:-1])))

    def test_md_prefixed_heading_does_not_crash(self):
        source = "## MD-Setup\n\n正文\n"
        doc = _render_pipeline(source)
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, sorted(lines))


if __name__ == "__main__":
    unittest.main()
