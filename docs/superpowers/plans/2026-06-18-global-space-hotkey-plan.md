# 全局空格快捷键打开选中文件 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现全局空格快捷键，按空格时读取资源管理器/桌面选中的文件路径并在 Popup 中打开。

**Architecture:** 新增 `global_hotkey.py` 模块，通过 ctypes 调用 Windows 底层键盘钩子 + 剪贴板读取选中文件，通过 Qt 信号通知主程序打开文件。

**Tech Stack:** ctypes (Windows API), PySide6 (QObject/Signal/QTimer/QClipboard)

---

## 修改文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `global_hotkey.py` | 新建 | 全局键盘钩子 + 剪贴板读取 + 信号发射 |
| `md_viewer.py` | 修改 | 初始化 GlobalHotkey，连接信号 |
| `version.py` | 修改 | 版本号升到 1.5.1 |

---

### Task 1: 创建 `global_hotkey.py` 骨架（ctypes 定义 + 类结构）

**Files:**
- Create: `global_hotkey.py`

- [ ] **Step 1: 创建文件，定义 ctypes 签名和 GlobalHotkey 类骨架**

```python
"""全局空格快捷键监听模块。通过 Windows 底层键盘钩子捕获空格键，
获取资源管理器/桌面选中文件路径，发射 Qt 信号通知主程序。"""
import ctypes
from ctypes import wintypes
import time

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

# ---- Win32 常量 ----
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
VK_SPACE = 0x20
VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x0002

# ---- ctypes 结构体 ----
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

# Hook 回调函数类型
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT)
)

# ---- Win32 API 函数签名 ----
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)

user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)

user32.CallNextHookEx.restype = ctypes.c_long
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

user32.keybd_event.restype = None
user32.keybd_event.argtypes = (wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.POINTER(ctypes.c_ulong))

kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)

# Windows Explorer / Desktop 窗口类名
EXPLORER_CLASSES = {"CabinetWClass", "ExploreWClass"}
DESKTOP_CLASSES = {"Progman", "WorkerW"}

# ---- 全局钩子实例引用（模块级，供钩子回调访问） ----
_hotkey_instance = None


def _hook_callback(nCode, wParam, lParam):
    """低层键盘钩子回调：仅设置标志位，不做任何耗时操作。"""
    if nCode >= 0 and wParam == WM_KEYDOWN:
        kb = lParam.contents
        if kb.vkCode == VK_SPACE and _hotkey_instance is not None:
            _hotkey_instance._space_triggered = True
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


class GlobalHotkey(QObject):
    """全局空格热键监听器。"""

    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hook_id = None
        self._hook_proc = None
        self._space_triggered = False

        # 轮询定时器，50ms 间隔检查空格标志
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll)

        self._install_hook()
        self._poll_timer.start()

    def _install_hook(self):
        """注册全局键盘钩子。"""
        global _hotkey_instance
        _hotkey_instance = self
        self._hook_proc = HOOKPROC(_hook_callback)
        h_instance = kernel32.GetModuleHandleW(None)
        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, h_instance, 0
        )

    def _uninstall_hook(self):
        """注销全局键盘钩子。"""
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
        global _hotkey_instance
        _hotkey_instance = None
```

- [ ] **Step 2: 提交**

```bash
git add global_hotkey.py
git commit -m "feat: 创建 global_hotkey 模块骨架（Win32 ctypes 定义 + 钩子回调）"
```

---

### Task 2: 实现 `handle_space()` — 窗口检测 + Ctrl+C + 剪贴板读取

**Files:**
- Modify: `global_hotkey.py` — 在 `_uninstall_hook` 之后追加

- [ ] **Step 1: 追加 `_poll`、`handle_space`、`_get_foreground_class`、`_send_ctrl_c`、`_read_clipboard_files`、`_on_file_selected`**

```python
    def _poll(self):
        """QTimer 回调：检查空格触发标志。"""
        if self._space_triggered:
            self._space_triggered = False
            self.handle_space()

    def _get_foreground_class(self):
        """获取当前前台窗口的类名。"""
        hwnd = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _send_ctrl_c(self):
        """模拟 Ctrl+C 组合键，通知前台窗口复制选中文件到剪贴板。"""
        null = ctypes.c_ulong(0)
        user32.keybd_event(VK_CONTROL, 0, 0, None)           # Ctrl down
        user32.keybd_event(ord('C'), 0, 0, None)              # C down
        time.sleep(0.02)
        user32.keybd_event(ord('C'), 0, KEYEVENTF_KEYUP, None)  # C up
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, None)  # Ctrl up

    def _read_clipboard_files(self):
        """从剪贴板读取 CF_HDROP 格式的文件路径列表。"""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        urls = mime.urls()
        return [u.toLocalFile() for u in urls if u.isLocalFile()]

    def handle_space(self):
        """处理空格热键：获取前台窗口的选中文件并发射信号。"""
        class_name = self._get_foreground_class()
        if class_name not in EXPLORER_CLASSES and class_name not in DESKTOP_CLASSES:
            return

        self._send_ctrl_c()
        time.sleep(0.15)  # 等待 Windows 将文件路径写入剪贴板

        files = self._read_clipboard_files()
        if files:
            self.file_selected.emit(files[0])

    def __del__(self):
        self._uninstall_hook()
```

- [ ] **Step 2: 提交**

```bash
git add global_hotkey.py
git commit -m "feat: 实现 handle_space — 窗口检测 + Ctrl+C + 剪贴板读取"
```

---

### Task 3: 在 `md_viewer.py` 中集成 GlobalHotkey

**Files:**
- Modify: `md_viewer.py` — `__init__` 方法和文件头部导入

- [ ] **Step 1: 新增导入**

在文件头部导入区域（第 10 行 `from version import VERSION` 之后）追加：

```python
from global_hotkey import GlobalHotkey
```

- [ ] **Step 2: 在 `__init__` 中初始化并连接信号**

当前 `__init__` 末尾（`self.init_tray()` 之后）追加：

```python
        self.init_tray()

        # 全局空格热键 — 打开资源管理器/桌面选中的文件
        self._hotkey = GlobalHotkey(self)
        self._hotkey.file_selected.connect(self._handle_hotkey_file)
```

- [ ] **Step 3: 新增 `_handle_hotkey_file` 方法**

在 `init_tray` 方法之后插入：

```python
    def _handle_hotkey_file(self, path):
        """全局热键回调：加载文件，如果窗口隐藏则恢复显示。"""
        self.load_file(path)
        if self.isHidden():
            self.restore_window()
```

- [ ] **Step 4: 语法检查**

```bash
cd G:\UGit\popup && python -c "import py_compile; py_compile.compile('md_viewer.py', doraise=True); print('OK')"
```

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py
git commit -m "feat: 集成 GlobalHotkey — 空格键打开资源管理器选中文件"
```

---

### Task 4: 升级版本号

**Files:**
- Modify: `version.py`

- [ ] **Step 1: 修改 VERSION**

找到：
```python
VERSION = "1.5.0"
```

改为：
```python
VERSION = "1.5.1"
```

- [ ] **Step 2: 提交**

```bash
git add version.py
git commit -m "chore: 版本号升级至 1.5.1"
```

---

### Task 5: 手动验证

- [ ] **Step 1: 语法检查**

```bash
cd G:\UGit\popup && python -c "import py_compile; py_compile.compile('global_hotkey.py', doraise=True); py_compile.compile('md_viewer.py', doraise=True); print('OK')"
```

- [ ] **Step 2: 启动应用**

```bash
cd G:\UGit\popup && python md_viewer.py
```
验证：窗口正常显示，托盘图标存在，无限台报错

- [ ] **Step 3: 验证资源管理器选中文件按空格**

在资源管理器中选中一个 .md 文件，按空格 → Popup 打开该文件

- [ ] **Step 4: 验证桌面选中文件按空格**

在桌面选中一个文件图标，按空格 → Popup 打开该文件

- [ ] **Step 5: 验证无选中时无反应**

资源管理器中不选中任何文件，按空格 → 无反应

- [ ] **Step 6: 验证非目标窗口时无反应**

切换到浏览器/编辑器窗口，按空格 → 无反应（浏览器正常接收到空格键）

- [ ] **Step 7: 验证托盘状态下自动恢复**

将 Popup 缩到托盘，资源管理器中选中文件按空格 → 窗口恢复并打开文件

- [ ] **Step 8: 验证退出时钩子注销**

退出 Popup → 按空格不再触发文件打开
