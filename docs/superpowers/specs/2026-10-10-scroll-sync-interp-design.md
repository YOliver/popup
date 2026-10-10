# 滚动同步错位修复：映射懒刷新 + 视觉行单位 + 段内插值 设计

## 背景

打开编辑面板后，预览与编辑器的双向滚动同步严重错位：

- 在预览侧滚动：编辑器跳动无规律。
- 在编辑侧滚动：开头勉强对齐，越往后偏得越多。

复现文档：`失去的二十年.md`（2748 行、约 13 万字、1329 个进入映射的锚点、31 张图片，单行段落最长约 450 字）。

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
- 预览侧坐标 Y：像素 = `preview_sb.value()`；锚点的 Y 值 = `documentLayout().blockBoundingRect(blk).y()`。

### 2. 预览映射：完整构建 + 懒刷新 Y

实测完整构建 `_build_anchor_map`（Python 逐片段遍历）在复现文档上耗时 120.8ms，放在滚动回调里会造成明显卡顿。但宽度变化只会改变锚点所在块的 Y，不会改变锚点落在哪个块。因此把构建拆成两级：

**完整构建（只在内容变化时执行）**
- `_build_anchor_map(doc)` 拆分为：
  - `_collect_anchor_blocks(doc) -> (lines, blocks)`：遍历片段，找出锚点行号及其所在的 `QTextBlock`（即原来的遍历逻辑）。
  - `_anchor_block_ys(doc, blocks) -> ys`：对每个块取 `blockBoundingRect(blk).y()`，再做累计最大值处理（见第 4 节"单调性保护"）。
  - `_build_anchor_map` 保留为两者的组合，返回值 `(lines, ys)` 不变，`tests/test_anchor_map.py` 中的现有用例无需修改（新增用例见"测试"一节）。
- 锚点落在哪个块只取决于文档结构，与排版宽度无关（已实测：全宽与变窄后完整重建得到的 1329 个锚点行号完全相同），因此缓存块列表是安全的。
- `reload_file()` 调用 `_collect_anchor_blocks` 与 `_anchor_block_ys`，保存 `_anchor_lines / _anchor_blocks / _anchor_ys`，并清除脏标记。

**懒刷新 Y（宽度变化后执行）**
- 新增状态 `self._anchor_dirty = False` 和 `self._anchor_blocks = []`。
- 在 `init_ui` 中连接 `self.text_browser.document().documentLayout().documentSizeChanged`，回调只执行 `self._anchor_dirty = True`。拖动分隔条时可能每帧都触发，回调必须足够轻。
- 新增 `_ensure_anchor_map()`：若 `_anchor_dirty` 为真，则用缓存的 `_anchor_blocks` 调用 `_anchor_block_ys` 只重算 `_anchor_ys`（不重新遍历片段），然后清除脏标记。两个同步方法查表前都先调用它。

**清空映射**
- 预览文档还会在两处被 `setHtml` 替换且不重建映射：读文件失败（`md_viewer.py:922`）和帮助文档缺失（`md_viewer.py:1404`）。替换后缓存的 `QTextBlock` 会失效（可能指向错误的块），所以这两处在 `setHtml` 后调用 `_clear_anchor_map()`，清空三个列表并清除脏标记。清空后同步逻辑走现有的比例回退。
- 启动时的欢迎页（`md_viewer.py:488`）发生在任何映射构建之前，无需处理。

**已验证的前提与预期行为**
- `setHtml` 不会替换 `documentLayout` 对象（已实测），信号只需连接一次。
- `reload_file()` 返回后，预览还会再触发 1 次 `documentSizeChanged`（实测，来自延迟排版或图片加载），脏标记会被重新置为 True，下一次滚动时触发一次 Y 刷新。这属于预期行为，代价只是一次廉价的 Y 重算。

### 3. 编辑侧锚点坐标实时查询

不缓存编辑侧坐标。每次同步时调用 `_edit_anchor_points() -> (Es, Ys)`，它负责生成插值用的完整折线点：

1. 把 `_anchor_lines` 逐个转换成视觉行 E = `findBlockByNumber(line).firstLineNumber()`，与 `_anchor_ys` 一一对齐。
2. `findBlockByNumber` 返回无效块的锚点（编辑内容行数变少时会出现）连同对应的 Y 一起跳过。
3. 补首尾点（规则见第 4 节"端点补点"）。

返回的 Es、Ys 等长且已包含首尾补点，可直接传给 `_map_scroll`。这样编辑面板宽度变化时无需维护失效逻辑。实测 1329 个锚点耗时 1.7ms；编辑面板加宽后 `firstLineNumber` 会立即更新（总视觉行从 2801 变为 2792）。

### 4. 分段线性插值

新增纯函数（静态方法）：

```python
@staticmethod
def _interp(xs, ys, x):
    """分段线性插值：xs 非降序，返回 x 在 (xs, ys) 折线上对应的 y。
    x <= xs[0] 返回 ys[0]；x >= xs[-1] 返回 ys[-1]；
    x 恰好等于一组重复节点（相邻 xs 相等）的值时，返回最后一个等值节点的 y。"""
```

使用 `bisect_right` 定位区间：`i = bisect_right(xs, x)`，在 `[xs[i-1], xs[i])` 区间内插值。由于 `bisect_right` 会越过所有等值节点，零宽区间 `xs[i-1] == xs[i]` 永远不会被选中，因此不会除零；x 等于重复值时自然落在最后一个等值节点上。

端点补点（在 `_edit_anchor_points` 中完成，保证首尾也能插值，并保持单调）：

- 首部插入 `(0, 0)`。
- 尾部追加 `(编辑器总视觉行数 edit_doc.lineCount(), 预览文档高度 doc.size().height())`。两者都是内容坐标，必然不小于最后一个锚点。
- 目标值超出滚动条范围时，由 `setValue` 自行截断。

零宽区间的来源：首部补点 `(0, 0)` 与第一个锚点重合（第一个锚点的 E 通常为 0）；单调性保护把倒退的 Y 抹平。（同一个块中的多个锚点只取第一个，不会产生重复 Y。）以上情况都由 `_interp` 的重复节点规则处理。

**单调性保护**

`_interp` 依赖 xs 非降序。当前复现文档两侧均单调（已实测），但其他文档可能出现 Y 倒退（例如浮动元素），此时二分查找会落入错误区间。`_anchor_block_ys` 在返回前对 Y 做累计最大值处理（`y_i = max(y_i, y_{i-1})`），倒退的锚点会退化成零宽区间，由插值规则自然处理。编辑侧 E 来自递增行号的 `firstLineNumber`，本身单调，无需处理。

**底部对齐规则**

插值按"视口顶部"对齐，两侧滚动条最大值对应的内容位置不同（实测编辑器 max=2766，末锚点在 2788）。因此一侧滚到底时，另一侧可能还差一截。规则：源滚动条 `maximum() > 0` 且 `value() >= maximum()` 时，目标直接设为 `dst.maximum()`，不走插值。

**统一入口**

把底部规则和插值合成一个纯函数，两个方向共用，只交换参数：

```python
@staticmethod
def _map_scroll(value, src_max, dst_max, xs, ys):
    """把源滚动条值映射为目标滚动条值。
    src_max > 0 且 value >= src_max 时返回 dst_max（底部对齐）；
    否则返回 round(_interp(xs, ys, value))。"""
```

- 编辑→预览：`preview_sb.setValue(_map_scroll(edit_sb.value(), edit_sb.maximum(), preview_sb.maximum(), Es, Ys))`
- 预览→编辑：`edit_sb.setValue(_map_scroll(preview_sb.value(), preview_sb.maximum(), edit_sb.maximum(), Ys, Es))`

其中 Es / Ys 来自 `_edit_anchor_points()`，已包含首尾补点。

**比例回退的条件**

- `_anchor_lines` 为空（文档没有锚点，或映射已被 `_clear_anchor_map` 清空）：沿用现有的 `_proportional_value`。
- 锚点非空但在编辑侧全部无效：`_edit_anchor_points` 只返回首尾两个补点，插值结果即为两侧内容的线性比例，效果等同于比例同步，无需单独分支。

### 5. 打开面板时的首次定位

`toggle_edit_panel` 中原来的 `self._sync_preview_to_edit(0)` 改为 `QTimer.singleShot(0, lambda: self._sync_preview_to_edit(0))`，等预览因变窄重新排版、编辑器加载文本完成布局后再定位。由于有懒刷新，即使时序有偏差，下一次滚动也会自动纠正。

### 6. 删除的代码

`_sync_preview_to_edit` 中基于 `blockBoundingGeometry(...).y() + edit_sb.value()` 的错误计算，以及两个方法中基于 `_nearest_anchor_index` 的块首对齐查表，全部由插值替代。`_nearest_anchor_index` 仅被这两个方法调用，替换后不再有调用方，连同其测试 `tests/test_anchor_index.py` 一并删除。

### 7. 已知行为（不处理）

- **部分锚点不进入映射**：复现文档共注入 1363 个锚点，映射中只有 1329 个。原因是同一个块中只取第一个锚点（nl2br 形成的多行段落、多行引用都属于这种情况）。插值可以覆盖这些空隙。
- **拖分隔条或调整窗口后不会立即重新对齐**：拖动本身不触发同步，下一次任一侧滚动时自动纠正。
- **预览滚动条范围滞后于排版**：实测刚变窄时预览文档高 128488，滚动条最大值仍为旧值 145206；处理完事件后才更新为 127782（= 128488 − 视口高 706）。因此排版刚变化时，底部对齐规则和打开面板时的首次定位可能读到旧的最大值，下一次滚动会自动纠正。
- **到底时最后一格会跳一下**：一侧滚到底时，另一侧从插值位置直接跳到底部。跳动幅度取决于两侧末尾内容疏密的差异。

## 改动范围

代码只修改 `md_viewer.py`（测试改动见"测试"一节）：

- `__init__`：新增 `_anchor_dirty`、`_anchor_blocks`
- `init_ui`：连接 `documentSizeChanged`
- `toggle_edit_panel`：延迟首次同步
- `_sync_preview_to_edit` / `_sync_edit_to_preview`：改为调用 `_map_scroll`
- `reload_file`：改用两级构建，保存 `_anchor_blocks`，清除脏标记；读文件失败分支调用 `_clear_anchor_map`
- `open_help_doc`：帮助文档缺失分支调用 `_clear_anchor_map`
- `_build_anchor_map`：拆分为 `_collect_anchor_blocks` + `_anchor_block_ys`，自身保留为组合
- 新增 `_interp`、`_map_scroll`、`_ensure_anchor_map`、`_edit_anchor_points`、`_clear_anchor_map`
- 删除 `_nearest_anchor_index`

## 测试

测试文件改动：`tests/test_scroll_sync.py`、`tests/test_anchor_map.py` 追加用例；删除 `tests/test_anchor_index.py`。

### 单元测试（`tests/test_scroll_sync.py` 追加）

`_interp` 纯函数：

- 区间中点插值正确
- x 小于首点、大于尾点时截断到端点
- 正好命中节点
- 重复节点不除零，x 等于重复值时返回最后一个等值节点的 y
- 只有单个点

`_map_scroll` 纯函数：

- 源在底部（`value >= src_max > 0`）时返回 `dst_max`
- `src_max == 0` 时不触发底部规则，走插值
- 非底部时结果等于 `round(_interp(...))`

### 集成测试（offscreen，文档层面，不断言像素）

现有测试都不会创建 `MarkdownViewer`。创建它会注册全局热键、建立托盘图标并读写 QSettings，对测试进程有副作用，因此集成测试只在 `QTextDocument` 层面进行，沿用 `tests/test_anchor_map.py` 现有的 `_doc()` 写法。

`tests/test_anchor_map.py` 追加：

- `_collect_anchor_blocks` 与旧行为一致：返回的行号与 `_build_anchor_map` 相同，块数与行号数相等。
- 单调性保护：把 `_collect_anchor_blocks` 得到的块列表倒序传给 `_anchor_block_ys`，断言输出非降。
- 宽度变化后只重算 Y 的结果正确：取得块列表后调用 `doc.setTextWidth()` 改变宽度，断言 `_anchor_block_ys(doc, blocks)` 与重新完整调用 `_build_anchor_map(doc)` 得到的 ys 相等。

不写单元测试、交给真实平台探针或手动冒烟验证的部分：`documentSizeChanged` 置脏、`_ensure_anchor_map` 清脏、`_clear_anchor_map` 在两个错误分支被调用。

### 真实平台探针（实现后执行，不入库）

用 `失去的二十年.md` 打开编辑面板：

- 改变分隔条宽度并处理事件后 `_anchor_dirty` 为 True；触发一次滚动同步后为 False。
- 懒刷新后的 `_anchor_ys` 与完整重建结果一致。
- 懒刷新耗时远小于完整构建（目标 < 10ms，对比完整构建 120ms）。
- 编辑器滚动到某个锚点块的 `firstLineNumber` 后，预览值约等于该锚点 Y；反向同理。
- 任一侧滚到底时，另一侧也在底部。

### 手动冒烟

用 `失去的二十年.md` 分别检查开头、中段、末尾三个位置：两侧滚轮滚动后对齐情况、长段落内部连续跟随、拖分隔条后继续滚动仍对齐、关闭再打开面板后定位正确。另外打开一个不存在的帮助文档后，两侧滚动不报错（走比例回退）。

offscreen 环境下字体度量不可信，像素级对齐只能靠真实平台探针和手动冒烟验证。
