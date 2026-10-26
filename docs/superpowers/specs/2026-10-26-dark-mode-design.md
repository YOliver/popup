# 深色模式设计

## 目标

为 Popup 增加深色模式，覆盖整个窗口（预览、目录、编辑面板、搜索条、菜单栏、下拉/托盘菜单、状态栏、滚动条、对话框、系统标题栏）。

## 需求

- **切换方式**：手动切换，选择持久化，重启后保持。不跟随系统主题。
- **入口**：「窗口」菜单内的可勾选项「深色模式」，位于分辨率列表之后（中间加分隔线）。无快捷键。
- **持久化**：`QSettings` 键 `appearance/dark_mode`，类型 bool，默认 `False`。
- **标题栏**：深色模式下 Windows 系统标题栏同步变深，由 Qt 随配色方案自动处理。
- **浅色零回归**：系统为浅色主题时，浅色模式外观与当前版本完全一致（默认风格 `windows11` 不变）。
- **锁定配色方案**：当前版本的 `windows11` 风格会跟随系统深浅色。系统为深色时，调色板变深而内联 QSS 仍是浅色，两者混在一起。新版本无论系统主题如何，都显式请求所选配色方案，顺带修正这个混搭问题。

## 非目标

- 跟随系统主题、三档切换。
- 代码块语法着色（当前 codehilite 只输出 class、未引入 pygments CSS，深色下同样为单色）。
- 图片背景处理（透明 PNG 在深色下显示为深底，属预期）。

## 方案：主题色表 + 样式模板

### 1. 主题色表

模块级定义两个字典 `LIGHT`、`DARK`，键集合必须完全一致。浅色值与现有硬编码一一对应；现存的近似色（如 `#f5f5f5`/`#f0f0f0`、`#e8e8e8`/`#e0e0e0`、`#ddd`/`#ccc`）拆为不同的键各自保留原值，不合并。

| 键 | 用途 | LIGHT | DARK |
|---|---|---|---|
| `bg` | 正文背景、搜索输入框背景 | `#fff` | `#1e1e1e` |
| `fg` | 正文文字、目录项文字 | `#333` | `#d4d4d4` |
| `heading` | 标题文字 | `#1a1a1a` | `#e8e8e8` |
| `toc_bg` | 目录边栏背景 | `#f7f7f7` | `#252526` |
| `search_bg` | 搜索条背景 | `#f5f5f5` | `#2d2d2d` |
| `toggle_bg` | 目录折叠按钮背景 | `#f0f0f0` | `#2d2d2d` |
| `hover` | 目录项悬停、图钉悬停 | `#e8e8e8` | `#3a3a3a` |
| `pressed` | 折叠按钮悬停、图钉选中 | `#e0e0e0` | `#45454a` |
| `selected` | 目录选中背景 | `#d0e4ff` | `#264f78` |
| `strong_fg` | 目录选中/按钮悬停/搜索选项选中文字 | `#000` | `#fff` |
| `border` | 分隔线、表格边框、引用左边线 | `#ddd` | `#3c3c3c` |
| `input_border` | 搜索输入框常态边框 | `#ccc` | `#555` |
| `muted` | 次要文字（计数、折叠按钮、引用文字） | `#666` | `#9a9a9a` |
| `code_bg` | `code`/`pre`/`th` 背景 | `#f4f4f4` | `#2a2a2a` |
| `quote_bg` | 引用段落背景 | `#e8e8e8` | `#2f2f2f` |
| `link` | 链接 | `#0366d6` | `#4ea1ff` |
| `error` | 内联错误文字 | `red` | `#f14c4c` |
| `error_border` | 搜索“无结果”边框 | `#e00` | `#f14c4c` |
| `pin_on` | 图钉“钉住”状态填充色 | `#2c2c2c` | `#e0e0e0` |

### 2. 样式生成函数

把现有内联 QSS 抽成接收颜色字典 `c` 的模块级函数，返回 QSS 字符串：

- `_toc_qss(c)`：目录 `QTreeWidget`
- `_browser_qss(c)`：`QTextBrowser`
- `_toc_toggle_qss(c)`：目录折叠按钮
- `_search_bar_qss(c)`：搜索条容器
- `_search_input_qss(c, error=False)`：搜索输入框；`error=True` 时边框用 `error_border`，否则用 `input_border`。合并现有 5 处重复的输入框 QSS。
- `_muted_label_qss(c)`：匹配计数标签
- `_option_btn_qss(c)`：大小写/全词按钮
- `_pin_btn_qss(c)`：图钉按钮

`wrap_html(body, c=None)` 保持 `@staticmethod`，增加颜色字典参数，`c is None` 时取 `LIGHT`，CSS 中的颜色全部取自 `c`。默认值保证现有测试（`test_anchor_pipeline`、`test_code_wrap`、`test_indent_rendering`、`test_quote_rendering` 以单参数调用）不变。`md_viewer.py` 内 4 处调用统一传 `self._colors`。内联 `<p style='color:red;'>` 改为 `color:{c['error']}`。

`_build_pin_icon(on_color="#2c2c2c")`：`PIN_SVG_ON` 常量保留，生成时把其中的 `#2c2c2c` 替换为 `on_color`。默认参数保证现有调用与 `tests/test_pin_icon.py` 不变。

### 3. 配色方案（替代自定义调色板）

应用级颜色交给 Qt 6.8+ 的 `QStyleHints.setColorScheme`，**不切换风格、不手写 `QPalette`**：

```python
QApplication.styleHints().setColorScheme(
    Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light
)
```

本机（PySide6 6.11.1，Windows 平台插件）实测：

| 状态 | 风格 | Window | Base | Text | Mid |
|---|---|---|---|---|---|
| 初始（系统浅色） | `windows11` | `#f3f3f3` | `#ffffff` | `#000000` | `#a0a0a0` |
| `setColorScheme(Dark)` | `windows11` | `#1e1e1e` | `#2d2d2d` | `#ffffff` | `#282828` |
| `setColorScheme(Light)` | `windows11` | 与初始一致 | 与初始一致 | 与初始一致 | 与初始一致 |

据此：

- 菜单栏、下拉/托盘菜单、状态栏、滚动条、分隔条、编辑面板、对话框均由 `windows11` 风格的深色调色板覆盖，派生角色（`Light`/`Mid`/`Dark`/`Shadow` 等）由 Qt 生成，不会残留浅色边框。
- 浅色模式下切回 `Light` 即恢复初始调色板，无需记录和恢复原风格、原调色板。
- 显式请求配色方案后，Qt 不再跟随系统主题变化，满足“不跟随系统”的需求。
- 内联 QSS 与 `wrap_html` 的 CSS 不受调色板影响，仍由第 1、2 节的色表驱动。

`setColorScheme` 是 Qt 6.8 新增的接口，`requirements.txt` 中的 `PySide6>=6.5` 需同步提升为 `PySide6>=6.8`。

### 4. 主题应用流程

`MarkdownViewer.__init__`：

1. 读取 `self._dark_mode = QSettings().value("appearance/dark_mode", False, type=bool)`。
2. 在 `init_ui()` 内部、处理命令行文件参数之前调用 `apply_theme(self._dark_mode)`，保证首次显示即为正确主题、无白闪。此时 `file_path` 为空，`apply_theme` 第 4 步只渲染廉价的欢迎页；随后命令行文件按原逻辑加载并覆盖，避免启动时 Markdown 被解析两次。`apply_theme` 用到的控件（含 `pin_btn`）须在该调用点之前创建完毕。

菜单项：`self.dark_action` 可勾选，在 `triggered.connect` 之前 `setChecked(self._dark_mode)`；`triggered` 连接 `toggle_dark_mode(checked)`，它会更新 `self._dark_mode`、写入 `QSettings`，再调用 `apply_theme(checked)`。

`apply_theme(dark)` 按顺序执行：

1. `self._colors = DARK if dark else LIGHT`
2. 应用级配色方案：`QApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)`（见第 3 节）。浅色启动时也要调用，以锁定浅色、不跟随系统。
3. 用第 2 节函数重设各控件 stylesheet（搜索输入框按当前是否“无结果”选择 `error`，以 `match_count_label.text() == "无结果"` 判定）。
4. 重渲染预览：已打开文件则 `reload_file()`（自带滚动位置保留与锚点映射重建）；否则调用 `_show_welcome()`。`_show_welcome()` 由 `init_ui` 末尾现有欢迎页代码抽出，两处共用；`init_ui` 末尾的“无文件则显示欢迎页”逻辑保留（欢迎页渲染开销可忽略，重复一次无妨）。
5. `self.pin_btn.setIcon(_build_pin_icon(self._colors['pin_on']))`

### 5. 标题栏着色

不写 ctypes/DWM 代码。Qt 的 Windows 平台插件会根据当前配色方案自行设置 `DWMWA_USE_IMMERSIVE_DARK_MODE`（属性 20）。本机实测（`DwmGetWindowAttribute` 读回）：

| 场景 | 属性 20 |
|---|---|
| 窗口已显示，初始（浅色） | 0 |
| 窗口已显示后 `setColorScheme(Dark)` | 1 |
| 再 `setColorScheme(Light)` | 0 |
| 先 `setColorScheme(Dark)` 再创建并显示新窗口 | 1 |

所以构造期和运行期切换都无需 `showEvent` 补调，也不必处理 `winId()` 时机。属性写入后非客户区能否立即重绘（尤其是 Win10）只能目测，列入手动冒烟；若发现 Win10 需要重新激活窗口才变色，再单独补 `SWP_FRAMECHANGED` 重绘，本设计不预先引入。

## 测试

### 自动化：`tests/test_theme.py`（offscreen）

1. `LIGHT.keys() == DARK.keys()`。
2. `wrap_html(body, LIGHT)` 包含现有关键值：`background: #fff`、`color: #333`、`color: #0366d6`、`background: #f4f4f4`、`background-color: #e8e8e8`。
3. `wrap_html(body, DARK)` 包含 `DARK['bg']`、`DARK['fg']`，且不含 `background: #fff`。
4. `_search_input_qss(c, error=True)` 含 `c['error_border']`；`error=False` 含 `c['input_border']`。
5. `_build_pin_icon(DARK['pin_on'])` 的 On 状态 pixmap 非空，且非透明像素平均亮度 > 128。
6. 构造 `MarkdownViewer`，`apply_theme(True)` 后：`setColorScheme` 最近一次以 `Qt.ColorScheme.Dark` 调用、`toc_tree.styleSheet()` 含 `DARK['toc_bg']`、应用风格名与构造前一致（不切换风格）；再 `apply_theme(False)` 后 `setColorScheme` 以 `Qt.ColorScheme.Light` 调用、`toc_tree.styleSheet()` 含 `LIGHT['toc_bg']`。
   - offscreen 平台不支持配色方案请求（实测 `setColorScheme(Dark)` 后 `colorScheme()` 仍为 `Unknown`、调色板不变），因此不断言调色板或 `colorScheme()`，改为 patch `md_viewer.QApplication.styleHints`，断言 `setColorScheme` 的调用参数。真实调色板变化由第 3 节实测与手动冒烟覆盖。
   - 现有测试从未构造过 `MarkdownViewer`，本条需隔离构造副作用：patch `md_viewer.GlobalHotkey`（避免安装全局键盘钩子）、patch `sys.argv` 为单元素列表（避免 pytest 参数被当作文件打开）。
   - 本条只调用 `apply_theme`，不调用 `toggle_dark_mode`，因此不写入用户 `QSettings`。
7. 现有 `tests/` 全部通过，无需修改（`test_pin_icon.py` 依赖 `_build_pin_icon()` 默认参数，`wrap_html` 相关测试依赖 `c=None` 默认值）。

### 手动冒烟

offscreen 下字体与像素断言不可靠，以下视觉项手动验证：

- 标题栏随切换立即变色，包括启动即为深色的情况（Win11 与 Win10 各一次，如有条件）
- 系统主题为深色时选浅色模式，界面保持纯浅色（无深色调色板与浅色 QSS 混搭）；运行中切换系统主题，界面不跟随
- 菜单栏、下拉菜单、托盘右键菜单
- 引用块、代码块、行内代码、表格、链接、标题
- 目录边栏悬停/选中、折叠按钮
- 搜索条与“无结果”红框
- 编辑面板与保存按钮
- QMessageBox、打开文件对话框
- 重启后主题保持
- 来回切换后预览滚动位置保持、双向滚动同步正常

## 依赖与文档

- `requirements.txt`：`PySide6>=6.5` 改为 `PySide6>=6.8`（`setColorScheme` 自 6.8 起提供）。

- `README.md`「菜单」一节：「窗口」条目补充“深色模式开关”。
- `helpdocs/使用手册.md`「窗口菜单」一节：补充「深色模式」勾选项说明，注明选择会被记住。
