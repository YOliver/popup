# 引用块（blockquote）视觉增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Markdown 引用块（`>`）显示为整块浅灰背景 + 左侧竖线 + 内边距，与正文形成清晰视觉区分。

**Architecture:** 在渲染管线中新增一步 HTML 后处理——把 python-markdown 输出的 `<blockquote>` 替换为单列表格结构，利用 Qt 对表格整块背景/边框/内边距的完整支持。后处理逻辑抽取为纯静态方法 `_style_blockquotes()` 便于单元测试。

**Tech Stack:** Python 3.8+、python-markdown、PySide6（QTextDocument）、标准库 unittest。

## Global Constraints

- 不引入新依赖（测试使用标准库 `unittest`，不用 pytest）。
- 仅修改 `md_viewer.py`（+ 新建测试文件）。
- 代码注释、commit message 使用中文。
- 背景色 `#f6f8fa`、左竖线 `#ddd` 4px、内边距 `8px 16px`、文字色 `#666`（数值从设计文档逐字取用）。
- 范围仅 blockquote 视觉，非目标：深色主题、可配置颜色、其他块元素样式调整。

---

### Task 1: 新增 `_style_blockquotes` 纯函数（TDD）

**Files:**
- Modify: `md_viewer.py`（在 `_build_base_url` 方法之后新增 `_style_blockquotes` 静态方法）
- Test: `tests/test_blockquote.py`（新建）

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces: `MarkdownViewer._style_blockquotes(html: str) -> str`，供 Task 2 在 `reload_file()` 中调用。输入为 markdown 渲染出的 HTML，输出把 `<blockquote>` 转为单列表格结构的 HTML。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_blockquote.py`：

```python
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
```

- [ ] **Step 2: 运行测试验证失败**

在项目根目录 `g:\UGit\popup` 运行：

```bash
python -m unittest tests.test_blockquote -v
```

Expected: FAIL，报错 `AttributeError: type object 'MarkdownViewer' has no attribute '_style_blockquotes'`。

- [ ] **Step 3: 实现最小代码**

在 `md_viewer.py` 的 `_build_base_url` 方法之后（该方法的 `return QUrl.fromLocalFile(base_dir)` 之后、`on_file_changed` 之前）新增：

```python
    @staticmethod
    def _style_blockquotes(html: str) -> str:
        """把 blockquote 转为单列表格，使 Qt 能渲染整块背景 + 左竖线。

        Qt 富文本引擎不支持 blockquote 的块级背景（会降级为文字级背景），
        而 table 支持整块背景/边框/内边距。python-markdown 输出的 blockquote
        标签无属性、格式固定，字符串替换安全；嵌套引用自然变为嵌套表格。
        """
        html = html.replace("<blockquote>", '<table class="md-quote"><tr><td>')
        html = html.replace("</blockquote>", "</td></tr></table>")
        return html
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m unittest tests.test_blockquote -v
```

Expected: PASS，3 个测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_blockquote.py
git commit -m "feat: 新增 _style_blockquotes 将引用块转为表格结构"
```

---

### Task 2: 接入渲染管线并更新 CSS

**Files:**
- Modify: `md_viewer.py`（`reload_file()` 中 `md.convert()` 后加后处理调用；`wrap_html()` 的 `<style>` 中替换 blockquote 样式）
- Test: `tests/test_quote_rendering.py`（新建，集成测试）

**Interfaces:**
- Consumes: `MarkdownViewer._style_blockquotes(html: str) -> str`（Task 1 产出）。
- Produces: 渲染时 blockquote 显示为整块浅灰背景 + 左竖线。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_quote_rendering.py`（offscreen 集成测试，无需 GUI 事件循环）：

```python
import unittest

import markdown
from PySide6.QtGui import QTextDocument, QTextTable, QTextTableCellFormat

from md_viewer import MarkdownViewer


class TestQuoteRendering(unittest.TestCase):
    def test_quote_renders_as_styled_table(self):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        body = md.convert("> quote text")
        body = MarkdownViewer._style_blockquotes(body)
        html = MarkdownViewer.wrap_html(body)

        doc = QTextDocument()
        doc.setHtml(html)

        tables = [c for c in doc.rootFrame().childFrames()
                  if isinstance(c, QTextTable)]
        self.assertEqual(len(tables), 1)

        fmt = tables[0].format()
        self.assertEqual(fmt.background().color().name(), "#f6f8fa")
        self.assertEqual(fmt.border(), 0.0)

        cell_fmt = QTextTableCellFormat(tables[0].cellAt(0, 0).format())
        self.assertEqual(cell_fmt.leftBorder(), 4.0)
        self.assertEqual(cell_fmt.topBorder(), 0.0)
        self.assertEqual(cell_fmt.rightBorder(), 0.0)
        self.assertEqual(cell_fmt.bottomBorder(), 0.0)
        self.assertEqual(cell_fmt.leftPadding(), 16.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m unittest tests.test_quote_rendering -v
```

Expected: FAIL（`wrap_html` 尚未包含 `table.md-quote` 样式，table 背景为 NoBrush，断言 `#f6f8fa` 失败）。

- [ ] **Step 3: 实现代码**

**改动 1**：`md_viewer.py` 的 `reload_file()` 中，把这一行：

```python
        html_body = md.convert(normalized)
```

替换为：

```python
        html_body = md.convert(normalized)
        html_body = self._style_blockquotes(html_body)
```

**改动 2**：`md_viewer.py` 的 `wrap_html()` 中，把 `<style>` 里的这段 CSS：

```css
blockquote {
    border-left: 4px solid #ddd;
    margin: 0;
    padding: 0 16px;
    color: #666;
}
```

替换为：

```css
table.md-quote {
    background-color: #f6f8fa;
    border: none;
    width: 100%;
    margin: 8px 0;
}
table.md-quote td {
    border: none;
    border-left: 4px solid #ddd;
    padding: 8px 16px;
    color: #666;
}
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m unittest tests.test_quote_rendering -v
```

Expected: PASS，集成测试通过（table 背景 `#f6f8fa`、无表格边框、左竖线 4px、内边距 16px）。

- [ ] **Step 5: 回归测试**

```bash
python -m unittest discover -s tests -v
```

Expected: 全部通过（含 Task 1 的 3 个 `test_blockquote` 与图片功能的 5 个 `test_base_url`，共 9 个）。

- [ ] **Step 6: 手动视觉冒烟**

准备一个含引用的 md 文件（含单段、多段、嵌套 `>>` 引用），运行：

```bash
python md_viewer.py 你的含引用文件.md
```

Expected 验证清单：
1. 引用块显示整块浅灰背景 + 左侧竖线 + 内边距。
2. 引用文字为灰色 `#666`，正文仍为黑色。
3. 嵌套引用（`>>`）内外层各自整块背景。
4. 回归：正文、代码块、图片、目录边栏、搜索均正常。

（此步骤为人工视觉验证，若在子代理环境执行可跳过，留待人工验收。）

- [ ] **Step 7: 提交**

```bash
git add md_viewer.py tests/test_quote_rendering.py
git commit -m "feat: 引用块整块背景渲染并更新样式"
```

---

## 自审记录

- **Spec 覆盖**：spec 第 4.1 改动点 1（reload_file 后处理）→ Task 2 改动 1；改动点 2（`_style_blockquotes`）→ Task 1；改动点 3（CSS 新增/删除）→ Task 2 改动 2；第 5 节边界（嵌套/无引用）→ Task 1 单元测试覆盖；第 6 节测试（单元/offscreen/手动）→ 两任务对应。
- **占位符扫描**：无 TBD/TODO，所有步骤含完整代码或命令。
- **类型一致性**：`_style_blockquotes(html: str) -> str` 在 Task 1 定义、Task 2 调用，签名一致。
