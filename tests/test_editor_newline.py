import unittest

from md_viewer import MarkdownViewer


class TestDetectNewline(unittest.TestCase):
    def test_crlf_detected(self):
        self.assertEqual(MarkdownViewer._detect_newline("a\r\nb\r\n"), "\r\n")

    def test_lf_default(self):
        self.assertEqual(MarkdownViewer._detect_newline("a\nb\n"), "\n")

    def test_empty_defaults_to_lf(self):
        self.assertEqual(MarkdownViewer._detect_newline(""), "\n")

    def test_mixed_with_crlf_detected_as_crlf(self):
        self.assertEqual(MarkdownViewer._detect_newline("a\r\nb\nc"), "\r\n")


class TestApplyNewline(unittest.TestCase):
    def test_crlf_applied(self):
        self.assertEqual(
            MarkdownViewer._apply_newline("a\nb\nc", "\r\n"), "a\r\nb\r\nc"
        )

    def test_lf_unchanged(self):
        self.assertEqual(MarkdownViewer._apply_newline("a\nb\nc", "\n"), "a\nb\nc")

    def test_empty_text(self):
        self.assertEqual(MarkdownViewer._apply_newline("", "\r\n"), "")


if __name__ == "__main__":
    unittest.main()
