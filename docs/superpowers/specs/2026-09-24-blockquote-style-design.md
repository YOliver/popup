# 引用块（blockquote）视觉增强 — 设计文档

- 日期：2026-09-24
- 状态：待实现
- 关联版本：v1.5.3

## 1. 背景与问题

Markdown 引用块（`>` 开头的行）在 Popup 中渲染为灰色文字 + 轻微缩进，与正文几乎无区分，不够突出。主流 Markdown 软件的做法是给引用块一个整块浅色背景 + 左侧竖线。

Popup 用 Qt 富文本引擎（`QTextBrowser` / `QTextDocument`）渲染 HTML。**实测确认**：Qt 对 `blockquote` 的 `background-color` 只会降级为「文字级背景」（背景贴着文字宽度，短行末尾无色块），无法实现整块背景。而 Qt 对 `<table>` 的整块背景、单元格左侧边框、内边距支持完整。

## 2. 目标与非目标

### 目标

- 引用块显示为**整块浅灰背景 + 左侧竖线 + 内边距**，与正文形成清晰视觉区分。

### 非目标（YAGNI）

- 深色主题 / 主题切换。
- 背景颜色可配置。
- 其他块元素（列表、代码块、表格）的样式调整。
- 引用块内的特殊语法增强。

## 3. 方案概述

在渲染管线中新增一步 HTML 后处理：把 python-markdown 输出的 `<blockquote>...</blockquote>` 替换为等价的单列表格结构，利用 Qt 对表格的完整背景/边框/内边距支持，达到整块背景效果。

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
        """把 blockquote 转为单列表格，使 Qt 能渲染整块背景 + 左竖线。

        Qt 富文本引擎不支持 blockquote 的块级背景（会降级为文字级背景），
        而 table 支持整块背景/边框/内边距。python-markdown 输出的 blockquote
        标签无属性、格式固定，字符串替换安全；嵌套引用自然变为嵌套表格。
        """
        html = html.replace("<blockquote>", '<table class="md-quote"><tr><td>')
        html = html.replace("</blockquote>", "</td></tr></table>")
        return html
```

3. `wrap_html()` 的 `<style>` 中，**新增**以下样式，并**删除**原 `blockquote { ... }` 样式（转换后 HTML 中不再存在 blockquote 元素）：

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

### 4.2 关键细节

- 上述 CSS 属性均已实测在 Qt 中生效：`table` 整块背景（`background-color`）、`border: none`（消除表格默认边框线）、`td` 的 `border-left`（左侧竖线）、`td` 的 `padding`。
- `wrap_html()` 已有全局 `td { border: 1px solid #ddd }`（用于 markdown 表格），会命中引用块的单元格使其出现整圈边框。故 `table.md-quote td` 中必须用 `border: none` 先行覆盖，再设 `border-left`，才能得到「仅左侧竖线」（已实测：left=4px，top/right/bottom=0）。
- python-markdown 的 blockquote 输出标签固定为 `<blockquote>` / `</blockquote>`（无属性、无空白变体），`str.replace` 替换安全，不会误伤正文中的字面文本。
- 嵌套引用（`>>`）输出为嵌套的 `<blockquote>`，替换后成为嵌套 `<table>`；已实测 Qt 支持嵌套表格结构解析，内外层引用均获得背景。

### 4.3 数据流

```
Markdown → md.convert() → HTML（含 <blockquote>）
                          ↓
            _style_blockquotes() → <table class="md-quote">...
                          ↓
            setHtml() → Qt 渲染整块背景 + 左竖线
```

### 4.4 错误处理

纯字符串替换，无 I/O、无异常路径，无需额外 try/except。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 单段引用 `> text` | 整块背景 + 左竖线 + 内边距 |
| 多段引用（blockquote 内多个 `<p>`） | 同一单元格内多段，共用一块背景 |
| 嵌套引用 `>> text` | 内外层各自整块背景（嵌套表格） |
| 引用内含列表/代码块 | 在单元格内正常渲染 |
| 空引用 `>` | 生成空单元格，无异常 |
| 文档无引用 | `replace` 无匹配，HTML 不变，零影响 |

## 6. 测试计划

1. **单元测试**（`_style_blockquotes` 为纯函数，可自动化）：
   - 单个 blockquote → 替换为表格结构。
   - 嵌套 blockquote → 嵌套表格。
   - 无 blockquote → 字符串原样不变。
2. **offscreen 冒烟**：渲染含引用的 md，断言 `QTextDocument` 中生成 `QTextTable` 且 `frameFormat().background()` 为 `#f6f8fa`、单元格 `leftBorder` 为 4px。
3. **手动视觉冒烟**：打开含引用的真实 md 文件，确认整块背景、左竖线、文字颜色符合预期，并回归检查正文/代码块/图片显示不受影响。

## 7. 影响分析

- 改动集中在 `md_viewer.py` 的渲染管线（`reload_file` 后处理 + `wrap_html` CSS），不触碰图片、目录、搜索、托盘等模块。
- 不引入新依赖。
- 仅影响 blockquote 的视觉呈现，不改动其文本内容与语义；无引用时行为完全不变。
