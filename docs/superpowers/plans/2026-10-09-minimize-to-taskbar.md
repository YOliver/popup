# 最小化改为正常缩到任务栏 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除让「最小化 → 缩到托盘」生效的 `changeEvent` 重写，使最小化正常缩到任务栏，点 X 缩托盘行为保持不变。

**Architecture:** 只删 `md_viewer.py` 里的 `changeEvent` 方法，最小化回归 Qt 默认行为；同步更新 README 与使用手册中「最小化缩托盘」的措辞；版本号升到 v1.7.4。

**Tech Stack:** Python 3.8+ / PySide6 (Qt6)

## Global Constraints

- 业务代码只改 `md_viewer.py`；文档改 `README.md`、`helpdocs/使用手册.md`；版本号改 `version.py`。不得改动其他文件。
- 不新增任何第三方依赖。
- 代码注释与 git commit message 一律中文。
- 版本号最终为 `"1.7.4"`。
- 点 X 缩托盘、托盘图标、`_save_window_geometry`、`closeEvent`、`init_tray`、`restore_window` 等全部保留，不得改动。

---

### Task 1: 删除 changeEvent 方法（最小化回归 Qt 默认）

**Files:**
- Modify: `md_viewer.py`（删除 `changeEvent` 方法）

**Interfaces:**
- Consumes: 无
- Produces: 无（仅删代码）

- [ ] **Step 1: 确认 changeEvent 当前位置**

先运行确认方法位置（行号可能因历史改动漂移，以实际文本为准）：

```bash
grep -n "def changeEvent" md_viewer.py
```

- [ ] **Step 2: 删除 changeEvent 方法**

用 Edit 把 `closeEvent` 方法结尾 + `changeEvent` 方法整段，替换为 `closeEvent` 方法结尾 + `_save_window_geometry`（即删除 changeEvent，保留方法间一个空行）。

old_string：

```python
    def closeEvent(self, event):
        """重写关闭事件：点 X 缩到托盘，仅 _quitting=True 时真正退出。"""
        if self._quitting:
            event.accept()
        else:
            self._save_window_geometry()
            self.hide()
            event.ignore()

    def changeEvent(self, event):
        """重写状态变更事件：最小化时缩到托盘。"""
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                self._save_window_geometry()
                self.hide()
        super().changeEvent(event)

    def _save_window_geometry(self):
```

new_string：

```python
    def closeEvent(self, event):
        """重写关闭事件：点 X 缩到托盘，仅 _quitting=True 时真正退出。"""
        if self._quitting:
            event.accept()
        else:
            self._save_window_geometry()
            self.hide()
            event.ignore()

    def _save_window_geometry(self):
```

- [ ] **Step 3: 确认 changeEvent 已删除、QEvent 仍被使用**

```bash
grep -n "def changeEvent" md_viewer.py
```

Expected: 无输出（方法已删除）。

```bash
grep -n "QEvent" md_viewer.py
```

Expected: 仍有输出（`eventFilter` 里用 `QEvent.Type.KeyPress`，说明 `QEvent` import 必须保留，不删）。

- [ ] **Step 4: 运行回归测试**

Run: `python -m pytest tests/ -q`
Expected: 76 passed（本任务无新增测试，确认删除 changeEvent 未破坏现有逻辑）

- [ ] **Step 5: 手动冒烟**

Run: `python md_viewer.py`

- [ ] 点最小化按钮 → 窗口正常缩到任务栏（任务栏出现图标）
- [ ] 点任务栏图标 → 窗口恢复，位置大小不变
- [ ] 点 X → 仍缩到系统托盘（任务栏无图标）
- [ ] 双击托盘图标 → 恢复窗口（不变）
- [ ] 右键托盘图标 → 退出进程（不变）
- [ ] 最小化恢复后，窗口置顶状态保持不变

- [ ] **Step 6: 提交**

```bash
git add md_viewer.py
git commit -m "fix: 最小化改为正常缩到任务栏（不再缩到托盘）"
```

---

### Task 2: 文档同步与版本号

**Files:**
- Modify: `version.py`
- Modify: `README.md`
- Modify: `helpdocs/使用手册.md`

**Interfaces:**
- Consumes: 无
- Produces: 无

- [ ] **Step 1: 更新版本号**

把 `version.py` 内容改为：

```python
VERSION = "1.7.4"
```

- [ ] **Step 2: 更新 README.md（两处）**

(1) 功能列表（第 16 行附近）：

```
- 支持系统托盘：点击 X 或最小化按钮缩到托盘，双击托盘图标恢复
```

改为：

```
- 支持系统托盘：点击 X 缩到托盘，双击托盘图标恢复；最小化正常缩到任务栏
```

(2) 「系统托盘」小节（第 62 行附近）：

```
- 点击 **X** 或 **最小化按钮** → 缩到系统托盘
```

改为：

```
- 点击 **X** → 缩到系统托盘
- 点击 **最小化按钮** → 正常缩到任务栏
```

改之前先 `Read` README.md 确认原文，以实际文本做精确替换。

- [ ] **Step 3: 更新 helpdocs/使用手册.md**

「系统托盘」小节：

```
- **点击 X 或最小化按钮**：窗口隐藏到系统托盘，进程继续运行
- **双击托盘图标**：恢复窗口
- **右键托盘图标 → 退出**：真正退出进程
```

改为：

```
- **点击 X**：窗口隐藏到系统托盘，进程继续运行
- **点击最小化按钮**：正常最小化到任务栏，点击任务栏图标恢复
- **双击托盘图标**：恢复窗口
- **右键托盘图标 → 退出**：真正退出进程
```

改之前先 `Read` 该文件确认原文。

- [ ] **Step 4: 提交**

```bash
git add version.py README.md helpdocs/使用手册.md
git commit -m "chore: 打包 v1.7.4（同步版本号与最小化行为说明）"
```

---

## Self-Review 结论

- **Spec 覆盖**：删 changeEvent（Task 1）、README 两处 + 使用手册一处 + 版本号（Task 2），spec 全部验证点映射到 Task 1 Step 5 冒烟清单。
- **占位符**：无 TBD/TODO，删代码与改文档均给出精确 old/new 文本。
- **类型一致性**：无跨任务函数/签名，仅删方法与改文本，无一致性问题。
