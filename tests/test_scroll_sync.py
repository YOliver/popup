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


class TestInterp(unittest.TestCase):
    def test_midpoint(self):
        self.assertEqual(MarkdownViewer._interp([0, 10], [0, 100], 5), 50)

    def test_below_first_clamps(self):
        self.assertEqual(MarkdownViewer._interp([10, 20], [100, 200], 3), 100)

    def test_above_last_clamps(self):
        self.assertEqual(MarkdownViewer._interp([10, 20], [100, 200], 99), 200)

    def test_exact_node(self):
        self.assertEqual(MarkdownViewer._interp([0, 10, 20], [0, 100, 400], 10), 100)

    def test_second_segment(self):
        self.assertEqual(MarkdownViewer._interp([0, 10, 20], [0, 100, 400], 15), 250)

    def test_duplicate_nodes_return_last_equal_node(self):
        # x 等于重复值 10：返回最后一个等值节点的 y（300），且不除零
        self.assertEqual(
            MarkdownViewer._interp([0, 10, 10, 20], [0, 100, 300, 500], 10), 300)

    def test_duplicate_nodes_at_start(self):
        # 首部补点 (0,0) 与首锚点 (0,8) 重合
        self.assertEqual(MarkdownViewer._interp([0, 0, 10], [0, 8, 108], 0), 8)

    def test_duplicate_nodes_at_end(self):
        self.assertEqual(MarkdownViewer._interp([0, 10, 10], [0, 100, 300], 10), 300)

    def test_single_point(self):
        self.assertEqual(MarkdownViewer._interp([5], [42], 0), 42)
        self.assertEqual(MarkdownViewer._interp([5], [42], 9), 42)


class TestMapScroll(unittest.TestCase):
    def test_source_at_bottom_maps_to_dst_max(self):
        self.assertEqual(
            MarkdownViewer._map_scroll(100, 100, 777, [0, 1000], [0, 50]), 777)

    def test_source_beyond_bottom_maps_to_dst_max(self):
        self.assertEqual(
            MarkdownViewer._map_scroll(120, 100, 777, [0, 1000], [0, 50]), 777)

    def test_zero_src_max_uses_interp(self):
        self.assertEqual(
            MarkdownViewer._map_scroll(0, 0, 777, [0, 10], [5, 15]), 5)

    def test_not_at_bottom_rounds_interp(self):
        # interp([0,3],[0,10],1) = 3.333... → 3
        self.assertEqual(
            MarkdownViewer._map_scroll(1, 100, 777, [0, 3], [0, 10]), 3)


if __name__ == "__main__":
    unittest.main()
