"""
Markdown 实时预览工具
- 渲染 Markdown 文件并可视化显示
- 监听文件变化，自动刷新
- 窗口始终置顶
- 窗口大小可调
"""

import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog
)
from PySide6.QtGui import QAction
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent
import markdown
from version import VERSION


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
        self.setWindowTitle(f"Markdown Viewer v{VERSION}")
        self.setGeometry(100, 100, 800, 600)

        # 启用拖拽
        self.setAcceptDrops(True)

        # 窗口置顶
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Web 视图用于渲染 HTML
        self.web_view = QWebEngineView()
        self.web_view.setAcceptDrops(False)
        self.setCentralWidget(self.web_view)

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

        # 如果命令行传入了文件路径，直接打开
        if len(sys.argv) > 1:
            path = sys.argv[1]
            if os.path.isfile(path):
                self.load_file(path)

        if not self.file_path:
            self.web_view.setHtml(self.wrap_html("<p>请通过 <b>文件 → 打开</b> 选择一个 Markdown 文件</p>"))

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
        self.setWindowTitle(f"Markdown Viewer v{VERSION} - {os.path.basename(self.file_path)}")

        # 添加文件监听
        self.watcher.addPath(self.file_path)
        self.reload_file()

    def reload_file(self):
        if not self.file_path or not os.path.isfile(self.file_path):
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            self.web_view.setHtml(self.wrap_html(f"<p style='color:red;'>读取文件失败: {e}</p>"))
            return

        # 渲染 Markdown
        html_body = markdown.markdown(
            content,
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        self.web_view.setHtml(self.wrap_html(html_body))

    def on_file_changed(self, path):
        """文件变化回调，使用延迟刷新"""
        # 某些编辑器保存时会先删除再创建文件，需要重新添加监听
        if not os.path.isfile(path):
            QTimer.singleShot(500, lambda: self.re_watch(path))
        else:
            self.refresh_timer.start()

    def re_watch(self, path):
        """重新添加文件监听（处理编辑器删除-重建的情况）"""
        if os.path.isfile(path):
            if path not in self.watcher.files():
                self.watcher.addPath(path)
            self.reload_file()

    def showEvent(self, event):
        """窗口显示后，对 WebEngineView 内部子控件安装事件过滤器"""
        super().showEvent(event)
        # QWebEngineView 内部的渲染 widget 会拦截拖拽，需要过滤
        from PySide6.QtWidgets import QWidget
        for child in self.web_view.findChildren(QWidget):
            child.setAcceptDrops(False)
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        """拦截子控件的拖拽事件，转发到主窗口处理"""
        if event.type() == QEvent.Type.DragEnter:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        elif event.type() == QEvent.Type.Drop:
            urls = event.mimeData().urls()
            if urls:
                path = urls[0].toLocalFile()
                if os.path.isfile(path):
                    self.load_file(path)
            return True
        elif event.type() == QEvent.Type.DragMove:
            event.acceptProposedAction()
            return True
        return super().eventFilter(obj, event)

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

    def set_window_size(self, width, height):
        """设置窗口大小"""
        self.resize(width, height)

    @staticmethod
    def wrap_html(body):
        """将 Markdown 渲染结果包装为完整 HTML 页面"""
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    padding: 20px;
    max-width: 900px;
    margin: 0 auto;
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
    border-radius: 3px;
    font-size: 0.9em;
}}
pre {{
    background: #f4f4f4;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
}}
pre code {{
    background: none;
    padding: 0;
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
img {{
    max-width: 100%;
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
    app = QApplication(sys.argv)
    viewer = MarkdownViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
