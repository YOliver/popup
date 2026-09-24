# 引用块（blockquote）视觉增强 — 设计文档

- 日期：2026-09-24
- 状态：已实现
- 关联版本：v1.5.3

## 1. 背景与问题

Markdown 引用块（`>` 开头的行）在 Popup 中渲染为灰色文字 + 轻微缩进，与正文几乎无区分，不够突出。主流 Markdown 软件的做法是给引用块一个浅色背景 + 左侧竖线。

Popup 用 Qt 富文本引擎（`QTextBrowser` / `QTextDocument`）渲染 HTML。经像素级实测，Qt 引擎对背景的绘制能力如下：

| 背景位置 | 数据层 | 实际渲染 |
|---------|--------|---------|
| `<table>` / `<td>` 的 `background-color` | 有值 | **不绘制** |
| 段落 `<p>` 的 `background-color`（block 级） | 有值 | ✅ 绘制（覆盖文字行宽度） |
| `<td>` 的 `border-left`（左侧竖线） | 有值 | ✅ 绘制 |

即：Qt 富文本引擎**不渲染表格/单元格的背景**，但渲染段落（block）背景和边框。因此「整块铺满的背景」在 Qt 下无法实现，可做到的是「左竖线 + 段落级浅灰背景」。

## 2. 目标与非目标

### 目标

- 引用块显示为**左侧竖线 + 段落级浅灰背景 + 内边距**，与正文形成清晰视觉区分。

### 非目标（YAGNI）

- 整块铺满的背景（Qt 引擎不支持表格背景渲染，属技术限制）。
- 深色主题 / 主题切换。
- 背景颜色可配置。
- 其他块元素（列表、代码块、表格）的样式调整。

## 3. 方案概述

在渲染管线中新增一步 HTML 后处理：把 python-markdown 输出的 `<blockquote>...</blockquote>` 替换为单列表格结构。表格用于提供**左侧竖线**（`td` 的 `border-left`，Qt 能渲染）；背景由**引用块内段落 `<p>` 的 block 级背景**提供（Qt 能渲染）。

## 4. 详细设计

### 4.1 改动点（仅 `md_viewer.py`）

1. `reload_file()` 中，`md.convert()` 之后、`setHtml()` 之前，对 HTML 做后处理：

```python
html_body = md.convert(normalized)
html_body = self._style_blockquotes(html_body)
```

2. 新增静态方法 `_style_blockquotes`（放在 `_build_base_url` 之后）：

```python
    @staticmethod
    def _style_blockquotes(html: str) -> str:
        """把 blockquote 转为单列表格，使 Qt 能渲染左竖线 + 段落背景。

        Qt 富文本引擎不渲染 table/td 的背景（仅渲染段落 block 背景与边框），
        故用 td 的 border-left 提供左竖线，背景由 td 内段落 p 的 block 背景
        提供。python-markdown 输出的 blockquote 标签无属性、格式固定，字符串
        替换安全；嵌套引用自然变为嵌套表格。
        """
        html = html.replace(
            "<blockquote>",
            '<table class="md-quote"><tr><td class="md-quote-cell">',
        )
        html = html.replace("</blockquote>", "</td></tr></table>")
        return html
```

3. `wrap_html()` 的 `<style>` 中，**新增**以下样式，并**删除**原 `blockquote { ... }` 样式（转换后 HTML 中不再存在 blockquote 元素）：

```css
table.md-quote {
    border: none;
    width: 100%;
    margin: 8px 0;
}
td.md-quote-cell {
    border: none;
    border-left: 4px solid #ddd;
    padding: 8px 16px;
    color: #666;
}
td.md-quote-cell p {
    background-color: #e8e8e8;
}
```

### 4.2 关键细节

- **背景不能放 table/td 层**：Qt 对 `<table>`/`<td>` 的 `background-color` 只在数据层（`frameFormat().background()`）有值，渲染层不绘制（像素级实测确认）。必须放在段落 `<p>` 的 block 层才会绘制。
- **背景色 `#e8e8e8`**：比最初设计的 `#f6f8fa` 深，因为 block 背景只覆盖文字行宽度，浅色在纯白底上几乎不可见。
- **左竖线走边框**：`td.md-quote-cell` 的 `border-left: 4px solid #ddd`（Qt 渲染边框）。`wrap_html()` 已有全局 `td { border: 1px solid #ddd }`（用于 markdown 表格），必须用 `border: none` 先行覆盖再设 `border-left`，否则整圈边框。
- **避免误伤内嵌表格**：`td.md-quote-cell` 用 class 选择器（而非 `table.md-quote td` 后代选择器），切断对引用块内嵌 markdown 表格的误伤（已实测内嵌表格保持 1px 全边框）。
- **python-markdown 标签固定**：blockquote 输出标签固定为 `<blockquote>` / `</blockquote>`（无属性），`str.replace` 替换安全。
- **嵌套引用**：`>>` 输出嵌套 `<blockquote>`，替换后为嵌套 `<table>`，内外层段落各自获得背景与左竖线。

### 4.3 数据流

```
Markdown → md.convert() → HTML（含 <blockquote>）
                          ↓
            _style_blockquotes() → <table class="md-quote">（左竖线容器）
                          ↓
            setHtml() → Qt 渲染：td 左竖线 + 段落 block 背景
```

### 4.4 错误处理

纯字符串替换，无 I/O、无异常路径，无需额外 try/except。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 单段引用 `> text` | 左竖线 + 段落浅灰背景 + 内边距 |
| 多段引用（blockquote 内多个 `<p>`） | 各段各自背景，共用左竖线 |
| 嵌套引用 `>> text` | 内外层各自左竖线 + 段落背景（嵌套表格） |
| 引用内嵌 markdown 表格 | 表格保持 1px 全边框，不被误伤 |
| 引用内含列表/代码块 | 正常渲染（列表/代码块自身无引用背景，属已知局限） |
| 空引用 `>` | 生成空单元格，无异常 |
| 文档无引用 | `replace` 无匹配，HTML 不变，零影响 |

## 6. 测试计划

1. **单元测试**（`_style_blockquotes` 为纯函数，可自动化）：
   - 单个 blockquote → 替换为表格结构（含 `td class="md-quote-cell"`）。
   - 嵌套 blockquote → 嵌套表格。
   - 无 blockquote → 字符串原样不变。
2. **offscreen 集成测试**：渲染含引用的 md，断言 `QTextDocument` 中生成 `QTextTable`、单元格 `leftBorder` 为 4px（其他三边 0）、引用段落 block 的 `background` 为 `#e8e8e8`；并验证引用内嵌表格不被误伤。
3. **手动视觉冒烟**：打开含引用的真实 md 文件，确认左竖线、段落浅灰背景、文字颜色符合预期，并回归检查正文/代码块/图片显示不受影响。

## 7. 影响分析

- 改动集中在 `md_viewer.py` 的渲染管线（`reload_file` 后处理 + `wrap_html` CSS），不触碰图片、目录、搜索、托盘等模块。
- 不引入新依赖。
- 仅影响 blockquote 的视觉呈现，不改动其文本内容与语义；无引用时行为完全不变。
