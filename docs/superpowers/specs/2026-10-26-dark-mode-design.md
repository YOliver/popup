# 深色模式设计

## 目标

为 Popup 增加深色模式，覆盖整个窗口（预览、目录、编辑面板、搜索条、菜单栏、下拉/托盘菜单、状态栏、滚动条、对话框、系统标题栏）。

## 需求

- **切换方式**：手动切换，选择持久化，重启后保持。不跟随系统主题。
- **入口**：「窗口」菜单内的可勾选项「深色模式」，位于分辨率列表之后（中间加分隔线）。无快捷键。
- **持久化**：`QSettings` 键 `appearance/dark_mode`，类型 bool，默认 `False`。
- **标题栏**：深色模式下 Windows 系统标题栏同步变深；不支持的系统静默跳过。
- **浅色零回归**：浅色模式外观（含系统 windowsvista 风格）与当前版本完全一致。

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

### 3. 深色调色板

`_dark_palette()` 返回 `QPalette`，颜色取自 `DARK`：

- `Window`/`Button`/`AlternateBase`/`ToolTipBase` → `search_bg`
- `Base` → `bg`
- `WindowText`/`Text`/`ButtonText`/`ToolTipText` → `fg`
- `BrightText` → `strong_fg`
- `Highlight` → `selected`，`HighlightedText` → `strong_fg`
- `Link` → `link`
- `PlaceholderText` → `muted`
- `Disabled` 组的 `WindowText`/`Text`/`ButtonText` → `#6a6a6a`

### 4. 主题应用流程

`MarkdownViewer.__init__`：

1. 记录原始风格与调色板：`self._orig_style = app.style().name()`、`self._orig_palette = QPalette(app.palette())`。
2. 读取 `self._dark_mode = QSettings().value("appearance/dark_mode", False, type=bool)`。
3. 在 `init_ui()` 内部、处理命令行文件参数之前调用 `apply_theme(self._dark_mode)`，保证首次显示即为正确主题、无白闪。此时 `file_path` 为空，第 4 步只渲染廉价的欢迎页；随后命令行文件按原逻辑加载并覆盖，避免启动时 Markdown 被解析两次。`apply_theme` 用到的控件（含 `pin_btn`）须在该调用点之前创建完毕。

菜单项：`self.dark_action` 可勾选，在 `triggered.connect` 之前 `setChecked(self._dark_mode)`；`triggered` 连接 `toggle_dark_mode(checked)`，它会更新 `self._dark_mode`、写入 `QSettings`，再调用 `apply_theme(checked)`。

`apply_theme(dark)` 按顺序执行：

1. `self._colors = DARK if dark else LIGHT`
2. 应用级风格：
   - 深色：`app.setStyle("Fusion")`，`app.setPalette(_dark_palette())`
   - 浅色：`app.setStyle(self._orig_style)`，`app.setPalette(self._orig_palette)`
3. 用第 2 节函数重设各控件 stylesheet（搜索输入框按当前是否“无结果”选择 `error`，以 `match_count_label.text() == "无结果"` 判定）。
4. 重渲染预览：已打开文件则 `reload_file()`（自带滚动位置保留与锚点映射重建）；否则调用 `_show_welcome()`。`_show_welcome()` 由 `init_ui` 末尾现有欢迎页代码抽出，两处共用；`init_ui` 末尾的“无文件则显示欢迎页”逻辑保留（欢迎页渲染开销可忽略，重复一次无妨）。
5. `self.pin_btn.setIcon(_build_pin_icon(self._colors['pin_on']))`
6. 若窗口已创建原生句柄（`self.isVisible()`），调用 `_apply_titlebar_dark(dark)`。

`showEvent`：在现有置顶逻辑之后追加 `_apply_titlebar_dark(self._dark_mode)`，幂等。原因：构造期 `winId()` 不可用（见图钉代码注释），首次标题栏着色放到显示时。

### 5. 标题栏着色

`_apply_titlebar_dark(dark)`：

1. `hwnd = int(self.winId())`，`value = ctypes.c_int(1 if dark else 0)`。
2. `DwmSetWindowAttribute(hwnd, 20, byref(value), 4)`（`DWMWA_USE_IMMERSIVE_DARK_MODE`，Win10 20H1+）；返回值非 0 时改用属性 `19` 重试（Win10 1809–1909）。
3. 仍失败则 `logger.debug` 记录并返回，不抛异常。
4. 成功后调用 `SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)` 强制重绘非客户区（Win10 否则需重新激活才变色）。

`dwmapi` 通过 `ctypes.windll.dwmapi` 加载，`argtypes`/`restype` 与现有 `_user32.SetWindowPos` 声明方式一致。新增常量 `SWP_NOZORDER = 0x0004`、`SWP_FRAMECHANGED = 0x0020`。

## 测试

### 自动化：`tests/test_theme.py`（offscreen）

1. `LIGHT.keys() == DARK.keys()`。
2. `wrap_html(body, LIGHT)` 包含现有关键值：`background: #fff`、`color: #333`、`color: #0366d6`、`background: #f4f4f4`、`background-color: #e8e8e8`。
3. `wrap_html(body, DARK)` 包含 `DARK['bg']`、`DARK['fg']`，且不含 `background: #fff`。
4. `_search_input_qss(c, error=True)` 含 `c['error_border']`；`error=False` 含 `c['input_border']`。
5. `_build_pin_icon(DARK['pin_on'])` 的 On 状态 pixmap 非空，且非透明像素平均亮度 > 128。
6. `_dark_palette()` 的 `Window`、`Base`、`Text` 颜色分别等于 `DARK['search_bg']`、`DARK['bg']`、`DARK['fg']`。
7. 构造 `MarkdownViewer`，`apply_theme(True)` 后应用风格名为 `fusion`、`toc_tree.styleSheet()` 含 `DARK['toc_bg']`；再 `apply_theme(False)` 后风格名与调色板 `Window` 色恢复为初始值，`toc_tree.styleSheet()` 含 `LIGHT['toc_bg']`。
   - 现有测试从未构造过 `MarkdownViewer`，本条需隔离构造副作用：patch `md_viewer.GlobalHotkey`（避免安装全局键盘钩子）、patch `sys.argv` 为单元素列表（避免 pytest 参数被当作文件打开）、patch `_apply_titlebar_dark`。
   - 本条只调用 `apply_theme`，不调用 `toggle_dark_mode`，因此不写入用户 `QSettings`。
   - offscreen 下初始风格可能本就是 `fusion`，“恢复”断言以构造时记录的 `_orig_style` 为准，不硬编码 `windowsvista`。
8. 现有 `tests/` 全部通过，无需修改（`test_pin_icon.py` 依赖 `_build_pin_icon()` 默认参数，`wrap_html` 相关测试依赖 `c=None` 默认值）。

### 手动冒烟

offscreen 下字体与像素断言不可靠，以下视觉项手动验证：

- 标题栏随切换变色（Win11 与 Win10 各一次，如有条件）
- 菜单栏、下拉菜单、托盘右键菜单
- 引用块、代码块、行内代码、表格、链接、标题
- 目录边栏悬停/选中、折叠按钮
- 搜索条与“无结果”红框
- 编辑面板与保存按钮
- QMessageBox、打开文件对话框
- 重启后主题保持
- 来回切换后预览滚动位置保持、双向滚动同步正常

## 文档

- `README.md`「菜单」一节：「窗口」条目补充“深色模式开关”。
- `helpdocs/使用手册.md`「窗口菜单」一节：补充「深色模式」勾选项说明，注明选择会被记住。
