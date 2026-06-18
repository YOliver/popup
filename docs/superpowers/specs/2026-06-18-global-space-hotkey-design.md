# 全局空格快捷键打开选中文件 - 设计文档

**日期**: 2026-06-18
**版本**: v1.5.0 → v1.5.1

## 1. 背景

用户期望在 Popup 运行时（无论前台还是后台托盘），按空格键即可打开资源管理器或桌面中当前选中（高亮）的文件。若当前无选中文件，则无反应。

## 2. 目标行为

| 操作 | 条件 | 行为 |
|------|------|------|
| 按空格键 | 资源管理器中有文件被选中 | 打开选中的文件（在 Popup 中预览） |
| 按空格键 | 资源管理器中无文件选中 | 无反应 |
| 按空格键 | 当前前台为其他程序窗口 | 无反应 |
| 按空格键 | 多个文件被选中 | 打开第一个文件 |

## 3. 技术方案

### 3.1 架构

新增独立模块 `global_hotkey.py`，通过 ctypes 调用 Windows API 完成键盘监听和文件获取，不引入新 Python 依赖。

```
md_viewer.py ── (创建) ──→ GlobalHotkey ──→ (信号) ──→ 打开文件
                                 │
                        ctypes 调用
                        ┌─────────────────┐
                        │ WH_KEYBOARD_LL  │  低层键盘钩子
                        │ keybd_event     │  模拟 Ctrl+C
                        │ QT Clipboard    │  读取 CF_HDROP
                        └─────────────────┘
```

### 3.2 新增文件：`global_hotkey.py`

**类：`GlobalHotkey(QObject)`**

```
作用：全局空格键监听 + 获取选中文件路径
依赖：ctypes, PySide6.QtCore, PySide6.QtGui (clipboard)
```

**属性：**
- `hook_id` — `SetWindowsHookEx` 返回的钩子句柄
- `CALLBACK_TYPE` — ctypes 函数指针类型（`WINFUNCTYPE`）
- `clipboard_snapshot` — 监听前保存的原始剪贴板内容

**方法：**

1. **`__init__()`** — 定义 ctypes 结构体/函数签名，调用 `install_hook()`
2. **`install_hook()`** — 调用 `SetWindowsHookExW(WH_KEYBOARD_LL=13, ...)` 注册钩子
3. **`uninstall_hook()`** — 调用 `UnhookWindowsHookEx()` 解注册（在应用退出时调用）
4. **`handle_space()`** — 处理空格事件的核心方法：
   - 获取当前前台窗口：`GetForegroundWindow()`
   - 获取窗口类名：`GetClassNameW()`
   - 仅当类名为 `CabinetWClass`、`ExploreWClass`（资源管理器）或 `Progman`/`WorkerW`（桌面）时才继续
   - 保存当前剪贴板内容
   - 通过 `keybd_event` 发送 Ctrl+C 到前台窗口
   - 短延迟后读取 Qt 剪贴板的文件列表
   - 恢复原始剪贴板
   - 若无文件或不在目标窗口，直接返回
   - 若有文件，调用 `on_file_selected(path)` 发射信号
5. **`on_file_selected(path)`** — 发射 `file_selected = Signal(str)` 信号
6. **`low_level_keyboard_proc(nCode, wParam, lParam)`** — 钩子回调（静态/模块级函数）：
   - 仅处理 `wParam == WM_KEYDOWN` 且 `vkCode == VK_SPACE(0x20)` 的情况
   - 调用 `QApplication.postEvent()` 将处理延迟到事件循环执行
   - 调用 `CallNextHookEx()` 放行按键

### 3.3 修改文件：`md_viewer.py`

**`__init__` 修改：**
- 在 `self.init_tray()` 调用后，创建 `GlobalHotkey` 实例
- 连接信号到新的 `handle_hotkey_file(path)` 方法：
  - 加载文件：`self.load_file(path)`
  - 如果窗口当前隐藏（在托盘中），自动恢复：`self.restore_window()`

**新增导入：**
```python
from global_hotkey import GlobalHotkey
```

### 3.4 调用关系

```
Windows → Keyboard Hook → Qt Event → handle_space()
                                        ├─ 检查前台窗口
                                        ├─ 保存剪贴板 → 发送 Ctrl+C → 读剪贴板 → 恢复剪贴板
                                        ├─ 有文件 → file_selected.emit(path)
                                        └─ 无文件 → 返回
                                        │
                                  md_viewer.py
                                  load_file(path)
```

## 4. Window API 详细定义

通过 ctypes 调用的 Windows API：

| API | 作用 |
|-----|------|
| `SetWindowsHookExW` | 注册全局键盘钩子 |
| `UnhookWindowsHookEx` | 注销钩子 |
| `CallNextHookEx` | 传递给下一个钩子 |
| `GetMessageW` | 消息循环（Qt 事件循环已包含） |
| `GetForegroundWindow` | 获取前台窗口句柄 |
| `GetClassNameW` | 获取窗口类名 |
| `keybd_event` / `SendInput` | 模拟键盘输入（Ctrl+C） |
| `GetWindowThreadProcessId` | 备用：获取窗口所属进程（验证是否为 explorer.exe） |

## 5. 异常处理

- 前台窗口为 Explorer/桌面的验证：通过 `GetClassNameW` 检查类名
- 前台窗口为资源管理器但无选中文件：Ctrl+C 不会放入任何文件到剪贴板，逻辑自然跳过
- 钩子注册失败（无管理员权限等）：静默失败，不影响主程序运行
- 退出时确保 `uninstall_hook()` 被调用，避免资源泄漏

## 6. 影响范围

- **新增文件**：`global_hotkey.py`（约 150 行）
- **修改文件**：`md_viewer.py`（新增约 5 行初始化代码）
- **不引入新依赖**：仅使用标准库 ctypes + 已有的 PySide6
- **版本号**：`version.py` 中 VERSION 改为 `"1.5.1"`

## 7. 验证点

- [ ] Popup 在前台时，在资源管理器中按空格 → 文件在 Popup 中打开
- [ ] Popup 缩到托盘时，在资源管理器中按空格 → 文件在 Popup 中打开（窗口自动恢复）
- [ ] 桌面选中一个文件图标，按空格 → 文件在 Popup 中打开
- [ ] 资源管理器中无选中文件，按空格 → 无反应
- [ ] 当前前台为浏览器/编辑器等其他程序，按空格 → 无反应
- [ ] Popup 退出时，全局热键正确解注册

## 8. 不做的事

- 不添加修饰键（Ctrl+Space、Win+Space 等）
- 不弹出窗口询问文件（直接打开）
- 不处理多文件选中（仅打开第一个）
