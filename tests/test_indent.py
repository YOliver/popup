import unittest

from md_viewer import MarkdownViewer


class TestPreserveIndent(unittest.TestCase):
    def test_two_fullwidth_spaces_become_marker(self):
        out = MarkdownViewer._preserve_indent("\u3000\u3000这是正文。")
        self.assertEqual(out, '<i data-indent="2"></i>这是正文。')

    def test_single_fullwidth_space(self):
        out = MarkdownViewer._preserve_indent("\u3000正文")
        self.assertEqual(out, '<i data-indent="1"></i>正文')

    def test_no_indent_unchanged(self):
        self.assertEqual(MarkdownViewer._preserve_indent("正文"), "正文")

    def test_halfwidth_space_not_touched(self):
        self.assertEqual(MarkdownViewer._preserve_indent("  正文"), "  正文")

    def test_code_fence_content_not_replaced(self):
        content = "```\n\u3000\u3000code line\n```"
        self.assertEqual(MarkdownViewer._preserve_indent(content), content)


class TestApplyIndent(unittest.TestCase):
    def test_marker_becomes_text_indent(self):
        html = '<p><i data-indent="2"></i>正文</p>'
        out = MarkdownViewer._apply_indent(html, 14.0)
        self.assertEqual(out, '<p style="text-indent:28.0px">正文</p>')

    def test_plain_paragraph_unchanged(self):
        html = '<p>正文</p>'
        self.assertEqual(MarkdownViewer._apply_indent(html, 14.0), html)

    def test_three_fullwidth_spaces(self):
        html = '<p><i data-indent="3"></i>正文</p>'
        out = MarkdownViewer._apply_indent(html, 14.0)
        self.assertEqual(out, '<p style="text-indent:42.0px">正文</p>')


if __name__ == "__main__":
    unittest.main()
