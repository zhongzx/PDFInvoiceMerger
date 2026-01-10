import sys
import os
import re
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QTreeWidget, QTreeWidgetItem, QLabel, QFileDialog, 
                             QSplitter, QMessageBox, QScrollArea, QAbstractItemView, QFrame,
                             QTreeWidgetItemIterator, QMenu)
from PyQt6.QtCore import Qt, QMimeData, QSize, pyqtSignal, QTemporaryDir, QTimer, QEvent
from PyQt6.QtGui import QDrag, QPixmap, QImage, QIcon, QAction, QPainter, QBrush, QColor
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
import traceback

from config import TRANS
from core import PDFProcessor, ArchiveExtractor

class DraggableTreeWidget(QTreeWidget):
    """
    A QTreeWidget that supports external file drops.
    """
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(False) # Disable internal drag as we use global sorting
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHeaderHidden(True)
        self.setIndentation(0)
        # 增加字体大小和行间距
        self.setStyleSheet("""
            QTreeWidget {
                font-size: 14px;
            }
            QTreeWidget::item {
                padding: 5px;
            }
        """)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            items = self.selectedItems()
            for item in items:
                # Toggle Check State
                if item.data(0, Qt.ItemDataRole.UserRole).get("type") == "page":
                    current_state = item.checkState(0)
                    new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                    item.setCheckState(0, new_state)
        elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            # Emit a signal or call parent to remove items
            if hasattr(self.parent(), 'remove_selected_items'):
                self.parent().remove_selected_items(self)
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
            urls = event.mimeData().urls()
            file_paths = []
            for url in urls:
                file_path = url.toLocalFile()
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.pdf', '.zip', '.rar', '.7z']:
                    file_paths.append(file_path)
            
            if file_paths:
                self.files_dropped.emit(file_paths)
        else:
            super().dropEvent(event)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = 'zh' # Default to Chinese
        self.merged_pdf_path = None
        self.temp_merged_doc = None # fitz.Document
        self.temp_dir = QTemporaryDir() # Temp dir for extracted files
        
        # Preview State
        self.current_preview_type = None
        self.current_preview_data = None
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.refresh_preview)
        
        self.has_conflicts = False

        self.init_ui()
        self.update_texts()
        
        # Set App Icon
        icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def init_ui(self):
        self.resize(1400, 900) 
        self.setAcceptDrops(True) # 全窗口接收拖拽
        
        # 现代深色主题样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                font-size: 14px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            }
            QPushButton {
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 500;
                border: none;
                transition: all 0.2s ease;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.05);
            }
            QTreeWidget {
                font-size: 14px;
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 5px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px 0;
            }
            QTreeWidget::item:selected {
                background-color: #0a84ff;
                color: white;
            }
            QTreeWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QScrollArea {
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                background-color: #252525;
            }
            QLabel {
                color: #e0e0e0;
            }
            QStatusBar {
                background-color: #1a1a1a;
                color: #888;
                border-top: 1px solid #333;
            }
            QSplitter::handle {
                background-color: #3a3a3a;
                width: 2px;
            }
            QSplitter::handle:hover {
                background-color: #0a84ff;
            }
        """) 
        
        central_widget = QWidget()
        central_widget.setStyleSheet("background-color: #1e1e1e;")
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Splitter for resizable panels
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- Left Panel: Valid Items ---
        left_panel = QWidget()
        left_panel.setStyleSheet("""
            QWidget {
                background-color: #252525;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 左侧标题
        left_title = QLabel("待处理文件")
        left_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: 600;
                color: #0a84ff;
                padding: 10px 15px;
                background-color: rgba(10, 132, 255, 0.1);
                border-radius: 6px;
                margin-bottom: 10px;
            }
        """)
        left_layout.addWidget(left_title)
        
        self.file_list = DraggableTreeWidget(self)
        self.file_list.setHeaderHidden(True)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self.show_valid_context_menu)
        self.file_list.itemSelectionChanged.connect(self.on_item_selected)
        self.file_list.files_dropped.connect(self.add_dropped_files)
        left_layout.addWidget(self.file_list)

        # Statistics Label
        self.lbl_stats = QLabel()
        self.lbl_stats.setStyleSheet("""
            QLabel {
                font-weight: 500;
                color: #aaa;
                padding: 8px;
                background-color: rgba(255, 255, 255, 0.05);
                border-radius: 4px;
                margin-top: 10px;
            }
        """)
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.lbl_stats)

        # --- Middle Panel: Preview & Global Actions ---
        middle_panel = QWidget()
        middle_panel.setStyleSheet("""
            QWidget {
                background-color: #252525;
                border-radius: 10px;
                padding: 15px;
            }
        """)
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(0, 0, 0, 0)

        # Action Buttons (Top Bar)
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)
        
        # 主操作按钮样式
        button_style = """
            QPushButton {
                padding: 12px 24px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 14px;
                border: none;
                color: white;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
                transform: translateY(-1px);
            }
            QPushButton:pressed {
                transform: translateY(0);
            }
            QPushButton:disabled {
                background-color: #555;
                color: #888;
            }
        """
        
        self.btn_merge = QPushButton()
        self.btn_merge.clicked.connect(self.merge_files)
        self.btn_merge.setStyleSheet(button_style + """
            QPushButton {
                background-color: #0a84ff;
            }
            QPushButton:hover {
                background-color: #0071e3;
            }
        """)
        
        self.btn_save = QPushButton()
        self.btn_save.clicked.connect(self.save_file)
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet(button_style + """
            QPushButton {
                background-color: #32d74b;
            }
            QPushButton:hover {
                background-color: #28a745;
            }
        """)

        self.btn_print = QPushButton()
        self.btn_print.clicked.connect(self.print_merged_file)
        self.btn_print.setEnabled(False)
        self.btn_print.setStyleSheet(button_style + """
            QPushButton {
                background-color: #ff9f0a;
            }
            QPushButton:hover {
                background-color: #ff9500;
            }
        """)
        
        # 辅助按钮样式
        aux_button_style = """
            QPushButton {
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                background-color: rgba(255, 255, 255, 0.1);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
        """
        
        self.btn_lang = QPushButton()
        self.btn_lang.clicked.connect(self.toggle_language)
        self.btn_lang.setStyleSheet(aux_button_style)
        
        self.btn_about = QPushButton()
        self.btn_about.clicked.connect(self.show_about)
        self.btn_about.setStyleSheet(aux_button_style)

        top_bar.addWidget(self.btn_merge)
        top_bar.addWidget(self.btn_save)
        top_bar.addWidget(self.btn_print)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_lang)
        top_bar.addWidget(self.btn_about)
        middle_layout.addLayout(top_bar)

        # Preview Area
        self.lbl_preview_title = QLabel()
        self.lbl_preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: 600;
                color: #0a84ff;
                padding: 15px;
                background-color: rgba(10, 132, 255, 0.1);
                border-radius: 8px;
                margin: 10px 0;
            }
        """)
        middle_layout.addWidget(self.lbl_preview_title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scroll_area.setWidget(self.preview_container)
        middle_layout.addWidget(self.scroll_area)

        # --- Right Panel: Unrecognized Items ---
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_unrecognized = QLabel("Unrecognized Pages")
        self.lbl_unrecognized.setStyleSheet("font-weight: bold; color: #f44336;")
        right_layout.addWidget(self.lbl_unrecognized)
        
        self.unrecognized_list = QTreeWidget()
        self.unrecognized_list.setHeaderHidden(True)
        self.unrecognized_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.unrecognized_list.customContextMenuRequested.connect(self.show_invalid_context_menu)
        self.unrecognized_list.itemSelectionChanged.connect(self.on_item_selected)
        right_layout.addWidget(self.unrecognized_list)
        
        # Initial State: Hide Right Panel
        self.right_panel.setVisible(False)

        # Add panels to splitter
        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(middle_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setStretchFactor(1, 2) # Middle panel takes more space

        # Status Bar
        self.status_bar = self.statusBar()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        file_paths = []
        for url in urls:
            path = url.toLocalFile()
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.pdf', '.zip', '.rar', '.7z']:
                file_paths.append(path)
        if file_paths:
            self.add_dropped_files(file_paths)

    def show_valid_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        
        pop_menu = QMenu(self)
        if item:
            remove_action = QAction("删除所选" if self.current_lang == 'zh' else "Remove Selected", self)
            remove_action.triggered.connect(self.remove_selected_files)
            pop_menu.addAction(remove_action)
            pop_menu.addSeparator()
        
        clear_action = QAction("清空列表" if self.current_lang == 'zh' else "Clear All", self)
        clear_action.triggered.connect(self.clear_all_valid)
        pop_menu.addAction(clear_action)
        
        pop_menu.exec(self.file_list.viewport().mapToGlobal(pos))

    def show_invalid_context_menu(self, pos):
        item = self.unrecognized_list.itemAt(pos)
        
        pop_menu = QMenu(self)
        if item:
            remove_action = QAction("删除所选" if self.current_lang == 'zh' else "Remove Selected", self)
            remove_action.triggered.connect(lambda: self.remove_selected_items(self.unrecognized_list))
            pop_menu.addAction(remove_action)
            pop_menu.addSeparator()
            
        clear_action = QAction("清空列表" if self.current_lang == 'zh' else "Clear All", self)
        clear_action.triggered.connect(self.clear_unrecognized)
        pop_menu.addAction(clear_action)
        
        pop_menu.exec(self.unrecognized_list.viewport().mapToGlobal(pos))

    def clear_all_valid(self):
        self.file_list.clear()
        self.current_preview_type = None
        self.current_preview_data = None
        self.clear_preview()
        self.merged_pdf_path = None
        if self.temp_merged_doc:
            self.temp_merged_doc.close()
            self.temp_merged_doc = None
        self.btn_print.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.update_statistics()

    def remove_unrecognized_item(self, item):
        self.remove_selected_items(self.unrecognized_list)

    def clear_unrecognized(self):
        self.unrecognized_list.clear()
        self.right_panel.setVisible(False)

    def update_texts(self):
        t = TRANS[self.current_lang]
        self.setWindowTitle(t['window_title'])
        
        # Setup all buttons with platform-specific styles and shortcuts
        self.setup_button(self.btn_merge, 'merge')
        self.setup_button(self.btn_save, 'save_pdf')
        self.setup_button(self.btn_print, 'print')
        self.setup_button(self.btn_lang, 'lang_switch')
        self.setup_button(self.btn_about, 'about_btn')
        
        self.lbl_preview_title.setText(t['preview_label'])
        self.lbl_unrecognized.setText("识别失败页面" if self.current_lang == 'zh' else "Unrecognized Pages")
        self.status_bar.showMessage(t['status_ready'])
        self.update_statistics()

    def setup_button(self, btn, key):
        """
        Sets button text and shortcuts based on the operating system.
        - Windows: Keeps (&A) for Alt+A mnemonics.
        - macOS: Removes (&A) and sets Cmd+A shortcut.
        - Linux: Converts (&A) to (_A) and sets Alt+A shortcut.
        """
        t = TRANS[self.current_lang]
        raw_text = t.get(key, "")
        
        # Extract the mnemonic letter (e.g., 'A' from 'Add (&A)')
        match = re.search(r'\(&([A-Z])\)', raw_text)
        letter = match.group(1) if match else ""
        
        if sys.platform == "darwin":
            # macOS Style: No mnemonics in text, use Command key
            clean_text = re.sub(r'\s*\(&[A-Z]\)', '', raw_text)
            btn.setText(clean_text)
            if letter:
                btn.setShortcut(f"Cmd+{letter}")
        elif sys.platform == "win32":
            # Windows Style: Use & for Alt mnemonics (Qt handles this automatically)
            btn.setText(raw_text)
            # Clear any manual shortcut to let the mnemonic work
            btn.setShortcut("") 
        else:
            # Linux Style: Show as (_P) but use Alt+P
            # Note: Qt uses & for mnemonics on Linux too, but we format the text as requested
            linux_text = raw_text.replace('(&', '(_').replace(')', '')
            btn.setText(linux_text)
            if letter:
                # On Linux, we might need to explicitly set the Alt shortcut if using (_) format
                btn.setShortcut(f"Alt+{letter}")

    def update_statistics(self):
        total_pages = 0
        selected_pages = 0
        
        iterator = QTreeWidgetItemIterator(self.file_list)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "page":
                total_pages += 1
                if item.checkState(0) == Qt.CheckState.Checked:
                    selected_pages += 1
            iterator += 1
            
        t = TRANS[self.current_lang]
        self.lbl_stats.setText(t['stats_label'].format(total_pages, selected_pages))

    def show_about(self):
        t = TRANS[self.current_lang]
        QMessageBox.about(self, t['about_title'], t['about_content'])

    def toggle_language(self):
        self.current_lang = 'en' if self.current_lang == 'zh' else 'zh'
        self.update_texts()
        self.update_list_items_text()

    def update_list_items_text(self):
        # Update both valid and invalid lists
        for tree in [self.file_list, self.unrecognized_list]:
            iterator = QTreeWidgetItemIterator(tree)
            while iterator.value():
                item = iterator.value()
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("type") == "page":
                    info = data.get("info", {})
                    if info.get("type") == "invoice":
                        prefix = "发票" if self.current_lang == 'zh' else "Invoice"
                        item.setText(0, f"{prefix} {info.get('date')} {info.get('number')}")
                    elif info.get("type") == "trip":
                        prefix = "行程" if self.current_lang == 'zh' else "Trip"
                        item.setText(0, f"{prefix} {info.get('date')} {info.get('number')}")
                    else:
                        # For "other", display_text is already extracted characters
                        item.setText(0, info.get("display_text", ""))
                iterator += 1

    def add_file_item(self, path):
        t = TRANS[self.current_lang]
        doc = None
        try:
            doc = fitz.open(path)
            for i in range(doc.page_count):
                page = doc[i]
                info = PDFProcessor.identify_page(page)
                
                # Store common data
                item_data = {
                    "type": "page", 
                    "path": path, 
                    "page_num": i,
                    "info": info
                }

                if info["type"] == "other":
                    # Add to right list
                    item = QTreeWidgetItem(self.unrecognized_list)
                    item.setText(0, info["display_text"])
                    item.setData(0, Qt.ItemDataRole.UserRole, item_data)
                    self.right_panel.setVisible(True)
                else:
                    # Add to left list
                    item = QTreeWidgetItem(self.file_list)
                    # Use localized prefix
                    prefix = "发票" if self.current_lang == 'zh' else "Invoice"
                    if info["type"] == "trip":
                        prefix = "行程" if self.current_lang == 'zh' else "Trip"
                    
                    item.setText(0, f"{prefix} {info['date']} {info['number']}")
                    item.setCheckState(0, Qt.CheckState.Checked)
                    item.setData(0, Qt.ItemDataRole.UserRole, item_data)
                    
            # Auto sort left list
            self.sort_valid_list()
            
        except Exception as e:
            print(f"Error adding file {path}: {e}")
        finally:
            if doc: doc.close()

    def sort_valid_list(self):
        """
        根据日期和号码对左侧列表进行全局排序。
        """
        items = []
        root = self.file_list.invisibleRootItem()
        for i in range(root.childCount()):
            items.append(root.takeChild(0))
            
        # 排序逻辑: 日期 (升序) -> 号码 (升序)
        items.sort(key=lambda x: (
            x.data(0, Qt.ItemDataRole.UserRole)["info"].get("date", "9999-12-31"),
            x.data(0, Qt.ItemDataRole.UserRole)["info"].get("number", "")
        ))
        
        for item in items:
            root.addChild(item)

    def on_item_changed(self, item, column):
        self.check_duplicates()
        self.update_statistics()
        
        # If conflicts arise after merge, disable save/print to force re-check
        if self.has_conflicts:
            self.btn_save.setEnabled(False)
            self.btn_print.setEnabled(False)

    def check_duplicates(self):
        """
        Check for duplicate invoice numbers.
        Logic:
        - Total Count > 1 AND Checked Count > 1: All Checked items RED (Duplicate Conflict).
        - Total Count > 1 AND Checked Count == 1: The single Checked item BLUE (Conflict Resolved).
        - Total Count == 1: Default (Unique).
        - Unchecked items: Always Default.
        """
        # Block signals to prevent infinite recursion
        was_blocked = self.file_list.signalsBlocked()
        if not was_blocked:
            self.file_list.blockSignals(True)
            
        self.has_conflicts = False

        try:
            # 1. Collect ALL invoice numbers (Checked and Unchecked)
            inv_map = {} # number -> list of all items
            
            iterator = QTreeWidgetItemIterator(self.file_list)
            while iterator.value():
                item = iterator.value()
                data = item.data(0, Qt.ItemDataRole.UserRole)
                
                # Reset style for everyone initially
                item.setData(0, Qt.ItemDataRole.ForegroundRole, None)
                item.setToolTip(0, "")

                if data and data.get("type") == "page":
                    info = data.get("info", {})
                    inv_num = info.get("number")
                    if inv_num:
                        if inv_num not in inv_map:
                            inv_map[inv_num] = []
                        inv_map[inv_num].append(item)
                iterator += 1
                
            # 2. Analyze and Highlight
            red_brush = QBrush(Qt.GlobalColor.red)
            # Use a softer blue (SteelBlue: #4682B4)
            blue_brush = QBrush(QColor("#4682B4"))
            
            for num, all_items in inv_map.items():
                checked_items = [item for item in all_items if item.checkState(0) == Qt.CheckState.Checked]
                total_count = len(all_items)
                checked_count = len(checked_items)
                
                if checked_count > 1:
                    # Conflict exists: Mark all checked as RED
                    self.has_conflicts = True
                    for item in checked_items:
                        item.setForeground(0, red_brush)
                        item.setToolTip(0, f"Duplicate Invoice No: {num}")
                elif checked_count == 1:
                    # Single checked item
                    item = checked_items[0]
                    if total_count > 1:
                        # Was a duplicate, now resolved -> BLUE
                        item.setForeground(0, blue_brush)
                        item.setToolTip(0, f"Resolved Invoice No: {num}")
                    else:
                        # Truly unique -> Default (already reset)
                        pass 
                # Unchecked items remain Default
                
        finally:
            if not was_blocked:
                self.file_list.blockSignals(False)

    def add_dropped_files(self, paths):
        self.file_list.blockSignals(True)
        try:
            for path in paths:
                ext = os.path.splitext(path)[1].lower()
                if ext == '.pdf':
                    self.add_file_item(path)
                elif ext in ['.zip', '.rar', '.7z']:
                    self.process_archive(path)
        finally:
            self.file_list.blockSignals(False)
            self.check_duplicates()
            self.update_statistics()

    def process_archive(self, archive_path):
        t = TRANS[self.current_lang]
        self.status_bar.showMessage(t['extracting'].format(os.path.basename(archive_path)))
        QApplication.processEvents()

        try:
            # Use Core Logic
            found_pdfs = ArchiveExtractor.extract_and_find_pdfs(archive_path, self.temp_dir.path())
            
            # Block signals to prevent duplicate check on every item add
            is_blocked = self.file_list.signalsBlocked()
            if not is_blocked:
                self.file_list.blockSignals(True)
            
            try:
                for pdf_path in found_pdfs:
                    self.add_file_item(pdf_path)
            finally:
                if not is_blocked:
                    self.file_list.blockSignals(False)
                
            self.status_bar.showMessage(t['status_ready'])
            # Only check if we are not in a recursive call (e.g. from add_dropped_files)
            # Actually process_archive might be called from add_dropped_files which already blocks.
            # So we should respect the outer block.
            # If signals were not blocked before, we unblock and check.
            if not is_blocked:
                self.check_duplicates()
                self.update_statistics()
            
        except Exception as e:
            print(f"Archive error: {e}")
            QMessageBox.warning(self, t.get('archive_error_title', "Archive Error"), f"{str(e)}")

    def remove_selected_items(self, tree_widget):
        items = tree_widget.selectedItems()
        if not items:
            return
            
        root = tree_widget.invisibleRootItem()
        for item in items:
            (item.parent() or root).removeChild(item)
            
        if tree_widget == self.unrecognized_list:
            if self.unrecognized_list.topLevelItemCount() == 0:
                self.right_panel.setVisible(False)
        else:
            self.check_duplicates()
            self.update_statistics()
            self.clear_preview()

    def remove_selected_files(self):
        self.remove_selected_items(self.file_list)

    def eventFilter(self, source, event):
        if source == self.scroll_area and event.type() == QEvent.Type.Resize:
            self.preview_timer.start(200) # Debounce 200ms
        return super().eventFilter(source, event)

    def refresh_preview(self):
        if not self.current_preview_type:
            return
            
        # Re-call show methods but with logic to prevent infinite recursion if any
        # The show methods clear preview and rebuild it.
        try:
            if self.current_preview_type == 'file':
                self.show_file_preview(self.current_preview_data)
            elif self.current_preview_type == 'page':
                path, pnum = self.current_preview_data
                self.show_page_preview(path, pnum)
            elif self.current_preview_type == 'doc':
                doc = self.current_preview_data
                # Check if doc is valid/open
                try:
                    if doc.page_count > 0:
                        self.show_doc_preview(doc)
                except:
                    self.current_preview_type = None
        except Exception as e:
            print(f"Refresh preview error: {e}")

    def on_item_selected(self):
        items = self.file_list.selectedItems()
        if not items:
            return
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        
        if not data:
            return
            
        if data['type'] == 'file':
            self.show_file_preview(data['path'])
        elif data['type'] == 'page':
            self.show_page_preview(data['path'], data['page_num'])

    def clear_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def show_file_preview(self, path):
        self.current_preview_type = 'file'
        self.current_preview_data = path
        
        self.clear_preview()
        t = TRANS[self.current_lang]
        self.lbl_preview_title.setText(f"{t['preview_label']} - {os.path.basename(path)}")
        
        try:
            doc = fitz.open(path)
            # Display all pages
            for i in range(len(doc)):
                self.display_page(doc[i])
            doc.close()
        except Exception as e:
            print(f"Preview error: {e}")

    def show_page_preview(self, path, page_num):
        self.current_preview_type = 'page'
        self.current_preview_data = (path, page_num)
        
        self.clear_preview()
        t = TRANS[self.current_lang]
        self.lbl_preview_title.setText(f"{t['preview_label']} - {os.path.basename(path)} (Page {page_num+1})")
        
        try:
            doc = fitz.open(path)
            if 0 <= page_num < len(doc):
                self.display_page(doc[page_num])
            doc.close()
        except Exception as e:
            print(f"Page preview error: {e}")

    def show_doc_preview(self, doc):
        self.current_preview_type = 'doc'
        self.current_preview_data = doc
        
        self.clear_preview()
        t = TRANS[self.current_lang]
        self.lbl_preview_title.setText(t['preview_label'])
        
        for i in range(len(doc)):
            self.display_page(doc[i])

    def display_page(self, page):
        # Calculate scale to fit width
        # viewport width - scrollbar width (approx 20) - margins (20)
        available_width = self.scroll_area.viewport().width() - 30 
        if available_width < 100: available_width = 100
        
        scale = available_width / page.rect.width
        
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        
        fmt = QImage.Format.Format_RGB888
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        qpix = QPixmap.fromImage(img)
        
        lbl = QLabel()
        lbl.setPixmap(qpix)
        lbl.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.preview_layout.addWidget(lbl)

    def merge_files(self):
        t = TRANS[self.current_lang]
        
        # 收集所有选中的有效页面
        pages_to_merge = []
        iterator = QTreeWidgetItemIterator(self.file_list)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.CheckState.Checked:
                data = item.data(0, Qt.ItemDataRole.UserRole)
                pages_to_merge.append((data["path"], data["page_num"], data["info"]))
            iterator += 1
            
        if not pages_to_merge:
            QMessageBox.warning(self, t['confirm_title'], t['error_no_files'])
            return

        try:
            self.status_bar.showMessage(t['status_processing'])
            
            # 生成合并后的 PDF 文档对象
            self.temp_merged_doc = PDFProcessor.merge_half_page_pdfs(pages_to_merge)
            
            # 更新预览
            self.refresh_preview()
            
            self.btn_save.setEnabled(True)
            self.btn_print.setEnabled(True)
            self.status_bar.showMessage(t['status_ready'])
            
        except Exception as e:
            QMessageBox.critical(self, t['confirm_title'], t['status_error'].format(str(e)))
            traceback.print_exc()

    def save_file(self):
        if not self.temp_merged_doc:
            return
            
        t = TRANS[self.current_lang]
        out_path, _ = QFileDialog.getSaveFileName(self, t['save_prompt'], "merged_invoices.pdf", t['file_filter'])
        if not out_path:
            return
            
        try:
            self.temp_merged_doc.save(out_path)
            self.merged_pdf_path = out_path
            self.status_bar.showMessage(t['status_merged'].format(out_path))
            QMessageBox.information(self, t['confirm_title'], t['status_merged'].format(out_path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {str(e)}")

    def print_merged_file(self):
        if not self.temp_merged_doc:
            return

        # Instead of QPrintPreviewDialog, we open the file with the system default viewer
        # This provides the best "native" preview and print experience
        import tempfile
        import subprocess
        try:
            # Create a temp file
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            
            self.temp_merged_doc.save(temp_path)
            
            # Cross-platform open
            if sys.platform == 'win32':
                os.startfile(temp_path)
            elif sys.platform == 'darwin':
                subprocess.call(['open', temp_path])
            else:
                subprocess.call(['xdg-open', temp_path])
            
        except Exception as e:
             QMessageBox.critical(self, "Error", f"Failed to open system preview: {str(e)}")

    # def handle_print_request(self, printer): ... (Removed as no longer needed)

def main():
    def excepthook(exc_type, exc_value, exc_tb):
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("Error:", tb)
        app = QApplication.instance()
        if app:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("Application Error")
            msg.setInformativeText(str(exc_value))
            msg.setDetailedText(tb)
            msg.exec()

    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()