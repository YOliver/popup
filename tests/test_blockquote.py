import unittest

from md_viewer import MarkdownViewer


class TestStyleBlockquotes(unittest.TestCase):
    def test_single_blockquote(self):
        html = "<blockquote>\n<p>text</p>\n</blockquote>"
        out = MarkdownViewer._style_blockquotes(html)
        self.assertIn('<table class="md-quote"><tr><td>', out)
        self.assertIn("</td></tr></table>", out)
        self.assertNotIn("<blockquote>", out)
        self.assertNotIn("</blockquote>", out)

    def test_nested_blockquote(self):
        html = "<blockquote><p>outer</p><blockquote><p>inner</p></blockquote></blockquote>"
        out = MarkdownViewer._style_blockquotes(html)
        self.assertEqual(out.count('<table class="md-quote">'), 2)
        self.assertEqual(out.count("</td></tr></table>"), 2)

    def test_no_blockquote_unchanged(self):
        html = "<p>plain</p><ul><li>item</li></ul>"
        self.assertEqual(MarkdownViewer._style_blockquotes(html), html)


if __name__ == "__main__":
    unittest.main()
