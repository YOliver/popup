# 文本搜索功能设计文档

- 日期：2026-07-02
- 目标应用：Popup（PySide6 桌面 Markdown 预览器）
- 需求来源：Ctrl+F 弹出搜索框，输入内容对正文做全文匹配

## 1. 需求概述

为 Markdown 预览器的正文区（右侧 `QTextBrowser`）增加文本搜索能力：

- 按 `Ctrl+F` 在正文区顶部弹出内嵌搜索条。
- 实时匹配：边输入边高亮第一个结果，并显示"第 N / 共 M 个"计数。
- 上/下导航：Enter / ↓ 下一个，Shift+Enter / ↑ 上一个，到边界回绕（wrap around）。
- 匹配选项：区分大小写、全词匹配两个可切换开关（默认均关闭）。
- 预填选中词：弹出时若正文有选中文本，则自动填入搜索框并全选。
- Esc 关闭搜索条。

## 2. 技术方案（方案 A）

完全使用 Qt 原生 API，不改动 HTML 结构：

- 跳转与高亮：`QTextBrowser.find(text, flags)`，找到后自动选中匹配文本，选区即高亮。
- 实时计数：`QTextBrowser.document().find(...)` 从文档开头循环扫描统计总数并定位当前序号（`find()` 本身不返回总数）。
- 匹配选项映射为 `QTextDocument.FindFlag`：
  - 区分大小写 → `FindCaseSensitively`
  - 全词匹配 → `FindWholeWords`
  - 反向导航 → `FindBackward`

被否决的备选方案：

- 方案 B（`ExtraSelection` 全量高亮）：代码量更大，超出当前需求。
- 方案 C（HTML `<mark>` 重渲染）：破坏原 HTML、影响滚动与目录联动，最易出 bug，不采用。

Markdown 文档规模小，每次改词全文扫描计数的性能开销可忽略。

## 3. 架构与放置位置

全部实现在现有 `MarkdownViewer` 类内（`md_viewer.py`），不新增文件。

### 3.1 布局改动

当前正文容器 `content_widget` 使用 `QHBoxLayout`（左侧折叠按钮 `toc_toggle_btn` + `text_browser`，见 `md_viewer.py:170-176`）。

改造为在其外再包一层 `QVBoxLayout`：

```
content_widget (QVBoxLayout)
├── search_bar (QWidget, 默认隐藏)      ← 新增，横跨正文区顶部
└── content_row (QWidget, QHBoxLayout)  ← 原有布局
    ├── toc_toggle_btn
    └── text_browser
```

搜索条横跨正文区顶部、不遮挡文字，与目录树（splitter 左栏）相互独立。

### 3.2 搜索条构成（`search_bar`）

一个 `QWidget`，水平布局，包含：

- `search_input`：`QLineEdit` 搜索输入框。
- `match_count_label`：`QLabel`，显示"第 N / 共 M 个" / "无结果"。
- `prev_btn`：上一个（▲）。
- `next_btn`：下一个（▼）。
- `case_btn`：区分大小写开关（"Aa"），可勾选 `QToolButton`，默认关闭。
- `word_btn`：全词匹配开关（"全词"），可勾选 `QToolButton`，默认关闭。
- `close_btn`：关闭（✕）。

样式沿用现有浅色扁平风格（参考 `toc_toggle_btn` 的 QSS），高度紧凑。无结果时输入框边框变红。

### 3.3 触发

新增 `Ctrl+F` 的 `QAction`（写法同现有 Ctrl+O / F5 / Ctrl+B，见 `md_viewer.py:198-212`），`triggered` 连接到 `show_search()`。

搜索条内的键盘交互通过给 `search_input` 安装事件过滤器（或子类化处理 `keyPressEvent`）拦截 Enter / Shift+Enter / Esc。

## 4. 核心方法

- `show_search()`：显示搜索条；若正文有选中文本则预填入输入框并全选；聚焦输入框。若已显示则重新聚焦并全选已有内容。
- `on_search_text_changed(text)`：实时触发。空文本 → 清状态；否则从本次搜索起点重新 `find()` 并刷新计数。
- `find_next()` / `find_previous()`：向后 / 向前 `find()`，到末尾 / 开头时回绕，刷新计数。
- `update_match_count()`：全文扫描算 total 与 current，更新计数标签与红框状态。
- `toggle_case()` / `toggle_whole_word()`：切换标志后立即从当前位置重新查找并刷新计数。
- `close_search()`：隐藏搜索条，清除选区，焦点还给正文。

标志拼装：根据 `case_btn` / `word_btn` 勾选状态组合 `QTextDocument.FindFlag`，反向导航时追加 `FindBackward`。

## 5. 键盘交互

- `Ctrl+F`：显示搜索条并聚焦；若已显示则重新聚焦并全选输入框内容。
- 输入框内：`Enter` = 下一个，`Shift+Enter` = 上一个，`Esc` = 关闭。

## 6. 边界情况

- 空输入：清除计数、清除选区、边框恢复正常，不查找。
- 无匹配：计数显示"无结果"，输入框边框变红；上/下按钮此时无操作。
- 切换匹配选项：立即用新标志从当前位置重新查找并刷新计数。
- 文档切换 / 刷新（`open_file` / `reload_file`）：若搜索条开着，保留搜索词并重新计数。
- 回绕：到边界循环，不弹提示。
- 与目录折叠（Ctrl+B）、全局空格热键并存互不影响。

## 7. 测试方式

项目为 PySide6 GUI，无现有自动化测试框架。采用手动验证清单，实现后逐条走查：

1. Ctrl+F 弹出、Esc 关闭；重复 Ctrl+F 全选已有词。
2. 实时输入即时高亮第一个匹配、计数正确。
3. Enter / Shift+Enter 与上下按钮导航正确，末尾 / 开头回绕。
4. 区分大小写、全词开关各自生效且即时刷新。
5. 预填选中词场景。
6. 无结果红框、空输入清空状态。
7. 打开新文件 / 刷新后搜索状态正确（保留搜索词并重新计数）。
8. 与目录折叠、全局热键并存无冲突。

> 若后续希望加轻量自动化测试（如 pytest-qt），可另行评估；当前默认走手动清单，符合项目现状。

## 8. 影响范围

- 仅修改 `md_viewer.py`：调整正文容器布局、新增搜索条控件与相关方法、新增 Ctrl+F 快捷键。
- 不新增源文件；不改动 Markdown 渲染逻辑、目录树、全局热键模块。
