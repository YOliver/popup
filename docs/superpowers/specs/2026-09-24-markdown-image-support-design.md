# Markdown 图片显示支持 — 设计文档

- 日期：2026-09-24
- 状态：待实现
- 关联版本：v1.5.3

## 1. 背景与问题

Popup 用 python-markdown 把 Markdown 转成 HTML，再用 `QTextBrowser.setHtml()` 显示。当前渲染流程（`md_viewer.py:653-687`）只调用：

```python
self.text_browser.setHtml(self.wrap_html(html_body))
```

`setHtml()` 未传入基准 URL，`QTextDocument` 的 `baseUrl` 保持为空。因此 Markdown 里的相对路径图片 `![alt](img/a.png)` 会变成 `<img src="img/a.png">`，但 Qt 无法把相对路径解析到实际文件，最终只显示一个破损文件图标。

## 2. 目标与非目标

### 目标

- 正确显示 Markdown 中引用的**本地相对路径**图片。
- 支持常见位图格式：PNG、JPG/JPEG、GIF、BMP（由 Qt 的 `QImageReader` 原生支持，无需额外处理；GIF 仅显示首帧，静态显示，不播放动画）。

### 非目标（YAGNI）

- SVG 矢量图。
- 网络图片（http/https）。
- 本地绝对路径（`C:\...`）。
- base64 / data URI 内嵌图片。
- 图片文件变化时的自动刷新（当前 `QFileSystemWatcher` 仅监听 md 文件本身，本设计不改动该行为）。

## 3. 方案概述

采用「设置 QTextBrowser 基准 URL」方案：在渲染前，把 md 文件所在目录设为 `QTextDocument` 的 `baseUrl`。Qt 会以该目录为基准解析 `<img>` 的相对 `src`，通过内置资源加载机制读取本地文件并用 `QImageReader` 解码显示。

## 4. 详细设计

### 4.1 改动点

**文件：`md_viewer.py`**

1. 在 Qt 导入处新增 `QUrl`（当前第 48-49 行）：

```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent, QUrl
```

2. 在 `reload_file()` 的 `setHtml()` 调用前设置基准 URL（当前第 687 行附近）：

```python
base_dir = os.path.dirname(self.file_path)
if not base_dir.endswith(os.sep):
    base_dir += os.sep
base_url = QUrl.fromLocalFile(base_dir)
self.text_browser.document().setBaseUrl(base_url)
self.text_browser.setHtml(self.wrap_html(html_body))
```

### 4.2 关键细节

- `self.file_path` 在 `load_file()`（`md_viewer.py:645`）已通过 `os.path.abspath()` 规范为绝对路径，故 `os.path.dirname()` 得到的是绝对目录。
- 目录字符串末尾必须带 `os.sep`，确保 `QUrl.fromLocalFile()` 将路径识别为**目录**而非文件；否则相对路径会错误地解析到父目录。因 `os.path.dirname()` 对盘符根目录（如 `C:\`）已返回带尾随分隔符的结果，故用 `endswith(os.sep)` 判断避免重复追加（实测重复追加会产出损坏的 `file:///C://`）。
- `QUrl.fromLocalFile()` 会自动对中文、空格等特殊字符做百分号编码，Qt 加载资源时用 `toLocalFile()` 还原为真实路径，因此中文/空格路径无需额外处理。
- 先 `setBaseUrl()` 再 `setHtml()`。已实测验证 `setHtml()` 不会重置已设置的 `baseUrl`，且 `wrap_html()` 输出的 HTML 不含 `<base>` 标签，故此顺序确定正确。

### 4.3 数据流

```
Markdown 文件 → md.convert() → HTML（含 <img src="相对路径">）
                              ↓
             document().setBaseUrl(目录)
                              ↓
             setHtml(html) → QTextDocument 解析相对 src
                              ↓
             Qt 资源加载（toLocalFile + QImageReader）→ 位图渲染显示
```

### 4.4 错误处理

- 图片文件不存在或无法解码：Qt 不抛异常、不崩溃，`QTextBrowser` 显示 `alt` 文本（若提供）或空白占位。此为可接受的降级表现，无需额外代码。
- 无需新增 try/except 或资源清理逻辑。

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 子目录图片 `![](img/a.png)` | 正常显示 |
| 中文文件名 `![](图片.png)` | 正常显示（QUrl 自动编码） |
| 空格路径 `![](my image.png)` | 正常显示 |
| 父目录图片 `![](../shared.png)` | 正常显示（按 URL 规则解析 `../`） |
| 图片缺失 / 路径错误 | 显示 alt 文本或空白，不崩溃 |
| md 文件位于盘符根目录（如 `C:\foo.md`） | `endswith` 判断避免重复分隔符，正确解析到根目录 |

## 6. 测试计划

本项目无自动化测试框架，采用手动冒烟测试。准备一个测试 md 文件及其图片，逐项验证：

1. 子目录图片正常渲染。
2. 中文文件名图片正常渲染。
3. 含空格路径图片正常渲染。
4. `../` 父目录图片正常渲染。
5. 缺失图片：显示 alt/空白，程序不崩溃。
6. 回归检查：F5 刷新、文件监听自动刷新、目录边栏跳转、Ctrl+F 搜索、拖拽打开均不受影响。

## 7. 影响分析

- 改动集中在 `reload_file()` 一处，不触碰渲染预处理（`_dedent_fenced_blocks`、`_normalize_list_indent`）、目录、搜索、托盘等其他模块。
- 不引入新依赖。
- 不改变现有文本渲染行为，仅补充图片资源的基准路径解析。
