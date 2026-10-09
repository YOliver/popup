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
import bisect
import logging
from logging.handlers import RotatingFileHandler
import markdown
import ctypes
from ctypes import wintypes
from version import VERSION
from global_hotkey import GlobalHotkey

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
    QHBoxLayout, QVBoxLayout, QSystemTrayIcon, QMenu, QLineEdit,
    QPushButton, QPlainTextEdit, QMessageBox
)
from PySide6.QtGui import (
    QAction, QIcon, QTextDocument, QTextCursor, QFontMetricsF,
    QShortcut, QKeySequence, QFont, QPainter, QPixmap
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent, QUrl, QByteArray, QRectF, QSettings
logger.debug("Import PySide6: +%.0fms (%.0fms total)",
             (time.perf_counter() - _t) * 1000,
             (time.perf_counter() - _startup_time) * 1000)

# ---- 图钉（置顶开关）图标 ----
PIN_SVG_ON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="#2c2c2c" d="M16 9l-3-3V2h1V0H2v2h1v4L0 9v2h6v4'
    'c0 1 1 1 1 2h2c0-1 1-1 1-2v-4h6V9z"/>'
    '</svg>'
)
PIN_SVG_OFF = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="#9a9a9a" d="M16 9l-3-3V2h1V0H2v2h1v4L0 9v2h6v4'
    'c0 1 1 1 1 2h2c0-1 1-1 1-2v-4h6V9z"/>'
    '</svg>'
)


def _svg_to_pixmap(svg: str, size: int = 16) -> QPixmap:
    """把内嵌 SVG 字符串渲染成 size×size 的透明底 QPixmap。"""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    # 显式指定目标矩形，否则按 SVG 固有尺寸（24x24）渲染到 16x16 会被裁剪
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def _build_pin_icon() -> QIcon:
    """构建图钉 QIcon：Off=浅色（松开）、On=深色（钉住）。"""
    icon = QIcon()
    icon.addPixmap(_svg_to_pixmap(PIN_SVG_OFF), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_svg_to_pixmap(PIN_SVG_ON), QIcon.Mode.Normal, QIcon.State.On)
    return icon


# ---- Win32 置顶切换 ----
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

_user32 = ctypes.windll.user32
_user32.SetWindowPos.argtypes = (
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, wintypes.UINT,
)
_user32.SetWindowPos.restype = wintypes.BOOL


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

        # 编辑面板与滚动同步状态
        self._syncing = False      # 滚动同步防循环标志位
        self._file_newline = "\n"  # 记录原文件换行风格，保存时保持一致
        self._edit_load_ok = True  # 文件内容是否成功加载；读失败时禁止保存
        # 锚点映射表（源行号 ↔ 预览 Y），滚动同步查表用
        self._anchor_lines = []
        self._anchor_ys = []

        # 文本搜索状态
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(150)
        self._count_timer.timeout.connect(lambda: self.update_match_count())

        # 置顶状态（首次默认置顶，与既有行为一致）
        self._always_on_top = QSettings().value("window/always_on_top", True, type=bool)

        self.init_ui()
        self.init_tray()

        # 全局空格热键 — 打开资源管理器/桌面选中的文件
        self._hotkey = GlobalHotkey(self)
        self._hotkey.file_selected.connect(self._handle_hotkey_file)

    def init_ui(self):
        _t = time.perf_counter()

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

        # 文本搜索条（默认隐藏，Ctrl+F 弹出）
        self.search_bar = QWidget()
        self.search_bar.setStyleSheet("""
            QWidget#search_bar {
                background: #f5f5f5;
                border-bottom: 1px solid #ddd;
            }
        """)
        self.search_bar.setObjectName("search_bar")
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(8, 4, 8, 4)
        search_layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("查找...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px 8px;
                background: #fff;
                min-width: 200px;
            }
        """)
        self.search_input.installEventFilter(self)

        self.match_count_label = QLabel("")
        self.match_count_label.setStyleSheet("color: #666; font-size: 12px;")

        self.prev_btn = QToolButton()
        self.prev_btn.setText("▲")
        self.prev_btn.setToolTip("上一个 (Shift+Enter / ↑)")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.next_btn = QToolButton()
        self.next_btn.setText("▼")
        self.next_btn.setToolTip("下一个 (Enter / ↓)")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.case_btn = QToolButton()
        self.case_btn.setText("Aa")
        self.case_btn.setToolTip("区分大小写")
        self.case_btn.setCheckable(True)
        self.case_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.case_btn.setStyleSheet("QToolButton:checked { color: #000; font-weight: bold; }")
        self.word_btn = QToolButton()
        self.word_btn.setText("全词")
        self.word_btn.setToolTip("全词匹配")
        self.word_btn.setCheckable(True)
        self.word_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.word_btn.setStyleSheet("QToolButton:checked { color: #000; font-weight: bold; }")

        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("关闭 (Esc)")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.match_count_label)
        search_layout.addWidget(self.prev_btn)
        search_layout.addWidget(self.next_btn)
        search_layout.addWidget(self.case_btn)
        search_layout.addWidget(self.word_btn)
        search_layout.addWidget(self.close_btn)

        self.search_bar.hide()

        # 信号连接（所有方法已在前面 Task 中定义，连接时立即可用）
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.next_btn.clicked.connect(self.find_next)
        self.prev_btn.clicked.connect(self.find_previous)
        self.case_btn.toggled.connect(self.toggle_case)
        self.word_btn.toggled.connect(self.toggle_whole_word)
        self.close_btn.clicked.connect(self.close_search)

        # 内层行：左边缘按钮 + QTextBrowser（原有布局）
        content_row = QWidget()
        content_row_layout = QHBoxLayout(content_row)
        content_row_layout.setContentsMargins(0, 0, 0, 0)
        content_row_layout.setSpacing(0)
        content_row_layout.addWidget(self.toc_toggle_btn)
        content_row_layout.addWidget(self.text_browser)

        # 正文容器：搜索条（默认隐藏）+ 内层行
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self.search_bar)
        content_layout.addWidget(content_row)

        # 右侧 txt 编辑面板（默认隐藏）
        self.edit_panel = QWidget()
        edit_layout = QVBoxLayout(self.edit_panel)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(0)
        edit_toolbar = QHBoxLayout()
        edit_toolbar.setContentsMargins(6, 4, 6, 4)
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_edit)
        edit_toolbar.addWidget(self.save_btn)
        edit_toolbar.addStretch()
        edit_layout.addLayout(edit_toolbar)
        self.edit_text = QPlainTextEdit()
        self.edit_text.setFont(QFont("Consolas", 11))  # 等宽字体，保证代码块/表格对齐
        edit_layout.addWidget(self.edit_text)

        # 用 Splitter 组合边栏、正文、编辑面板，支持拖动调节宽度
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.toc_tree)
        self.splitter.addWidget(content_widget)
        self.splitter.addWidget(self.edit_panel)
        self.splitter.setStretchFactor(0, 0)   # 目录：固定
        self.splitter.setStretchFactor(1, 1)   # 正文：拉伸
        self.splitter.setStretchFactor(2, 0)   # 编辑面板：固定（可拖拽调宽）
        self.splitter.setSizes([140, 460, 300])  # 三栏初始宽度
        self.setCentralWidget(self.splitter)

        # 编辑器保存快捷键（仅编辑器聚焦时生效）
        # 注意：PySide6 6.11 已移除 QShortcut(QKeySequence, parent, context)
        # 的三位置参数形式，需用带 callable 的重载或 parent+setter。
        self.save_shortcut = QShortcut(
            QKeySequence("Ctrl+S"),
            self.edit_text,
            self.save_edit,
            context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
        )

        self.edit_panel.hide()

        # 双向滚动同步（比例粗同步）
        self.text_browser.verticalScrollBar().valueChanged.connect(
            self._sync_preview_to_edit
        )
        self.edit_text.verticalScrollBar().valueChanged.connect(
            self._sync_edit_to_preview
        )

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

        # 编辑面板切换入口（顶级菜单项，位于"文件"之后、"窗口"之前）
        self.edit_action = QAction("编辑", self)
        self.edit_action.setCheckable(True)  # 面板显示时打勾，作为状态指示
        self.edit_action.triggered.connect(self.toggle_edit_panel)
        menubar.addAction(self.edit_action)

        # 目录折叠快捷键
        toggle_toc_action = QAction(self)
        toggle_toc_action.setShortcut("Ctrl+B")
        toggle_toc_action.triggered.connect(self.toggle_toc)
        self.addAction(toggle_toc_action)

        # 文本搜索快捷键
        search_action = QAction(self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(lambda: self.show_search())
        self.addAction(search_action)

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

        # 图钉按钮：切换窗口置顶（放在菜单栏最右侧）
        self.pin_btn = QToolButton(self)
        self.pin_btn.setIcon(_build_pin_icon())
        self.pin_btn.setCheckable(True)
        # 必须在 toggled.connect 之前 setChecked，否则构造期会误触发 toggle_always_on_top 去调用尚未可用的 winId()
        self.pin_btn.setChecked(self._always_on_top)
        self.pin_btn.setToolTip("取消置顶" if self._always_on_top else "窗口置顶")
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                padding: 2px 6px;
            }
            QToolButton:hover {
                background: #e8e8e8;
            }
            QToolButton:checked {
                background: #e0e0e0;
            }
        """)
        self.pin_btn.toggled.connect(self.toggle_always_on_top)
        menubar.setCornerWidget(self.pin_btn, Qt.Corner.TopRightCorner)

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

    def eventFilter(self, obj, event):
        """拦截搜索框键盘事件"""
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.find_previous()
                else:
                    self.find_next()
                return True
            elif key == Qt.Key.Key_Escape:
                self.close_search()
                return True
            elif key == Qt.Key.Key_Down:
                self.find_next()
                return True
            elif key == Qt.Key.Key_Up:
                self.find_previous()
                return True
        return super().eventFilter(obj, event)

    def _search_flags(self):
        """根据当前选项配置构建查找标志"""
        flags = QTextDocument.FindFlags()
        if self.case_btn.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.word_btn.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags

    def _clear_search_state(self):
        """清空搜索高亮和计数状态"""
        self.match_count_label.setText("")
        cursor = self.text_browser.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.text_browser.setTextCursor(cursor)
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px 8px;
                background: #fff;
                min-width: 200px;
            }
        """)

    def _do_find(self):
        """从文档开头开始查找，始终定位到第一个匹配"""
        text = self.search_input.text()
        if not text:
            self._clear_search_state()
            return
        flags = self._search_flags()
        cursor = self.text_browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_browser.setTextCursor(cursor)
        found = self.text_browser.find(text, flags)
        if not found:
            self.match_count_label.setText("无结果")
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #e00;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)
        else:
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)

    def _schedule_count_update(self):
        """防抖延迟刷新匹配计数"""
        self._count_timer.start()

    def update_match_count(self):
        """全文扫描统计匹配总数并定位当前序号"""
        text = self.search_input.text()
        if not text:
            self._clear_search_state()
            return
        flags = self._search_flags()
        cur_cursor = self.text_browser.textCursor()
        # 当前选中位置：若有选区用 selectionStart，否则用光标位置
        cur_pos = cur_cursor.selectionStart() if cur_cursor.hasSelection() else cur_cursor.position()
        doc = self.text_browser.document()
        pos = 0
        total = 0
        current = 0
        while True:
            cursor = doc.find(text, pos, flags)
            if cursor.isNull():
                break
            total += 1
            # 判断当前匹配是否包含当前光标位置
            if cursor.selectionStart() <= cur_pos <= cursor.selectionEnd():
                current = total
            pos = cursor.position()
        if total == 0:
            self.match_count_label.setText("无结果")
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #e00;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)
        else:
            if current == 0:
                current = 1  # 可能当前光标恰好在第一个匹配前
            self.match_count_label.setText(f"第 {current} / 共 {total} 个")
            self.search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 2px 8px;
                    background: #fff;
                    min-width: 200px;
                }
            """)

    def find_next(self):
        """向后查找下一个匹配，到末尾回绕"""
        text = self.search_input.text()
        if not text:
            return
        flags = self._search_flags()
        found = self.text_browser.find(text, flags)
        if not found:
            # 回绕：从文档开头重新查找
            cursor = self.text_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.find(text, flags)
        self.update_match_count()

    def find_previous(self):
        """向前查找上一个匹配，到开头回绕"""
        text = self.search_input.text()
        if not text:
            return
        flags = self._search_flags() | QTextDocument.FindFlag.FindBackward
        found = self.text_browser.find(text, flags)
        if not found:
            # 回绕：从文档末尾重新查找
            cursor = self.text_browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_browser.setTextCursor(cursor)
            self.text_browser.find(text, flags)
        self.update_match_count()

    def on_search_text_changed(self, text):
        """输入文本变化时实时触发搜索"""
        if not text:
            self._clear_search_state()
            return
        self._do_find()
        self._schedule_count_update()

    def close_search(self):
        """关闭搜索条，清理状态"""
        self._count_timer.stop()
        self._clear_search_state()
        self.search_bar.hide()
        self.text_browser.setFocus()

    def show_search(self):
        """显示搜索条，有选中文本时预填"""
        if self.search_bar.isVisible():
            # 已显示：重新聚焦并全选
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self.search_bar.show()
            cursor = self.text_browser.textCursor()
            if cursor.hasSelection():
                self.search_input.setText(cursor.selectedText())
            self.search_input.setFocus()
            self.search_input.selectAll()

    def toggle_case(self, checked):
        """切换区分大小写后重新查找"""
        self._do_find()
        self.update_match_count()

    def toggle_whole_word(self, checked):
        """切换全词匹配后重新查找"""
        self._do_find()
        self.update_match_count()

    def _handle_hotkey_file(self, path):
        """全局热键回调：加载文件，如果窗口隐藏或最小化则恢复显示。"""
        self.load_file(path)
        if self.isHidden() or self.isMinimized():
            self.restore_window()

    def init_tray(self):
        """初始化系统托盘图标和右键菜单。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
        if os.path.isfile(icon_path):
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray_icon = QSystemTrayIcon(self)

        self.tray_icon.setToolTip(f"Popup v{VERSION}")

        # 右键菜单
        menu = QMenu()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit_app)
        self.tray_icon.setContextMenu(menu)

        # 双击托盘图标恢复窗口
        self.tray_icon.activated.connect(self.on_tray_activated)

        self.tray_icon.show()

    def on_tray_activated(self, reason):
        """托盘图标激活回调：双击恢复窗口。"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.restore_window()

    def closeEvent(self, event):
        """重写关闭事件：点 X 缩到托盘，仅 _quitting=True 时真正退出。"""
        if self._quitting:
            event.accept()
        else:
            self._save_window_geometry()
            self.hide()
            event.ignore()

    def _save_window_geometry(self):
        """保存当前窗口位置和大小。"""
        self._window_geometry = self.geometry()

    def restore_window(self):
        """从托盘或最小化状态恢复窗口，回到原位置和大小。"""
        if self._window_geometry is not None:
            self.setGeometry(self._window_geometry)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        """首次显示及每次从托盘恢复时，幂等应用置顶状态。"""
        super().showEvent(event)
        self._apply_always_on_top(self._always_on_top)

    def toggle_always_on_top(self, checked):
        """切换窗口置顶状态并持久化。"""
        self._always_on_top = checked
        self._apply_always_on_top(checked)
        self.pin_btn.setToolTip("取消置顶" if checked else "窗口置顶")
        QSettings().setValue("window/always_on_top", checked)

    def _apply_always_on_top(self, on):
        """用 Win32 SetWindowPos 直接改 HWND 的 topmost 属性，不重建窗口。"""
        hwnd = int(self.winId())
        _user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST if on else HWND_NOTOPMOST,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def quit_app(self):
        """真正退出应用：清除托盘图标后退出进程。"""
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self._quitting = True
        QApplication.quit()

    def toggle_edit_panel(self):
        """切换右侧编辑面板显隐；显示时加载当前文件原文"""
        if not self.file_path:
            QMessageBox.warning(self, "提示", "请先打开文件")
            return
        if self.edit_panel.isVisible():
            self.edit_panel.hide()
            self.edit_action.setChecked(False)
        else:
            self.edit_panel.show()
            self.edit_action.setChecked(True)
            self.load_edit_text()
            self._sync_preview_to_edit(0)  # 显示时定位到预览当前比例位置

    def load_edit_text(self):
        """读取当前文件原文到编辑器，记录换行风格"""
        if not self.file_path or not os.path.isfile(self.file_path):
            self._edit_load_ok = False
            return
        try:
            with open(self.file_path, "r", encoding="utf-8", newline="") as f:
                content = f.read()
        except Exception as e:
            self.edit_text.clear()
            self._edit_load_ok = False
            QMessageBox.warning(self, "读取失败", f"无法读取文件: {e}")
            return
        self._file_newline = self._detect_newline(content)
        self._edit_load_ok = True
        self._syncing = True
        try:
            self.edit_text.setPlainText(content)
        finally:
            self._syncing = False

    def save_edit(self):
        """把编辑器内容原子写回原文件并刷新预览"""
        if not self.edit_panel.isVisible():
            return
        if not self.file_path:
            return
        if not self._edit_load_ok:
            QMessageBox.warning(self, "保存失败", "文件内容未成功加载，无法保存")
            return
        text = self.edit_text.toPlainText()
        text = self._apply_newline(text, self._file_newline)
        tmp_path = self.file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            os.replace(tmp_path, self.file_path)  # 原子替换，失败不破坏原文件
        except Exception as e:
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            QMessageBox.warning(self, "保存失败", f"写入文件失败: {e}")
            return
        self.reload_file()

    def _sync_preview_to_edit(self, value):
        """预览滚动 → 编辑器滚动条按锚点映射跟随（仅滚动视图，不动光标）。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        if not self.edit_panel.isVisible():
            return
        edit_sb = self.edit_text.verticalScrollBar()
        self._syncing = True
        try:
            if self._anchor_lines:
                y = self.text_browser.verticalScrollBar().value()
                i = self._nearest_anchor_index(self._anchor_ys, y)
                line = self._anchor_lines[i]
                blk = self.edit_text.document().findBlockByNumber(line)
                if not blk.isValid():
                    return
                doc_y = self.edit_text.blockBoundingGeometry(blk).y() + edit_sb.value()
                edit_sb.setValue(int(doc_y))
            else:
                edit_sb.setValue(self._proportional_value(
                    self.text_browser.verticalScrollBar(), edit_sb))
        finally:
            self._syncing = False

    def _sync_edit_to_preview(self, value):
        """编辑器滚动 → 预览滚动条按锚点映射跟随。

        value 由 valueChanged(int) 信号传入，方法内部取滚动条当前值，忽略入参。
        """
        if self._syncing:
            return
        preview_sb = self.text_browser.verticalScrollBar()
        self._syncing = True
        try:
            if self._anchor_lines:
                line = self.edit_text.firstVisibleBlock().blockNumber()
                i = self._nearest_anchor_index(self._anchor_lines, line)
                preview_sb.setValue(self._anchor_ys[i])
            else:
                preview_sb.setValue(self._proportional_value(
                    self.edit_text.verticalScrollBar(), preview_sb))
        finally:
            self._syncing = False

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

        # 编辑面板可见时，同步编辑器内容到新文件，防止保存写错文件
        if self.edit_panel.isVisible():
            self.load_edit_text()

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
        # 先拍平缩进围栏，再规范列表缩进（必须先 dedent 后 normalize，
        # 否则 normalize 改动的缩进量会导致围栏对不齐）
        normalized = self._dedent_fenced_blocks(content)
        normalized = self._normalize_list_indent(normalized)
        normalized = self._inject_anchors(normalized)
        normalized = self._preserve_indent(normalized)
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        html_body = md.convert(normalized)
        em_px = self._body_em_px()
        html_body = self._apply_indent(html_body, em_px)
        html_body = self._fix_image_line_height(html_body)
        html_body = self._style_blockquotes(html_body)
        html_body = self._strip_trailing_br(html_body)

        # 更新目录边栏（从 toc 扩展直接拿 slug，避免文本搜索误匹配）
        self.update_toc(getattr(md, 'toc_tokens', []))

        # 保存滚动位置
        scrollbar = self.text_browser.verticalScrollBar()
        scroll_pos = scrollbar.value()

        _t_render = time.perf_counter()
        base_url = self._build_base_url(self.file_path)
        self.text_browser.document().setBaseUrl(base_url)

        # 程序性滚动隔离：setHtml/setValue 会触发 valueChanged，
        # 用 _syncing 包裹，避免刷新时误触发滚动同步导致闪动
        self._syncing = True
        try:
            self.text_browser.setHtml(self.wrap_html(html_body))
            # 恢复滚动位置
            scrollbar.setValue(scroll_pos)
        finally:
            self._syncing = False

        self._anchor_lines, self._anchor_ys = self._build_anchor_map(
            self.text_browser.document()
        )

        # 若搜索条开着，刷新搜索状态
        if self.search_bar.isVisible() and self.search_input.text():
            self._do_find()
            self.update_match_count()

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
    def _dedent_fenced_blocks(content: str) -> str:
        """把缩进的代码围栏（```` ``` ````` / `~~~`）及其内部行整体左移到顶格。

        python-markdown 的 fenced_code 扩展不识别缩进在列表项内的围栏，
        会把 ``` 退化成内联 code，导致多行内容在 Qt 富文本里挤成一行。
        本函数在渲染前把所有缩进围栏拍平到顶格，使 fenced_code 能正确识别。
        围栏内代码的相对缩进予以保留。
        """
        lines = content.split('\n')
        out = []
        i = 0
        open_re = re.compile(r'^(\s*)(`{3,}|~{3,})(.*)$')
        close_re = re.compile(r'^(\s*)(`{3,}|~{3,})\s*$')
        while i < len(lines):
            line = lines[i]
            m = open_re.match(line)
            if m and m.group(1):  # 缩进围栏开始
                indent = m.group(1)
                fence_char = m.group(2)[0]    # ` 或 ~
                fence_len = len(m.group(2))   # 反引号/波浪号个数
                out.append(line[len(indent):])
                i += 1
                while i < len(lines):
                    inner = lines[i]
                    cm = close_re.match(inner)
                    # 闭合判断：同类型且数量 >= 开启围栏
                    if cm and cm.group(2)[0] == fence_char and len(cm.group(2)) >= fence_len:
                        out.append(inner[len(indent):] if inner.startswith(indent) else inner.lstrip())
                        i += 1
                        break
                    out.append(inner[len(indent):] if inner.startswith(indent) else inner.lstrip())
                    i += 1
            else:
                out.append(line)
                i += 1
        return '\n'.join(out)

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

    @staticmethod
    def _inject_anchors(content: str) -> str:
        """在每个 Markdown 块起始行注入零高锚点 <a id="popup-anchor-N"></a>，N 为 0-based 源行号。

        锚点插在块标记字符之后（标题 #、列表 -/1.、引用 >）或段落行首全角空格
        之后，避免破坏 markdown 结构与段首缩进。跳过代码围栏、表格、HTML 块、
        水平线、setext 标题（下划线及其文本行）、引用式链接定义、缩进代码块。
        复用 _normalize_list_indent 的围栏跟踪模式。
        """
        out = []
        in_fence = False
        fence_marker = None
        fence_re = re.compile(r'^(```+|~~~+)')
        heading_re = re.compile(r'^(\s{0,3})(#{1,6})\s+(.*)$')
        list_re = re.compile(r'^(\s*)([-*+]|\d+[.)])\s+(.*)$')
        quote_re = re.compile(r'^(\s*(?:>\s*)+)(.*)$')
        fullspace_re = re.compile(r'^(\u3000+)')
        html_re = re.compile(r'^\s*<')
        hrule_re = re.compile(r'^\s{0,3}([-*_])\s*(\1\s*){2,}$')
        setext_re = re.compile(r'^\s{0,3}=+\s*$')
        setext2_re = re.compile(r'^\s{0,3}-{1,}\s*$')
        refdef_re = re.compile(r'^\s{0,3}\[([^\]]+)\]:\s*\S*')
        lines = content.split('\n')
        for idx in range(len(lines)):
            line = lines[idx]
            stripped = line.lstrip(' ')
            m = fence_re.match(stripped)
            if m:
                if in_fence and stripped.startswith(fence_marker):
                    in_fence = False
                elif not in_fence:
                    in_fence = True
                    fence_marker = m.group(1)[:3]
                out.append(line)
                continue
            if in_fence or not stripped or stripped.startswith('|'):
                out.append(line)
                continue
            if (html_re.match(line) or hrule_re.match(line)
                    or setext_re.match(line) or setext2_re.match(line)
                    or refdef_re.match(line)):
                out.append(line)
                continue
            anchor = f'<a id="popup-anchor-{idx}"></a>'
            mh = heading_re.match(line)
            if mh:
                out.append(f'{mh.group(1)}{mh.group(2)} {anchor}{mh.group(3)}')
                continue
            ml = list_re.match(line)
            if ml:
                out.append(f'{ml.group(1)}{ml.group(2)} {anchor}{ml.group(3)}')
                continue
            mq = quote_re.match(line)
            if mq:
                if mq.group(2).strip('\u3000 \t'):
                    out.append(f'{mq.group(1)}{anchor}{mq.group(2)}')
                else:
                    out.append(line)  # 空引用行不注锚，保持段落分隔符
                continue
            if len(line) - len(stripped) >= 4:
                out.append(line)  # 缩进代码块
                continue
            mf = fullspace_re.match(line)
            if mf:
                out.append(f'{mf.group(1)}{anchor}{line[len(mf.group(1)):]}')
            elif idx + 1 < len(lines) and (
                    setext_re.match(lines[idx + 1])
                    or setext2_re.match(lines[idx + 1])):
                out.append(line)  # setext 标题文本行，跳过注入
            else:
                out.append(f'{anchor}{line}')
        return '\n'.join(out)

    @staticmethod
    def _preserve_indent(content: str) -> str:
        """把行首连续 N 个全角空格替换为 <i data-indent="N"></i> 占位标记。

        python-markdown 会剥掉行首空白，Qt 也会剥掉段首全角空格，故在转换前
        用内联 HTML 占位。跳过代码围栏内部行（<pre><code> 内 Qt 会原样保留
        前导空格，替换反而会污染代码）。
        """
        out = []
        in_fence = False
        fence_marker = None
        fence_re = re.compile(r'^(```+|~~~+)')
        indent_re = re.compile(r'^(\u3000+)')
        for line in content.split('\n'):
            stripped = line.lstrip(' ')
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
            m = indent_re.match(line)
            if m:
                out.append('<i data-indent="%d"></i>' % len(m.group(1)) + line[m.end():])
            else:
                out.append(line)
        return '\n'.join(out)

    @staticmethod
    def _apply_indent(html: str, em_px: float) -> str:
        """把 <p><i data-indent="N"></i> 替换为 <p style="text-indent:%.1fpx">。

        Qt 的 CSS 解析不支持 em 单位（text-indent:2em 被忽略），仅支持 px，
        故用 em_px（一个汉字/全角空格的像素宽度）换算成 px。占位标记只出现在
        <p> 段首，故正则只匹配 <p>；其他容器内的空 <i> 标记渲染为零宽、不可见。
        """
        def repl(m):
            n = int(m.group(1))
            return '<p style="text-indent:%.1fpx">' % (n * em_px)
        return re.sub(r'<p><i data-indent="(\d+)"></i>', repl, html)

    @staticmethod
    def _font_em_px(font) -> float:
        """返回给定字号下一个全角空格的像素宽度（约 1em），缺字形回退 14.0。"""
        em_px = QFontMetricsF(font).horizontalAdvance('\u3000')
        return em_px if em_px > 0 else 14.0

    def _body_em_px(self) -> float:
        """返回正文字号下一个全角空格的像素宽度（约 1em），用于 text-indent 换算。

        命令行直接打开文件时，首次 reload 发生在 show() 之前，样式表尚未应用，
        font() 仍是默认字号。先 ensurePolished 强制应用样式表，保证度量到
        正确的 14px 正文字号；全角空格缺字形时回退 14.0。
        """
        self.text_browser.ensurePolished()
        return self._font_em_px(self.text_browser.font())

    @staticmethod
    def _build_base_url(file_path: str) -> QUrl:
        """返回 md 文件所在目录的基准 URL，供 QTextBrowser 解析相对路径图片。

        目录末尾必须带分隔符，否则 QUrl.fromLocalFile 会把路径当文件处理，
        导致相对路径错误解析到父目录；根目录（如 C:\\）的 dirname 已带尾随
        分隔符，故用 endswith 判断避免重复追加（重复追加会产出损坏的 C://）。
        """
        base_dir = os.path.dirname(file_path)
        if not base_dir.endswith(os.sep):
            base_dir += os.sep
        return QUrl.fromLocalFile(base_dir)

    @staticmethod
    def _fix_image_line_height(html: str) -> str:
        r"""给「仅含图片（可带前置锚点）的段落」注入 line-height:100%。

        Qt 会把 body 的 line-height 倍数作用于图片行，导致图片行高被放大 1.6 倍，
        图片下方出现大段空白。对纯图片段落覆盖为 100%，恢复图片实际行高。
        python-markdown 输出格式固定为 <p><a id="popup-anchor-N"></a><img .../></p>；
        同一段落可能含多张图片，nl2br 扩展会把段落内软换行转成 <br />，
        故用 (?:<img [^>]*/>\s*(?:<br />\s*)?)+ 匹配一张或多张图片（其间可夹 <br />）。
        段落可能已带 style（如 _apply_indent 注入的 text-indent），需合并而非覆盖。
        """
        pattern = (
            r'<p(?: style="([^"]*)")?>'
            r'((?:<a id="popup-anchor-\d+"></a>)*(?:<img [^>]*/>\s*(?:<br />\s*)?)+)</p>'
        )

        def repl(m):
            existing = m.group(1)
            content = m.group(2)
            if existing:
                return f'<p style="{existing.rstrip(";")};line-height:100%">{content}</p>'
            return f'<p style="line-height:100%">{content}</p>'

        return re.sub(pattern, repl, html)

    @staticmethod
    def _style_blockquotes(html: str) -> str:
        """把 blockquote 转为单列表格，使 Qt 能渲染整块背景 + 左竖线。

        Qt 富文本引擎不支持 blockquote 的块级背景（会降级为文字级背景），
        而 table 支持整块背景/边框/内边距。python-markdown 输出的 blockquote
        标签无属性、格式固定，字符串替换安全；嵌套引用自然变为嵌套表格。
        """
        html = html.replace(
            "<blockquote>",
            '<table class="md-quote"><tr><td class="md-quote-cell">',
        )
        html = html.replace("</blockquote>", "</td></tr></table>")
        return html

    @staticmethod
    def _strip_trailing_br(html: str) -> str:
        """删除段落末尾的悬空 <br />。

        引用块末尾的空引用行经 nl2br 会转成段落末尾的 <br />，Qt 渲染为
        末尾空行盒（带背景的空灰条）。正常段落末尾本无 <br />，删除无副作用。
        """
        return re.sub(r'<br />\s*</p>', '</p>', html)

    def on_file_changed(self, path):
        """文件变化回调，使用延迟刷新"""
        if not os.path.isfile(path):
            # 使用带 parent 的 QTimer，窗口销毁时自动取消，防止访问已释放对象
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(500)
            timer.timeout.connect(lambda: self.re_watch(path))
            timer.start()
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

    @staticmethod
    def _proportional_value(src, dst):
        """按比例把 src 滚动条当前位置映射为 dst 滚动条的目标值"""
        ratio = src.value() / max(src.maximum(), 1)
        return round(ratio * dst.maximum())

    @staticmethod
    def _nearest_anchor_index(arr, target):
        """在非降序数组 arr 中返回最后一个 <= target 的索引；target 小于首元素返回 0。"""
        idx = bisect.bisect_right(arr, target) - 1
        return idx if idx >= 0 else 0

    @staticmethod
    def _build_anchor_map(doc):
        """遍历 QTextDocument 找出所有 <a id="popup-anchor-N"> 锚点，返回 (行号列表, Y 列表)。

        锚点属性附着到紧随其后的字符，通过 fragment 的 anchorNames 检测；
        block 的文档 Y 用 documentLayout().blockBoundingRect(block).y() 取得。
        """
        lines, ys = [], []
        blk = doc.begin()
        while blk.isValid():
            found = None
            it = blk.begin()
            while not it.atEnd():
                for name in it.fragment().charFormat().anchorNames():
                    if name.startswith("popup-anchor-"):
                        suffix = name[len("popup-anchor-"):]
                        if suffix.isdigit():
                            found = int(suffix)
                        break
                if found is not None:
                    break
                it += 1
            if found is not None:
                lines.append(found)
                ys.append(doc.documentLayout().blockBoundingRect(blk).y())
            blk = blk.next()
        return lines, ys

    @staticmethod
    def _detect_newline(content):
        """检测文本使用的换行风格：含 \r\n 则视为 CRLF，否则 LF"""
        return "\r\n" if "\r\n" in content else "\n"

    @staticmethod
    def _apply_newline(text, newline):
        """按目标换行风格还原换行符（text 来自 toPlainText，统一为 \n）"""
        if newline == "\r\n":
            return text.replace("\n", "\r\n")
        return text

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
    white-space: pre-wrap;
}}
table.md-quote {{
    border: none;
    width: 100%;
    margin: 8px 0;
}}
td.md-quote-cell {{
    border: none;
    border-left: 4px solid #ddd;
    padding: 8px 16px;
    color: #666;
}}
td.md-quote-cell p {{
    background-color: #e8e8e8;
    margin: 0;
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
    app.setOrganizationName("Popup")
    app.setApplicationName("Popup")
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
