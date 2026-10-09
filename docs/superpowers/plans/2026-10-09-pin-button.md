# 窗口置顶开关按钮（图钉）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在菜单栏最右侧加一个图钉按钮，用 Win32 `SetWindowPos` 切换窗口置顶，并用 `QSettings` 记住状态。

**Architecture:** 全部改动集中在 `md_viewer.py`。置顶状态单一来源为 `SetWindowPos`（不用 `Qt.WindowStaysOnTopHint` flag），首次显示经 `showEvent` 幂等应用初始状态；图钉图标用内嵌 SVG 常量 + `QSvgRenderer` 渲染为 `QIcon` 两态。

**Tech Stack:** Python 3.8+ / PySide6（Qt6）/ ctypes / python-markdown

## Global Constraints

- 业务代码只改 `md_viewer.py`；仅新增一个测试文件 `tests/test_pin_icon.py`。
- 不新增第三方依赖：ctypes 为标准库，QtSvg 随 PySide6 完整安装附带。
- 版本号 `version.py` 最终为 `"1.7.3"`。
- 代码注释与 commit message 一律中文（遵循项目惯例）。
- 置顶切换必须用 `SetWindowPos`，禁止重新引入 `Qt.WindowType.WindowStaysOnTopHint` flag。

---

### Task 1: 图钉图标（SVG 常量 + 渲染辅助函数）

**Files:**
- Modify: `md_viewer.py`（新增导入、SVG 常量、两个模块级函数）
- Test: `tests/test_pin_icon.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces:
  - `PIN_SVG_ON: str` / `PIN_SVG_OFF: str` — 模块级 SVG 字符串常量
  - `_svg_to_pixmap(svg: str, size: int = 16) -> QPixmap`
  - `_build_pin_icon() -> QIcon`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_pin_icon.py`：

```python
import os

# 必须在 import PySide6 之前设置，否则 QApplication 会用默认平台插件
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtCore import QByteArray
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer

from md_viewer import PIN_SVG_ON, PIN_SVG_OFF, _build_pin_icon

_app = QApplication.instance() or QApplication([])


class TestPinIcon(unittest.TestCase):
    def test_pin_svg_on_is_valid(self):
        renderer = QSvgRenderer(QByteArray(PIN_SVG_ON.encode("utf-8")))
        self.assertTrue(renderer.isValid())

    def test_pin_svg_off_is_valid(self):
        renderer = QSvgRenderer(QByteArray(PIN_SVG_OFF.encode("utf-8")))
        self.assertTrue(renderer.isValid())

    def test_build_pin_icon_not_null(self):
        self.assertFalse(_build_pin_icon().isNull())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_pin_icon.py -v`
Expected: FAIL，报 `ImportError: cannot import name 'PIN_SVG_ON' from 'md_viewer'`

- [ ] **Step 3: 新增导入**

在 `md_viewer.py` 顶部导入区做三处改动：

(1) `from PySide6.QtCore import ...` 行追加 `QByteArray, QRectF`，最终为：

```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent, QUrl, QByteArray, QRectF
```

(2) `from PySide6.QtGui import ...` 行追加 `QPainter, QPixmap`，最终为：

```python
from PySide6.QtGui import (
    QAction, QIcon, QTextDocument, QTextCursor, QFontMetricsF,
    QShortcut, QKeySequence, QFont, QPainter, QPixmap
)
```

(3) 在 QtGui 导入之后新增一行：

```python
from PySide6.QtSvg import QSvgRenderer
```

- [ ] **Step 4: 新增 SVG 常量与辅助函数**

在 `class MarkdownViewer(QMainWindow):` 定义**之前**（`logger.debug("Import PySide6: ...")` 之后）插入：

```python
# ---- 图钉（置顶开关）图标 ----
PIN_SVG_ON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="#2c2c2c" d="M16 9l-3-3V2h1V0H2v2h1v4L0 9v2h6v4'
    'c0 1 1 1 1 2h2c0-1 1-1 1-2v-4h6V9z"/>'
    '</svg>'
)
PIN_SVG_OFF = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="#9a9a9a" d="M16 9l-3-3V2h1V0H2v2h1v4L0 9v2h6v4'
    'c0 1 1 1 1 2h2c0-1 1-1 1-2v-4h6V9z"/>'
    '</svg>'
)


def _svg_to_pixmap(svg: str, size: int = 16) -> QPixmap:
    """把内嵌 SVG 字符串渲染成 size×size 的透明底 QPixmap。"""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    # 显式指定目标矩形，否则按 SVG 固有尺寸（24x24）渲染到 16x16 会被裁剪
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def _build_pin_icon() -> QIcon:
    """构建图钉 QIcon：Off=浅色（松开）、On=深色（钉住）。"""
    icon = QIcon()
    icon.addPixmap(_svg_to_pixmap(PIN_SVG_OFF), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_svg_to_pixmap(PIN_SVG_ON), QIcon.Mode.Normal, QIcon.State.On)
    return icon
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_pin_icon.py -v`
Expected: 3 passed

- [ ] **Step 6: 回归并提交**

Run: `python -m pytest tests/ -q`
Expected: 75 passed（原 72 + 新增 3）

```bash
git add md_viewer.py tests/test_pin_icon.py
git commit -m "feat: 新增图钉图标渲染辅助函数与单元测试"
```

---

### Task 2: 置顶切换核心 + 图钉按钮接入 + 持久化

**Files:**
- Modify: `md_viewer.py`（Win32 常量、`__init__`、`init_ui`、三个方法、`main`）

**Interfaces:**
- Consumes: `_build_pin_icon()`（Task 1）
- Produces: 实例属性 `self._always_on_top: bool`、`self.pin_btn: QToolButton`；方法 `showEvent(self, event)`、`toggle_always_on_top(self, checked)`、`_apply_always_on_top(self, on)`

- [ ] **Step 1: 新增 ctypes/QSettings 导入与 Win32 常量**

先在 `md_viewer.py` 顶部导入区补两处：

(1) 标准库区（`import markdown` 之后、`from version import VERSION` 附近）加：

```python
import ctypes
from ctypes import wintypes
```

(2) `from PySide6.QtCore import ...` 行追加 `QSettings`，最终为：

```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent, QUrl, QByteArray, QRectF, QSettings
```

然后在 Task 1 插入的 `_build_pin_icon` 函数**之后**、`class MarkdownViewer` **之前**插入：

```python
# ---- Win32 置顶切换 ----
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

_user32 = ctypes.windll.user32
_user32.SetWindowPos.argtypes = (
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
)
_user32.SetWindowPos.restype = wintypes.BOOL
```

- [ ] **Step 2: `__init__` 读取初始置顶状态**

在 `__init__` 中 `self.init_ui()` 调用**之前**插入：

```python
        # 置顶状态（首次默认置顶，与既有行为一致）
        self._always_on_top = QSettings().value("window/always_on_top", True, type=bool)
```

- [ ] **Step 3: 删除 `init_ui` 里的硬编码置顶行**

删除这两行（连同注释）：

```python
        # 窗口置顶（先设置 flags 再设置其他属性，避免 show() 时重建窗口）
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
```

- [ ] **Step 4: 菜单栏右侧接入图钉按钮**

在 `init_ui` 中，`logger.debug("init_ui: ...")` 那一行**之前**插入：

```python
        # 图钉按钮：切换窗口置顶（放在菜单栏最右侧）
        self.pin_btn = QToolButton(self)
        self.pin_btn.setIcon(_build_pin_icon())
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(self._always_on_top)
        self.pin_btn.setToolTip("取消置顶" if self._always_on_top else "窗口置顶")
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                padding: 2px 6px;
            }
            QToolButton:hover {
                background: #e8e8e8;
            }
            QToolButton:checked {
                background: #e0e0e0;
            }
        """)
        self.pin_btn.toggled.connect(self.toggle_always_on_top)
        menubar.setCornerWidget(self.pin_btn, Qt.Corner.TopRightCorner)
```

- [ ] **Step 5: 新增三个方法**

在 `restore_window` 方法定义结束后（`def quit_app(self):` **之前**）插入：

```python
    def showEvent(self, event):
        """首次显示及每次从托盘恢复时，幂等应用置顶状态。"""
        super().showEvent(event)
        self._apply_always_on_top(self._always_on_top)

    def toggle_always_on_top(self, checked):
        """切换窗口置顶状态并持久化。"""
        self._always_on_top = checked
        self._apply_always_on_top(checked)
        self.pin_btn.setToolTip("取消置顶" if checked else "窗口置顶")
        QSettings().setValue("window/always_on_top", checked)

    def _apply_always_on_top(self, on):
        """用 Win32 SetWindowPos 直接改 HWND 的 topmost 属性，不重建窗口。"""
        hwnd = int(self.winId())
        _user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST if on else HWND_NOTOPMOST,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
```

- [ ] **Step 6: `main()` 设置组织名/应用名**

在 `main()` 中 `app = QApplication(sys.argv)` **之后**插入：

```python
    app.setOrganizationName("Popup")
    app.setApplicationName("Popup")
```

- [ ] **Step 7: 运行测试回归**

Run: `python -m pytest tests/ -q`
Expected: 75 passed（本任务无新增测试，确认未破坏现有逻辑）

- [ ] **Step 8: 手动冒烟**

Run: `python md_viewer.py`

逐项核对 spec 验证点：

- [ ] 首次启动（无历史设置）窗口置顶，图钉为「钉住」深色态
- [ ] 点击图钉 → 窗口变普通窗口（可被其他窗口遮挡），图标变浅色「松开」态
- [ ] 再次点击 → 恢复置顶，图标变深色
- [ ] 切换过程窗口不闪烁、不跳动、位置大小不变
- [ ] 切到非置顶后，最小化缩托盘、双击托盘恢复、点 X 缩托盘均正常
- [ ] 非置顶态下点 X 缩托盘 → 双击恢复，窗口仍为非置顶
- [ ] 关闭退出后重启 → 恢复到上次状态

- [ ] **Step 9: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 新增窗口置顶开关图钉按钮（SetWindowPos 切换 + QSettings 记忆）"
```

---

### Task 3: 版本号与 README 更新

**Files:**
- Modify: `version.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 无（仅文档/版本号）
- Produces: 无

- [ ] **Step 1: 更新版本号**

把 `version.py` 内容改为：

```python
VERSION = "1.7.3"
```

- [ ] **Step 2: 更新 README**

三处改动：

(1) 顶部版本号：`> 当前版本：v1.7.2` → `> 当前版本：v1.7.3`

(2) 功能列表第 12 行 `- 窗口始终置顶，不会被其他窗口遮挡` 改为：

```markdown
- 窗口可置顶：菜单栏右侧图钉按钮切换是否置顶，状态自动记忆
```

(3) 「菜单」小节末尾追加一行说明：

```markdown
- **图钉按钮** — 菜单栏最右侧，点击切换窗口置顶/普通状态
```

- [ ] **Step 3: 提交**

```bash
git add version.py README.md
git commit -m "chore: 打包 v1.7.3（同步版本号与 README 置顶开关说明）"
```

---

## Self-Review 结论

- **Spec 覆盖**：图标（Task 1）、置顶切换/持久化/按钮接入（Task 2）、版本号+README（Task 3），spec 全部验证点均映射到 Task 2 Step 8 冒烟清单。
- **占位符**：无 TBD/TODO，每个改代码步骤均给出完整代码块。
- **类型一致性**：`_build_pin_icon`（Task 1 定义）→ `self.pin_btn.setIcon(_build_pin_icon())`（Task 2 消费）名称一致；`self._always_on_top` 在 `__init__`、`init_ui`、三个方法中拼写一致。
