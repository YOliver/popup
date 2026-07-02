# 文本搜索功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Popup 桌面 Markdown 预览器添加内嵌文本搜索功能（Ctrl+F 弹出搜索条，实时全文匹配与高亮）

**Architecture:** 全部改动集中在 `md_viewer.py` 的 `MarkdownViewer` 类内。在正文区顶部新增一个 `QWidget` 搜索条，由 `QLineEdit` 输入框、计数标签、导航/选项/关闭按钮组成。用 `QTextBrowser.find()` 做跳转+选区高亮，用 `QTextDocument.find()` 全文循环扫描实现匹配计数。键盘交互通过 `eventFilter` 拦截。

**Tech Stack:** Python 3.8+, PySide6 (Qt), `QTextBrowser.find()`, `QTextDocument.find()`

**Spec:** `docs/superpowers/specs/2026-07-02-text-search-design.md`

## Global Constraints

- 仅修改 `md_viewer.py`，不新增文件
- 匹配选项：区分大小写 + 全词匹配，默认均关闭
- 计数扫描防抖 150ms，跳转/高亮即时
- 只高亮当前匹配项（`find()` 选区），其余不标记
- 搜索条默认隐藏，Ctrl+F 弹出
- 事件过滤器拦截 Enter / Shift+Enter / Esc / ↓ / ↑
- 打开新文件/刷新时保留搜索词并重新计数

---

### Task 1: 新增 QLineEdit 导入与搜索状态变量

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py:43-49`

**Interfaces:**
- Produces: `QLineEdit` 可用；`self._count_timer`（QTimer, singleShot, 150ms）；`self.search_bar`, `self.search_input`, `self.match_count_label`, `self.prev_btn`, `self.next_btn`, `self.case_btn`, `self.word_btn`, `self.close_btn`（后续任务创建与使用）

- [ ] **Step 1: 在 PySide6 导入中添加 QLineEdit**

```python
# 修改 md_viewer.py 第 43-47 行
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QTextBrowser,
    QSplitter, QTreeWidget, QTreeWidgetItem, QWidget, QToolButton,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu, QLineEdit
)
```

- [ ] **Step 2: 在 __init__ 中初始化搜索状态变量**

在 `__init__` 方法中，`self.init_ui()` 调用之前（约第 73 行前），添加：

```python
        # 文本搜索状态
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(150)
        self._count_timer.timeout.connect(lambda: self.update_match_count())
```

- [ ] **Step 3: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 4: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 添加 QLineEdit 导入与搜索状态初始化"
```

---

### Task 2: 创建搜索条控件并重构正文容器布局

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py:149-184`（搜索条定义插在 toc_toggle_btn 之后、content_widget 构建之前）
- Modify: `g:\UGit\popup\md_viewer.py:170-176`（原有 HBoxLayout 被替换为外层 VBoxLayout 包裹）

**Interfaces:**
- Consumes: `self.toc_toggle_btn`, `self.text_browser`（已有）
- Produces: `self.search_bar`（QWidget, hidden）、`self.search_input`（QLineEdit）、`self.match_count_label`（QLabel）、`self.prev_btn`/`self.next_btn`（QToolButton）、`self.case_btn`/`self.word_btn`（QToolButton, checkable）、`self.close_btn`（QToolButton）

- [ ] **Step 1: 插入搜索条创建代码**

在 `self.toc_toggle_btn` 定义之后、原有 `content_widget` 构建之前（约第 168-169 行之间），插入：

```python
        # 文本搜索条（默认隐藏，Ctrl+F 弹出）
        self.search_bar = QWidget()
        self.search_bar.setStyleSheet("""
            QWidget#search_bar {
                background: #f5f5f5;
                border-bottom: 1px solid #ddd;
            }
        """)
        self.search_bar.setObjectName("search_bar")
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(8, 4, 8, 4)
        search_layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("查找...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px 8px;
                background: #fff;
                min-width: 200px;
            }
        """)
        self.search_input.installEventFilter(self)

        self.match_count_label = QLabel("")
        self.match_count_label.setStyleSheet("color: #666; font-size: 12px;")

        self.prev_btn = QToolButton()
        self.prev_btn.setText("▲")
        self.prev_btn.setToolTip("上一个 (Shift+Enter / ↑)")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.next_btn = QToolButton()
        self.next_btn.setText("▼")
        self.next_btn.setToolTip("下一个 (Enter / ↓)")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.case_btn = QToolButton()
        self.case_btn.setText("Aa")
        self.case_btn.setToolTip("区分大小写")
        self.case_btn.setCheckable(True)
        self.case_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.case_btn.setStyleSheet("QToolButton:checked { color: #000; font-weight: bold; }")

        self.word_btn = QToolButton()
        self.word_btn.setText("全词")
        self.word_btn.setToolTip("全词匹配")
        self.word_btn.setCheckable(True)
        self.word_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.word_btn.setStyleSheet("QToolButton:checked { color: #000; font-weight: bold; }")

        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("关闭 (Esc)")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.match_count_label)
        search_layout.addWidget(self.prev_btn)
        search_layout.addWidget(self.next_btn)
        search_layout.addWidget(self.case_btn)
        search_layout.addWidget(self.word_btn)
        search_layout.addWidget(self.close_btn)

        self.search_bar.hide()
```

- [ ] **Step 2: 重构正文容器布局**

将原有的 HBoxLayout 包裹方案（约第 170-176 行）：

```python
        # 正文容器：左边缘按钮 + QTextBrowser
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.toc_toggle_btn)
        content_layout.addWidget(self.text_browser)
```

替换为外层 VBoxLayout（搜索条 + 原有内层 HBoxLayout）：

```python
        # 内层行：左边缘按钮 + QTextBrowser（原有布局）
        content_row = QWidget()
        content_row_layout = QHBoxLayout(content_row)
        content_row_layout.setContentsMargins(0, 0, 0, 0)
        content_row_layout.setSpacing(0)
        content_row_layout.addWidget(self.toc_toggle_btn)
        content_row_layout.addWidget(self.text_browser)

        # 正文容器：搜索条（默认隐藏）+ 内层行
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.search_bar)
        content_layout.addWidget(content_row)
```

- [ ] **Step 3: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 4: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 添加搜索条控件并重构正文容器布局"
```

---

### Task 3: 新增 Ctrl+F 快捷键

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py:208-212`

**Interfaces:**
- Consumes: `self.show_search`（Task 4 实现）
- Produces: Ctrl+F 快捷键触发

- [ ] **Step 1: 在已有快捷键区域添加 Ctrl+F Action**

在现有 `toggle_toc_action` 之后（约第 212 行后），添加：

```python
        # 文本搜索快捷键
        search_action = QAction(self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(lambda: self.show_search())
        self.addAction(search_action)
```

- [ ] **Step 2: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 添加 Ctrl+F 文本搜索快捷键"
```

---

### Task 4: 实现 eventFilter 拦截搜索框键盘事件

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py:55` 之后（在 MarkdownViewer 类中新增方法）

**Interfaces:**
- Consumes: `self.search_input`（已创建，Task 2 安装了 eventFilter）、`self.find_next`、`self.find_previous`、`self.close_search`（后续任务实现）
- Produces: `eventFilter(self, obj, event)` 方法

- [ ] **Step 1: 新增 eventFilter 方法**

在 `MarkdownViewer` 类内（在 `def __init__` 之后的位置），添加：

```python
    def eventFilter(self, obj, event):
        """拦截搜索框键盘事件"""
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.find_previous()
                else:
                    self.find_next()
                return True
            elif key == Qt.Key.Key_Escape:
                self.close_search()
                return True
            elif key == Qt.Key.Key_Down:
                self.find_next()
                return True
            elif key == Qt.Key.Key_Up:
                self.find_previous()
                return True
        return super().eventFilter(obj, event)
```

- [ ] **Step 2: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现 eventFilter 拦截搜索框键盘事件"
```

---

### Task 5: 实现 _search_flags、show_search、close_search

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py`（在 `MarkdownViewer` 类中添加方法）

**Interfaces:**
- Consumes: `self.case_btn.isChecked()`, `self.word_btn.isChecked()`, `self.search_bar`, `self.search_input`, `self.text_browser.textCursor()`, `self._count_timer`, `self.text_browser.textCursor().clearSelection()` 选区和 `text_browser.setFocus()`
- Produces: `_search_flags()` 返回 `QTextDocument.FindFlags`；`show_search()`；`close_search()`
- Depends on Task 6: `_do_find()` 和 `_schedule_count_update()` 暂未定义，`show_search` 中对已有文本时调用这两个方法，需 Task 6 补充

- [ ] **Step 1: 新增 _search_flags 辅助方法**

```python
    def _search_flags(self):
        """根据当前选项配置构建查找标志"""
        flags = QTextDocument.FindFlags()
        if self.case_btn.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.word_btn.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags
```

- [ ] **Step 2: 新增 _clear_search_state 辅助方法**

```python
    def _clear_search_state(self):
        """清空搜索高亮和计数状态"""
        self.match_count_label.setText("")
        cursor = self.text_browser.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.text_browser.setTextCursor(cursor)
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px 8px;
                background: #fff;
                min-width: 200px;
            }
        """)
```

- [ ] **Step 3: 新增 close_search 方法**

```python
    def close_search(self):
        """关闭搜索条，清理状态"""
        self._count_timer.stop()
        self._clear_search_state()
        self.search_bar.hide()
        self.text_browser.setFocus()
```

- [ ] **Step 4: 新增 show_search 方法（先占位，Task 6 补完）**

```python
    def show_search(self):
        """显示搜索条，有选中文本时预填"""
        if self.search_bar.isVisible():
            # 已显示：重新聚焦并全选
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self.search_bar.show()
            cursor = self.text_browser.textCursor()
            if cursor.hasSelection():
                self.search_input.setText(cursor.selectedText())
            self.search_input.setFocus()
            self.search_input.selectAll()
            # 若已有文本（预填或之前残留），触发搜索
            if self.search_input.text():
                self._do_find()
                self._schedule_count_update()
```

- [ ] **Step 5: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 6: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现搜索标志、show_search 和 close_search"
```

---

### Task 6: 实现 _do_find、_schedule_count_update、on_search_text_changed

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py`

**Interfaces:**
- Consumes: `self.text_browser.find()`, `self.search_input.text()`, `self._search_flags()`, `self.match_count_label`
- Produces: `_do_find()`, `_schedule_count_update()`, `on_search_text_changed(text)`（作为 `textChanged` 槽函数）

- [ ] **Step 1: 新增 _do_find 方法**

```python
    def _do_find(self):
        """从当前光标位置向后查找（不回绕）"""
        text = self.search_input.text()
        if not text:
            self._clear_search_state()
            return
        flags = self._search_flags()
        found = self.text_browser.find(text, flags)
        if not found:
            self.match_count_label.setText("无结果")
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #e00;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)
        else:
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)
```

- [ ] **Step 2: 新增 _schedule_count_update 方法**

```python
    def _schedule_count_update(self):
        """防抖延迟刷新匹配计数"""
        self._count_timer.start()
```

- [ ] **Step 3: 新增 on_search_text_changed 方法**

```python
    def on_search_text_changed(self, text):
        """输入文本变化时实时触发搜索"""
        if not text:
            self._clear_search_state()
            return
        self._do_find()
        self._schedule_count_update()
```

- [ ] **Step 4: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现搜索、计数调度和输入文本变化处理"
```

---

### Task 7: 实现 find_next、find_previous 导航方法

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py`

**Interfaces:**
- Consumes: `self.text_browser.find()`, `self.text_browser.textCursor()`, `self.text_browser.moveCursor()`, `self._search_flags()`, `self.update_match_count()`
- Produces: `find_next()`, `find_previous()`

- [ ] **Step 1: 新增 find_next 方法**

```python
    def find_next(self):
        """向后查找下一个匹配，到末尾回绕"""
        text = self.search_input.text()
        if not text:
            return
        flags = self._search_flags()
        found = self.text_browser.find(text, flags)
        if not found:
            # 回绕：从文档开头重新查找
            cursor = self.text_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.find(text, flags)
        self.update_match_count()
```

- [ ] **Step 2: 新增 find_previous 方法**

```python
    def find_previous(self):
        """向前查找上一个匹配，到开头回绕"""
        text = self.search_input.text()
        if not text:
            return
        flags = self._search_flags() | QTextDocument.FindFlag.FindBackward
        found = self.text_browser.find(text, flags)
        if not found:
            # 回绕：从文档末尾重新查找
            cursor = self.text_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.find(text, flags)
        self.update_match_count()
```

- [ ] **Step 3: 在文件顶部导入中补充 QTextCursor**

在第 49 行 `from PySide6.QtCore import` 中添加 `QTextCursor`：

```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent
```

改为：

```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent
from PySide6.QtGui import QTextCursor
```

- [ ] **Step 4: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现 find_next 和 find_previous 导航方法"
```

---

### Task 8: 实现 update_match_count 全文扫描计数

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py`

**Interfaces:**
- Consumes: `self.search_input.text()`, `self._search_flags()`, `self.text_browser.textCursor()`, `self.text_browser.document().find()`
- Produces: `update_match_count()` 更新 `self.match_count_label` 文本和红框状态

- [ ] **Step 1: 新增 update_match_count 方法**

```python
    def update_match_count(self):
        """全文扫描统计匹配总数并定位当前序号"""
        text = self.search_input.text()
        if not text:
            self._clear_search_state()
            return
        flags = self._search_flags()
        cur_cursor = self.text_browser.textCursor()
        # 当前选中位置：若有选区用 selectionStart，否则用光标位置
        cur_pos = cur_cursor.selectionStart() if cur_cursor.hasSelection() else cur_cursor.position()
        doc = self.text_browser.document()
        pos = 0
        total = 0
        current = 0
        while True:
            cursor = doc.find(text, pos, flags)
            if cursor.isNull():
                break
            total += 1
            # 判断当前匹配是否包含当前光标位置
            if cursor.selectionStart() <= cur_pos <= cursor.selectionEnd():
                current = total
            pos = cursor.position()
        if total == 0:
            self.match_count_label.setText("无结果")
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #e00;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)
        else:
            if current == 0:
                current = 1  # 可能当前光标恰好在第一个匹配前
            self.match_count_label.setText(f"第 {current} / 共 {total} 个")
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)
```

- [ ] **Step 2: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现 update_match_count 全文扫描计数"
```

---

### Task 9: 实现 toggle_case 和 toggle_whole_word

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py`

**Interfaces:**
- Consumes: `self._do_find()`, `self.update_match_count()`
- Produces: `toggle_case(checked)`, `toggle_whole_word(checked)`

- [ ] **Step 1: 新增 toggle_case 和 toggle_whole_word 方法**

```python
    def toggle_case(self, checked):
        """切换区分大小写后重新查找"""
        self._do_find()
        self.update_match_count()

    def toggle_whole_word(self, checked):
        """切换全词匹配后重新查找"""
        self._do_find()
        self.update_match_count()
```

- [ ] **Step 2: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现切换匹配选项的重新查找"
```

---

### Task 10: 连接所有信号

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py`

**Interfaces:**
- Consumes: 已定义的 `self.search_input`, `self.next_btn`, `self.prev_btn`, `self.case_btn`, `self.word_btn`, `self.close_btn`, `self.on_search_text_changed`, `self.find_next`, `self.find_previous`, `self.toggle_case`, `self.toggle_whole_word`, `self.close_search`
- Produces: 所有信号正确连接

- [ ] **Step 1: 在搜索条构建末尾添加所有信号连接**

在 Task 2 中 `self.search_bar.hide()` 之后，添加：

```python
        # 信号连接（所有方法已在前面 Task 中定义，连接时立即可用）
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.next_btn.clicked.connect(self.find_next)
        self.prev_btn.clicked.connect(self.find_previous)
        self.case_btn.toggled.connect(self.toggle_case)
        self.word_btn.toggled.connect(self.toggle_whole_word)
        self.close_btn.clicked.connect(self.close_search)
```

- [ ] **Step 2: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 连接搜索条所有信号"
```

---

### Task 11: 修改 load_file 支持搜索状态保留

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py:343-354`

**Interfaces:**
- Consumes: `self.search_bar.isVisible()`, `self.search_input.text()`, `self._do_find()`, `self.update_match_count()`
- Produces: 文件名更新后自动重新计数

- [ ] **Step 1: 在 load_file 方法末尾添加搜索状态刷新**

在 `load_file` 方法的 `logger.info("Opened file: %s", self.file_path)` 之前（约第 354 行），添加：

```python
        # 若搜索条开着，文档内容已通过 reload_file 刷新，重新计数
        if self.search_bar.isVisible() and self.search_input.text():
            self._do_find()
            self.update_match_count()
```

- [ ] **Step 2: 验证语法无报错**

Run: `python -c "import ast; ast.parse(open('md_viewer.py').read()); print('OK')"`

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 文档切换时保留并刷新搜索状态"
```

---

### Task 12: 启动验证

**Files:**
- 无新增文件

**Interfaces:**
- 验证完整的搜索功能

- [ ] **Step 1: 启动应用测试基本功能**

Run: `python md_viewer.py`

验证下列场景：

1. Ctrl+F 弹出搜索条、Esc 关闭。
2. 重复 Ctrl+F 在搜索条已显示时全选已有词。
3. 输入关键词即时高亮第一个匹配。
4. Enter / ↓ / 下一按钮导航正确。
5. Shift+Enter / ↑ / 上一按钮导航正确。
6. 末尾继续按"下一个"回绕到从头匹配。
7. 开头继续按"上一个"回绕到从尾匹配。
8. 点击"区分大小写"和"全词匹配"开关，验证各自生效且即时刷新。
9. 在正文选中一段文字，然后按 Ctrl+F，验证搜索框预填选中词并搜索。
10. 输入不存在的文本，验证输入框变红、计数显示"无结果"。
11. 清空输入框，验证计数、高亮、红框均清除。
12. 保持搜索条开着，打开另一个 Markdown 文件，验证保留搜索词并重新计数。
13. 保持搜索条开着，刷新当前文件（F5），验证保留搜索词并重新计数。
14. Ctrl+B 折叠/展开目录，与搜索功能互不冲突。
15. 确认 Ctrl+F 不与其它快捷键或 QTextBrowser 内置快捷键冲突。
16. 确认无匹配时上/下导航按钮不弹出任何对话框或提示（回绕静默处理）。

- [ ] **Step 2: 如有问题修复后重新验证**

- [ ] **Step 3: 提交最终版本**

```bash
git add md_viewer.py
git commit -m "feat: 文本搜索功能完成，所有验证项通过"
```
