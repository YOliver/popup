import unittest

from md_viewer import MarkdownViewer


class TestInjectAnchors(unittest.TestCase):
    def test_heading(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("# 标题\n"),
            '# <a id="popup-anchor-0"></a>标题\n',
        )

    def test_list_item(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("- 项\n"),
            '- <a id="popup-anchor-0"></a>项\n',
        )

    def test_quote(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("> 引用\n"),
            '> <a id="popup-anchor-0"></a>引用\n',
        )

    def test_plain_paragraph(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("正文\n"),
            '<a id="popup-anchor-0"></a>正文\n',
        )

    def test_paragraph_with_fullwidth_indent(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("\u3000\u3000正文\n"),
            '\u3000\u3000<a id="popup-anchor-0"></a>正文\n',
        )

    def test_nested_list(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("- 父\n    - 子\n"),
            '- <a id="popup-anchor-0"></a>父\n    - <a id="popup-anchor-1"></a>子\n',
        )

    def test_nested_quote(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("> 引用\n> > 嵌套\n"),
            '> <a id="popup-anchor-0"></a>引用\n> > <a id="popup-anchor-1"></a>嵌套\n',
        )

    def test_fence_not_injected(self):
        content = "```\ncode\n```\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_table_not_injected(self):
        content = "| a | b |\n|---|---|\n| 1 | 2 |\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_indented_code_not_injected(self):
        content = "    code line\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_html_block_not_injected(self):
        content = "<div>x</div>\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_horizontal_rule_not_injected(self):
        content = "---\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_blank_line_unchanged_and_line_number(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("第一行\n\n第三行\n"),
            '<a id="popup-anchor-0"></a>第一行\n\n<a id="popup-anchor-2"></a>第三行\n',
        )

    def test_setext_underline_not_injected(self):
        content = "标题\n===\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_reference_link_definition_not_injected(self):
        content = "[x]: http://a\n"
        self.assertEqual(MarkdownViewer._inject_anchors(content), content)

    def test_blank_quote_lines_not_anchored(self):
        src = "> 文字\n>\n>　\n> 更多"
        out = MarkdownViewer._inject_anchors(src)
        lines = out.split("\n")
        self.assertIn("popup-anchor-0", lines[0])
        self.assertEqual(lines[1], ">")       # 空引用行不注锚，原样保留
        self.assertEqual(lines[2], ">　")     # 仅全角空格的引用行也不注锚
        self.assertIn("popup-anchor-3", lines[3])


if __name__ == "__main__":
    unittest.main()
