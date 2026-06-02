"""
Popup - Markdown 实时预览工具
- 渲染 Markdown 文件并可视化显示
- 监听文件变化，自动刷新
- 窗口始终置顶
- 窗口大小可调
"""

import sys
import os
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
    QApplication, QMainWindow, QFileDialog, QLabel, QTextBrowser
)
from PySide6.QtGui import QAction, QIcon
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer
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

        self.init_ui()

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
        self.setCentralWidget(self.text_browser)

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
        html_body = markdown.markdown(
            content,
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )

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
