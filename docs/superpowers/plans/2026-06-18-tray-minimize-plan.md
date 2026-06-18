# 点击关闭按钮缩到系统托盘 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修改 Popup 窗口关闭/最小化行为，不退出进程，而是缩到 Windows 系统托盘。

**Architecture:** 在 `MarkdownViewer` 中新增 `QSystemTrayIcon`，重写 `closeEvent` 和 `changeEvent` 拦截关闭和最小化事件，通过 `_quitting` 标志区分"缩到托盘"和"真正退出"。

**Tech Stack:** PySide6 (QSystemTrayIcon, QMenu, QEvent)

---

## 修改文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `md_viewer.py` | 修改 | 新增托盘逻辑、重写事件 |
| `version.py` | 修改 | 版本号升到 1.5.0 |

---

### Task 1: 更新导入语句

**Files:**
- Modify: `md_viewer.py:42-48`

- [ ] **Step 1: 在 `PySide6.QtWidgets` 导入中追加 `QSystemTrayIcon, QMenu`**

找到第 42-46 行：
```python
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QTextBrowser,
    QSplitter, QTreeWidget, QTreeWidgetItem, QWidget, QToolButton,
    QHBoxLayout, QVBoxLayout
)
```

改为：
```python
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QTextBrowser,
    QSplitter, QTreeWidget, QTreeWidgetItem, QWidget, QToolButton,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu
)
```

- [ ] **Step 2: 在 `PySide6.QtCore` 导入中追加 `QEvent`**

找到第 48 行：
```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer
```

改为：
```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent
```

- [ ] **Step 3: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 新增 QSystemTrayIcon/QMenu/QEvent 导入"
```

---

### Task 2: 新增属性并调用托盘初始化

**Files:**
- Modify: `md_viewer.py:54-67`

- [ ] **Step 1: 在 `__init__` 中新增三个属性**

在 `self.init_ui()` 调用后（第 67 行之后），新增属性初始化和 `init_tray()` 调用。

当前 `__init__`（第 54-67 行）：
```python
class MarkdownViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.file_path = None
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self.on_file_changed)

        # 延迟刷新定时器，避免频繁刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(300)
        self.refresh_timer.timeout.connect(self.reload_file)

        self.init_ui()
```

改为：
```python
class MarkdownViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.file_path = None
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self.on_file_changed)

        # 延迟刷新定时器，避免频繁刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(300)
        self.refresh_timer.timeout.connect(self.reload_file)

        # 托盘相关属性（在 init_ui 之后初始化）
        self.tray_icon = None
        self._window_geometry = None
        self._quitting = False

        self.init_ui()
        self.init_tray()
```

- [ ] **Step 2: 提交**

```bash
git add md_viewer.py
git commit -m "feat: MarkdownViewer 新增托盘属性和 init_tray 调用"
```

---

### Task 3: 实现 `init_tray()` 方法

**Files:**
- Modify: `md_viewer.py` — 在 `init_ui()` 方法之后插入新方法

- [ ] **Step 1: 在 `init_ui()` 方法结束后（第 251 行 `)`) 之后、`open_file()` 之前）插入 `init_tray()`**

```python
    def init_tray(self):
        """初始化系统托盘图标和右键菜单。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.isfile(icon_path):
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray_icon = QSystemTrayIcon(self)

        self.tray_icon.setToolTip(f"Popup v{VERSION}")

        # 右键菜单
        menu = QMenu()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit_app)
        self.tray_icon.setContextMenu(menu)

        # 双击托盘图标恢复窗口
        self.tray_icon.activated.connect(self.on_tray_activated)

        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """托盘图标激活回调：双击恢复窗口。"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()
```

- [ ] **Step 2: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现 init_tray 托盘图标及右键菜单"
```

---

### Task 4: 实现 `closeEvent` 重写

**Files:**
- Modify: `md_viewer.py` — 在 `init_tray()` 方法之后插入

- [ ] **Step 1: 插入 `closeEvent` 方法**

```python
    def closeEvent(self, event):
        """重写关闭事件：点 X 缩到托盘，仅 _quitting=True 时真正退出。"""
        if self._quitting:
            event.accept()
        else:
            self._save_window_geometry()
            self.hide()
            event.ignore()
```

- [ ] **Step 2: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 重写 closeEvent 实现缩到托盘"
```

---

### Task 5: 实现 `changeEvent` 重写

**Files:**
- Modify: `md_viewer.py` — 在 `closeEvent` 之后插入

- [ ] **Step 1: 插入 `changeEvent` 方法**

```python
    def changeEvent(self, event):
        """重写状态变更事件：最小化时缩到托盘。"""
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                self._save_window_geometry()
                self.hide()
        super().changeEvent(event)
```

- [ ] **Step 2: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 重写 changeEvent 拦截最小化事件"
```

---

### Task 6: 实现辅助方法 (`_save_window_geometry`, `restore_window`, `quit_app`)

**Files:**
- Modify: `md_viewer.py` — 在 `changeEvent` 之后插入

- [ ] **Step 1: 插入三个辅助方法**

```python
    def _save_window_geometry(self):
        """保存当前窗口位置和大小。"""
        self._window_geometry = self.geometry()

    def restore_window(self):
        """从托盘恢复窗口，回到原位置和大小。"""
        if self._window_geometry is not None:
            self.setGeometry(self._window_geometry)
        self.show()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        """真正退出应用：清除托盘图标后退出进程。"""
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self._quitting = True
        QApplication.quit()
```

- [ ] **Step 2: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 实现窗口几何保存/恢复和退出方法"
```

---

### Task 7: 升级版本号

**Files:**
- Modify: `version.py`

- [ ] **Step 1: 修改版本号**

找到：
```python
VERSION = "1.4.2"
```

改为：
```python
VERSION = "1.5.0"
```

- [ ] **Step 2: 提交**

```bash
git add version.py
git commit -m "chore: 版本号升级至 1.5.0"
```

---

### Task 8: 运行启动验证

- [ ] **Step 1: 启动应用**

```bash
python md_viewer.py
```

验证：窗口正常显示，托盘区出现 Popup 图标。

- [ ] **Step 2: 验证点 X 缩到托盘**

点击窗口 X 按钮 → 窗口消失，托盘图标存在，进程未退出。

- [ ] **Step 3: 验证双击托盘恢复窗口**

双击托盘图标 → 窗口在原来位置和大小时恢复。

- [ ] **Step 4: 验证最小化按钮缩到托盘**

点击最小化按钮 → 窗口消失，托盘图标存在。

- [ ] **Step 5: 验证右键退出**

右键托盘图标 → 弹出菜单，点击"退出" → 托盘图标消失，进程退出。

- [ ] **Step 6: 验证恢复后功能正常**

恢复窗口后，打开/关闭文件、刷新等原有功能正常。

- [ ] **Step 7: 验证文件内容保持**

打开一个 md 文件，点 X 缩到托盘，双击恢复 → 文件内容仍在。
