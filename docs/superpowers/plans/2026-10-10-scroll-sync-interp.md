# 滚动同步错位修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复编辑面板打开后预览与编辑器双向滚动同步错位：映射随排版宽度懒刷新、编辑侧改用视觉行单位、锚点之间分段线性插值。

**Architecture:** 锚点映射拆成两级——内容变化时完整构建（锚点行号 + 所在 `QTextBlock`），排版变化时只用缓存的块重算 Y。编辑侧坐标每次同步时用 `firstLineNumber()` 实时查询。两个方向共用纯函数 `_map_scroll`（底部对齐 + `_interp` 分段线性插值）。

**Tech Stack:** Python 3.14、PySide6（`QTextBrowser` / `QPlainTextEdit` / `QTextDocument`）、python-markdown、pytest（用例用 `unittest` 写法）。

**Spec:** `docs/superpowers/specs/2026-10-10-scroll-sync-interp-design.md`

## Global Constraints

- 代码只改 `md_viewer.py`；测试改 `tests/test_scroll_sync.py`、`tests/test_anchor_map.py`，删除 `tests/test_anchor_index.py`。
- 测试中不得创建 `MarkdownViewer` 实例（会注册全局热键、建托盘、读写 QSettings）；只测静态方法和 `QTextDocument`。
- Qt 测试文件首行设置 `os.environ['QT_QPA_PLATFORM'] = 'offscreen'`；offscreen 下不断言具体像素值。
- `documentSizeChanged` 回调只置脏标记，不做任何计算。
- 无锚点时的比例回退 `_proportional_value` 保持不变。
- 运行全部测试：`python -m pytest tests -q`（基线 81 passed）。
- 提交信息用中文，前缀 `feat:` / `fix:` / `test:` / `refactor:`。

## File Structure

| 文件 | 职责 | 改动 |
|---|---|---|
| `md_viewer.py` | 主窗口与全部渲染/同步逻辑 | 新增纯函数 `_interp`、`_map_scroll`、`_collect_anchor_blocks`、`_anchor_block_ys`；新增实例方法 `_mark_anchor_dirty`、`_ensure_anchor_map`、`_clear_anchor_map`、`_edit_anchor_points`；改写两个同步方法、`reload_file`、`open_help_doc`、`toggle_edit_panel`、`init_ui`、`__init__`；删除 `_nearest_anchor_index` |
| `tests/test_scroll_sync.py` | 纯函数单元测试（无 Qt） | 追加 `_interp`、`_map_scroll` 用例 |
| `tests/test_anchor_map.py` | `QTextDocument` 层面的锚点映射测试 | 追加拆分函数、单调保护、宽度变化用例 |
| `tests/test_anchor_index.py` | `_nearest_anchor_index` 测试 | 删除 |

---

### Task 1: 插值与滚动映射纯函数

**Files:**
- Modify: `md_viewer.py`（在 `_proportional_value` 之后、`_nearest_anchor_index` 之前，约第 1299 行）
- Test: `tests/test_scroll_sync.py`

**Interfaces:**
- Consumes: 无（`bisect` 已在 `md_viewer.py` 顶部导入）
- Produces:
  - `MarkdownViewer._interp(xs: list[float], ys: list[float], x: float) -> float`：xs 非降序、与 ys 等长且非空。
  - `MarkdownViewer._map_scroll(value: int, src_max: int, dst_max: int, xs: list[float], ys: list[float]) -> int`

- [ ] **Step 1: 写失败测试**

在 `tests/test_scroll_sync.py` 的 `if __name__ == "__main__":` 之前追加：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_scroll_sync.py -q`
Expected: FAIL，报 `AttributeError: type object 'MarkdownViewer' has no attribute '_interp'`（及 `_map_scroll`）

- [ ] **Step 3: 实现**

在 `md_viewer.py` 的 `_proportional_value` 方法之后插入：

```python
    @staticmethod
    def _interp(xs, ys, x):
        """分段线性插值：xs 非降序，返回 x 在 (xs, ys) 折线上对应的 y。

        x < xs[0] 返回 ys[0]；x >= xs[-1] 返回 ys[-1]；
        x 恰好等于一组重复节点的值时，返回最后一个等值节点的 y。
        bisect_right 会越过所有等值节点，零宽区间永远不会被选中，因此不会除零。
        """
        if x < xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x)
        x0, x1 = xs[i - 1], xs[i]
        y0, y1 = ys[i - 1], ys[i]
        return y0 + (y1 - y0) * (x - x0) / (x1 - x0)

    @staticmethod
    def _map_scroll(value, src_max, dst_max, xs, ys):
        """把源滚动条值映射为目标滚动条值。

        src_max > 0 且 value >= src_max 时返回 dst_max（底部对齐）；
        否则返回 round(_interp(xs, ys, value))。
        """
        if src_max > 0 and value >= src_max:
            return dst_max
        return round(MarkdownViewer._interp(xs, ys, value))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_scroll_sync.py -q`
Expected: 17 passed（原 4 个 + 新 13 个）

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_scroll_sync.py
git commit -m "feat: 新增 _interp 分段线性插值与 _map_scroll 滚动映射纯函数"
```

---

### Task 2: 拆分锚点映射构建并加单调保护

**Files:**
- Modify: `md_viewer.py:1306-1332`（`_build_anchor_map`）
- Test: `tests/test_anchor_map.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `MarkdownViewer._collect_anchor_blocks(doc: QTextDocument) -> tuple[list[int], list[QTextBlock]]`：锚点源行号与所在块，一一对应，按文档顺序。
  - `MarkdownViewer._anchor_block_ys(doc: QTextDocument, blocks: list[QTextBlock]) -> list[float]`：每块 `blockBoundingRect().y()`，经累计最大值处理，非降序。
  - `MarkdownViewer._build_anchor_map(doc) -> tuple[list[int], list[float]]`：签名与返回值不变。

- [ ] **Step 1: 写失败测试**

在 `tests/test_anchor_map.py` 末尾的 `if __name__ == "__main__":` 之前（`TestBuildAnchorMap` 类之后）追加：

```python
def _long_doc():
    para = '很长的段落文字' * 40
    return _doc(''.join(
        '<p><a id="popup-anchor-%d"></a>%s</p>' % (i * 3, para) for i in range(3)))


class TestSplitAnchorMap(unittest.TestCase):
    def test_collect_matches_build(self):
        doc = _long_doc()
        lines, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        self.assertEqual(lines, MarkdownViewer._build_anchor_map(doc)[0])
        self.assertEqual(lines, [0, 3, 6])
        self.assertEqual(len(blocks), len(lines))

    def test_block_ys_monotonic_when_blocks_reversed(self):
        doc = _long_doc()
        _, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        ys = MarkdownViewer._anchor_block_ys(doc, list(reversed(blocks)))
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(len(ys), 3)

    def test_recompute_ys_after_width_change_matches_full_build(self):
        doc = _long_doc()
        doc.setTextWidth(800)
        _, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        wide = MarkdownViewer._anchor_block_ys(doc, blocks)
        doc.setTextWidth(200)
        narrow = MarkdownViewer._anchor_block_ys(doc, blocks)
        self.assertEqual(narrow, MarkdownViewer._build_anchor_map(doc)[1])
        self.assertNotEqual(narrow, wide)  # 确认宽度变化确实改变了 Y，测试有效
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_anchor_map.py -q`
Expected: 新增 3 个 FAIL，报 `AttributeError: ... '_collect_anchor_blocks'`；原有用例 PASS

- [ ] **Step 3: 实现**

把 `md_viewer.py` 中整个 `_build_anchor_map` 静态方法替换为：

```python
    @staticmethod
    def _collect_anchor_blocks(doc):
        """遍历 QTextDocument 找出所有 <a id="popup-anchor-N"> 锚点，返回 (行号列表, 所在块列表)。

        锚点属性附着到紧随其后的字符，通过 fragment 的 anchorNames 检测；
        每个块只取第一个锚点。结果只取决于文档结构，与排版宽度无关。
        """
        lines, blocks = [], []
        blk = doc.begin()
        while blk.isValid():
            found = None
            it = blk.begin()
            while not it.atEnd():
                for name in it.fragment().charFormat().anchorNames():
                    if name.startswith("popup-anchor-"):
                        suffix = name[len("popup-anchor-"):]
                        if suffix.isdigit():
                            found = int(suffix)
                        break
                if found is not None:
                    break
                it += 1
            if found is not None:
                lines.append(found)
                blocks.append(blk)
            blk = blk.next()
        return lines, blocks

    @staticmethod
    def _anchor_block_ys(doc, blocks):
        """返回各块在文档中的 Y，并做累计最大值处理保证非降序（防浮动元素等导致 Y 倒退）。"""
        layout = doc.documentLayout()
        ys = []
        top = float("-inf")
        for blk in blocks:
            top = max(top, layout.blockBoundingRect(blk).y())
            ys.append(top)
        return ys

    @staticmethod
    def _build_anchor_map(doc):
        """完整构建锚点映射，返回 (行号列表, Y 列表)。"""
        lines, blocks = MarkdownViewer._collect_anchor_blocks(doc)
        return lines, MarkdownViewer._anchor_block_ys(doc, blocks)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests -q`
Expected: `97 passed`（基线 81 + Task 1 的 13 + 本任务 3）

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_anchor_map.py
git commit -m "refactor: 锚点映射拆分为 _collect_anchor_blocks 与 _anchor_block_ys，Y 加单调保护"
```

---

### Task 3: 映射状态管理（懒刷新、清空）

**Files:**
- Modify: `md_viewer.py:134-136`（`__init__` 状态）
- Modify: `md_viewer.py:371-377`（`init_ui` 信号连接）
- Modify: `md_viewer.py:920-923`（`reload_file` 读失败分支）
- Modify: `md_viewer.py:966-968`（`reload_file` 构建映射）
- Modify: `md_viewer.py:1398-1406`（`open_help_doc` 缺失分支）
- Test: 无新单元测试（按 spec，需 `MarkdownViewer` 实例，交给 Task 5 探针）

**Interfaces:**
- Consumes: Task 2 的 `_collect_anchor_blocks`、`_anchor_block_ys`
- Produces（实例属性与方法，Task 4 使用）:
  - 属性 `self._anchor_lines: list[int]`、`self._anchor_blocks: list[QTextBlock]`、`self._anchor_ys: list[float]`、`self._anchor_dirty: bool`
  - `self._mark_anchor_dirty(*_) -> None`
  - `self._ensure_anchor_map() -> None`：脏时用缓存块重算 `_anchor_ys` 并清脏
  - `self._clear_anchor_map() -> None`

- [ ] **Step 1: `__init__` 新增状态**

把 `md_viewer.py` 中：

```python
        # 锚点映射表（源行号 ↔ 预览 Y），滚动同步查表用
        self._anchor_lines = []
        self._anchor_ys = []
```

替换为：

```python
        # 锚点映射表（源行号 ↔ 预览 Y），滚动同步查表用
        self._anchor_lines = []
        self._anchor_blocks = []   # 锚点所在 QTextBlock，宽度变化时据此只重算 Y
        self._anchor_ys = []
        self._anchor_dirty = False  # 预览排版变化后置位，下次同步前懒刷新 Y
```

- [ ] **Step 2: `init_ui` 连接 `documentSizeChanged`**

把：

```python
        # 双向滚动同步（比例粗同步）
        self.text_browser.verticalScrollBar().valueChanged.connect(
            self._sync_preview_to_edit
        )
        self.edit_text.verticalScrollBar().valueChanged.connect(
            self._sync_edit_to_preview
        )
```

替换为：

```python
        # 双向滚动同步（锚点插值）
        self.text_browser.verticalScrollBar().valueChanged.connect(
            self._sync_preview_to_edit
        )
        self.edit_text.verticalScrollBar().valueChanged.connect(
            self._sync_edit_to_preview
        )
        # 预览排版变化（宽度、图片加载）后标记映射过期；setHtml 不替换 layout，连接一次即可
        self.text_browser.document().documentLayout().documentSizeChanged.connect(
            self._mark_anchor_dirty
        )
```

- [ ] **Step 3: 新增三个状态方法**

在 `_sync_preview_to_edit` 方法定义之前插入：

```python
    def _mark_anchor_dirty(self, *_):
        """documentSizeChanged 回调：只置脏标记，拖分隔条时可能每帧触发，不做计算"""
        self._anchor_dirty = True

    def _ensure_anchor_map(self):
        """映射过期时用缓存的块只重算 Y（不重新遍历片段）"""
        if self._anchor_dirty:
            self._anchor_ys = self._anchor_block_ys(
                self.text_browser.document(), self._anchor_blocks)
            self._anchor_dirty = False

    def _clear_anchor_map(self):
        """预览被替换为非文件内容后清空映射，同步回退到比例方式"""
        self._anchor_lines = []
        self._anchor_blocks = []
        self._anchor_ys = []
        self._anchor_dirty = False
```

- [ ] **Step 4: `reload_file` 改用两级构建**

把：

```python
        self._anchor_lines, self._anchor_ys = self._build_anchor_map(
            self.text_browser.document()
        )
```

替换为：

```python
        doc = self.text_browser.document()
        self._anchor_lines, self._anchor_blocks = self._collect_anchor_blocks(doc)
        self._anchor_ys = self._anchor_block_ys(doc, self._anchor_blocks)
        self._anchor_dirty = False
```

- [ ] **Step 5: `reload_file` 读失败分支清空映射**

把：

```python
            logger.error("Failed to read file: %s", e)
            self.text_browser.setHtml(self.wrap_html(f"<p style='color:red;'>读取文件失败: {e}</p>"))
            return
```

替换为：

```python
            logger.error("Failed to read file: %s", e)
            self.text_browser.setHtml(self.wrap_html(f"<p style='color:red;'>读取文件失败: {e}</p>"))
            self._clear_anchor_map()
            return
```

- [ ] **Step 6: `open_help_doc` 缺失分支清空映射**

把：

```python
            logger.warning("Help doc not found: %s", path)
            self.text_browser.setHtml(self.wrap_html(
                f"<p style='color:red;'>帮助文档未找到: {os.path.basename(path)}</p>"
            ))
```

替换为：

```python
            logger.warning("Help doc not found: %s", path)
            self.text_browser.setHtml(self.wrap_html(
                f"<p style='color:red;'>帮助文档未找到: {os.path.basename(path)}</p>"
            ))
            self._clear_anchor_map()
```

- [ ] **Step 7: 运行全部测试**

Run: `python -m pytest tests -q`
Expected: `97 passed`（与 Task 2 结束时相同）

- [ ] **Step 8: 启动冒烟**

Run: `timeout 8 python md_viewer.py "C:/Users/oliveryin/Desktop/失去的二十年/失去的二十年.md"; echo exit=$?`
Expected: 窗口正常打开，8 秒后被 timeout 结束（`exit=124`），终端无 Traceback

- [ ] **Step 9: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 锚点映射随预览排版变化懒刷新 Y，错误页清空映射"
```

---

### Task 4: 同步方法改为插值，删除块首查表

**Files:**
- Modify: `md_viewer.py`（`toggle_edit_panel` 约第 791 行；`_sync_preview_to_edit` / `_sync_edit_to_preview` 约第 840-885 行；删除 `_nearest_anchor_index`）
- Delete: `tests/test_anchor_index.py`

**Interfaces:**
- Consumes: Task 1 的 `_map_scroll`；Task 3 的 `_ensure_anchor_map`、`_anchor_lines`、`_anchor_ys`
- Produces: `self._edit_anchor_points() -> tuple[list[int], list[float]]`：(Es, Ys) 等长、非降、含首尾补点

- [ ] **Step 1: 新增 `_edit_anchor_points`**

在 Task 3 新增的 `_clear_anchor_map` 之后插入：

```python
    def _edit_anchor_points(self):
        """生成插值折线点 (Es, Ys)：编辑侧视觉行 ↔ 预览 Y，含首尾补点。

        E 用 firstLineNumber() 实时查询（与编辑器滚动条单位一致，宽度变化自动正确）；
        编辑内容行数少于锚点行号时，该锚点连同其 Y 一起跳过。
        """
        edit_doc = self.edit_text.document()
        es, ys = [0], [0.0]
        for line, y in zip(self._anchor_lines, self._anchor_ys):
            blk = edit_doc.findBlockByNumber(line)
            if blk.isValid():
                es.append(blk.firstLineNumber())
                ys.append(y)
        es.append(edit_doc.lineCount())
        ys.append(self.text_browser.document().size().height())
        return es, ys
```

- [ ] **Step 2: 改写两个同步方法**

把 `_sync_preview_to_edit` 和 `_sync_edit_to_preview` 两个方法整体替换为：

```python
    def _sync_preview_to_edit(self, value):
        """预览滚动 → 编辑器滚动条按锚点插值跟随（仅滚动视图，不动光标）。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        if not self.edit_panel.isVisible():
            return
        preview_sb = self.text_browser.verticalScrollBar()
        edit_sb = self.edit_text.verticalScrollBar()
        self._syncing = True
        try:
            self._ensure_anchor_map()
            if self._anchor_lines:
                es, ys = self._edit_anchor_points()
                edit_sb.setValue(self._map_scroll(
                    preview_sb.value(), preview_sb.maximum(),
                    edit_sb.maximum(), ys, es))
            else:
                edit_sb.setValue(self._proportional_value(preview_sb, edit_sb))
        finally:
            self._syncing = False

    def _sync_edit_to_preview(self, value):
        """编辑器滚动 → 预览滚动条按锚点插值跟随。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        preview_sb = self.text_browser.verticalScrollBar()
        edit_sb = self.edit_text.verticalScrollBar()
        self._syncing = True
        try:
            self._ensure_anchor_map()
            if self._anchor_lines:
                es, ys = self._edit_anchor_points()
                preview_sb.setValue(self._map_scroll(
                    edit_sb.value(), edit_sb.maximum(),
                    preview_sb.maximum(), es, ys))
            else:
                preview_sb.setValue(self._proportional_value(edit_sb, preview_sb))
        finally:
            self._syncing = False
```

- [ ] **Step 3: 打开面板时延迟首次定位**

在 `toggle_edit_panel` 中把：

```python
            self._sync_preview_to_edit(0)  # 显示时定位到预览当前比例位置
```

替换为：

```python
            # 推迟到事件循环下一轮：等预览变窄重排、编辑器完成布局后再定位
            QTimer.singleShot(0, lambda: self._sync_preview_to_edit(0))
```

- [ ] **Step 4: 删除 `_nearest_anchor_index` 及其测试**

删除 `md_viewer.py` 中整个方法：

```python
    @staticmethod
    def _nearest_anchor_index(arr, target):
        """在非降序数组 arr 中返回最后一个 <= target 的索引；target 小于首元素返回 0。"""
        idx = bisect.bisect_right(arr, target) - 1
        return idx if idx >= 0 else 0
```

（`import bisect` 保留，`_interp` 仍在使用。）

Run: `git rm tests/test_anchor_index.py`

- [ ] **Step 5: 确认无残留引用**

Run: `grep -rn "_nearest_anchor_index\|blockBoundingGeometry" md_viewer.py tests/`
Expected: 无输出

- [ ] **Step 6: 运行全部测试**

Run: `python -m pytest tests -q`
Expected: `92 passed`（97 减去 `test_anchor_index.py` 的 5 个用例）

- [ ] **Step 7: 启动冒烟**

Run: `timeout 8 python md_viewer.py "C:/Users/oliveryin/Desktop/失去的二十年/失去的二十年.md"; echo exit=$?`
Expected: `exit=124`，终端无 Traceback

- [ ] **Step 8: 提交**

```bash
git add md_viewer.py
git commit -m "fix: 滚动同步改为视觉行单位的锚点插值，修复编辑面板打开后错位"
```

---

### Task 5: 真实平台探针与手动冒烟（不入库）

**Files:**
- Create（临时，不提交）: `/tmp/probe_sync.py`

**Interfaces:**
- Consumes: Task 3/4 的全部实例方法与属性

- [ ] **Step 1: 写探针脚本**

创建 `/tmp/probe_sync.py`（真实平台，**不要**设置 offscreen）：

```python
import sys, time
sys.path.insert(0, r"g:/UGit/popup")
from PySide6.QtWidgets import QApplication
from md_viewer import MarkdownViewer

PATH = r"C:/Users/oliveryin/Desktop/失去的二十年/失去的二十年.md"


def pump(app, n=20):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.02)


app = QApplication(sys.argv)
w = MarkdownViewer(); w.resize(1200, 800); w.show(); pump(app)
w.load_file(PATH); pump(app)
w.toggle_edit_panel(); pump(app)
doc = w.text_browser.document()
psb, esb = w.text_browser.verticalScrollBar(), w.edit_text.verticalScrollBar()

# 1. 拖分隔条后置脏，同步一次后清脏，且懒刷新结果与完整重建一致
sz = w.splitter.sizes(); w.splitter.setSizes([sz[0], sz[1] - 150, sz[2] + 150]); pump(app)
print("1a dirty after resize:", w._anchor_dirty)
t = time.perf_counter(); w._ensure_anchor_map(); dt = (time.perf_counter() - t) * 1000
print("1b dirty after ensure:", w._anchor_dirty, "| refresh %.1fms (目标 <10ms)" % dt)
print("1c ys == full rebuild:", w._anchor_ys == MarkdownViewer._build_anchor_map(doc)[1])

# 2. 编辑器滚到某锚点块的视觉行 → 预览约等于该锚点 Y；反向同理
k = len(w._anchor_lines) // 2
line, y = w._anchor_lines[k], w._anchor_ys[k]
e = w.edit_text.document().findBlockByNumber(line).firstLineNumber()
esb.setValue(e); pump(app, 5)
print("2a edit→preview: preview=%d anchorY=%d diff=%d" % (psb.value(), y, psb.value() - y))
psb.setValue(int(y)); pump(app, 5)
print("2b preview→edit: edit=%d anchorE=%d diff=%d" % (esb.value(), e, esb.value() - e))

# 3. 底部对齐
esb.setValue(esb.maximum()); pump(app, 5)
print("3a edit bottom → preview at max:", psb.value() == psb.maximum())
psb.setValue(0); pump(app, 5); psb.setValue(psb.maximum()); pump(app, 5)
print("3b preview bottom → edit at max:", esb.value() == esb.maximum())
```

- [ ] **Step 2: 运行探针**

Run: `timeout 120 python /tmp/probe_sync.py 2>&1 | grep -E "^[0-9]"`
Expected:
- `1a dirty after resize: True`
- `1b dirty after ensure: False`，refresh 耗时 < 10ms
- `1c ys == full rebuild: True`
- `2a` 的 diff 绝对值 ≤ 1；`2b` 的 diff 绝对值 ≤ 1
- `3a ... True`、`3b ... True`

任一项不符：停下，用 superpowers:systematic-debugging 排查，不要调阈值凑结果。（若只有 2b 不符，先检查 `_anchor_ys[k]` 是否与相邻锚点 Y 相同——重复 Y 会按规则映射到最后一个等值节点，属于预期，可换一个 k 重测。）

- [ ] **Step 3: 手动冒烟（请用户执行）**

请用户运行 `start.bat` 打开 `失去的二十年.md`，打开编辑面板后逐项确认：
1. 开头、中段、末尾三处：在预览侧滚轮滚动，编辑器对应到同一段内容。
2. 同样三处：在编辑侧滚轮滚动，预览对应到同一段内容。
3. 在一个长段落内部慢慢滚动，对侧连续跟随，不停顿、不跳变。
4. 拖动分隔条改变宽度后继续滚动，仍然对齐。
5. 关闭再打开编辑面板，编辑器定位到预览当前位置。
6. 任一侧滚到底，另一侧也到底。
7. 打开一个不存在的帮助文档（或临时改名帮助文件后点帮助菜单），两侧滚动不报错。

- [ ] **Step 4: 清理**

Run: `rm -f /tmp/probe_sync.py`
