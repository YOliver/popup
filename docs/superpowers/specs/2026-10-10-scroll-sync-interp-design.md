# 滚动同步错位修复：映射懒重建 + 视觉行单位 + 段内插值 设计

## 背景

打开编辑面板后，预览与编辑器的双向滚动同步严重错位：

- 在预览侧滚动：编辑器跳动无规律。
- 在编辑侧滚动：开头勉强对齐，越往后偏得越多。

复现文档：`失去的二十年.md`（2748 行、约 13 万字、1331 个锚点、31 张图片，单行段落最长约 450 字）。

## 根因（已在真实平台用探针实测确认）

### 根因 1：预览锚点映射过期

`_anchor_lines / _anchor_ys` 只在 `reload_file()` 中构建一次。打开编辑面板后预览从全宽变窄，文本重新换行，各锚点的真实 Y 变化了，但映射表没有重建。实测（预览宽 827px 时）：

| 锚点序号 | 旧 Y | 实际 Y |
|---|---|---|
| 10 | 618 | 685 |
| 665 | 55664 | 65326 |
| 1330 | 108354 | 128390 |

误差随位置线性增长，对应"越往后偏得越多"。拖动分隔条、调整窗口大小、图片异步加载完成也会导致同样的过期。

### 根因 2：预览→编辑混用了像素和行两种单位

`QPlainTextEdit` 的垂直滚动条以**视觉行**为单位（实测 max=2766，总视觉行 2801），不是像素。`_sync_preview_to_edit`（`md_viewer.py:859`）把 `blockBoundingGeometry(blk).y()`（像素，且相对当前首个可见块计算）和 `edit_sb.value()`（行）相加后作为滚动条目标值，结果没有意义，对应"无规律"。

### 根因 3（次要）：只按块首对齐

锚点只在块首。长段落在源码中占 1 行，在预览中可能有十几行。段内滚动时对侧停住不动，到下一个块才跳过去。

## 目标

- 两侧任一侧滚动时，对侧都按相同的内容位置跟随，整篇文档内误差不累积。
- 在长段落内部滚动时，对侧连续跟随，不跳变。
- 预览宽度变化（打开/关闭面板、拖分隔条、改窗口大小、图片加载）后映射自动保持正确。

## 不在范围内

- 编辑器中有未保存修改、行号与预览不一致的情况：保持现状（保存后 `reload_file` 会重建映射）。
- 无锚点时的比例回退逻辑 `_proportional_value`：保持不变。

## 设计

### 1. 统一坐标

两侧都采用"视口顶部所在的内容位置"：

- 编辑侧坐标 E：视觉行号 = `edit_sb.value()`；锚点的 E 值 = `findBlockByNumber(line).firstLineNumber()`。
- 预览侧坐标 Y：像素 = `preview_sb.value()`；锚点的 Y 值 = `documentLayout().blockBoundingRect(blk).y()`（沿用 `_build_anchor_map`）。

### 2. 预览映射懒重建

- 新增状态 `self._anchor_dirty = False`。
- 在 `init_ui` 中连接 `self.text_browser.document().documentLayout().documentSizeChanged`，回调只执行 `self._anchor_dirty = True`，不做重计算。拖动分隔条时可能每帧都触发，所以回调必须足够轻。
- 新增 `_ensure_anchor_map()`：若 `_anchor_dirty` 为真，则调用 `_build_anchor_map` 重建 `_anchor_lines / _anchor_ys`，然后清除脏标记。两个同步方法在查表前都先调用它。
- `reload_file()` 构建映射后清除脏标记（`setHtml` 本身会触发 `documentSizeChanged`）。
- 前提：`setHtml` 不会替换 `documentLayout` 对象，信号连接一次即可长期有效。实现时需在真实平台验证。若不成立，改为在 `reload_file` 中每次 `setHtml` 后重新连接。

### 3. 编辑侧锚点坐标实时查询

不缓存编辑侧坐标。每次同步时用 `_edit_anchor_points()` 把 `_anchor_lines` 逐个转换成视觉行 E；`findBlockByNumber` 返回无效块的锚点（编辑内容行数变少时会出现）直接跳过，同时也跳过对应的 Y。这样编辑面板宽度变化时无需维护失效逻辑。规模约 1300 次 C++ 调用，每次滚动的开销在毫秒级，可以接受。

### 4. 分段线性插值

新增纯函数（静态方法）：

```python
@staticmethod
def _interp(xs, ys, x):
    """分段线性插值：xs 非降序，返回 x 在 (xs, ys) 折线上对应的 y。
    x <= xs[0] 返回 ys[0]；x >= xs[-1] 返回 ys[-1]；
    命中零宽区间（相邻 xs 相等）时返回该区间左端 y。"""
```

使用 `bisect` 定位区间。两侧共用同一个函数，只交换参数：

- 编辑→预览：`preview_sb.setValue(round(_interp(Es, Ys, edit_sb.value())))`
- 预览→编辑：`edit_sb.setValue(round(_interp(Ys, Es, preview_sb.value())))`

端点补点（保证首尾也能插值，并保持单调）：

- 首部插入 `(0, 0)`。
- 尾部追加 `(编辑器总视觉行数 edit_doc.lineCount(), 预览文档高度 doc.size().height())`。两者都是内容坐标，必然不小于最后一个锚点。
- 目标值超出滚动条范围时，由 `setValue` 自行截断。

相邻锚点 Y 相同（例如同一个 block 中存在多个锚点）不会造成除零，由 `_interp` 的零宽区间规则处理。

### 5. 打开面板时的首次定位

`toggle_edit_panel` 中原来的 `self._sync_preview_to_edit(0)` 改为 `QTimer.singleShot(0, lambda: self._sync_preview_to_edit(0))`，等预览因变窄重新排版、编辑器加载文本完成布局后再定位。由于有懒重建，即使时序有偏差，下一次滚动也会自动纠正。

### 6. 删除的代码

`_sync_preview_to_edit` 中基于 `blockBoundingGeometry(...).y() + edit_sb.value()` 的错误计算，以及两个方法中基于 `_nearest_anchor_index` 的块首对齐查表，全部由插值替代。`_nearest_anchor_index` 仅被这两个方法调用，替换后不再有调用方，连同其测试 `tests/test_anchor_index.py` 一并删除。

## 改动范围

仅修改 `md_viewer.py`：

- `__init__`：新增 `_anchor_dirty`
- `init_ui`：连接 `documentSizeChanged`
- `toggle_edit_panel`：延迟首次同步
- `_sync_preview_to_edit` / `_sync_edit_to_preview`：改为插值
- `reload_file`：清除脏标记
- 新增 `_interp`、`_ensure_anchor_map`、`_edit_anchor_points`
- 删除 `_nearest_anchor_index` 及 `tests/test_anchor_index.py`

## 测试

### 单元测试（`tests/test_scroll_sync.py` 追加）

`_interp` 纯函数：

- 区间中点插值正确
- x 小于首点、大于尾点时截断到端点
- 正好命中节点
- 零宽区间不除零，返回左端值
- 只有单个点

### 集成测试（offscreen，不断言像素）

- 用 `MarkdownViewer` 加载含锚点的小文档后，`_anchor_dirty` 为 False；改变 `text_browser` 宽度并处理事件后变为 True；调用 `_ensure_anchor_map()` 后变回 False，且映射长度不变、Y 单调非降。

### 真实平台探针（实现后执行，不入库）

用 `失去的二十年.md` 打开编辑面板：

- 懒重建后的 `_anchor_ys` 与新鲜构建的结果一致。
- 编辑器滚动到某个锚点块的 `firstLineNumber` 后，预览值约等于该锚点 Y；反向同理。

### 手动冒烟

用 `失去的二十年.md` 分别检查开头、中段、末尾三个位置：两侧滚轮滚动后对齐情况、长段落内部连续跟随、拖分隔条后继续滚动仍对齐、关闭再打开面板后定位正确。

offscreen 环境下字体度量不可信，像素级对齐只能靠真实平台探针和手动冒烟验证。
