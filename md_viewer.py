"""
Popup - Markdown 实时预览工具
- 渲染 Markdown 文件并可视化显示
- 监听文件变化，自动刷新
- 窗口始终置顶
- 窗口大小可调
"""

import sys
import os
import re
import time
import logging
from logging.handlers import RotatingFileHandler
import markdown
from version import VERSION

_startup_time = time.perf_counter()


def setup_logging():
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "Popup")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "mdviewer.log"),
        maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    ))
    logger = logging.getLogger("Popup")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


logger = setup_logging()
logger.info("=== Popup v%s starting ===", VERSION)
logger.debug("Logging init: +%.0fms", (time.perf_counter() - _startup_time) * 1000)

_t = time.perf_counter()
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QLabel, QTextBrowser,
    QSplitter, QTreeWidget, QTreeWidgetItem, QWidget, QToolButton,
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent
logger.debug("Import PySide6: +%.0fms (%.0fms total)",
             (time.perf_counter() - _t) * 1000,
             (time.perf_counter() - _startup_time) * 1000)


class MarkdownViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.file_path = None
        self.watcher = QFileSystemWatcher()
        self.watcher.fileChanged.connect(self.on_file_changed)

        # 延迟刷新定时器，避免频繁刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(300)
        self.refresh_timer.timeout.connect(self.reload_file)

        # 托盘相关属性（在 init_ui 之后初始化）
        self.tray_icon = None
        self._window_geometry = None
        self._quitting = False

        self.init_ui()
        self.init_tray()

    def init_ui(self):
        _t = time.perf_counter()

        # 窗口置顶（先设置 flags 再设置其他属性，避免 show() 时重建窗口）
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.setWindowTitle(f"Popup v{VERSION}")
        self.setGeometry(100, 100, 800, 600)

        # 设置应用和窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.isfile(icon_path):
            icon = QIcon(icon_path)
            QApplication.instance().setWindowIcon(icon)
            self.setWindowIcon(icon)

        # 启用拖拽
        self.setAcceptDrops(True)

        # 目录边栏
        self.toc_tree = QTreeWidget()
        self.toc_tree.setHeaderLabel("目录")
        self.toc_tree.setIndentation(8)  # 减小层级缩进
        self.toc_tree.setRootIsDecorated(False)  # 不显示展开/折叠三角
        self.toc_tree.setStyleSheet("""
            QTreeWidget {
                background: #f7f7f7;
                border: none;
                font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 12px;
                padding: 4px 2px;
            }
            QTreeWidget::item {
                padding: 2px 2px;
                border: none;
                color: #333;
            }
            QTreeWidget::item:hover {
                background: #e8e8e8;
                color: #333;
            }
            QTreeWidget::item:selected {
                background: #d0e4ff;
                color: #000;
            }
            QTreeWidget::item:selected:active {
                background: #d0e4ff;
                color: #000;
            }
            QTreeWidget::item:selected:!active {
                background: #d0e4ff;
                color: #000;
            }
        """)
        self.toc_tree.itemClicked.connect(self.on_toc_clicked)

        # QTextBrowser 作为渲染控件（无需 Chromium，即时创建）
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                background: #fff;
                border: none;
                font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 14px;
                padding: 20px;
            }
        """)

        # 目录折叠/展开按钮 - 贴在正文左边缘
        self.toc_toggle_btn = QToolButton()
        self.toc_toggle_btn.setText("▶")
        self.toc_toggle_btn.setToolTip("显示目录 (Ctrl+B)")
        self.toc_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toc_toggle_btn.setFixedWidth(16)
        self.toc_toggle_btn.setStyleSheet("""
            QToolButton {
                background: #f0f0f0;
                border: none;
                border-right: 1px solid #ddd;
                color: #666;
                font-size: 10px;
            }
            QToolButton:hover {
                background: #e0e0e0;
                color: #000;
            }
        """)
        self.toc_toggle_btn.clicked.connect(self.toggle_toc)

        # 正文容器：左边缘按钮 + QTextBrowser
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.toc_toggle_btn)
        content_layout.addWidget(self.text_browser)

        # 用 Splitter 组合边栏和正文，支持拖动调节宽度
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.toc_tree)
        self.splitter.addWidget(content_widget)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([140, 660])
        self.setCentralWidget(self.splitter)

        # 默认隐藏目录
        self.toc_tree.hide()

        # 状态栏 - 字数统计
        self.word_count_label = QLabel("")
        self.statusBar().addPermanentWidget(self.word_count_label)

        # 菜单栏
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")

        open_action = QAction("打开...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        refresh_action = QAction("刷新", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.reload_file)
        file_menu.addAction(refresh_action)

        # 目录折叠快捷键
        toggle_toc_action = QAction(self)
        toggle_toc_action.setShortcut("Ctrl+B")
        toggle_toc_action.triggered.connect(self.toggle_toc)
        self.addAction(toggle_toc_action)

        # 窗口菜单 - 分辨率选择
        window_menu = menubar.addMenu("窗口")
        resolutions = [
            ("400 x 300", 400, 300),
            ("600 x 400", 600, 400),
            ("800 x 600", 800, 600),
            ("1024 x 768", 1024, 768),
            ("1280 x 720", 1280, 720),
            ("1920 x 1080", 1920, 1080),
        ]
        for label, w, h in resolutions:
            action = QAction(label, self)
            action.triggered.connect(lambda checked, width=w, height=h: self.set_window_size(width, height))
            window_menu.addAction(action)

        # 日志菜单
        log_menu = menubar.addMenu("日志")
        open_log_action = QAction("打开日志目录", self)
        open_log_action.triggered.connect(self.open_log_dir)
        log_menu.addAction(open_log_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        helpdocs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpdocs")
        help_items = [
            ("欢迎", "welcome.md"),
            ("关于", "about.md"),
            ("使用手册", "使用手册.md"),
        ]
        for label, filename in help_items:
            doc_path = os.path.join(helpdocs_dir, filename)
            action = QAction(label, self)
            action.triggered.connect(lambda checked, p=doc_path: self.open_help_doc(p))
            help_menu.addAction(action)

        logger.debug("init_ui: %.0fms (%.0fms total)",
                     (time.perf_counter() - _t) * 1000,
                     (time.perf_counter() - _startup_time) * 1000)

        # 如果命令行传入了文件路径，直接打开
        if len(sys.argv) > 1:
            path = sys.argv[1]
            if os.path.isfile(path):
                self.load_file(path)

        if not self.file_path:
            self.text_browser.setHtml(self.wrap_html(
                "<p>请通过 <b>文件 → 打开</b> 选择一个 Markdown 文件，或直接拖拽文件到窗口中</p>"
            ))

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开 Markdown 文件", "",
            "Markdown 文件 (*.md *.markdown *.txt);;所有文件 (*)"
        )
        if path:
            self.load_file(path)

    def load_file(self, path):
        # 移除旧的监听
        if self.file_path and self.file_path in self.watcher.files():
            self.watcher.removePath(self.file_path)

        self.file_path = os.path.abspath(path)
        self.setWindowTitle(f"Popup v{VERSION} - {os.path.basename(self.file_path)}")

        # 添加文件监听
        self.watcher.addPath(self.file_path)
        self.reload_file()
        logger.info("Opened file: %s", self.file_path)

    def reload_file(self):
        if not self.file_path or not os.path.isfile(self.file_path):
            return

        _t = time.perf_counter()
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error("Failed to read file: %s", e)
            self.text_browser.setHtml(self.wrap_html(f"<p style='color:red;'>读取文件失败: {e}</p>"))
            return

        _t_md = time.perf_counter()
        # python-markdown 严格按 4 空格识别嵌套列表，但很多用户惯用 3 空格
        # （与有序列表标记 "1. " 后内容的列对齐）。这里把"列表项内"3 空格缩进
        # 规范为 4 空格，避免子列表被解析成同级项。代码围栏内不处理。
        normalized = self._normalize_list_indent(content)
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        html_body = md.convert(normalized)

        # 更新目录边栏（从 toc 扩展直接拿 slug，避免文本搜索误匹配）
        self.update_toc(getattr(md, 'toc_tokens', []))

        # 保存滚动位置
        scrollbar = self.text_browser.verticalScrollBar()
        scroll_pos = scrollbar.value()

        _t_render = time.perf_counter()
        self.text_browser.setHtml(self.wrap_html(html_body))

        # 恢复滚动位置
        scrollbar.setValue(scroll_pos)

        # 更新状态栏字数统计
        char_count = len(content)
        char_no_space = len(content.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", ""))
        line_count = content.count("\n") + 1
        self.word_count_label.setText(f"  {char_no_space} chars | {char_count} chars (with spaces) | {line_count} lines  ")

        logger.debug("reload_file: read=%.0fms, markdown=%.0fms, setHtml=%.0fms, total=%.0fms",
                     (_t_md - _t) * 1000,
                     (_t_render - _t_md) * 1000,
                     (time.perf_counter() - _t_render) * 1000,
                     (time.perf_counter() - _t) * 1000)

    @staticmethod
    def _normalize_list_indent(content: str) -> str:
        """把列表项内 3 空格缩进的子项规范为 4 空格。

        典型场景：
            1. step:
               - sub a   ← 这里只有 3 个空格（与 "1. " 后内容对齐）
               - sub b
        python-markdown 不会把它识别为嵌套子列表，会"提级"成同级 li。
        本函数把"行首恰好 3 个空格 + 列表标记/正文"的行改为 4 空格。
        代码围栏（``` ~~~）内的行保持原样。
        """
        out = []
        in_fence = False
        fence_marker = None
        fence_re = re.compile(r'^(```+|~~~+)')
        for line in content.split('\n'):
            stripped = line.lstrip(' ')
            indent_len = len(line) - len(stripped)
            m = fence_re.match(stripped)
            if m:
                if in_fence and stripped.startswith(fence_marker):
                    in_fence = False
                elif not in_fence:
                    in_fence = True
                    fence_marker = m.group(1)[:3]
                out.append(line)
                continue
            if in_fence:
                out.append(line)
                continue
            # 仅处理"行首恰好 3 个空格"的非空行
            if indent_len == 3 and stripped:
                out.append(' ' + line)  # 3 → 4
            else:
                out.append(line)
        return '\n'.join(out)

    def on_file_changed(self, path):
        """文件变化回调，使用延迟刷新"""
        if not os.path.isfile(path):
            QTimer.singleShot(500, lambda: self.re_watch(path))
        else:
            self.refresh_timer.start()
        logger.debug("File changed: %s", path)

    def re_watch(self, path):
        """重新添加文件监听（处理编辑器删除-重建的情况）"""
        if os.path.isfile(path):
            if path not in self.watcher.files():
                self.watcher.addPath(path)
            self.reload_file()

    def dragEnterEvent(self, event):
        """拖拽进入窗口时判断是否接受"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖拽释放时打开文件"""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isfile(path):
                self.load_file(path)

    def open_log_dir(self):
        """打开日志存储目录"""
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "Popup")
        if os.path.isdir(log_dir):
            os.startfile(log_dir)
        else:
            logger.warning("Log directory not found: %s", log_dir)

    def set_window_size(self, width, height):
        """设置窗口大小"""
        self.resize(width, height)

    def toggle_toc(self):
        """显示/隐藏目录边栏"""
        if self.toc_tree.isVisible():
            self.toc_tree.hide()
            self.toc_toggle_btn.setText("▶")
            self.toc_toggle_btn.setToolTip("显示目录 (Ctrl+B)")
        else:
            self.toc_tree.show()
            self.toc_toggle_btn.setText("◀")
            self.toc_toggle_btn.setToolTip("隐藏目录 (Ctrl+B)")

    def update_toc(self, toc_tokens):
        """根据 markdown toc 扩展产出的 tokens 更新目录树。

        每个 token 形如 {'level':int,'id':str,'name':str,'children':[...]}。
        把 id（HTML anchor slug）保存到 UserRole，点击时用 scrollToAnchor 精确跳转。
        """
        self.toc_tree.clear()

        def add_tokens(tokens, parent):
            for tok in tokens:
                item = QTreeWidgetItem([tok.get('name', '')])
                item.setData(0, Qt.ItemDataRole.UserRole, tok.get('id', ''))
                if parent is None:
                    self.toc_tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                if tok.get('children'):
                    add_tokens(tok['children'], item)

        add_tokens(toc_tokens, None)
        self.toc_tree.expandAll()

    def on_toc_clicked(self, item, column):
        """点击目录项，按 anchor id 精确跳转"""
        anchor_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not anchor_id:
            return
        self.text_browser.scrollToAnchor(anchor_id)

    def open_help_doc(self, path):
        """打开帮助文档"""
        if os.path.isfile(path):
            self.load_file(path)
        else:
            logger.warning("Help doc not found: %s", path)
            self.text_browser.setHtml(self.wrap_html(
                f"<p style='color:red;'>帮助文档未找到: {os.path.basename(path)}</p>"
            ))

    @staticmethod
    def wrap_html(body):
        """将 Markdown 渲染结果包装为完整 HTML 页面"""
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    line-height: 1.6;
    color: #333;
    background: #fff;
}}
h1, h2, h3, h4, h5, h6 {{
    margin-top: 1.2em;
    margin-bottom: 0.6em;
    color: #1a1a1a;
}}
code {{
    background: #f4f4f4;
    padding: 2px 6px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 0.9em;
}}
pre {{
    background: #f4f4f4;
    padding: 12px;
}}
blockquote {{
    border-left: 4px solid #ddd;
    margin: 0;
    padding: 0 16px;
    color: #666;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
}}
th {{
    background: #f4f4f4;
}}
a {{
    color: #0366d6;
}}
</style>
</head>
<body>
{body}
</body>
</html>"""


def main():
    _t = time.perf_counter()
    app = QApplication(sys.argv)
    logger.debug("QApplication created: %.0fms (%.0fms total)",
                 (time.perf_counter() - _t) * 1000,
                 (time.perf_counter() - _startup_time) * 1000)

    _t = time.perf_counter()
    viewer = MarkdownViewer()
    viewer.show()
    logger.debug("Window shown: %.0fms (%.0fms total)",
                 (time.perf_counter() - _t) * 1000,
                 (time.perf_counter() - _startup_time) * 1000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
