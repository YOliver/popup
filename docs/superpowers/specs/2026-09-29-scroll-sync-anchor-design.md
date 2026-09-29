# 预览/编辑滚动同步锚点对齐 — 设计文档

- 日期：2026-09-29
- 状态：待实现
- 关联版本：v1.7.0

## 1. 背景与问题

当前预览与编辑面板的滚动同步用全局比例映射（`_proportional_value`：`目标值 = 源滚动比例 × 目标总高`），其隐含前提是**两侧内容高度成固定比例**。该前提不成立：

- 编辑面板（`QPlainTextEdit` 纯文本）行高固定，高度 ≈ 行数，线性。
- 预览面板（`QTextBrowser` 渲染 Markdown）标题有上下边距、代码块有 12px 内边距、图片占真实像素、表格/引用/列表各有额外高度，视觉高度与源文行数严重非线性。

同一内容在两侧映射出的滚动比例不同，且「高度权重差异」逐块累积——越靠后偏差越大。用户反馈"两边内容越到后面越对不上、差距越来越大"，与此吻合。

## 2. 目标与非目标

### 目标

- 预览与编辑面板双向滚动同步达到**段落级对齐**：一侧当前正在看的段落，另一侧大致停在同段落附近，偏差控制在几行内，且**不再随文档长度累积**。
- 保持双向同步、实时触发（滚动条 `valueChanged`）、编辑器侧仅滚动不动光标、防死循环等既有行为。

### 非目标（YAGNI）

- 行级精确对齐（段落内部不追求逐行精确）。
- 表格、代码块内部逐行对齐（这两类结构内无锚点，靠相邻锚点插值，段落级已足够）。
- 同步开关、滚动位置持久化、章节级（仅标题）对齐——均沿用既有决策不做。

## 3. 方案概述

用**锚点插值映射**替代全局比例映射：

1. 渲染前，在每个 Markdown 块起始行注入零高锚点 `<a id="md-N"></a>`（N = 0-based 源行号），注入位置在块标记字符之后（或段落行首全角空格之后），不破坏 markdown 结构与现有段首缩进。
2. 渲染后，遍历预览 `QTextDocument` 定位每个锚点所在 block 的文档 Y，建立两个单调递增数组：`_anchor_lines[]`（源行号）与 `_anchor_ys[]`（预览 Y）。
3. 滚动同步改为查表：编辑→预览用「编辑器首可见块行号 → 最近锚点 → 预览 Y」；预览→编辑用「预览视口顶部 Y → 最近锚点 → 源行号 → 编辑器滚动位置」。

## 4. 详细设计

### 4.1 锚点注入（纯函数 `_inject_anchors(content)`，`md.convert` 之前）

**管线位置**：在 `_dedent_fenced_blocks` / `_normalize_list_indent` 之后、`_preserve_indent` 之前。

**关键依据（已实测）**：空锚点 `<a id="md-N"></a>` 在 Qt 富文本中，其锚点属性会附着到紧随其后的第一个字符；渲染后通过 fragment 的 `charFormat().isAnchor()` + `anchorNames()` 检测，block 的文档 Y 用 `documentLayout().blockBoundingRect(block).y()` 取得，单调递增。锚点须插在**块标记字符之后**（而非行首），否则行首 `#`/`-`/`>` 前插入任何内容都会使 markdown 不再识别该结构。

**算法**（逐行，0-based 行号 `idx`，复用现有围栏跟踪模式 `fence_re = ^(```+|~~~+)`）：

| 行类型 | 处理 |
|--------|------|
| 代码围栏开/合行、围栏内行 | 原样保留，不注入 |
| 空行 | 原样保留 |
| 表格行（`lstrip` 后以 `\|` 开头） | 原样保留，不注入 |
| 标题 `^(\s{0,3})(#{1,6})\s+(.*)$` | `{缩进}{#号} <a id="md-{idx}"></a>{标题文本}` |
| 列表项 `^(\s{0,3})([-*+]|\d+[.)])\s+(.*)$` | `{缩进}{标记} <a id="md-{idx}"></a>{项文本}` |
| 引用 `^(\s{0,3})>\s?(.*)$` | `{缩进}> <a id="md-{idx}"></a>{引用文本}` |
| 普通段落（其余非空行） | 锚点插在行首连续全角空格之后：`{全角空格}<a id="md-{idx}"></a>{正文}`；无全角空格则直接 `{锚点}{行}` |

**与段首缩进的交互**：段落锚点插在全角空格之后，`_preserve_indent` 随后把行首全角空格替换为 `<i data-indent="N"></i>`，得到 `<i data-indent="N"></i><a id="md-N"></a>正文`；`_apply_indent` 的正则 `re.sub(r'<p><i data-indent="(\d+)"></i>', ...)` 仍匹配 `<p>` 后紧跟的 `<i>` 前缀（`<a>` 在其后，不受影响），缩进正常、锚点保留。

### 4.2 映射表构建 `_build_anchor_map()`

在 `reload_file` 的 `setHtml` 之后调用，遍历预览文档：

```python
def _build_anchor_map(self):
    doc = self.text_browser.document()
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
    self._anchor_lines = lines
    self._anchor_ys = ys
```

若 `lines` 为空（无锚点，如纯表格/纯代码块文档），滚动同步回退到现有比例映射。

### 4.3 最近锚点查找（纯函数 `_nearest_anchor_index(arr, target)`）

```python
@staticmethod
def _nearest_anchor_index(arr, target):
    """在非降序数组 arr 中返回最后一个 <= target 的索引；target 小于首元素返回 0。"""
    import bisect
    idx = bisect.bisect_right(arr, target) - 1
    return idx if idx >= 0 else 0
```

语义：段落级对齐下，「当前视口顶部」属于某个块，应定位到该块**起始锚点**，即「最后一个 <= target 的锚点」。

### 4.4 双向同步改造

**`_sync_preview_to_edit(value)`**（预览滚动 → 编辑器跟随）：

```python
if self._syncing: return
if not self.edit_panel.isVisible(): return
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

**`_sync_edit_to_preview(value)`**（编辑器滚动 → 预览跟随）：

```python
if self._syncing: return
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

### 4.5 关键细节

- **编辑器行号 = 源行号**：`QPlainTextEdit` 每 `\n` 一个 block，软折行不产生新 block，故 `firstVisibleBlock().blockNumber()` 即 0-based 源行号。`_inject_anchors` 的 `N` 与之一致（注入不增删行）。
- **锚点注入不改变行数**：锚点只往行内插入字符，`content.split('\n')` 行数与原始一致，行号不漂移。
- **编辑器侧文档坐标**：`blockBoundingGeometry(blk).y()` 返回视口坐标（随滚动变化），加 `edit_sb.value()` 得到稳定文档 Y；直接 `setValue` 到该 Y 即可让目标块成为首可见行。
- **映射表构建时机**：`QTextDocumentLayout` 为同步布局，`setHtml` 后立即可测量（已实测）。
- **回退路径**：`_anchor_lines` 为空时，两个 sync 方法退化为现有 `_proportional_value`，保证纯表格/纯代码块等无锚点文档行为不回退。
- **防循环**：沿用 `self._syncing` 标志；本设计中用 `try/finally` 确保 `_syncing` 复位（修正既有实现中 `setValue` 抛异常会导致标志卡死的隐患，属顺带加固）。

### 4.6 数据流

```
Markdown 源文件
  → _dedent_fenced_blocks → _normalize_list_indent
  → _inject_anchors（注入 <a id="md-N">）
  → _preserve_indent → md.convert → _apply_indent → _style_blockquotes
  → setHtml → _build_anchor_map（构建 _anchor_lines/_anchor_ys）

编辑滚动 → firstVisibleBlock().blockNumber() → _nearest_anchor_index(_anchor_lines)
        → _anchor_ys[i] → preview_sb.setValue
预览滚动 → sb.value() → _nearest_anchor_index(_anchor_ys)
        → _anchor_lines[i] → findBlockByNumber → blockBoundingGeometry → edit_sb.setValue
```

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 普通文档（标题/段落/列表/引用/代码块混合） | 段落级对齐，偏差几行内且不累积 |
| 代码块内部（编辑器 N 行 ↔ 预览 1 个 pre 块） | 无锚点，靠前后相邻锚点插值，段落级可接受 |
| 表格（多行 ↔ 1 个 table） | 同上，靠相邻锚点插值 |
| 纯代码块/纯表格文档（无任何锚点） | 回退比例映射，行为等同现状 |
| 空文件/单屏短文 | 两侧 maximum=0，同步无害 |
| 段首全角空格缩进的段落 | 缩进保留，锚点在缩进后、正文前，映射正常 |
| 标题（toc 扩展会加 `id="_1"`） | `_1` 非 `md-` 前缀被忽略，仅取 `md-N` |
| 快速连续滚动 | 查表 + `_syncing` 防循环，无抖动回环 |
| 窗口缩放/刷新 | `reload_file` 重建映射表，位置不漂移 |

## 6. 测试计划

1. **纯函数单测（自动化）**：
   - `_inject_anchors`：标题/列表/引用/段落各类型的锚点注入位置与行号；代码围栏内不注入；表格行不注入；段落全角空格后注入；无全角空格段落行首注入；空行不变。
   - `_nearest_anchor_index`：正常命中、target 过小返回 0、target 恰在锚点上、target 超出数组末尾返回末索引。调用方以 `if self._anchor_lines:` 保证非空，不测空数组。
2. **手动视觉冒烟（主要）**——因 `MarkdownViewer` 实例化会注册全局键盘钩子，且 offscreen 缺字体影响 `QPlainTextEdit` 度量，GUI 度量部分以手动验证为主：
   - 打开含多级标题、长段落、代码块、列表、引用的较长 md，滚动预览 → 编辑器首可见行与预览当前段落对齐，滚动到底部偏差不再累积。
   - 反向滚动编辑器 → 预览对齐。
   - 段首缩进段落、纯代码块文档、空文件、快速连续滚动均无异常。

## 7. 影响分析

- 改动集中在 `md_viewer.py`：新增 `_inject_anchors`、`_build_anchor_map`、`_nearest_anchor_index`，改造 `_sync_preview_to_edit` / `_sync_edit_to_preview`，新增 `_anchor_lines` / `_anchor_ys` 成员。
- 不引入新依赖（`bisect` 为标准库）。
- 锚点注入仅在渲染管线内生效，不影响编辑器原文、文件读写、保存、搜索、目录、托盘、热键。
- 无锚点文档自动回退比例映射，行为不退化。
