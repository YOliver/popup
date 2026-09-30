# 图片与图注间距过大修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Markdown 图片段落与其后图注之间约 237px 的异常空白，使图片紧贴图注（正常约 12px 段落间距）。

**Architecture:** 根因是 `wrap_html()` 中 `body { line-height: 1.6 }` 被 Qt 富文本引擎作用于含图片的行，把行高放大 1.6 倍。方案为在渲染管线中新增一个纯字符串后处理静态方法 `_fix_image_line_height`，对「仅含图片（可带前置锚点）的 `<p>`」注入 `style="line-height:100%"` 覆盖继承的 1.6 倍，并在 `reload_file()` 的 `_apply_indent` 之后、`_style_blockquotes` 之前调用。

**Tech Stack:** Python 3.8+、PySide6（QTextBrowser）、python-markdown（tables/fenced_code/codehilite/toc/nl2br）、unittest（pytest 运行）。

## Global Constraints

- Python >= 3.8；依赖 `PySide6>=6.5`、`markdown>=3.4`（`requirements.txt`）。
- 代码注释与 git commit message 使用中文（用户全局规则）。
- 不引入新依赖。
- 锚点前缀 `popup-anchor-` 为既有约定，正则必须与之保持一致；`_build_anchor_map` 依赖该前缀，替换中必须原样保留锚点标签。
- 只影响「纯图片段落」的行高，正文段落 1.6 倍行距保持不变。

---

## File Structure

- **Modify `md_viewer.py`** — 新增 `MarkdownViewer._fix_image_line_height` 静态方法（HTML 后处理，与 `_style_blockquotes`/`_apply_indent` 同风格），并在 `reload_file()` 中接入调用。
- **Create `tests/test_image_line_height.py`** — 纯字符串单元测试，覆盖单图/多图/软换行/带锚点/图文混排/完整管线。

正则（最终定稿，已实测通过所有用例）：

```python
pattern = r'<p>((?:<a id="popup-anchor-\d+"></a>)*(?:<img [^>]*/>\s*(?:<br />\s*)?)+)</p>'
```

匹配「段落内容完全由零或多个 `popup-anchor-N` 空锚点 + 一张或多张 `<img>`（其间可夹 `<br />`）组成」的裸 `<p>`。

---

### Task 1: 新增 `_fix_image_line_height` 静态方法与单元测试

**Files:**
- Modify: `md_viewer.py:1104-1115`（在 `_build_base_url` 之后、`_style_blockquotes` 之前插入新方法）
- Create: `tests/test_image_line_height.py`

**Interfaces:**
- Consumes: `import re`（`md_viewer.py:11` 已导入，无需新增）；`markdown`（测试用）。
- Produces: `MarkdownViewer._fix_image_line_height(html: str) -> str`，供 Task 2 的 `reload_file()` 调用。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_image_line_height.py`：

```python
import unittest

import markdown

from md_viewer import MarkdownViewer


class TestFixImageLineHeight(unittest.TestCase):
    def test_single_image_gets_line_height(self):
        html = '<p><img alt="" src="a.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn(
            '<p style="line-height:100%"><img alt="" src="a.png" /></p>', out
        )

    def test_image_with_anchor_keeps_anchor(self):
        html = '<p><a id="popup-anchor-89"></a><img alt="图1-1" src="fig1-1.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn(
            '<p style="line-height:100%"><a id="popup-anchor-89"></a>'
            '<img alt="图1-1" src="fig1-1.png" /></p>',
            out,
        )

    def test_mixed_text_image_unchanged(self):
        html = '<p>文字 <img alt="" src="a.png" /> 文字</p>'
        self.assertEqual(MarkdownViewer._fix_image_line_height(html), html)

    def test_multiple_images_same_line(self):
        html = '<p><img alt="" src="a.png" /> <img alt="" src="b.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn('<p style="line-height:100%">', out)

    def test_multiple_images_soft_break_with_br(self):
        html = '<p><img alt="" src="a.png" /><br />\n<img alt="" src="b.png" /></p>'
        out = MarkdownViewer._fix_image_line_height(html)
        self.assertIn('<p style="line-height:100%">', out)
        self.assertIn('<br />', out)

    def test_markdown_pipeline_produces_line_height(self):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        body = md.convert("![图1-1 测试](fig1-1.png)")
        out = MarkdownViewer._fix_image_line_height(body)
        self.assertIn(
            '<p style="line-height:100%"><img alt="图1-1 测试" src="fig1-1.png" /></p>',
            out,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_image_line_height.py -v`
Expected: FAIL，报 `AttributeError: type object 'MarkdownViewer' has no attribute '_fix_image_line_height'`

- [ ] **Step 3: 写最小实现**

在 `md_viewer.py` 的 `_build_base_url` 方法之后（当前 `md_viewer.py:1115` 的 `return QUrl.fromLocalFile(base_dir)` 之后、`@staticmethod\n    def _style_blockquotes` 之前）插入：

```python
    @staticmethod
    def _fix_image_line_height(html: str) -> str:
        """给「仅含图片（可带前置锚点）的段落」注入 line-height:100%。

        Qt 会把 body 的 line-height 倍数作用于图片行，导致图片行高被放大 1.6 倍，
        图片下方出现大段空白。对纯图片段落覆盖为 100%，恢复图片实际行高。
        python-markdown 输出格式固定为 <p><a id="popup-anchor-N"></a><img .../></p>；
        同一段落可能含多张图片，nl2br 扩展会把段落内软换行转成 <br />，
        故用 (?:<img [^>]*/>\s*(?:<br />\s*)?)+ 匹配一张或多张图片（其间可夹 <br />）。
        """
        pattern = r'<p>((?:<a id="popup-anchor-\d+"></a>)*(?:<img [^>]*/>\s*(?:<br />\s*)?)+)</p>'
        return re.sub(pattern, r'<p style="line-height:100%">\1</p>', html)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_image_line_height.py -v`
Expected: PASS（6 个用例全部通过）

- [ ] **Step 5: 提交**

```bash
git add tests/test_image_line_height.py md_viewer.py
git commit -m "feat: 新增图片段落行高修复函数与单元测试"
```

---

### Task 2: 接入 `reload_file` 渲染管线并回归

**Files:**
- Modify: `md_viewer.py:849-851`（`reload_file()` 中的后处理调用序列）

**Interfaces:**
- Consumes: `MarkdownViewer._fix_image_line_height(html: str) -> str`（Task 1 产出）。
- Produces: 无新接口；`reload_file()` 渲染结果中纯图片段落带 `line-height:100%`。

- [ ] **Step 1: 在 `reload_file` 中接入调用**

把 `md_viewer.py:849-851` 当前内容：

```python
        em_px = self._body_em_px()
        html_body = self._apply_indent(html_body, em_px)
        html_body = self._style_blockquotes(html_body)
```

改为：

```python
        em_px = self._body_em_px()
        html_body = self._apply_indent(html_body, em_px)
        html_body = self._fix_image_line_height(html_body)
        html_body = self._style_blockquotes(html_body)
```

- [ ] **Step 2: 运行全量测试回归**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（含新增 6 个用例与既有锚点、缩进、滚动同步、代码块折行等测试）

- [ ] **Step 3: 手动冒烟验证**

运行 `start.bat`，打开 `C:/Users/oliveryin/Desktop/失去的二十年/失去的二十年.md`，确认：
- 图 1-1 及其后图注 `*图1-1 全球经常项目收支不平衡*` 紧贴（无大段空白）。
- 目录边栏跳转、滚动同步、Ctrl+F 搜索正常。

- [ ] **Step 4: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 渲染管线接入图片段落行高修复"
```
