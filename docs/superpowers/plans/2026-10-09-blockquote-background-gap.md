# 引用块背景断开（段间白缝）修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给引用块内段落取消外边距，消除多段引用渲染时的段间白缝。

**Architecture:** 在 `wrap_html()` 的 `td.md-quote-cell p` CSS 规则加一行 `margin: 0;`，让段落背景连成一片；版本号升到 v1.7.5 并同步 README 顶部版本号。

**Tech Stack:** Python 3.8+ / PySide6 (Qt6)

## Global Constraints

- 业务代码只改 `md_viewer.py`；测试加在 `tests/test_quote_rendering.py`；版本号改 `version.py` 和 `README.md`。不得改动其他文件。
- 不新增任何第三方依赖。
- 代码注释与 git commit message 一律中文。
- 版本号最终为 `"1.7.5"`。
- 不修改 `_style_blockquotes` 方法、不改变引用块背景色/左竖线样式。

---

### Task 1: CSS 修复（引用段落 margin 归零）

**Files:**
- Modify: `md_viewer.py`（`wrap_html` 的 CSS，约第 1435-1437 行）
- Test: `tests/test_quote_rendering.py`（新增一个测试方法）

**Interfaces:**
- Consumes: 无
- Produces: 无（CSS 行为变更）

- [ ] **Step 1: 写失败的测试**

在 `tests/test_quote_rendering.py` 的 `TestQuoteRendering` 类中，新增如下方法（复用文件顶部已有的 `markdown`、`QTextDocument` 导入与 `_app`）：

```python
    def test_quote_paragraphs_have_zero_margin(self):
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        body = md.convert("> para one\n>\n> para two")
        body = MarkdownViewer._style_blockquotes(body)
        html = MarkdownViewer.wrap_html(body)

        doc = QTextDocument()
        doc.setHtml(html)

        margins = []
        blk = doc.begin()
        while blk.isValid():
            if blk.text() in ("para one", "para two"):
                fmt = blk.blockFormat()
                margins.append((fmt.topMargin(), fmt.bottomMargin()))
            blk = blk.next()

        self.assertEqual(margins, [(0.0, 0.0), (0.0, 0.0)])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_quote_rendering.py::TestQuoteRendering::test_quote_paragraphs_have_zero_margin -v`
Expected: FAIL，断言失败（引用段落 margin 为默认非 0 值，如 `[(12.0, 12.0), (12.0, 12.0)]` 而非 `[(0.0, 0.0), ...]`）

- [ ] **Step 3: 改 CSS**

在 `md_viewer.py` 的 `wrap_html()` 中，把（约第 1435-1437 行）：

```css
td.md-quote-cell p {{
    background-color: #e8e8e8;
}}
```

改为：

```css
td.md-quote-cell p {{
    background-color: #e8e8e8;
    margin: 0;
}}
```

注意保留 f-string 的 `{{ }}` 转义形式（原文就是 `td.md-quote-cell p {{` / `}}`）。改之前先 `Read` 确认原文。

- [ ] **Step 4: 运行测试确认通过 + 全量回归**

Run: `python -m pytest tests/test_quote_rendering.py -v`
Expected: 全部通过（含新增方法，共 3 个测试）

Run: `python -m pytest tests/ -q`
Expected: 77 passed（原 76 + 新增 1）

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_quote_rendering.py
git commit -m "fix: 引用块段落 margin 归零，消除多段引用段间白缝"
```

---

### Task 2: 版本号 v1.7.5

**Files:**
- Modify: `version.py`
- Modify: `README.md`（顶部版本号）

**Interfaces:**
- Consumes: 无
- Produces: 无

- [ ] **Step 1: 更新 version.py**

把 `version.py` 内容改为：

```python
VERSION = "1.7.5"
```

- [ ] **Step 2: 更新 README.md 顶部版本号**

把第 3 行：

```
> 当前版本：v1.7.4
```

改为：

```
> 当前版本：v1.7.5
```

改之前先 `Read` README.md 确认原文。

- [ ] **Step 3: 提交**

```bash
git add version.py README.md
git commit -m "chore: 打包 v1.7.5（同步版本号）"
```

---

## Self-Review 结论

- **Spec 覆盖**：CSS `margin:0` 修复（Task 1）、版本号 v1.7.5 + README 顶部同步（Task 2）。spec 验证点「多段引用背景连续」映射到 Task 1 的 TDD 测试，「版本号」映射到 Task 2。
- **占位符**：无 TBD/TODO，改 CSS 与测试均给出完整代码。
- **类型一致性**：测试断言 `blockFormat().topMargin()/bottomMargin()` 为 `0.0`，与 CSS `margin: 0` 语义一致；`wrap_html` 的 f-string `{{ }}` 转义形式在 old/new 中保持一致。
