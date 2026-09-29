# 预览/编辑滚动同步锚点对齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用锚点插值映射替代全局比例映射，使预览与编辑面板滚动同步达到段落级对齐、偏差不再随文档长度累积。

**Architecture:** 渲染前给每个 Markdown 块注入零高锚点 `<a id="md-N"></a>`（N=源行号），渲染后遍历 `QTextDocument` 测量锚点 Y 建立「源行号 ↔ 预览 Y」单调映射表，滚动同步改为查表（二分查找最近锚点），无锚点文档回退现有比例映射。

**Tech Stack:** Python 3.8+、PySide6（`QTextBrowser`/`QPlainTextEdit`/`QTextDocument`）、python-markdown、标准库 `bisect`。无新增依赖。

## Global Constraints

- 依赖版本下限：`PySide6>=6.5`、`markdown>=3.4`，不引入新依赖（`bisect` 为标准库）。
- 代码注释与 git commit message 使用中文。
- 目标平台 Windows；涉及 Qt 实例化的测试须在 `QT_QPA_PLATFORM=offscreen` 下运行。
- 测试框架：unittest 风格，运行命令 `python -m unittest discover -s tests -v`（全量）/ `python -m unittest tests.<文件> -v`（单个）。
- 锚点注入仅在渲染管线内生效，不得改动编辑器原文、文件读写、搜索、目录、托盘、热键。

---

### Task 1: `_nearest_anchor_index` 纯函数（二分查找最近锚点）

**Files:**
- Create: `tests/test_anchor_index.py`
- Modify: `md_viewer.py`（文件顶部 import 区加 `import bisect`；`_proportional_value` 方法后新增该方法）

**Interfaces:**
- Produces: `MarkdownViewer._nearest_anchor_index(arr, target)` — 静态方法，入参 `arr` 为非降序 list，`target` 为数值；返回「最后一个 `<= target` 的元素索引」，`target` 小于首元素时返回 `0`。供 Task 4 的 sync 方法调用。

- [ ] **Step 1: 编写失败测试**

新建 `tests/test_anchor_index.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_anchor_index -v`

Expected: 5 个测试均 FAIL，报 `AttributeError: type object 'MarkdownViewer' has no attribute '_nearest_anchor_index'`。

- [ ] **Step 3: 实现**

在 `md_viewer.py` 顶部 import 区（`import time` 之后）加：

```python
import bisect
```

在 `_proportional_value` 静态方法之后（`md_viewer.py:1073` 之后）新增：

```python
    @staticmethod
    def _nearest_anchor_index(arr, target):
        """在非降序数组 arr 中返回最后一个 <= target 的索引；target 小于首元素返回 0。"""
        idx = bisect.bisect_right(arr, target) - 1
        return idx if idx >= 0 else 0
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_anchor_index -v`

Expected: `Ran 5 tests ... OK`。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_anchor_index.py
git commit -m "feat: 新增 _nearest_anchor_index 最近锚点二分查找"
```

---

### Task 2: `_inject_anchors` 纯函数（锚点注入）

**Files:**
- Create: `tests/test_inject_anchors.py`
- Modify: `md_viewer.py`（在 `_normalize_list_indent` 方法之后、`_preserve_indent` 方法之前新增该方法）

**Interfaces:**
- Consumes: 无（纯字符串处理，复用既有围栏跟踪模式）。
- Produces: `MarkdownViewer._inject_anchors(content)` — 静态方法，入参源文本 `str`，返回注入锚点后的文本 `str`（行数不变）。供 Task 4 的 `reload_file` 调用。

- [ ] **Step 1: 编写失败测试**

新建 `tests/test_inject_anchors.py`：

```python
import unittest

from md_viewer import MarkdownViewer


class TestInjectAnchors(unittest.TestCase):
    def test_heading(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("# 标题\n"),
            '# <a id="md-0"></a>标题\n',
        )

    def test_list_item(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("- 项\n"),
            '- <a id="md-0"></a>项\n',
        )

    def test_quote(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("> 引用\n"),
            '> <a id="md-0"></a>引用\n',
        )

    def test_plain_paragraph(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("正文\n"),
            '<a id="md-0"></a>正文\n',
        )

    def test_paragraph_with_fullwidth_indent(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("\u3000\u3000正文\n"),
            '\u3000\u3000<a id="md-0"></a>正文\n',
        )

    def test_nested_list(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("- 父\n    - 子\n"),
            '- <a id="md-0"></a>父\n    - <a id="md-1"></a>子\n',
        )

    def test_nested_quote(self):
        self.assertEqual(
            MarkdownViewer._inject_anchors("> 引用\n> > 嵌套\n"),
            '> <a id="md-0"></a>引用\n> > <a id="md-1"></a>嵌套\n',
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
            '<a id="md-0"></a>第一行\n\n<a id="md-2"></a>第三行\n',
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_inject_anchors -v`

Expected: 13 个测试均 FAIL，报 `AttributeError: ... no attribute '_inject_anchors'`。

- [ ] **Step 3: 实现**

在 `_normalize_list_indent` 之后、`_preserve_indent` 之前（`md_viewer.py:944` 之前）新增：

```python
    @staticmethod
    def _inject_anchors(content: str) -> str:
        """在每个 Markdown 块起始行注入零高锚点 <a id="md-N"></a>，N 为 0-based 源行号。

        锚点插在块标记字符之后（标题 #、列表 -/1.、引用 >）或段落行首全角空格
        之后，避免破坏 markdown 结构与段首缩进。跳过代码围栏、表格、HTML 块、
        水平线、缩进代码块。复用 _normalize_list_indent 的围栏跟踪模式。
        """
        out = []
        in_fence = False
        fence_marker = None
        fence_re = re.compile(r'^(```+|~~~+)')
        heading_re = re.compile(r'^(\s{0,3})(#{1,6})\s+(.*)$')
        list_re = re.compile(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$')
        quote_re = re.compile(r'^(\s*(?:>\s*)+)(.*)$')
        fullspace_re = re.compile(r'^(\u3000+)')
        html_re = re.compile(r'^\s*<')
        hrule_re = re.compile(r'^\s{0,3}([-*_])\s*(\1\s*){2,}$')
        for idx, line in enumerate(content.split('\n')):
            stripped = line.lstrip(' ')
            m = fence_re.match(stripped)
            if m:
                if in_fence and stripped.startswith(fence_marker):
                    in_fence = False
                elif not in_fence:
                    in_fence = True
                    fence_marker = m.group(1)[:3]
                out.append(line)
                continue
            if in_fence or not stripped or stripped.startswith('|'):
                out.append(line)
                continue
            if html_re.match(line) or hrule_re.match(line):
                out.append(line)
                continue
            anchor = f'<a id="md-{idx}"></a>'
            mh = heading_re.match(line)
            if mh:
                out.append(f'{mh.group(1)}{mh.group(2)} {anchor}{mh.group(3)}')
                continue
            ml = list_re.match(line)
            if ml:
                out.append(f'{ml.group(1)}{ml.group(2)} {anchor}{ml.group(3)}')
                continue
            mq = quote_re.match(line)
            if mq:
                out.append(f'{mq.group(1)}{anchor}{mq.group(2)}')
                continue
            if len(line) - len(stripped) >= 4:
                out.append(line)  # 缩进代码块
                continue
            mf = fullspace_re.match(line)
            if mf:
                out.append(f'{mf.group(1)}{anchor}{line[len(mf.group(1)):]}')
            else:
                out.append(f'{anchor}{line}')
        return '\n'.join(out)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_inject_anchors -v`

Expected: `Ran 13 tests ... OK`。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_inject_anchors.py
git commit -m "feat: 新增 _inject_anchors 锚点注入"
```

---

### Task 3: `_build_anchor_map` 静态方法（渲染后构建映射表）

**Files:**
- Create: `tests/test_anchor_map.py`
- Modify: `md_viewer.py`（在 `_proportional_value` 之后新增该方法）

**Interfaces:**
- Consumes: 无（入参为 `QTextDocument` 实例）。
- Produces: `MarkdownViewer._build_anchor_map(doc)` — 静态方法，入参 `doc: QTextDocument`，返回 `(lines, ys)` 元组，`lines` 为锚点源行号 list，`ys` 为对应 block 文档 Y list（与 `lines` 等长、单调非降）。供 Task 4 的 `reload_file` 调用。

- [ ] **Step 1: 编写失败测试**

新建 `tests/test_anchor_map.py`（注意 `QT_QPA_PLATFORM` 在 import Qt 之前设置）：

```python
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])


def _doc(body):
    doc = QTextDocument()
    doc.setHtml('<html><body>%s</body></html>' % body)
    return doc


class TestBuildAnchorMap(unittest.TestCase):
    def test_returns_lines_and_monotonic_ys(self):
        doc = _doc(
            '<p><a id="md-0"></a>第一段</p>'
            '<p><a id="md-2"></a>第二段</p>'
            '<p><a id="md-5"></a>第三段</p>'
        )
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, [0, 2, 5])
        self.assertEqual(len(ys), 3)
        self.assertEqual(ys, sorted(ys))

    def test_ignores_non_md_anchors(self):
        doc = _doc('<h1 id="toc"><a id="md-1"></a>标题</h1>')
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, [1])

    def test_empty_when_no_anchors(self):
        doc = _doc('<p>无锚点段落</p>')
        lines, ys = MarkdownViewer._build_anchor_map(doc)
        self.assertEqual(lines, [])
        self.assertEqual(ys, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_anchor_map -v`

Expected: 3 个测试均 FAIL，报 `AttributeError: ... no attribute '_build_anchor_map'`。

- [ ] **Step 3: 实现**

在 `_proportional_value` 之后（`md_viewer.py:1073` 之后）新增：

```python
    @staticmethod
    def _build_anchor_map(doc):
        """遍历 QTextDocument 找出所有 <a id="md-N"> 锚点，返回 (行号列表, Y 列表)。

        锚点属性附着到紧随其后的字符，通过 fragment 的 anchorNames 检测；
        block 的文档 Y 用 documentLayout().blockBoundingRect(block).y() 取得。
        """
        lines, ys = [], []
        blk = doc.begin()
        while blk.isValid():
            found = None
            it = blk.begin()
            while not it.atEnd():
                for name in it.fragment().charFormat().anchorNames():
                    if name.startswith("md-"):
                        found = int(name[3:])
                        break
                if found is not None:
                    break
                it += 1
            if found is not None:
                lines.append(found)
                ys.append(doc.documentLayout().blockBoundingRect(blk).y())
            blk = blk.next()
        return lines, ys
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_anchor_map -v`

Expected: `Ran 3 tests ... OK`（可能伴随既有 `QFontDatabase: Cannot find font directory` 环境告警，非缺陷）。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_anchor_map.py
git commit -m "feat: 新增 _build_anchor_map 渲染后构建锚点映射表"
```

---

### Task 4: 接线集成（成员变量 + reload_file + 双向同步改造）

**Files:**
- Modify: `md_viewer.py`（`__init__` 成员区、`reload_file`、`_sync_preview_to_edit`、`_sync_edit_to_preview`）

**Interfaces:**
- Consumes: Task 1 的 `_nearest_anchor_index(arr, target)`、Task 2 的 `_inject_anchors(content)`、Task 3 的 `_build_anchor_map(doc)`；既有成员 `self._syncing`、`self.text_browser`、`self.edit_text`、`self.edit_panel`。
- Produces: 成员 `self._anchor_lines`、`self._anchor_ys`（`reload_file` 时刷新）。

- [ ] **Step 1: 新增成员变量**

在 `md_viewer.py:78-80` 的编辑面板状态区追加：

```python
        # 锚点映射表（源行号 ↔ 预览 Y），滚动同步查表用
        self._anchor_lines = []
        self._anchor_ys = []
```

- [ ] **Step 2: `reload_file` 接入注入与映射构建**

在 `reload_file` 的 `_normalize_list_indent` 之后、`_preserve_indent` 之前（`md_viewer.py:821-822`）插入注入：

```python
        normalized = self._dedent_fenced_blocks(content)
        normalized = self._normalize_list_indent(normalized)
        normalized = self._inject_anchors(normalized)
        normalized = self._preserve_indent(normalized)
```

在 `setHtml` 的 `finally` 之后（`md_viewer.py:850` 之后、`# 若搜索条开着` 之前）插入映射构建：

```python
        self._anchor_lines, self._anchor_ys = self._build_anchor_map(
            self.text_browser.document()
        )
```

- [ ] **Step 3: 改造 `_sync_preview_to_edit`**

将 `md_viewer.py:746-760` 的方法体替换为：

```python
    def _sync_preview_to_edit(self, value):
        """预览滚动 → 编辑器滚动条按锚点映射跟随（仅滚动视图，不动光标）。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        if not self.edit_panel.isVisible():
            return
        edit_sb = self.edit_text.verticalScrollBar()
        self._syncing = True
        try:
            if self._anchor_lines:
                y = self.text_browser.verticalScrollBar().value()
                i = self._nearest_anchor_index(self._anchor_ys, y)
                line = self._anchor_lines[i]
                blk = self.edit_text.document().findBlockByNumber(line)
                doc_y = self.edit_text.blockBoundingGeometry(blk).y() + edit_sb.value()
                edit_sb.setValue(int(doc_y))
            else:
                edit_sb.setValue(self._proportional_value(
                    self.text_browser.verticalScrollBar(), edit_sb))
        finally:
            self._syncing = False
```

- [ ] **Step 4: 改造 `_sync_edit_to_preview`**

将 `md_viewer.py:762-774` 的方法体替换为：

```python
    def _sync_edit_to_preview(self, value):
        """编辑器滚动 → 预览滚动条按锚点映射跟随。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        preview_sb = self.text_browser.verticalScrollBar()
        self._syncing = True
        try:
            if self._anchor_lines:
                line = self.edit_text.firstVisibleBlock().blockNumber()
                i = self._nearest_anchor_index(self._anchor_lines, line)
                preview_sb.setValue(self._anchor_ys[i])
            else:
                preview_sb.setValue(self._proportional_value(
                    self.edit_text.verticalScrollBar(), preview_sb))
        finally:
            self._syncing = False
```

- [ ] **Step 5: 运行全量回归**

Run: `python -m unittest discover -s tests -v`

Expected: `Ran 60 tests ... OK`（39 旧 + 21 新：Task1 5 + Task2 13 + Task3 3）。

- [ ] **Step 6: 手动视觉冒烟**

运行 `python md_viewer.py` 打开一份含多级标题、长段落、代码块、列表、引用的较长 md：
1. 打开"编辑"面板，滚动预览 → 编辑器首可见行与预览当前段落对齐；滚动到底部，偏差不再累积。
2. 反向滚动编辑器 → 预览对齐。
3. 段首全角空格缩进段落、纯代码块文档、空文件、快速连续滚动均无异常、无死循环。

- [ ] **Step 7: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 滚动同步改为锚点映射并接入渲染管线"
```

---

## Self-Review

**Spec coverage:**
- 锚点注入 `_inject_anchors`（spec 4.1）→ Task 2（含全部边界单测）。
- 映射表构建 `_build_anchor_map`（spec 4.2）→ Task 3。
- 最近锚点查找 `_nearest_anchor_index`（spec 4.3）→ Task 1。
- 双向同步改造 + 回退（spec 4.4）→ Task 4 Step 3/4。
- 成员变量、`reload_file` 接线（spec 4.5/4.6）→ Task 4 Step 1/2。
- 测试计划（spec 6）→ Task 1/2/3 单测 + Task 4 手动冒烟。

**Placeholder scan:** 无 TBD/TODO；每个代码步骤均含完整代码与命令。

**Type consistency:** `_nearest_anchor_index(arr, target)`、`_inject_anchors(content)`、`_build_anchor_map(doc)` 三个签名在定义任务与调用任务（Task 4）中一致；成员 `_anchor_lines`/`_anchor_ys` 命名前后一致。
