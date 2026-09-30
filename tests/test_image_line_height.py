import unittest

import markdown

from md_viewer import MarkdownViewer


class TestFixImageLineHeight(unittest.TestCase):
    def test_single_image_gets_line_height(self):
        html = '<p><img alt="" src="a.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn(
            '<p style="line-height:100%"><img alt="" src="a.png" /></p>', out
        )

    def test_image_with_anchor_keeps_anchor(self):
        html = '<p><a id="popup-anchor-89"></a><img alt="图1-1" src="fig1-1.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn(
            '<p style="line-height:100%"><a id="popup-anchor-89"></a>'
            '<img alt="图1-1" src="fig1-1.png" /></p>',
            out,
        )

    def test_mixed_text_image_unchanged(self):
        html = '<p>文字 <img alt="" src="a.png" /> 文字</p>'
        self.assertEqual(MarkdownViewer._fix_image_line_height(html), html)

    def test_multiple_images_same_line(self):
        html = '<p><img alt="" src="a.png" /> <img alt="" src="b.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn('<p style="line-height:100%">', out)

    def test_multiple_images_soft_break_with_br(self):
        html = '<p><img alt="" src="a.png" /><br />\n<img alt="" src="b.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn('<p style="line-height:100%">', out)
        self.assertIn('<br />', out)

    def test_markdown_pipeline_produces_line_height(self):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        body = md.convert("![图1-1 测试](fig1-1.png)")
        out = MarkdownViewer._fix_image_line_height(body)
        self.assertIn(
            '<p style="line-height:100%"><img alt="图1-1 测试" src="fig1-1.png" /></p>',
            out,
        )

    def test_indented_image_paragraph_merges_style(self):
        html = '<p style="text-indent:28.0px"><a id="popup-anchor-0"></a><img alt="" src="a.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn('<p style="text-indent:28.0px;line-height:100%">', out)
        self.assertIn('<a id="popup-anchor-0"></a>', out)

    def test_anchor_only_without_image_unchanged(self):
        html = '<p><a id="popup-anchor-1"></a></p>'
        self.assertEqual(MarkdownViewer._fix_image_line_height(html), html)


if __name__ == "__main__":
    unittest.main()
