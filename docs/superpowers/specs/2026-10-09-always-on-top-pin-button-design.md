# 窗口置顶开关按钮（图钉）- 设计文档

**日期**: 2026-10-09
**版本**: v1.7.2 → v1.7.3

## 1. 背景

Popup 当前通过 `setWindowFlags(... | Qt.WindowType.WindowStaysOnTopHint)` 把窗口**硬编码为始终置顶**（`md_viewer.py:103`），用户无法关闭。用户希望新增一个图钉按钮，可随时切换窗口是否置顶，且下次启动时记住上次的选择。

## 2. 目标行为

| 操作 | 当前行为 | 目标行为 |
|------|---------|---------|
| 启动软件 | 窗口始终置顶，无法关闭 | 按上次记住的状态显示；首次启动默认置顶 |
| 点击图钉按钮（置顶中 → 取消） | 无此按钮 | 窗口变为普通窗口（可被其他窗口遮挡） |
| 再次点击图钉按钮（普通 → 置顶） | 无此按钮 | 窗口恢复置顶 |
| 退出后重新启动 | 无状态记忆 | 恢复上次的置顶/非置顶状态 |

## 3. 技术方案

### 3.1 架构

所有修改集中在 `md_viewer.py` 单一文件内，不新增文件，不新增依赖（ctypes 为标准库，QtSvg 随 PySide6 完整安装附带）。

图钉按钮放在**菜单栏最右侧**，通过 `QMenuBar.setCornerWidget(btn, Qt.Corner.TopRightCorner)` 实现，不破坏系统原生标题栏。

置顶切换采用 **Win32 `SetWindowPos`** 直接改 HWND 的 topmost 属性：
- 运行时切换：`SetWindowPos` 平滑切换，**不重建窗口、无闪烁、不动几何**。
- 首次启动：仍在 `show()` 之前用 `setWindowFlags` 设置初始置顶（此时 `winId()` 尚不可用，无法用 `SetWindowPos`）。

### 3.2 置顶切换实现（Win32）

```python
import ctypes
from ctypes import wintypes

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

> **必须设置 `argtypes`**：`winId()` 返回的 HWND 在 64 位 Python 下是 64 位句柄，若不声明 `wintypes.HWND`，ctypes 默认按 32 位 int 传递，会导致句柄截断、切换失效。项目 `global_hotkey.py` 已有同类先例。

### 3.3 图钉图标（内嵌 SVG）

不引入图标资源文件，用模块级两个 SVG 字符串常量 + `QSvgRenderer` 渲染到 `QPixmap`，再装配为 `QIcon` 的 On/Off 两态：

- **置顶态（On）**：深色实心图钉（`fill:#2c2c2c`），表示「钉住」
- **非置顶态（Off）**：浅色空心图钉（`fill:#9a9a9a`），表示「松开」

两个 SVG 共用同一个图钉 path（Material Design `push_pin` 形状，Apache 2.0 许可），仅 `fill` 颜色不同。SVG 常量内容如下（`path d` 值即 Material push_pin 标准路径，实现时原样写入）：

```python
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
```

渲染流程：

```python
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

def _svg_to_pixmap(svg: str, size: int = 16) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap

def _build_pin_icon() -> QIcon:
    icon = QIcon()
    icon.addPixmap(_svg_to_pixmap(PIN_SVG_OFF), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_svg_to_pixmap(PIN_SVG_ON),  QIcon.Mode.Normal, QIcon.State.On)
    return icon
```

`QToolButton` 勾选状态（checked）与图钉 On/Off 一一对应，图标随状态自动切换。

### 3.4 状态持久化（QSettings）

- 存储 key：`window/always_on_top`，类型 bool，默认 `True`（首次默认置顶，与现有行为一致）。
- 在 `main()` 中为 `QApplication` 设置组织名/应用名，避免 QSettings 空 key 告警，并供后续其它设置复用：

```python
app.setOrganizationName("Popup")
app.setApplicationName("Popup")
```

### 3.5 改动点（`md_viewer.py`）

**新增导入**

- `PySide6.QtWidgets`：追加 `QToolButton`
- `PySide6.QtCore`：追加 `QByteArray`
- `PySide6.QtGui`：追加 `QPainter, QPixmap`
- `PySide6.QtSvg`：追加 `QSvgRenderer`
- 标准库：`import ctypes`、`from ctypes import wintypes`

**新增模块级常量**

- `PIN_SVG_OFF` / `PIN_SVG_ON` 两个 SVG 字符串
- `HWND_TOPMOST / HWND_NOTOPMOST / SWP_NOMOVE / SWP_NOSIZE / SWP_NOACTIVATE`
- Win32 `SetWindowPos` 的 argtypes/restype 声明

**新增模块级辅助函数**

- `_svg_to_pixmap(svg, size=16)`
- `_build_pin_icon()`

**`MarkdownViewer.__init__` 修改**

- 在 `init_ui()` 之前读取 QSettings 得到初始状态：

```python
self._always_on_top = QSettings().value("window/always_on_top", True, type=bool)
```

**`init_ui()` 修改**

1. 置顶标志改为条件设置（替换 `md_viewer.py:103` 的硬编码）：

```python
if self._always_on_top:
    self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
```

2. 菜单栏创建完成后（`menubar` 定义之后、`init_ui` 返回前）创建图钉按钮：

```python
self.pin_btn = QToolButton(self)
self.pin_btn.setIcon(_build_pin_icon())
self.pin_btn.setCheckable(True)
self.pin_btn.setChecked(self._always_on_top)
self.pin_btn.setToolTip("窗口置顶")
self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
self.pin_btn.toggled.connect(self.toggle_always_on_top)
menubar.setCornerWidget(self.pin_btn, Qt.Corner.TopRightCorner)
```

按钮配一套扁平 QSS，与菜单栏高度协调，`checked` 状态用浅色底标出（如 `QToolButton:checked { background: #e0e0e0; }`）。

**新增方法**

1. **`toggle_always_on_top(self, checked: bool)`**：
   - `self._always_on_top = checked`
   - 调用 `self._apply_always_on_top(checked)`
   - `QSettings().setValue("window/always_on_top", checked)` 持久化

2. **`_apply_always_on_top(self, on: bool)`**：
   - `hwnd = int(self.winId())`
   - `_user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)`

**`main()` 修改**

- `QApplication` 创建后立即设置 `setOrganizationName` / `setApplicationName`。

### 3.6 调用关系

```
首次启动: __init__ 读 QSettings ──→ init_ui 条件 setWindowFlags（show 前）
点击图钉: toggled(checked) ──→ toggle_always_on_top
                              ├─ _apply_always_on_top → SetWindowPos(HWND_TOPMOST/NOTOPMOST)
                              └─ QSettings.setValue 持久化
```

## 4. 异常处理

- **`winId()` 不可用**：`_apply_always_on_top` 仅在用户点击按钮时调用，此时窗口必已 `show()`、HWND 有效；首次启动走 `setWindowFlags` 分支，不依赖 `winId()`。
- **SetWindowPos 失败**：返回值为 0，静默忽略（置顶状态以按钮显示为准，下次点击可重试），不阻断主流程。
- **SVG 渲染失败 / QtSvg 缺失**：`QSvgRenderer` 无法加载时 `pixmap` 为空，按钮显示空白图标但功能不受影响（可用 tooltip 兜底）。PySide6 完整安装含 QtSvg，正常场景不会触发。
- **QSettings 读不到值**：`value(key, True, type=bool)` 的默认值兜底，首次运行正常置顶。

## 5. 影响范围

- **修改文件**：`md_viewer.py`
- **版本号**：`version.py` 的 `VERSION` 改为 `"1.7.3"`
- **README**：功能列表新增「窗口置顶开关（图钉按钮）」；若提到快捷键/菜单则同步说明图钉位置
- **不涉及**：打包配置（`Popup.spec` / `installer.iss`）、帮助文档、启动脚本、`global_hotkey.py`

## 6. 验证点

- [ ] 首次启动（无历史设置）窗口置顶，图钉按钮处于「钉住」深色态
- [ ] 点击图钉 → 窗口变为普通窗口（能被其他窗口遮挡），图标变浅色「松开」态
- [ ] 再次点击图钉 → 窗口恢复置顶，图标变深色
- [ ] 切换过程中窗口**不闪烁、不跳动、位置大小不变**
- [ ] 切到非置顶后，最小化缩托盘、双击托盘恢复、点 X 缩托盘等既有行为正常
- [ ] 关闭退出后重启 → 恢复到上次的非置顶/置顶状态
- [ ] 置顶态下全局空格打开文件、拖拽打开、目录跳转等功能不受影响

## 7. 不做的事

- 不做自绘标题栏（图钉只放菜单栏右侧）
- 不引入图标资源文件或新依赖
- 不改动托盘/关闭/最小化等既有窗口行为
- 不做多显示器、DWM 层级等进阶置顶控制
