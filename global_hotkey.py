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
        self._reading_clipboard = False  # 防重入标志

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
        if self._reading_clipboard:
            return  # 防重入：已有等待中的剪贴板读取

        class_name = self._get_foreground_class()
        if class_name not in EXPLORER_CLASSES and class_name not in DESKTOP_CLASSES:
            return

        self._send_ctrl_c()
        self._reading_clipboard = True
        # 异步等待 Windows 将文件路径写入剪贴板，避免阻塞 GUI 线程
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(150)
        timer.timeout.connect(self._read_clipboard_and_emit)
        timer.start()

    def _read_clipboard_and_emit(self):
        """读取剪贴板中的文件路径并发射信号。"""
        try:
            files = self._read_clipboard_files()
            if files:
                self.file_selected.emit(files[0])
        finally:
            self._reading_clipboard = False  # 确保标志被重置

    def __del__(self):
        self._uninstall_hook()
