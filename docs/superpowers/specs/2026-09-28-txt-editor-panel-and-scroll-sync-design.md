# 右侧 txt 编辑面板与滚动同步 — 设计文档

- 日期：2026-09-28
- 状态：待实现
- 关联版本：v1.7.0

## 1. 背景与问题

Popup 目前只能预览 Markdown 文件，无法在不离开 Popup 的情况下修改源文件；同时左侧预览与右侧编辑面板各自独立滚动，阅读时无法在两视图间快速对齐位置。

本设计解决两件事：

1. 在窗口右侧新增纯文本编辑面板，支持手动编辑与保存；
2. 预览与编辑面板之间做双向滚动比例同步。

## 2. 目标与非目标

### 目标

**编辑面板**

- 菜单栏新增"编辑"入口，点击在显示/隐藏之间切换右侧编辑面板。
- 面板以纯文本（txt）方式展示当前打开的 Markdown 源文件，可手动编辑。
- 支持保存（"保存"按钮 + `Ctrl+S`），保存写回原文件并刷新左侧预览。
- 面板为右侧固定内嵌，宽度可拖拽，不可浮动、不可拖出。

**滚动同步**

- 预览与编辑面板之间双向滚动比例同步（按 `value/maximum` 比例映射）。
- 实时触发（滚动条 `valueChanged` 一变化即同步）。
- 编辑器侧仅滚动视图、不移动光标。
- 防止双向同步死循环。

### 非目标（YAGNI）

- 语法高亮、行号、撤销重做以外的富编辑能力（`QPlainTextEdit` 自带撤销/复制粘贴，够用）。
- 新建/另存为/多标签编辑。
- 编码自动探测（沿用 UTF-8 约定，与 `reload_file` 一致）。
- 未保存改动（dirty）状态标记与离开提醒。
- 编辑器的自动外部同步（外部改动时编辑器不自动重载）。
- 行级/块级精确滚动映射、章节级（标题锚点）映射——比例粗同步下的错位属预期。
- 滚动位置持久化/恢复、同步开关。

## 3. 方案概述

在现有水平 `QSplitter` 最右侧新增编辑面板 widget（顶部"保存"按钮 + 下方 `QPlainTextEdit`），默认隐藏。菜单栏"文件"之后加顶级"编辑"`QAction` 切换面板显隐。保存采用原子写（临时文件 + `os.replace`），保证写失败不破坏原文件。

滚动同步：两侧 `QScrollBar` 各连一个 `valueChanged` 处理器，用 `self._syncing` 标志位防循环，按 `value/maximum` 比例互相映射。

## 4. 详细设计

### 4.1 改动点（仅 `md_viewer.py`）

**1. 导入追加**

```python
# QtWidgets 追加：QPushButton、QPlainTextEdit、QMessageBox
# QtGui    追加：QShortcut、QKeySequence
```

**2. `__init__` 新增成员**

```python
self._syncing = False      # 滚动同步防循环标志位
self._file_newline = "\n"  # 记录原文件换行风格，保存时保持一致
```

**3. `init_ui()` 中构建编辑面板并加入 splitter**

现有代码在 `self.splitter` 创建后设置了两个 widget 的 `setStretchFactor(0,0)/(1,1)` 与 `setSizes([140, 660])`。需替换为下面三栏设置：

```python
# 右侧 txt 编辑面板（默认隐藏）
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

# 加入 splitter 最右侧
self.splitter.addWidget(self.edit_panel)
self.splitter.setStretchFactor(0, 0)   # 目录：固定
self.splitter.setStretchFactor(1, 1)   # 正文：拉伸
self.splitter.setStretchFactor(2, 0)   # 编辑面板：固定（可拖拽调宽）
self.splitter.setSizes([140, 460, 300])  # 三栏初始宽度
self.edit_panel.hide()
```

**4. 编辑器快捷键（仅编辑器聚焦时生效）**

```python
self.save_shortcut = QShortcut(
    QKeySequence("Ctrl+S"),
    self.edit_text,
    Qt.ShortcutContext.WidgetWithChildrenShortcut,
)
self.save_shortcut.activated.connect(self.save_edit)
```

`WidgetWithChildrenShortcut` 保证 Ctrl+S 仅在编辑器（或其子控件）获得焦点时触发，而非整个窗口。

**5. 滚动同步信号连接**

```python
self.text_browser.verticalScrollBar().valueChanged.connect(
    self._sync_preview_to_edit
)
self.edit_text.verticalScrollBar().valueChanged.connect(
    self._sync_edit_to_preview
)
```

**6. 菜单栏加"编辑"**

把下面代码放在 `file_menu = menubar.addMenu("文件")` 相关代码之后、`window_menu = menubar.addMenu("窗口")` 之前：

```python
self.edit_action = QAction("编辑", self)
self.edit_action.triggered.connect(self.toggle_edit_panel)
menubar.addAction(self.edit_action)
```

`menubar.addAction` 会追加到当前菜单栏末尾，因此必须插入到"窗口"菜单创建之前，才能落在"文件"之后、"窗口"之前。

### 4.2 新增方法

**toggle_edit_panel()**：未打开文件时弹提示并返回；否则在显示/隐藏间切换；显示时加载当前文件文本，并做一次初始滚动同步。

**load_edit_text()**：读取 `self.file_path`（UTF-8）→ 检测换行风格 → `setPlainText`；读失败时在编辑器显示纯文本错误信息并弹 `QMessageBox` 警告。

**save_edit()**：面板不可见时直接返回；`toPlainText()` 后按原文件换行风格还原换行符，原子写回，成功后 `reload_file()` 刷新预览；写失败弹错误提示且不破坏原文件。

**滚动同步**：`_proportional_value(src, dst)`（静态辅助）、`_sync_preview_to_edit(value)`、`_sync_edit_to_preview(value)`。

### 4.3 关键代码示例

```python
def toggle_edit_panel(self):
    if not self.file_path:
        QMessageBox.warning(self, "提示", "请先打开文件")
        return
    if self.edit_panel.isVisible():
        self.edit_panel.hide()
    else:
        self.edit_panel.show()
        self.load_edit_text()
        self._sync_preview_to_edit(0)  # 显示时定位到预览当前比例位置


def load_edit_text(self):
    if not self.file_path or not os.path.isfile(self.file_path):
        return
    try:
        with open(self.file_path, "r", encoding="utf-8", newline="") as f:
            content = f.read()
    except Exception as e:
        self.edit_text.setPlainText(f"[读取失败] {e}")
        QMessageBox.warning(self, "读取失败", f"无法读取文件: {e}")
        return
    # 记录换行风格，保存时保持一致，避免 CRLF 被改写为 LF
    self._file_newline = "\r\n" if "\r\n" in content else "\n"
    self._syncing = True
    try:
        self.edit_text.setPlainText(content)
    finally:
        self._syncing = False


def save_edit(self):
    if not self.edit_panel.isVisible():
        return
    text = self.edit_text.toPlainText()
    if self._file_newline == "\r\n":
        text = text.replace("\n", "\r\n")
    tmp_path = self.file_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp_path, self.file_path)  # 原子替换，失败不破坏原文件
    except Exception as e:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        QMessageBox.warning(self, "保存失败", f"写入文件失败: {e}")
        return
    self.reload_file()


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

### 4.4 关键细节

**编辑面板**

- **编辑内容 = Markdown 源文件原文**（不是渲染后的 HTML）。"txt 方式打开"即纯文本打开源 `.md` 文件。
- **编码统一 UTF-8**：读写均 `encoding="utf-8"`，与现有 `reload_file` 一致。
- **换行符保持**：`load_edit_text` 用 `newline=""` 读取并检测是否含 `\r\n`，存入 `self._file_newline`；`save_edit` 按需把 `\n` 还原为 `\r\n`，写临时文件时用 `newline=""` 不做二次转换。避免 Windows CRLF 文件被改写成 LF，导致 git diff 全文件变化。
- **原子写**：写 `self.file_path + ".tmp"` 成功后 `os.replace` 到原路径；失败清理临时文件并弹提示，保证"写失败不破坏原文件"。
- **保存后刷新闭环**：`save_edit` 写文件后显式 `reload_file()`；写文件还会触发 `QFileSystemWatcher` → 300ms 防抖后再 reload 一次。两次 reload 幂等无害。
- **文件切换安全**：`load_file` 末尾若面板可见则 `load_edit_text()`，防止编辑器残留旧文件文本导致保存写错。
- **面板不自动外部同步**：外部（VS Code 等）改动文件时只刷新预览，不重载编辑器，避免覆盖用户未保存内容。
- **错误提示**：`QPlainTextEdit` 为纯文本控件、不支持富文本颜色，故"红色错误文本"改为"编辑器内纯文本错误信息 + `QMessageBox` 弹窗"。

**滚动同步**

- **防循环机制**：处理器入口 `if self._syncing: return`；`setValue` 期间置 `True`、结束后置 `False`。`QScrollBar.setValue()` 会在值变化时同步发 `valueChanged`，被同步侧因标志位直接返回，阻断回环。
- **映射公式**：`ratio = src.value() / max(src.maximum(), 1)`；`dst.setValue(round(ratio * dst.maximum()))`。`max(..., 1)` 防 `maximum == 0`（未加载/空文件/单屏）除零。
- **光标不动**：只操作滚动条 value，不触碰编辑器/预览光标。
- **面板隐藏保护**：`_sync_preview_to_edit` 在面板不可见时直接返回；`_sync_edit_to_preview` 由编辑器滚动条自身触发，编辑器必然可见。
- **程序性滚动隔离**：`reload_file` 的 `setHtml`/`setValue`、`load_edit_text` 的 `setPlainText` 都会触发 `valueChanged`。这些程序性改动期间用 `self._syncing` 包裹（见 4.3 `load_edit_text`，及 `reload_file` 中 `setHtml` + `scrollbar.setValue(scroll_pos)` 处），避免误触发同步导致滚动闪动或位置错乱。
- **初始同步**：`toggle_edit_panel` 显示面板后调用一次 `_sync_preview_to_edit`，让编辑器定位到预览当前比例位置。

### 4.5 数据流

```
点击"编辑" → toggle_edit_panel → (显示) load_edit_text → setPlainText
                                              └→ _sync_preview_to_edit(初始定位)

编辑文本 → 点"保存"或 Ctrl+S → save_edit: toPlainText → 换行还原
                                  → 写 .tmp → os.replace(原子替换)
                                              ↓
                                        reload_file → 刷新左侧预览

预览滚动 ──valueChanged──> _sync_preview_to_edit ──> setValue(edit 滚动条)
编辑器滚动 ──valueChanged──> _sync_edit_to_preview ──> setValue(preview 滚动条)
（两侧 setValue 触发对方 valueChanged，但 self._syncing 为 True → 直接返回）
```

### 4.6 错误处理

- 未打开文件点"编辑"：`QMessageBox` 提示，面板不显示。
- 读文件失败：编辑器内纯文本错误信息 + `QMessageBox` 警告。
- 写文件失败：清理临时文件 + `QMessageBox` 错误提示，原文件不变（原子写保证）。
- 滚动同步除零：`max(maximum(), 1)` 保护。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 未打开文件点"编辑" | 弹提示"请先打开文件"，面板不显示 |
| 打开文件后首次点"编辑" | 显示面板，填入当前文件原文，编辑器定位到预览当前比例位置 |
| 再次点"编辑" | 隐藏面板 |
| 面板可见时打开新文件（Ctrl+O/拖拽/热键） | 面板刷新为新文件原文 |
| 编辑后点"保存"/Ctrl+S | 原子写回原文件，预览立即刷新 |
| 保存后 | 编辑器内容 = 文件内容 = 预览内容，三者一致 |
| 文件被外部修改（VS Code 保存） | 仅预览刷新，编辑器不重载 |
| 文件只读/无写权限 | 保存弹错误提示，原文件不变 |
| 空文件 | 编辑器显示空内容，可正常编辑保存 |
| CRLF 文件编辑保存 | 换行符保持 CRLF，不被改写为 LF |
| 编辑面板隐藏时滚动预览 | 预览正常滚动，编辑器侧不同步 |
| 未打开文件 / 空内容 / 单屏短文 | 两侧滚动条 `maximum == 0`，同步无害、不报错 |
| 快速连续滚动 | 实时跟随；标志位保证不形成回环抖动 |
| 刷新/加载文本时 | 程序性滚动被 `_syncing` 隔离，不触发同步、不闪动 |

## 6. 测试计划

1. **手动冒烟（主要）**——因 `MarkdownViewer` 实例化会注册全局键盘钩子，无法在 offscreen 下安全实例化，本功能以手动验证为主：
   - 打开 md → 点"编辑" → 面板显示原文 → 修改 → Ctrl+S/按钮保存 → 预览刷新且文件内容正确。
   - 未打开文件点"编辑" → 提示，面板不显示。
   - 面板可见时切换文件 → 编辑器内容同步为新文件。
   - 保存后关闭面板再打开 → 显示最新内容。
   - 滚动预览 → 编辑器滚动条按比例跟随；反向同理。
   - 隐藏面板 → 滚动预览 → 编辑器侧无变化。
   - 快速来回滚动 → 无死循环、无卡死、无抖动回环。
   - CRLF 文件编辑保存 → 换行符不变，git diff 无全文件变化。
   - 只读文件保存 → 弹错误提示，原文件不变。
   - 空文件 / 单屏短文 → 无报错、无异常滚动。
2. **可离线验证点**：`_proportional_value` 为纯函数，可单独单测比例换算与除零保护；UTF-8 读写往返（写原文→读回一致）可抽纯函数或冒烟核对。

## 7. 影响分析

- 改动集中在 `md_viewer.py`：新增成员变量、编辑面板 UI、若干方法与信号连接，不触碰渲染管线、目录、搜索、托盘、热键等模块。
- 不引入新依赖（`QPlainTextEdit`、`QPushButton`、`QShortcut`、`QKeySequence`、`QMessageBox` 均为 PySide6 已有 API）。
- 新增面板默认隐藏、滚动同步默认开启且仅在面板可见时生效，对现有用户零感知变化。
- 保存采用原子写，且保持原换行风格，对既有文件无破坏性副作用。
