import unittest

from md_viewer import MarkdownViewer


class _FakeScrollBar:
    def __init__(self, value=0, maximum=0):
        self._value = value
        self._maximum = maximum

    def value(self):
        return self._value

    def maximum(self):
        return self._maximum


class TestProportionalValue(unittest.TestCase):
    def test_half_of_src_maps_to_half_of_dst(self):
        src = _FakeScrollBar(value=50, maximum=100)
        dst = _FakeScrollBar(maximum=200)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 100)

    def test_zero_maximum_does_not_divide_by_zero(self):
        src = _FakeScrollBar(value=0, maximum=0)
        dst = _FakeScrollBar(maximum=0)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 0)

    def test_full_src_maps_to_full_dst(self):
        src = _FakeScrollBar(value=100, maximum=100)
        dst = _FakeScrollBar(maximum=300)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 300)

    def test_rounds_to_nearest_int(self):
        src = _FakeScrollBar(value=1, maximum=3)
        dst = _FakeScrollBar(maximum=100)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 33)


if __name__ == "__main__":
    unittest.main()
