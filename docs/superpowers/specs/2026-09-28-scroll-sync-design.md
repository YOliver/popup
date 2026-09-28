# 左右面板滚动同步 — 设计文档

- 日期：2026-09-28
- 状态：待实现
- 关联版本：v1.7.0
- 依赖：`2026-09-28-txt-editor-panel-design.md`（右侧 txt 编辑面板）

## 1. 背景与问题

Popup 左侧预览（`QTextBrowser`，渲染后的 HTML）与右侧编辑面板（`QPlainTextEdit`，Markdown 源文件纯文本）各自独立滚动。用户在阅读预览时，无法快速在编辑器里定位到对应位置；反之亦然。希望加入双向滚动同步，让两侧滚动位置按比例保持对应。

## 2. 目标与非目标

### 目标

- 预览与编辑面板之间**双向**滚动同步。
- 采用**滚动比例粗同步**：按 `滚动条 value / maximum` 的比例互相映射。
- **实时**触发：滚动条 `valueChanged` 一变化即同步。
- 编辑器侧**仅滚动视图，不移动光标**（光标留在原处）。
- 防止双向同步引发的死循环。

### 非目标（YAGNI）

- 行级 / 块级精确映射（源文件行 ↔ 渲染块）。粗同步下渲染高度与文本行数不成比例（代码块、表格、图片会撑高预览），存在固有错位，属预期行为。
- 章节级（标题锚点）映射。
- 编辑器侧光标跟随定位。
- 滚动位置持久化 / 恢复。
- 用户可手动开关同步的开关项（默认开启，如后续有需求再加）。

## 3. 方案概述

两侧 `QScrollBar`（均为像素范围）各连接一个 `valueChanged` 处理器，用成员变量 `self._syncing` 作为防循环标志位。处理器把来源滚动条的当前比例 `value/maximum` 映射为目标滚动条的目标值。

## 4. 详细设计

### 4.1 改动点（仅 `md_viewer.py`）

1. `__init__` 中新增成员变量：`self._syncing = False`。

2. 在 `init_ui()` 中、编辑面板构建完成之后，连接两侧滚动条信号：

   ```python
   # 双向滚动同步（比例粗同步）
   self.text_browser.verticalScrollBar().valueChanged.connect(
       self._sync_preview_to_edit
   )
   self.edit_text.verticalScrollBar().valueChanged.connect(
       self._sync_edit_to_preview
   )
   ```

3. 新增方法与辅助函数：

   ```python
   @staticmethod
   def _proportional_value(src, dst):
       """按比例把 src 滚动条当前位置映射为 dst 滚动条的目标值"""
       ratio = src.value() / max(src.maximum(), 1)
       return round(ratio * dst.maximum())

   def _sync_preview_to_edit(self, value):
       """预览滚动 → 编辑器滚动条按比例跟随（仅滚动视图，不动光标）"""
       if self._syncing:
           return
       if not self.edit_panel.isVisible():
           return
       edit_sb = self.edit_text.verticalScrollBar()
       self._syncing = True
       edit_sb.setValue(
           self._proportional_value(self.text_browser.verticalScrollBar(), edit_sb)
       )
       self._syncing = False

   def _sync_edit_to_preview(self, value):
       """编辑器滚动 → 预览滚动条按比例跟随"""
       if self._syncing:
           return
       preview_sb = self.text_browser.verticalScrollBar()
       self._syncing = True
       preview_sb.setValue(
           self._proportional_value(self.edit_text.verticalScrollBar(), preview_sb)
       )
       self._syncing = False
   ```

### 4.2 关键细节

- **防循环机制**：`QScrollBar.setValue()` 会在值确实变化时同步发出 `valueChanged`。每个处理器入口先 `if self._syncing: return`，执行 `setValue` 期间把 `self._syncing` 置 `True`，结束后置回 `False`。被同步触发的那一侧处理器在标志位为 `True` 时直接返回，阻断回环。
- **映射公式**：`ratio = src.value() / max(src.maximum(), 1)`，`dst.setValue(round(ratio * dst.maximum()))`。`max(..., 1)` 防止 `maximum == 0`（未加载内容 / 空文件 / 内容不足一屏）时除零。
- **光标不动**：只操作滚动条 `value`，不触碰 `QPlainTextEdit` 光标或 `QTextBrowser` 光标。
- **面板隐藏保护**：`_sync_preview_to_edit` 在编辑面板不可见时直接返回，避免向隐藏面板的滚动条写入；`_sync_edit_to_preview` 由编辑器滚动条自身触发，编辑器必然可见，无需额外判断。

### 4.3 数据流

```
预览滚动 ──valueChanged──> _sync_preview_to_edit
                              │ (self._syncing==False 且面板可见)
                              ├─ 算 ratio = preview.value/maximum
                              └─ setValue(ratio * edit.maximum)
                                   │
                                   └─(触发 edit.valueChanged，但 self._syncing==True → 直接返回)

编辑器滚动 ──valueChanged──> _sync_edit_to_preview
                              │ (self._syncing==False)
                              ├─ 算 ratio = edit.value/maximum
                              └─ setValue(ratio * preview.maximum)
                                   │
                                   └─(触发 preview.valueChanged，但 self._syncing==True → 直接返回)
```

### 4.4 错误处理

- 除零保护：`max(maximum(), 1)`。
- 面板隐藏：预览侧处理器直接返回。
- 无文件 / 空内容：两侧滚动条 `maximum == 0`，映射结果 `setValue(0)`，无害。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 编辑面板隐藏时滚动预览 | 预览正常滚动，编辑器侧不同步 |
| 未打开文件 | 两侧滚动条 `maximum == 0`，同步无害，不报错 |
| 空文件 | 同上，`setValue(0)`，无异常 |
| 内容不足一屏（无滚动条） | `maximum == 0`，不触发实际滚动 |
| 快速连续滚动 | 实时跟随；标志位保证不形成回环抖动 |
| 双向同时滚动（不可能，单线程事件循环） | 同一时刻只处理一侧信号 |
| 编辑器侧光标位于视口外 | 滚动不移动光标，光标保持原位置 |

## 6. 测试计划

1. **手动冒烟（主要）**——因 `MarkdownViewer` 实例化会注册全局键盘钩子，无法在 offscreen 下安全实例化，本功能以手动验证为主：
   - 打开 md → 点"编辑"显示面板 → 滚动预览 → 编辑器滚动条按比例跟随。
   - 滚动编辑器 → 预览滚动条按比例跟随。
   - 隐藏面板 → 滚动预览 → 编辑器侧无变化。
   - 快速来回滚动 → 无死循环、无卡死、无抖动回环。
   - 空文件 / 单屏短文 → 无报错、无异常滚动。
2. **可离线验证点**：`_proportional_value` 为纯函数，可单独单测比例换算与除零保护。

## 7. 影响分析

- 改动集中在 `md_viewer.py`：新增 1 个成员变量、1 个静态辅助函数、2 个信号处理器与 2 行信号连接，不触碰渲染管线、目录、搜索、托盘、热键等模块。
- 不引入新依赖（`QScrollBar` 为 PySide6 已有 API）。
- **前置依赖**：本功能依赖右侧编辑面板（`self.edit_panel` / `self.edit_text`）已实现。若编辑面板尚未落地，本同步无法工作。
- 默认开启、无 UI 开关，对现有用户零感知变化（编辑面板默认隐藏，同步仅在面板可见时生效）。
