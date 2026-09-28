# 段首两字缩进（首行缩进）— 设计文档

- 日期：2026-09-28
- 状态：待实现
- 关联版本：v1.5.3（功能落地后建议升至 v1.5.4）

## 1. 背景与问题

用户的书稿 Markdown 遵循中文排版惯例——**每段首行缩进两个汉字**。用户手动在段首打全角空格 `U+3000`（通常打两个，与两个汉字对齐）实现缩进，但 Popup 预览中缩进丢失。

经实测，缩进丢失有两层原因：

1. **python-markdown 剥空白**：转换时剥掉行首空白（全角空格、半角空格均被删）。
2. **Qt 富文本引擎剥空白**：即使绕过 markdown，`QTextDocument` 也会剥掉 `<p>` 段首的所有空白字符。

实测结论：

| 段首字符 | Qt 渲染结果 |
|---------|------------|
| 全角空格 `U+3000` | 被删除 |
| em-space `U+2003` / en-space `U+2002` | 被删除 |
| `&#12288;`（U+3000 实体） | 被删除 |
| `&nbsp;`（`U+00A0`） | ✅ 保留，但为半字宽 |

即：**Qt 无法原样保留全角空格**。`&nbsp;` 虽能保留但只有半字宽，凑不出精确"两字缩进"。

进一步实测发现：Qt 的 CSS 解析**支持 `text-indent`，但只认 `px` 单位，不认 `em` 单位**（`text-indent:2em` 被忽略，`text-indent:28px` 正常生效）。`text-indent` 只缩进首行，正符合"首行缩进"。因此正确做法是：把"行首 N 个全角空格"转换为该段 `<p>` 的 `text-indent: N × em_px px`，其中 `em_px` = 一个汉字的像素宽度（约等于正文字号）。

## 2. 目标与非目标

### 目标

- 忠实还原用户手动打的段首缩进：行首 N 个全角空格 → 该段首行缩进 N 个字，视觉与"打 N 个全角空格"一致且对齐精确。
- 用户仍通过手动打空格的数量控制缩进宽度（符合其"缩进不对就自己补空格"的习惯）。

### 非目标（YAGNI）

- 对**所有**正文段落自动加固定缩进（用户明确选择"保留我打的空格"）。
- 处理段落中间的空白（HTML 折叠多空格是通用行为，非本需求）。
- 处理半角空格缩进（用户确认用全角空格；半角行首空格有 markdown 结构含义，不触碰）。
- 深色主题 / 缩进宽度可配置。

## 3. 方案概述

在渲染管线中新增一步**预处理**和一步**后处理**：

1. **预处理 `_preserve_indent(content)`**（`md.convert()` 之前）：把每行"行首连续 N 个全角空格"替换为内联占位标记 `<i data-indent="N"></i>`。python-markdown 将其视为内联 HTML 原样保留，并包进 `<p>`。
2. **后处理 `_apply_indent(html, em_px)`**（`md.convert()` 之后）：把 `<p><i data-indent="N"></i>` 替换为 `<p style="text-indent:{N×em_px}px">`。

已实测：`<i data-indent="2"></i>正文` 经 markdown 稳定输出 `<p><i data-indent="2"></i>正文</p>`；`text-indent:28px` 在 Qt 中正确落到 `blockFormat().textIndent()=28`。

## 4. 详细设计

### 4.1 改动点（仅 `md_viewer.py`）

1. `reload_file()` 中，在 `_dedent_fenced_blocks` / `_normalize_list_indent` 之后、`md.convert()` 之前增加预处理；在 `md.convert()` 之后、`_style_blockquotes` 之前增加后处理：

```python
normalized = self._dedent_fenced_blocks(content)
normalized = self._normalize_list_indent(normalized)
normalized = self._preserve_indent(normalized)
md = markdown.Markdown(...)
html_body = md.convert(normalized)
em_px = self._body_em_px()
html_body = self._apply_indent(html_body, em_px)
html_body = self._style_blockquotes(html_body)
```

2. 新增静态方法 `_preserve_indent`（放在 `_normalize_list_indent` 之后），仅跳过代码围栏内部行，其余行把行首全角空格转成占位标记：

```python
@staticmethod
def _preserve_indent(content: str) -> str:
    """把行首连续 N 个全角空格替换为 <i data-indent="N"></i> 占位标记。

    python-markdown 会剥掉行首空白，Qt 也会剥掉段首全角空格，故在转换前
    用内联 HTML 占位。跳过代码围栏内部行（<pre><code> 内 Qt 会原样保留
    前导空格，替换反而会污染代码）。
    """
```

3. 新增方法 `_apply_indent`（放在 `_preserve_indent` 之后）：

```python
@staticmethod
def _apply_indent(html: str, em_px: float) -> str:
    """把 <p><i data-indent="N"></i> 替换为 <p style="text-indent:{N*em_px}px">。

    Qt 的 CSS 解析不支持 em 单位（text-indent:2em 被忽略），仅支持 px，
    故用 em_px（一个汉字/全角空格的像素宽度）换算成 px。
    """
```

4. 新增方法 `_body_em_px`（计算一个汉字的像素宽度）：

```python
def _body_em_px(self) -> float:
    """返回正文字号下一个汉字的像素宽度（约 1em），用于 text-indent 换算。"""
    # 命令行直接打开文件时，首次 reload 发生在 show() 之前，样式表尚未
    # 应用，font() 仍是默认字号。先 ensurePolished 强制应用样式表，保证
    # 度量到正确的 14px 正文字号。
    self.text_browser.ensurePolished()
    em_px = QFontMetricsF(self.text_browser.font()).horizontalAdvance('\u3000')
    return em_px if em_px > 0 else 14.0
```

并在文件顶部 `from PySide6.QtGui import ...` 处补 `QFontMetricsF`。

### 4.2 关键细节

- **占位标记选型**：`<i data-indent="N"></i>` 是内联空元素。`<i>` 不在 markdown 的 HTML 块标签列表，会被包进 `<p>` 且属性不丢；空 `<i>` 渲染零宽，即使后处理遗漏也不显示多余内容。
- **`text-indent` 用 px 不用 em**：Qt 富文本 CSS 子集不支持 `em`（实测 `text-indent:2em` 被忽略），只认 `px`。`1em` 在数值上等于正文字号（14px），一个汉字/全角空格即 1em 宽，故 `N` 个全角空格 → `N × em_px` px，对齐精确。
- **`em_px` 来源**：从 `self.text_browser.font()`（正文样式表固定 `font-size: 14px`）用 `QFontMetricsF.horizontalAdvance('\u3000')` 实测得到；测量前先 `ensurePolished()` 强制应用样式表（命令行直接打开文件时首次 reload 发生在 `show()` 之前，否则会度量到默认 9pt 字号）；全角空格缺字形时回退 `14.0`。
- **跳过围栏内部**：`<pre><code>` 内 Qt 原样保留前导空格（已实测），若替换围栏内的全角空格会污染代码，故 `_preserve_indent` 需像 `_normalize_list_indent` 一样跟踪围栏开合状态。
- **不设块标记黑名单**：全角空格本就不是 ASCII 空白，markdown 不会把 `　# 标题` / `　- 项` 识别为标题/列表，替换只会影响"该段是否缩进"。为最大化忠实还原（用户要求"如实地显示包括空格"），不做黑名单，避免误伤以数字/连字符开头的正文段落。
- **与现有步骤顺序**：先 `_dedent_fenced_blocks`（拍平围栏）、再 `_normalize_list_indent`、再 `_preserve_indent`；`_apply_indent` 放在 `_style_blockquotes` 之前，二者互不干扰（引用内缩进同样被转成 text-indent 后再包进表格单元格）。

### 4.3 数据流

```
Markdown → _dedent_fenced_blocks → _normalize_list_indent → _preserve_indent
                                                                  ↓
                                     （行首全角空格 → <i data-indent="N">）
                                                                  ↓
                                     md.convert() → HTML（含占位标记）
                                                                  ↓
                                     _apply_indent → <p style="text-indent:{N×em_px}px">
                                                                  ↓
                                     _style_blockquotes → Qt setHtml 渲染
```

### 4.4 错误处理

纯字符串/正则处理 + 一次字体度量，无 I/O、无异常路径；`_body_em_px` 对缺字形做 `14.0` 回退。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 段首两个全角空格 `　　` | 该段 `<p>` 得 `text-indent:2×em_px px`，缩进两字 |
| 段首一个 / 三个全角空格 | 分别 `1em` / `3em`（宽度由用户打的空格数决定） |
| 无缩进的普通段落 | 不受影响，无 `text-indent` |
| 标题 `# 标题`（无前导空格） | 不受影响 |
| 列表项 / 引用 / 表格行 | 不受影响（行首无全角空格） |
| 代码围栏内含全角空格 | 不替换，`<pre><code>` 原样保留空格 |
| `　# 标题`（全角空格 + 井号） | 视为缩进段落，`#` 作字面文本、带缩进（与 markdown 自身对全角空格行的处理一致） |
| 全角空格出现在段落中间 | 维持 Qt 既有归一化行为，不处理（非本需求） |
| 文档无任何全角空格缩进 | 两步处理均无匹配，HTML 不变，零影响 |

## 6. 测试计划

1. **单元测试**（`_preserve_indent` / `_apply_indent` 为纯函数，可自动化）：
   - 行首两个全角空格 → 生成 `<i data-indent="2"></i>`。
   - 代码围栏内的全角空格 → 不被替换。
   - `_apply_indent` 将 `<p><i data-indent="2"></i>` 替换为 `<p style="text-indent:28.0px">`（`em_px=14`），且不误伤无标记段落。
2. **offscreen 集成测试**：渲染含缩进的 md，断言 `QTextDocument` 中缩进段落的 `blockFormat().textIndent()` 等于 `N × em_px`，无缩进段落为 0，代码围栏内文本原样保留。
3. **手动视觉冒烟**：打开含两字缩进的书稿 md，确认首行缩进两字、对齐精确；回归检查标题/列表/引用/代码块/图片显示不受影响。

## 7. 影响分析

- 改动集中在 `md_viewer.py` 的渲染管线（`reload_file` 预处理 + 后处理 + 一个字体度量方法），不触碰图片、目录、搜索、托盘等模块。
- 不引入新依赖（`QFontMetricsF` 属 PySide6 已有 API）。
- 仅影响行首为全角空格的行，无全角空格缩进的文档行为完全不变。
