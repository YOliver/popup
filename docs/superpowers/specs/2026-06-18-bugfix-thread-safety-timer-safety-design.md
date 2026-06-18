# 修复全局热键 GUI 线程阻塞和定时器野指针 - 设计文档

**日期**: 2026-06-18
**版本**: v1.5.1 → v1.5.2

## 1. 背景

代码审查发现两处运行时安全隐患：

1. **全局热键处理中 `time.sleep()` 阻塞 GUI 主线程**，导致按下空格快捷键时窗口短暂冻结
2. **文件监听重试定时器无 parent**，窗口销毁后定时器可能访问已释放的对象，存在崩溃风险

## 2. 目标行为

| BUG | 当前行为 | 目标行为 |
|-----|---------|---------|
| GUI 线程阻塞 | `handle_space()` 中 `time.sleep(0.15)` 阻塞主线程 150ms | 使用带 parent 的 `QTimer` 异步等待，GUI 线程无阻塞 |
| 定时器野指针 | `QTimer.singleShot(500, lambda)` 无 parent | 使用带 parent 的 `QTimer` 实例，窗口销毁时自动取消 |

## 3. 技术方案

### 3.1 BUG 1: GUI 主线程阻塞

**问题位置**: `global_hotkey.py:127-147`

当前代码流程：

```
handle_space():
  _send_ctrl_c()         # 阻塞 ~20ms（可接受）
  time.sleep(0.15)       # 阻塞 150ms ← 问题！
  files = _read_clipboard_files()
  if files: emit(...)
```

修复方案：将剪贴板读取逻辑拆分为独立方法，使用带 parent 的 `QTimer` 实例延迟调用。同时引入防重入标志，避免在 150ms 异步等待期间被重复触发。

```
handle_space():
  if self._reading_clipboard:      # 防重入：已有等待中的读取
      return
  _send_ctrl_c()                    # 阻塞 ~20ms
  self._reading_clipboard = True   # 设置防重入标志
  timer = QTimer(self)             # parent = self，窗口销毁时自动取消
  timer.setSingleShot(True)
  timer.setInterval(150)            # 异步，不阻塞
  timer.timeout.connect(self._read_clipboard_and_emit)
  timer.start()

_read_clipboard_and_emit():        # 新增方法
  try:
      files = _read_clipboard_files()
      if files: file_selected.emit(files[0])
  finally:
      self._reading_clipboard = False  # 确保标志被重置
```

**改动范围**: `global_hotkey.py`

1. **新增属性** `self._reading_clipboard = False` — 防重入标志，在 `__init__` 中初始化
2. **修改 `handle_space()`** — 移除 `time.sleep(0.15)` 和内联的剪贴板读取/信号发射代码，替换为带 parent 的 `QTimer` 实例；开头增加防重入检查
3. **新增 `_read_clipboard_and_emit()`** — 包含原 `handle_space` 末尾的剪贴板读取和信号发射逻辑，`try/finally` 确保防重入标志一定被重置

**防重入设计动机**：`_poll()` 每 50ms 触发一次，旧代码因 `time.sleep(0.15)` 阻塞了 `_poll`，天然防止了 150ms 窗口内的重复触发。改为异步后，用户若在 150ms 内再次按空格，会产生多个并行的 QTimer，导致重复打开文件。`_reading_clipboard` 标志解决此问题。

`_send_ctrl_c()` 方法内部的 `time.sleep(0.02)` 保持不变（20ms 阻塞可接受，且涉及 keybd_event 的时序要求）。

### 3.2 BUG 2: 定时器野指针

**问题位置**: `md_viewer.py:445`

当前代码：

```python
def on_file_changed(self, path):
    if not os.path.isfile(path):
        QTimer.singleShot(500, lambda: self.re_watch(path))
```

`QTimer.singleShot` 静态方法创建的定时器没有 parent，如果用户在 500ms 内关闭窗口，定时器触发时 `self` 对象可能已被 Qt 销毁，导致崩溃。

修复方案：使用带 parent 的 `QTimer` 实例。

```python
def on_file_changed(self, path):
    if not os.path.isfile(path):
        timer = QTimer(self)                          # parent = self
        timer.setSingleShot(True)
        timer.setInterval(500)
        timer.timeout.connect(lambda: self.re_watch(path))
        timer.start()
```

Qt 子对象机制：当 parent 被销毁时，所有子 `QObject` 自动销毁，定时器不会触发。

**改动范围**: `md_viewer.py`

3. **修改 `on_file_changed()` 方法** — 将 `QTimer.singleShot(...)` 替换为带 parent 的 `QTimer` 实例

### 3.3 调用关系（BUG 1）

```
Windows → Hook Callback → _space_triggered = True
                                    │
                    QTimer(50ms) → _poll() → handle_space()
                                        ├─ _reading_clipboard? → 是 → 跳过（防重入）
                                        ├─ 检查前台窗口
                                        ├─ 发送 Ctrl+C
                                        ├─ QTimer(self, 150ms, timeout → _read_clipboard_and_emit)
                                        └─ 返回（不阻塞）
                                               │
                                         150ms 后
                                               │
                                        _read_clipboard_and_emit()
                                        ├─ 读剪贴板
                                        └─ file_selected.emit(path)
```

## 4. 影响范围

- **BUG 1**: 仅 `global_hotkey.py` 一个文件，新增 1 个属性、1 个方法，修改 1 个方法
- **BUG 2**: 仅 `md_viewer.py` 一个文件，修改 1 个方法内代码
- **不涉及**: `version.py` 暂不升级（两个修复合计后再升级）
- **不引入新依赖**
- **API 不变**: `file_selected` 信号签名不变
- **行为不变**: 功能逻辑与修复前完全一致，仅消除阻塞和崩溃风险

## 5. 验证点

| 验证项 | 验证方法 |
|--------|----------|
| 空格快捷键打开文件 | 资源管理器中选中 .md 文件，按空格，应正常打开 |
| 空格快捷键恢复窗口 | 窗口缩到托盘后，按空格，应恢复并打开文件 |
| GUI 不冻结 | 空格快捷键触发时，快速拖拽窗口，不应卡顿 |
| 文件监听刷新 | 编辑器修改保存 Markdown 文件，应正常刷新 |
| 编辑器保存后关闭窗口 | 编辑器以"删除+重建"方式保存文件后，在 500ms 内关闭 Popup，不应崩溃 |
| 正常退出 | 点击托盘退出，进程正常结束 |

## 6. 已知限制

- **异步剪贴板读取**：`_send_ctrl_c()` 执行后，150ms 的异步等待期间事件循环继续运行，理论上其他应用可在此时覆盖剪贴板。该窗口仅 150ms，实际触发概率极低，不做额外处理。

## 7. 不做的事

- 不重构 `_send_ctrl_c()` 方法（20ms 阻塞可接受）
- 不引入 asyncio 或其他异步框架
- 不修改版本号（后续集中升级）
- 不添加 `cleanup()` 方法到 `GlobalHotkey`（`__del__` 修复不属于本次范围）
