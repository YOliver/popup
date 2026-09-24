import os
import unittest

from md_viewer import MarkdownViewer


class TestBuildBaseUrl(unittest.TestCase):
    def test_normal_subdir(self):
        path = os.path.join("C:\\", "foo", "bar", "readme.md")
        url = MarkdownViewer._build_base_url(path)
        self.assertEqual(url.toLocalFile(), "C:/foo/bar/")

    def test_root_dir(self):
        url = MarkdownViewer._build_base_url("C:\\readme.md")
        self.assertEqual(url.toLocalFile(), "C:/")

    def test_path_with_spaces(self):
        path = os.path.join("C:\\", "my dir", "readme.md")
        url = MarkdownViewer._build_base_url(path)
        self.assertEqual(url.toLocalFile(), "C:/my dir/")

    def test_path_with_chinese(self):
        path = os.path.join("C:\\", "中文目录", "readme.md")
        url = MarkdownViewer._build_base_url(path)
        self.assertEqual(url.toLocalFile(), "C:/中文目录/")

    def test_base_url_is_directory(self):
        url = MarkdownViewer._build_base_url("C:\\foo\\readme.md")
        self.assertTrue(url.path().endswith("/"))


if __name__ == "__main__":
    unittest.main()
