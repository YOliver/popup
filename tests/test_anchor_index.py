import unittest

from md_viewer import MarkdownViewer


class TestNearestAnchorIndex(unittest.TestCase):
    def test_normal_hit(self):
        arr = [0, 2, 5, 9]
        self.assertEqual(MarkdownViewer._nearest_anchor_index(arr, 6), 2)

    def test_target_below_first_returns_zero(self):
        arr = [3, 7, 10]
        self.assertEqual(MarkdownViewer._nearest_anchor_index(arr, 1), 0)

    def test_target_exactly_on_anchor(self):
        arr = [0, 4, 8]
        self.assertEqual(MarkdownViewer._nearest_anchor_index(arr, 4), 1)

    def test_target_beyond_last_returns_last(self):
        arr = [1, 5, 9]
        self.assertEqual(MarkdownViewer._nearest_anchor_index(arr, 100), 2)

    def test_single_element(self):
        arr = [7]
        self.assertEqual(MarkdownViewer._nearest_anchor_index(arr, 0), 0)
        self.assertEqual(MarkdownViewer._nearest_anchor_index(arr, 99), 0)


if __name__ == "__main__":
    unittest.main()
