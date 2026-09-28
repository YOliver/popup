# 段首两字缩进（首行缩进）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Popup 的 Markdown 预览中，把用户手动在段首打的 N 个全角空格（`U+3000`）忠实还原为首行缩进 N 个字。

**Architecture:** 在 `md_viewer.py` 的渲染管线中新增预处理 + 后处理。预处理 `_preserve_indent` 在 `md.convert()` 前把"行首连续 N 个全角空格"替换为内联占位标记 `<i data-indent="N"></i>`（markdown 原样保留）；后处理 `_apply_indent` 在 `md.convert()` 后把 `<p><i data-indent="N"></i>` 替换为 `<p style="text-indent:{N×em_px}px">`。`em_px` 由 `_body_em_px` 从正文字号（14px）度量得到。

**Tech Stack:** Python 3.8+、PySide6（Qt 富文本 `QTextDocument`）、python-markdown、标准库 `unittest`。

## Global Constraints

- 只改动 `md_viewer.py` 与新增测试文件，不触碰图片、目录、搜索、托盘等模块。
- 不引入新依赖（`QFontMetricsF` 属 PySide6 已有 API）。
- 代码注释与 git commit message 用中文。
- Qt 的 CSS 解析只支持 `text-indent` 的 `px` 单位，不支持 `em`；`em_px` 缺字形时回退 `14.0`。
- 仅处理行首为全角空格 `U+3000` 的行；半角空格、代码围栏内部、列表/引用/表格内的全角空格不处理。
- 测试用标准库 `unittest`；从仓库根目录运行（保证 `md_viewer` 可导入）。

---

### Task 1: 预处理 `_preserve_indent`

**Files:**
- Modify: `md_viewer.py`（在 `_normalize_list_indent` 之后、`_build_base_url` 之前新增方法）
- Test: `tests/test_indent.py`（新建，纯单元测试，无需 QApplication）

**Interfaces:**
- Consumes: 无（复用模块级 `re`）。
- Produces: `MarkdownViewer._preserve_indent(content: str) -> str`——输入 md 源文本，输出把"行首连续全角空格"替换为 `<i data-indent="N"></i>` 后的文本；跳过代码围栏内部行。

- [ ] **Step 1: 编写失败测试**

创建 `tests/test_indent.py`：

```python
import unittest

from md_viewer import MarkdownViewer


class TestPreserveIndent(unittest.TestCase):
    def test_two_fullwidth_spaces_become_marker(self):
        out = MarkdownViewer._preserve_indent("\u3000\u3000这是正文。")
        self.assertEqual(out, '<i data-indent="2"></i>这是正文。')

    def test_single_fullwidth_space(self):
        out = MarkdownViewer._preserve_indent("\u3000正文")
        self.assertEqual(out, '<i data-indent="1"></i>正文')

    def test_no_indent_unchanged(self):
        self.assertEqual(MarkdownViewer._preserve_indent("正文"), "正文")

    def test_halfwidth_space_not_touched(self):
        self.assertEqual(MarkdownViewer._preserve_indent("  正文"), "  正文")

    def test_code_fence_content_not_replaced(self):
        content = "```\n\u3000\u3000code line\n```"
        self.assertEqual(MarkdownViewer._preserve_indent(content), content)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_indent.TestPreserveIndent -v`
Expected: FAIL，报 `AttributeError: type object 'MarkdownViewer' has no attribute '_preserve_indent'`（或 import 失败）。

- [ ] **Step 3: 编写最小实现**

在 `md_viewer.py` 的 `_normalize_list_indent` 方法之后（`return '\n'.join(out)` 与 `@staticmethod` 的 `_build_base_url` 之间）插入：

```python
    @staticmethod
    def _preserve_indent(content: str) -> str:
        """把行首连续 N 个全角空格替换为 <i data-indent="N"></i> 占位标记。

        python-markdown 会剥掉行首空白，Qt 也会剥掉段首全角空格，故在转换前
        用内联 HTML 占位。跳过代码围栏内部行（<pre><code> 内 Qt 会原样保留
        前导空格，替换反而会污染代码）。
        """
        out = []
        in_fence = False
        fence_marker = None
        fence_re = re.compile(r'^(```+|~~~+)')
        indent_re = re.compile(r'^(\u3000+)')
        for line in content.split('\n'):
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
            if in_fence:
                out.append(line)
                continue
            m = indent_re.match(line)
            if m:
                out.append('<i data-indent="%d"></i>' % len(m.group(1)) + line[m.end():])
            else:
                out.append(line)
        return '\n'.join(out)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_indent.TestPreserveIndent -v`
Expected: PASS，5 个测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_indent.py
git commit -m "feat: 新增 _preserve_indent 将行首全角空格转为占位标记"
```

---

### Task 2: 后处理 `_apply_indent`

**Files:**
- Modify: `md_viewer.py`（在 `_preserve_indent` 之后新增方法）
- Test: `tests/test_indent.py`（追加 `TestApplyIndent` 测试类）

**Interfaces:**
- Consumes: 无。
- Produces: `MarkdownViewer._apply_indent(html: str, em_px: float) -> str`——输入 markdown 输出的 HTML 与 `em_px`（一个汉字像素宽度），把 `<p><i data-indent="N"></i>` 替换为 `<p style="text-indent:%.1fpx">`（px 值 = N × em_px）。

- [ ] **Step 1: 编写失败测试**

在 `tests/test_indent.py` 末尾（`if __name__` 之前）追加：

```python
class TestApplyIndent(unittest.TestCase):
    def test_marker_becomes_text_indent(self):
        html = '<p><i data-indent="2"></i>正文</p>'
        out = MarkdownViewer._apply_indent(html, 14.0)
        self.assertEqual(out, '<p style="text-indent:28.0px">正文</p>')

    def test_plain_paragraph_unchanged(self):
        html = '<p>正文</p>'
        self.assertEqual(MarkdownViewer._apply_indent(html, 14.0), html)

    def test_three_fullwidth_spaces(self):
        html = '<p><i data-indent="3"></i>正文</p>'
        out = MarkdownViewer._apply_indent(html, 14.0)
        self.assertEqual(out, '<p style="text-indent:42.0px">正文</p>')
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_indent.TestApplyIndent -v`
Expected: FAIL，报 `AttributeError: ... no attribute '_apply_indent'`。

- [ ] **Step 3: 编写最小实现**

在 `md_viewer.py` 的 `_preserve_indent` 方法之后插入：

```python
    @staticmethod
    def _apply_indent(html: str, em_px: float) -> str:
        """把 <p><i data-indent="N"></i> 替换为 <p style="text-indent:%.1fpx">。

        Qt 的 CSS 解析不支持 em 单位（text-indent:2em 被忽略），仅支持 px，
        故用 em_px（一个汉字/全角空格的像素宽度）换算成 px。占位标记只出现在
        <p> 段首，故正则只匹配 <p>；其他容器内的空 <i> 标记渲染为零宽、不可见。
        """
        def repl(m):
            n = int(m.group(1))
            return '<p style="text-indent:%.1fpx">' % (n * em_px)
        return re.sub(r'<p><i data-indent="(\d+)"></i>', repl, html)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_indent -v`
Expected: PASS，`TestPreserveIndent` 与 `TestApplyIndent` 共 8 个测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_indent.py
git commit -m "feat: 新增 _apply_indent 将占位标记转为 text-indent"
```

---

### Task 3: 接入渲染管线、`_body_em_px` 与集成测试

**Files:**
- Modify: `md_viewer.py:48`（导入 `QFontMetricsF`）、`md_viewer.py` 的 `reload_file`（约 672-678 行）、`md_viewer.py`（在 `_apply_indent` 之后新增 `_body_em_px` 方法）
- Test: `tests/test_indent_rendering.py`（新建，offscreen 集成测试）

**Interfaces:**
- Consumes: Task 1 的 `_preserve_indent`、Task 2 的 `_apply_indent`。
- Produces: `MarkdownViewer._body_em_px(self) -> float`——返回正文字号下一个全角空格的像素宽度（约 14.0），缺字形回退 14.0。

> 说明：集成测试用固定 `em_px=14.0` 走完 `_preserve_indent → markdown → _apply_indent → wrap_html → QTextDocument` 全链路，验证渲染产物正确；`_body_em_px` 与 `reload_file` 的接线依赖真实 widget，不在 offscreen 下实例化 `MarkdownViewer`，由 Step 5 手动冒烟覆盖（与现有 `test_quote_rendering.py` 的测试惯例一致）。

- [ ] **Step 1: 编写集成测试**

创建 `tests/test_indent_rendering.py`：

```python
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import unittest

import markdown
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument

from md_viewer import MarkdownViewer

_app = QApplication.instance() or QApplication([])


class TestIndentRendering(unittest.TestCase):
    def _render(self, source, em_px):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        normalized = MarkdownViewer._preserve_indent(source)
        body = md.convert(normalized)
        body = MarkdownViewer._apply_indent(body, em_px)
        html = MarkdownViewer.wrap_html(body)
        doc = QTextDocument()
        doc.setHtml(html)
        return doc

    def test_indented_paragraph_gets_text_indent(self):
        doc = self._render("\u3000\u3000正文", 14.0)
        found = False
        blk = doc.begin()
        while blk.isValid():
            if blk.text() == "正文":
                self.assertEqual(blk.blockFormat().textIndent(), 28.0)
                found = True
            blk = blk.next()
        self.assertTrue(found)

    def test_unindented_paragraph_has_no_indent(self):
        doc = self._render("正文", 14.0)
        blk = doc.begin()
        while blk.isValid():
            if blk.text() == "正文":
                self.assertEqual(blk.blockFormat().textIndent(), 0.0)
            blk = blk.next()

    def test_code_fence_content_preserved(self):
        doc = self._render("```\n\u3000\u3000code line\n```", 14.0)
        blk = doc.begin()
        found = False
        while blk.isValid():
            if "\u3000\u3000code line" in blk.text():
                self.assertEqual(blk.blockFormat().textIndent(), 0.0)
                found = True
            blk = blk.next()
        self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行集成测试确认通过（依赖 Task 1/2 已就绪）**

Run: `python -m unittest tests.test_indent_rendering -v`
Expected: PASS，3 个测试通过（若失败，说明 Task 1/2 未完成，先回去补）。

- [ ] **Step 3: 接入渲染管线并实现 `_body_em_px`**

3a. 修改 `md_viewer.py:48` 导入，追加 `QFontMetricsF`：

```python
from PySide6.QtGui import QAction, QIcon, QTextDocument, QTextCursor, QFontMetricsF
```

3b. 在 `md_viewer.py` 的 `reload_file` 中，把这段：

```python
        normalized = self._dedent_fenced_blocks(content)
        normalized = self._normalize_list_indent(normalized)
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        html_body = md.convert(normalized)
        html_body = self._style_blockquotes(html_body)
```

改为：

```python
        normalized = self._dedent_fenced_blocks(content)
        normalized = self._normalize_list_indent(normalized)
        normalized = self._preserve_indent(normalized)
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        html_body = md.convert(normalized)
        em_px = self._body_em_px()
        html_body = self._apply_indent(html_body, em_px)
        html_body = self._style_blockquotes(html_body)
```

3c. 在 `md_viewer.py` 的 `_apply_indent` 方法之后插入：

```python
    def _body_em_px(self) -> float:
        """返回正文字号下一个全角空格的像素宽度（约 1em），用于 text-indent 换算。

        命令行直接打开文件时，首次 reload 发生在 show() 之前，样式表尚未应用，
        font() 仍是默认字号。先 ensurePolished 强制应用样式表，保证度量到
        正确的 14px 正文字号；全角空格缺字形时回退 14.0。
        """
        self.text_browser.ensurePolished()
        em_px = QFontMetricsF(self.text_browser.font()).horizontalAdvance('\u3000')
        return em_px if em_px > 0 else 14.0
```

- [ ] **Step 4: 运行全部测试确认通过**

Run: `python -m unittest tests.test_indent tests.test_indent_rendering -v`
Expected: PASS，全部 11 个测试通过。

- [ ] **Step 5: 手动冒烟验证**

Run: `python md_viewer.py` 打开一份含 `　　`（两个全角空格）开头的正文段落的 md 文件，确认首行缩进两字、对齐精确；回归检查标题/列表/引用/代码块/图片显示不受影响。命令行直接打开文件（`python md_viewer.py your.md`）也确认缩进正确（覆盖 `ensurePolished` 的首次加载路径）。

- [ ] **Step 6: 提交**

```bash
git add md_viewer.py tests/test_indent_rendering.py
git commit -m "feat: 接入段首缩进管线并新增 _body_em_px 度量"
```
