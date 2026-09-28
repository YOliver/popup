# 右侧 txt 编辑面板 — 设计文档

- 日期：2026-09-28
- 状态：待实现
- 关联版本：v1.6.0（功能落地后建议升至 v1.7.0）

## 1. 背景与问题

Popup 目前只能预览 Markdown 文件，无法直接修改源文件。用户希望在不离开 Popup 的情况下快速编辑原文：在菜单栏加一个"编辑"入口，点击后在窗口右侧弹出 txt 编辑面板，以纯文本方式打开当前文档，支持手动编辑与保存。

## 2. 目标与非目标

### 目标

- 菜单栏新增"编辑"菜单项，点击在 显示/隐藏 之间切换右侧编辑面板。
- 编辑面板以纯文本方式（txt）展示当前打开的 Markdown 源文件，可手动编辑。
- 支持保存（"保存"按钮 + `Ctrl+S`），保存写回原文件，并刷新左侧预览。
- 面板为右侧固定内嵌，宽度可拖拽，不可浮动、不可拖出。

### 非目标（YAGNI）

- 语法高亮、行号、撤销重做以外的富编辑能力（`QPlainTextEdit` 自带撤销/复制粘贴，够用）。
- 新建/另存为/多标签编辑。
- 编码自动探测（沿用现有 UTF-8 约定，与 `reload_file` 一致）。
- 未保存改动（dirty）状态标记与离开提醒。
- 编辑器的自动外部同步（外部改动时编辑器不自动重载，避免覆盖未保存内容）。

## 3. 方案概述

在现有水平 `QSplitter`（`self.splitter`，已含目录树 + 正文区）最右侧新增一个编辑面板 widget，默认隐藏。面板为"顶部保存按钮 + 下方 `QPlainTextEdit`"的垂直布局。菜单栏"文件"之后加一个顶级"编辑"`QAction`，点击切换面板显隐；显示时读取当前文件原始文本填入编辑器。

## 4. 详细设计

### 4.1 改动点（仅 `md_viewer.py`）

1. 顶部导入追加 `QPushButton`、`QPlainTextEdit`（`from PySide6.QtWidgets import ...`），`QShortcut`、`QKeySequence`（`from PySide6.QtGui import ...`）。

2. `init_ui()` 中：
   - 在创建 `self.splitter` 之后，构建编辑面板并加入 splitter 最右侧、默认隐藏：

   ```python
   # 右侧 txt 编辑面板
   self.edit_panel = QWidget()
   edit_layout = QVBoxLayout(self.edit_panel)
   edit_layout.setContentsMargins(0, 0, 0, 0)
   edit_layout.setSpacing(0)
   edit_toolbar = QHBoxLayout()
   edit_toolbar.setContentsMargins(6, 4, 6, 4)
   self.save_btn = QPushButton("保存")
   self.save_btn.clicked.connect(self.save_edit)
   edit_toolbar.addWidget(self.save_btn)
   edit_toolbar.addStretch()
   edit_layout.addLayout(edit_toolbar)
   self.edit_text = QPlainTextEdit()
   edit_layout.addWidget(self.edit_text)
   self.splitter.addWidget(self.edit_panel)
   self.edit_panel.hide()
   ```

   - 给编辑器装 `Ctrl+S` 快捷键（作用于编辑器，只有编辑器获得焦点时才触发）：

   ```python
   self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self.edit_text)
   self.save_shortcut.activated.connect(self.save_edit)
   ```

   - 菜单栏加"编辑"菜单项（顶级 `QAction`，位于"文件"之后、"窗口"之前）：

   ```python
   self.edit_action = QAction("编辑", self)
   self.edit_action.triggered.connect(self.toggle_edit_panel)
   menubar.addAction(self.edit_action)
   ```

3. 新增方法：

   - `toggle_edit_panel()`：未打开文件时弹提示并返回；否则在 显示/隐藏 间切换；显示时加载当前文件文本。
   - `load_edit_text()`：读取 `self.file_path`（UTF-8）→ `edit_text.setPlainText`；读失败时在编辑器显示红色错误文本。
   - `save_edit()`：面板不可见时直接返回；把 `edit_text.toPlainText()` 写回 `self.file_path`（UTF-8）；成功后调用 `self.reload_file()` 刷新预览；写失败时弹错误提示（不覆盖原文件）。

4. `load_file()` 末尾追加：若编辑面板可见，调用 `self.load_edit_text()` 同步编辑器内容到新文件（防止编辑器残留旧文件文本导致保存写错）。

### 4.2 关键细节

- **编辑内容 = Markdown 源文件原文**（不是渲染后的 HTML）。"txt 方式打开"即纯文本打开源 `.md` 文件。
- **编码统一 UTF-8**：读写均用 `encoding="utf-8"`，与现有 `reload_file` 一致。
- **保存后的刷新闭环**：`save_edit` 写文件后显式 `reload_file()` 立即刷新预览；写文件还会触发现有 `QFileSystemWatcher` → 300ms 防抖后再 reload 一次。两次 reload 幂等无害。
- **文件切换安全**：`load_file` 里若面板可见则刷新编辑器，是防止"编辑器显示旧文件文本、用户保存却写入新文件"的关键保护。
- **面板不自动外部同步**：外部（如 VS Code）改动文件时，只刷新预览，不重载编辑器，避免覆盖用户尚未保存的编辑内容。
- **Ctrl+S 作用域**：`QShortcut` 以 `self.edit_text` 为父、用 Widget 级作用域，仅编辑器聚焦时触发；`save_edit` 内部再以"面板不可见即返回"兜底，避免面板隐藏时误触发。

### 4.3 数据流

```
点击"编辑" → toggle_edit_panel → (显示) load_edit_text: 读 file_path → setPlainText
编辑文本 → 点"保存"或 Ctrl+S → save_edit: toPlainText → 写回 file_path(UTF-8)
                                              ↓
                                        reload_file → 刷新左侧预览
```

### 4.4 错误处理

- 未打开文件时点"编辑"：不显示面板，弹出提示。
- 读文件失败：编辑器内显示红色错误文本。
- 写文件失败：弹出错误提示，不覆盖原文件。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 未打开文件点"编辑" | 弹提示"请先打开文件"，面板不显示 |
| 打开文件后首次点"编辑" | 显示面板，填入当前文件原文 |
| 再次点"编辑" | 隐藏面板 |
| 面板可见时打开新文件（Ctrl+O/拖拽/热键） | 面板刷新为新文件原文 |
| 编辑后点"保存"/Ctrl+S | 写回原文件，预览立即刷新 |
| 保存后 | 编辑器内容 = 文件内容 = 预览内容，三者一致 |
| 文件被外部修改（VS Code 保存） | 仅预览刷新，编辑器不重载 |
| 文件只读/无写权限 | 保存弹错误提示，原文件不变 |
| 空文件 | 编辑器显示空内容，可正常编辑保存 |

## 6. 测试计划

1. **手动冒烟（主要）**——因 `MarkdownViewer` 实例化会注册全局键盘钩子，无法在 offscreen 下安全实例化，本功能以手动验证为主：
   - 打开 md → 点"编辑" → 面板显示原文 → 修改 → Ctrl+S/按钮保存 → 预览刷新且文件内容正确。
   - 未打开文件点"编辑" → 提示，面板不显示。
   - 面板可见时切换文件 → 编辑器内容同步为新文件。
   - 保存后关闭面板再打开 → 显示最新内容。
2. **可离线验证点**：UTF-8 读写往返（写原文→读回一致），可抽成纯函数或直接在冒烟里核对。

## 7. 影响分析

- 改动集中在 `md_viewer.py` 的 UI 构建与少量方法，不触碰渲染管线、目录、搜索、托盘、热键等模块。
- 不引入新依赖（`QPlainTextEdit`、`QPushButton`、`QShortcut`、`QKeySequence` 均为 PySide6 已有 API）。
- 新增面板默认隐藏，对现有用户零影响；仅当用户主动点"编辑"才出现。
