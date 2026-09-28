# 右侧 txt 编辑面板与滚动同步 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Popup 窗口右侧新增纯文本编辑面板（可编辑并保存 Markdown 源文件），并实现预览与编辑面板的双向滚动比例同步。

**Architecture:** 改动集中在 `md_viewer.py`：在现有水平 `QSplitter` 最右侧加一个默认隐藏的编辑面板（"保存"按钮 + `QPlainTextEdit`），保存采用原子写；两侧 `QScrollBar` 各连一个 `valueChanged` 处理器，用 `self._syncing` 标志位防循环，按 `value/maximum` 比例互相映射。

**Tech Stack:** Python 3.14 + PySide6 6.11 + markdown；测试用标准库 `unittest`。

## Global Constraints

- 功能改动仅允许 `md_viewer.py`（新增测试文件 `tests/test_scroll_sync.py` 除外）。
- 依赖版本：`PySide6>=6.5`、`markdown>=3.4`（见 `requirements.txt`），不新增依赖。
- 读写文件统一 `encoding="utf-8"`，读取用 `newline=""`。
- 保存必须原子写（写临时文件 + `os.replace`），写失败不破坏原文件。
- 保存保持原换行风格（CRLF 文件不被改写为 LF）。
- 新增面板默认隐藏；滚动同步仅在面板可见时生效。
- **测试运行命令统一为 `python -m unittest tests.<file> -v`**（直接 `python tests/<file>.py` 会因 `sys.path` 不含项目根而报 `ModuleNotFoundError: md_viewer`）。
- **`MarkdownViewer` 无法在自动化测试中实例化**（`__init__` 会注册全局键盘钩子），故编辑面板与滚动同步的验证以手动冒烟为主；只有纯函数 `_proportional_value` 可自动化单测。

## File Structure

- **Modify: `md_viewer.py`** —— 唯一功能改动文件。追加导入、成员变量、编辑面板 UI、`toggle_edit_panel`/`load_edit_text`/`save_edit`/`_proportional_value`/`_sync_preview_to_edit`/`_sync_edit_to_preview` 方法、信号连接，并修改 `load_file`、`reload_file`。
- **Create: `tests/test_scroll_sync.py`** —— `_proportional_value` 的单元测试。

---

### Task 1: `_proportional_value` 滚动比例映射纯函数（TDD）

**Files:**
- Modify: `md_viewer.py`（新增静态方法 `_proportional_value`）
- Test: `tests/test_scroll_sync.py`

**Interfaces:**
- Produces: `MarkdownViewer._proportional_value(src, dst) -> int`。`src`/`dst` 为任意带 `value() -> int` 与 `maximum() -> int` 方法的对象（如 `QScrollBar`）。返回值 = `round(src.value() / max(src.maximum(), 1) * dst.maximum())`。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_scroll_sync.py`：

```python
import unittest

from md_viewer import MarkdownViewer


class _FakeScrollBar:
    def __init__(self, value=0, maximum=0):
        self._value = value
        self._maximum = maximum

    def value(self):
        return self._value

    def maximum(self):
        return self._maximum


class TestProportionalValue(unittest.TestCase):
    def test_half_of_src_maps_to_half_of_dst(self):
        src = _FakeScrollBar(value=50, maximum=100)
        dst = _FakeScrollBar(maximum=200)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 100)

    def test_zero_maximum_does_not_divide_by_zero(self):
        src = _FakeScrollBar(value=0, maximum=0)
        dst = _FakeScrollBar(maximum=0)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 0)

    def test_full_src_maps_to_full_dst(self):
        src = _FakeScrollBar(value=100, maximum=100)
        dst = _FakeScrollBar(maximum=300)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 300)

    def test_rounds_to_nearest_int(self):
        src = _FakeScrollBar(value=1, maximum=3)
        dst = _FakeScrollBar(maximum=100)
        self.assertEqual(MarkdownViewer._proportional_value(src, dst), 33)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_scroll_sync -v`
Expected: FAIL，`AttributeError: type object 'MarkdownViewer' has no attribute '_proportional_value'`

- [ ] **Step 3: 实现 `_proportional_value`**

在 `md_viewer.py` 的 `MarkdownViewer` 类中，`open_log_dir` 方法之前添加：

```python
    @staticmethod
    def _proportional_value(src, dst):
        """按比例把 src 滚动条当前位置映射为 dst 滚动条的目标值"""
        ratio = src.value() / max(src.maximum(), 1)
        return round(ratio * dst.maximum())
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_scroll_sync -v`
Expected: PASS（4 个测试全部通过）

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_scroll_sync.py
git commit -m "feat: 新增 _proportional_value 滚动比例映射函数"
```

---

### Task 2: 右侧 txt 编辑面板（编辑与保存）

**Files:**
- Modify: `md_viewer.py`

**Interfaces:**
- Consumes: 无（`_proportional_value` 在 Task 3 才被调用）。
- Produces: 实例属性 `self.edit_panel`（QWidget）、`self.edit_text`（QPlainTextEdit）、`self.save_btn`（QPushButton）、`self.edit_action`（QAction）、`self.save_shortcut`（QShortcut）、`self._syncing`（bool）、`self._file_newline`（str）；方法 `toggle_edit_panel()`、`load_edit_text()`、`save_edit()`。Task 3 依赖这些属性与方法。

> 注：本任务实现 `toggle_edit_panel` 时**不含**初始滚动同步行（`self._sync_preview_to_edit(0)`），该行在 Task 3 补上，避免 Task 2 引用尚未定义的方法。

- [ ] **Step 1: 追加导入**

将 `md_viewer.py` 顶部的导入（当前为第 43-49 行）改为：

```python
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QTextBrowser,
    QSplitter, QTreeWidget, QTreeWidgetItem, QWidget, QToolButton,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu, QLineEdit,
    QPushButton, QPlainTextEdit, QMessageBox
)
from PySide6.QtGui import (
    QAction, QIcon, QTextDocument, QTextCursor, QFontMetricsF,
    QShortcut, QKeySequence, QFont
)
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent, QUrl
```

- [ ] **Step 2: 新增成员变量**

在 `__init__` 中 `self._quitting = False` 之后添加：

```python
        # 编辑面板与滚动同步状态
        self._syncing = False      # 滚动同步防循环标志位
        self._file_newline = "\n"  # 记录原文件换行风格，保存时保持一致
```

- [ ] **Step 3: 构建编辑面板并加入 splitter**

在 `init_ui` 中，将现有 splitter 构建段（当前约第 267-274 行）：

```python
        # 用 Splitter 组合边栏和正文，支持拖动调节宽度
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.toc_tree)
        self.splitter.addWidget(content_widget)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([140, 660])
        self.setCentralWidget(self.splitter)
```

替换为：

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
        self.edit_text.setFont(QFont("Consolas", 11))  # 等宽字体，保证代码块/表格对齐
        edit_layout.addWidget(self.edit_text)

        # 用 Splitter 组合边栏、正文、编辑面板，支持拖动调节宽度
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.toc_tree)
        self.splitter.addWidget(content_widget)
        self.splitter.addWidget(self.edit_panel)
        self.splitter.setStretchFactor(0, 0)   # 目录：固定
        self.splitter.setStretchFactor(1, 1)   # 正文：拉伸
        self.splitter.setStretchFactor(2, 0)   # 编辑面板：固定（可拖拽调宽）
        self.splitter.setSizes([140, 460, 300])  # 三栏初始宽度
        self.setCentralWidget(self.splitter)

        # 编辑器保存快捷键（仅编辑器聚焦时生效）
        self.save_shortcut = QShortcut(
            QKeySequence("Ctrl+S"),
            self.edit_text,
            Qt.ShortcutContext.WidgetWithChildrenShortcut,
        )
        self.save_shortcut.activated.connect(self.save_edit)

        self.edit_panel.hide()
```

- [ ] **Step 4: 菜单栏加"编辑"**

在 `init_ui` 中，`refresh_action` 相关代码（`file_menu.addAction(refresh_action)`）之后、`window_menu = menubar.addMenu("窗口")` 之前，插入：

```python
        # 编辑面板切换入口（顶级菜单项，位于"文件"之后、"窗口"之前）
        self.edit_action = QAction("编辑", self)
        self.edit_action.setCheckable(True)  # 面板显示时打勾，作为状态指示
        self.edit_action.triggered.connect(self.toggle_edit_panel)
        menubar.addAction(self.edit_action)
```

- [ ] **Step 5: 新增编辑面板方法**

在 `md_viewer.py` 的 `quit_app` 方法之后（`QApplication.quit()` 之后、`open_file` 之前）添加：

```python
    def toggle_edit_panel(self):
        """切换右侧编辑面板显隐；显示时加载当前文件原文"""
        if not self.file_path:
            QMessageBox.warning(self, "提示", "请先打开文件")
            return
        if self.edit_panel.isVisible():
            self.edit_panel.hide()
            self.edit_action.setChecked(False)
        else:
            self.edit_panel.show()
            self.edit_action.setChecked(True)
            self.load_edit_text()

    def load_edit_text(self):
        """读取当前文件原文到编辑器，记录换行风格"""
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
        """把编辑器内容原子写回原文件并刷新预览"""
        if not self.edit_panel.isVisible():
            return
        if not self.file_path:
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
```

- [ ] **Step 6: 修改 `load_file` 同步编辑器**

在 `load_file` 方法末尾（`logger.info("Opened file: %s", self.file_path)` 之后）添加：

```python
        # 编辑面板可见时，同步编辑器内容到新文件，防止保存写错文件
        if self.edit_panel.isVisible():
            self.load_edit_text()
```

- [ ] **Step 7: 手动冒烟验证**

启动应用：`python md_viewer.py`

按以下清单手动验证：

| 操作 | 预期 |
|------|------|
| 未打开文件，点菜单"编辑" | 弹提示"请先打开文件"，面板不显示 |
| 打开一个 .md 文件，点"编辑" | 右侧出现面板，显示文件原文，菜单"编辑"项打勾 |
| 修改编辑器内容，点"保存" | 预览刷新，文件内容正确更新 |
| 修改内容，在编辑器聚焦时按 Ctrl+S | 同上，保存生效 |
| 再次点"编辑" | 面板隐藏，菜单"编辑"项取消打勾 |
| 面板可见时用 Ctrl+O/拖拽打开新文件 | 编辑器内容同步为新文件原文 |
| 打开一个 CRLF 换行的 .md 文件，编辑并保存 | 文件换行符仍为 CRLF（`git diff` 无全文件变化） |
| 打开一个只读文件，点"保存" | 弹"保存失败"提示，原文件不变 |

- [ ] **Step 8: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 新增右侧 txt 编辑面板（编辑与保存）"
```

---

### Task 3: 预览与编辑面板双向滚动同步

**Files:**
- Modify: `md_viewer.py`

**Interfaces:**
- Consumes: Task 1 的 `_proportional_value(src, dst)`；Task 2 的 `self.edit_panel`、`self.edit_text`、`self.text_browser`、`self._syncing`、`toggle_edit_panel`、`load_edit_text`。
- Produces: 方法 `_sync_preview_to_edit(value)`、`_sync_edit_to_preview(value)`；两处 `valueChanged` 信号连接；`reload_file` 的程序性滚动隔离；`toggle_edit_panel` 的初始同步行。

- [ ] **Step 1: 新增滚动同步方法**

在 `md_viewer.py` 的 `save_edit` 方法之后添加：

```python
    def _sync_preview_to_edit(self, value):
        """预览滚动 → 编辑器滚动条按比例跟随（仅滚动视图，不动光标）。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
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
        """编辑器滚动 → 预览滚动条按比例跟随。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        preview_sb = self.text_browser.verticalScrollBar()
        self._syncing = True
        preview_sb.setValue(
            self._proportional_value(self.edit_text.verticalScrollBar(), preview_sb)
        )
        self._syncing = False
```

- [ ] **Step 2: 连接滚动同步信号**

在 `init_ui` 中，`self.edit_panel.hide()` 之后添加：

```python
        # 双向滚动同步（比例粗同步）
        self.text_browser.verticalScrollBar().valueChanged.connect(
            self._sync_preview_to_edit
        )
        self.edit_text.verticalScrollBar().valueChanged.connect(
            self._sync_edit_to_preview
        )
```

- [ ] **Step 3: 修改 `reload_file` 隔离程序性滚动**

在 `reload_file` 中，将现有：

```python
        base_url = self._build_base_url(self.file_path)
        self.text_browser.document().setBaseUrl(base_url)
        self.text_browser.setHtml(self.wrap_html(html_body))

        # 恢复滚动位置
        scrollbar.setValue(scroll_pos)
```

替换为：

```python
        base_url = self._build_base_url(self.file_path)
        self.text_browser.document().setBaseUrl(base_url)

        # 程序性滚动隔离：setHtml/setValue 会触发 valueChanged，
        # 用 _syncing 包裹，避免刷新时误触发滚动同步导致闪动
        self._syncing = True
        try:
            self.text_browser.setHtml(self.wrap_html(html_body))
            # 恢复滚动位置
            scrollbar.setValue(scroll_pos)
        finally:
            self._syncing = False
```

- [ ] **Step 4: 补上 `toggle_edit_panel` 的初始同步**

在 `toggle_edit_panel` 中，`self.load_edit_text()` 之后补一行：

```python
            self.load_edit_text()
            self._sync_preview_to_edit(0)  # 显示时定位到预览当前比例位置
```

- [ ] **Step 5: 手动冒烟验证**

启动应用：`python md_viewer.py`，打开一个较长的 .md 文件，点"编辑"显示面板，按以下清单验证：

| 操作 | 预期 |
|------|------|
| 滚动预览 | 编辑器滚动条按比例跟随 |
| 滚动编辑器 | 预览滚动条按比例跟随 |
| 快速来回滚动 | 实时跟随，无死循环、无卡死、无抖动回环 |
| 隐藏面板后滚动预览 | 编辑器侧无变化 |
| 打开面板时 | 编辑器定位到预览当前比例位置 |
| 编辑保存后 | 预览刷新，无滚动闪动 |
| 空文件 / 单屏短文 | 无报错、无异常滚动 |

- [ ] **Step 6: 运行全部自动化测试确认无回归**

Run: `python -m unittest discover -s tests -v`
Expected: 全部 PASS（含 Task 1 新增的 4 个测试，以及既有 `test_base_url`、`test_blockquote`、`test_indent`、`test_indent_rendering`、`test_quote_rendering`）

- [ ] **Step 7: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 新增预览与编辑面板双向滚动同步"
```
