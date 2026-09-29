# 代码块长行自动折行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Markdown 代码块（`<pre>`）中的超长行随窗口宽度自动折行，消除水平滚动条。

**Architecture:** 在 `wrap_html` 的 `<pre>` CSS 样式块中追加 `white-space: pre-wrap;` 一条属性。Qt 富文本引擎（Qt 6）已实测支持该属性：渲染超长代码块时视觉行数从 1 折为 20、水平滚动条 `maximum` 从 5230 归零。

**Tech Stack:** Python 3.8+、PySide6（QTextBrowser 富文本）、python-markdown。无新增依赖。

## Global Constraints

- 依赖版本下限：`PySide6>=6.5`、`markdown>=3.4`，不引入新依赖。
- 代码注释与 git commit message 使用中文。
- 目标平台 Windows；测试须在 `QT_QPA_PLATFORM=offscreen` 下运行（无头环境）。
- 测试框架：unittest 风格（与 `tests/` 现有测试一致），运行命令 `python -m unittest discover -s tests -v`。

---

### Task 1: 代码块长行自动折行（TDD 完整循环）

**Files:**
- Create: `tests/test_code_wrap.py`
- Modify: `md_viewer.py:1173-1176`（`wrap_html` 的 `pre` 样式块）

**Interfaces:**
- Consumes: `MarkdownViewer.wrap_html(body)`（`md_viewer.py:1150`，静态方法，接收 HTML 片段返回完整 HTML 字符串）。
- Produces: `tests/test_code_wrap.py` 中 3 个测试用例；`wrap_html` 输出的 `pre` 样式含 `white-space: pre-wrap`。

- [ ] **Step 1: 编写失败测试**

新建 `tests/test_code_wrap.py`（注意 `QT_QPA_PLATFORM` 必须在 import Qt 之前设置）：

```python
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

from PySide6.QtWidgets import QApplication, QTextBrowser

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])

LONG_LINE = "这是一段很长的代码内容，用来测试自动折行行为。" * 20


def _render_code_block(width=300):
    """渲染含超长行的 <pre> 代码块，返回 QTextBrowser。"""
    body = f"<pre><code>{LONG_LINE}</code></pre>"
    tb = QTextBrowser()
    tb.resize(width, 600)
    tb.setHtml(MarkdownViewer.wrap_html(body))
    tb.document().setTextWidth(width)
    return tb


def _max_line_count(doc):
    """遍历所有 block，返回最大的视觉行数。"""
    max_lines = 0
    blk = doc.begin()
    while blk.isValid():
        layout = blk.layout()
        if layout is not None:
            max_lines = max(max_lines, layout.lineCount())
        blk = blk.next()
    return max_lines


class TestCodeBlockWrap(unittest.TestCase):
    def test_long_code_line_has_no_horizontal_scroll(self):
        tb = _render_code_block()
        self.assertEqual(tb.horizontalScrollBar().maximum(), 0)

    def test_long_code_line_wraps_into_multiple_lines(self):
        tb = _render_code_block()
        self.assertGreater(_max_line_count(tb.document()), 1)

    def test_wrap_html_contains_pre_wrap(self):
        html = MarkdownViewer.wrap_html("<p>正文</p>")
        self.assertIn("white-space: pre-wrap", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_code_wrap -v`

Expected: 3 个测试均 FAIL——
- `test_long_code_line_has_no_horizontal_scroll`: `AssertionError: 5230 != 0`
- `test_long_code_line_wraps_into_multiple_lines`: `AssertionError: 1 not greater than 1`
- `test_wrap_html_contains_pre_wrap`: `AssertionError: 'white-space: pre-wrap' not found in ...`

- [ ] **Step 3: 实现最小改动**

修改 `md_viewer.py:1173-1176`，`pre` 样式块追加 `white-space: pre-wrap;`：

```python
pre {{
    background: #f4f4f4;
    padding: 12px;
    white-space: pre-wrap;
}}
```

（注意：`wrap_html` 用 f-string 包裹 CSS，原文件该块为 `pre {{ ... }}` 双花括号转义形式，仅新增 `white-space: pre-wrap;` 一行，其余保持原样。）

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_code_wrap -v`

Expected: 3 个测试全部 PASS。

Run（全量回归）: `python -m unittest discover -s tests -v`

Expected: `Ran 37 tests ... OK`（34 旧 + 3 新）。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_code_wrap.py
git commit -m "feat: 代码块长行随窗口宽度自动折行"
```

---

## Self-Review

**Spec coverage:**
- 目标"代码块长行随窗口宽度自动折行、无水平滚动" → Task 1 Step 1 的 `test_long_code_line_has_no_horizontal_scroll` / `test_long_code_line_wraps_into_multiple_lines`。
- 目标"保留源码真实换行与空格、软折行" → 通过 `white-space: pre-wrap` 语义保证，`test_wrap_html_contains_pre_wrap` 守卫生效。
- 非目标（不动内联 code、不加续行标记、不改编辑面板）→ 无对应任务，符合预期。
- 测试计划第 6.1（offscreen 行为测试）+ 6.2（字符串断言）→ 已全部落入 Task 1。

**Placeholder scan:** 无 TBD/TODO；每个改动步骤均含完整代码。

**Type consistency:** `MarkdownViewer.wrap_html(body)` 签名与 `md_viewer.py:1150` 一致；测试直接复用该方法，无跨任务命名。
