# 点击关闭按钮缩到系统托盘 - 设计文档

**日期**: 2026-06-18
**版本**: v1.4.2 → v1.5.0

## 1. 背景

当前 Popup（Markdown 实时预览工具）点击窗口 X 按钮时，行为是直接关闭窗口并退出进程。用户期望的行为是：点 X 或最小化按钮时，软件不退出，而是缩到系统托盘（Windows 通知区域），用户可随时从托盘恢复窗口。

## 2. 目标行为

| 操作 | 当前行为 | 目标行为 |
|------|---------|---------|
| 点击 X 关闭按钮 | 窗口关闭、进程退出 | 窗口隐藏，缩到系统托盘 |
| 点击最小化按钮 | 窗口最小化到任务栏 | 窗口隐藏，缩到系统托盘 |
| 双击托盘图标 | 无托盘图标 | 恢复窗口（回到原位置和大小） |
| 右键托盘图标 | 无托盘图标 | 弹出菜单，点击「退出」关闭进程 |

## 3. 技术方案

### 3.1 架构

所有修改集中在 `md_viewer.py` 单一文件内，不新增文件，不新增依赖。

### 3.2 改动点

**新增导入**

- `PySide6.QtWidgets`：追加 `QSystemTrayIcon, QMenu`
- `PySide6.QtCore`：追加 `QEvent`

**MarkdownViewer 类修改**

1. **`__init__`** — 在 `self.init_ui()` 调用后，创建并初始化系统托盘。

2. **新增属性**：
   - `self.tray_icon: QSystemTrayIcon` — 系统托盘图标实例
   - `self._window_geometry` — 隐藏窗口前保存的窗口位置和大小，恢复时用 `setGeometry()` 还原
   - `self._quitting = False` — 退出标志，区分"缩到托盘"和"真正退出"

3. **新增方法 `init_tray()`**：
   - 创建 `QSystemTrayIcon`，使用 `app_icon.ico` 作为图标
   - 设置工具提示文字（如 "Popup v1.5.0"）
   - 创建右键菜单（`QMenu`），包含「退出」菜单项，触发 `self.quit_app()`
     - `quit_app()`：设置 `self._quitting = True`，然后调用 `QApplication.quit()`
   - 监听 `activated` 信号：只有双击（`QSystemTrayIcon.ActivationReason.DoubleClick`）才调用 `self.restore_window()`
   - 调用 `tray_icon.show()` 显示托盘图标

4. **新增方法 `closeEvent(event)`（重写）**：
   - 如果 `self._quitting` 为 True → `event.accept()` 真正关闭窗口（允许进程退出）
   - 否则 → `event.ignore()` + `self.hide()` + `self._save_window_geometry()`（缩到托盘）

5. **新增方法 `changeEvent(event)`（重写）**：
   - 监听 `QEvent.Type.WindowStateChange`
   - 当窗口状态变为最小化时，调用 `self.hide()` + `self._save_window_geometry()`

6. **新增方法 `_save_window_geometry()`**：
   - 将 `self.geometry()` 保存到 `self._window_geometry`

7. **新增方法 `restore_window()`**：
   - 如果 `self._window_geometry` 非空，调用 `self.setGeometry(self._window_geometry)`
   - 调用 `self.show()`、`self.raise_()`、`self.activateWindow()`

8. **新增方法 `quit_app()`**：
   - 调用 `self.tray_icon.hide()` 清除托盘图标（避免退出后图标残留）
   - 设置 `self._quitting = True`
   - 调用 `QApplication.quit()`

### 3.3 调用关系

```
用户点击 X/最小化 ──→ closeEvent() / changeEvent() ──→ hide() + save_geometry()
双击托盘图标 ──→ tray_icon.activated(DoubleClick) ──→ restore_window()
右键托盘 → 退出 ──→ quit_app()(_quitting=True) → QApplication.quit() → closeEvent 放行
```

## 4. 异常处理

- 托盘图标文件（`app_icon.ico`）不存在：静默跳过，使用系统默认图标
- 系统不支持托盘（非 Windows）：QSystemTrayIcon 的 `isSystemTrayAvailable()` 检查，不可用时托盘图标不显示，但关闭/最小化行为仍改为 hide（不退出），可通过 Alt+F4 退出

## 5. 影响范围

- **修改文件**：仅 `md_viewer.py`
- **不涉及**：打包配置、帮助文档、启动脚本
- **版本号**：`version.py` 中 VERSION 改为 `"1.5.0"`

## 6. 验证点

- [ ] 点 X → 窗口消失，托盘出现图标，进程未退出
- [ ] 点最小化按钮 → 同上
- [ ] 双击托盘图标 → 窗口在原来位置恢复
- [ ] 右键托盘图标 → 菜单出现，点击退出 → 进程退出
- [ ] 恢复窗口后仍可正常打开/关闭文件、刷新等
- [ ] 打开文件后点 X，再恢复窗口，文件内容仍在

## 7. 不做的事

- 不引入配置文件 / 可切换行为
- 不在窗口菜单栏添加"退出"按钮
- 不修改帮助文档（可在后续版本中更新）
