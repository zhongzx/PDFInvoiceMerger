import sys
import os
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QTreeWidget, QTreeWidgetItem, QLabel, QFileDialog, 
                             QSplitter, QMessageBox, QScrollArea, QAbstractItemView, QFrame,
                             QTreeWidgetItemIterator)
from PyQt6.QtCore import Qt, QMimeData, QSize, pyqtSignal, QTemporaryDir, QTimer, QEvent
from PyQt6.QtGui import QDrag, QPixmap, QImage, QIcon, QAction, QPainter, QBrush, QColor
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
import traceback

from config import TRANS
from core import PDFProcessor, ArchiveExtractor

class DraggableTreeWidget(QTreeWidget):
    """
    A QTreeWidget that supports internal reordering (top-level only) and external file drops.
    """
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHeaderHidden(True)
        self.setIndentation(20)
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
            item = self.currentItem()
            if item:
                # Toggle Check State
                # Only for page items
                if item.data(0, Qt.ItemDataRole.UserRole).get("type") == "page":
                    current_state = item.checkState(0)
                    new_state = Qt.CheckState.Unchecked if current_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                    item.setCheckState(0, new_state)
        elif event.key() == Qt.Key.Key_Down:
            # Handle cyclic navigation (Bottom -> Top)
            # And skip 'file' items
            current = self.currentItem()
            next_item = None
            
            if current:
                next_item = self.itemBelow(current)
                # Skip file items
                while next_item and (next_item.childCount() > 0 or next_item.data(0, Qt.ItemDataRole.UserRole).get("type") == "file"):
                    next_item = self.itemBelow(next_item)
            
            if not next_item:
                # Loop to top
                next_item = self.topLevelItem(0)
                # If top is file, find first valid child
                while next_item and (next_item.childCount() > 0 or next_item.data(0, Qt.ItemDataRole.UserRole).get("type") == "file"):
                    next_item = self.itemBelow(next_item)
            
            if next_item:
                self.setCurrentItem(next_item)

        elif event.key() == Qt.Key.Key_Up:
            # Handle cyclic navigation (Top -> Bottom)
            # And skip 'file' items
            current = self.currentItem()
            prev_item = None
            
            if current:
                prev_item = self.itemAbove(current)
                # Skip file items
                while prev_item and (prev_item.childCount() > 0 or prev_item.data(0, Qt.ItemDataRole.UserRole).get("type") == "file"):
                    prev_item = self.itemAbove(prev_item)
            
            if not prev_item:
                # Loop to bottom
                count = self.topLevelItemCount()
                if count > 0:
                    last = self.topLevelItem(count - 1)
                    while last.isExpanded() and last.childCount() > 0:
                        last = last.child(last.childCount() - 1)
                    prev_item = last
                    
                    # Check if last is file (e.g. empty file), though rare
                    while prev_item and (prev_item.childCount() > 0 or prev_item.data(0, Qt.ItemDataRole.UserRole).get("type") == "file"):
                        prev_item = self.itemAbove(prev_item)
            
            if prev_item:
                self.setCurrentItem(prev_item)
        else:
            super().keyPressEvent(event)

    def startDrag(self, supportedActions):
        # 强制选择父节点（文件）如果当前选中的是子节点（页面）
        # Force dragging the file (top-level), not the page
        item = self.currentItem()
        if item and item.parent():
            # It's a child (page), select the parent (file) instead
            self.setCurrentItem(item.parent())
        
        super().startDrag(supportedActions)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            # Internal move
            # Allow default visual feedback (insertion line)
            super().dragMoveEvent(event)
            # Accept the event to allow dropping
            event.accept()

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
            # Handle internal move - Strictly enforce flat structure
            event.accept()
            
            source_item = self.currentItem()
            if not source_item:
                return
            
            # Ensure source is top-level (safety check)
            if source_item.parent():
                source_item = source_item.parent()
                
            # Find drop target
            pos = event.position().toPoint()
            target_item = self.itemAt(pos)
            
            root = self.invisibleRootItem()
            source_index = root.indexOfChild(source_item)
            
            # Determine insertion index
            target_index = -1
            
            if target_item:
                # If target is a page, look at its file
                if target_item.parent():
                    target_item = target_item.parent()
                
                target_index = root.indexOfChild(target_item)
                
                # Get drop indicator position
                indicator = self.dropIndicatorPosition()
                
                if indicator == QAbstractItemView.DropIndicatorPosition.BelowItem:
                    target_index += 1
                elif indicator == QAbstractItemView.DropIndicatorPosition.OnItem:
                    # Treat "On Item" as "Insert After" (Below)
                    target_index += 1
                elif indicator == QAbstractItemView.DropIndicatorPosition.OnViewport:
                    target_index = root.childCount()
                # AboveItem: target_index stays same (insert before)
            else:
                # Dropped on empty space -> Append to end
                target_index = root.childCount()
            
            # Execute Move
            if source_index != target_index:
                # Adjust index if moving downwards
                if source_index < target_index:
                    target_index -= 1
                
                # Use takeChild/insertChild to move
                item_to_move = root.takeChild(source_index)
                root.insertChild(target_index, item_to_move)
                
                # Restore selection
                self.setCurrentItem(item_to_move)
                item_to_move.setExpanded(True)

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
        self.resize(1200, 800) # Slightly larger for better preview
        # Global style
        self.setStyleSheet("""
            QWidget {
                font-size: 14px;
            }
            QPushButton {
                padding: 8px 15px;
            }
        """) 
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20) # Increase global spacing

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- Left Panel: File List & Controls ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Tree Widget (Replaces ListWidget)
        self.file_list = DraggableTreeWidget(self)
        self.file_list.itemSelectionChanged.connect(self.on_item_selected)
        self.file_list.files_dropped.connect(self.add_dropped_files)
        self.file_list.itemChanged.connect(self.on_item_changed)
        left_layout.addWidget(self.file_list)

        # Statistics Label
        self.lbl_stats = QLabel()
        self.lbl_stats.setStyleSheet("font-weight: bold; color: #333; margin: 5px 0;")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.lbl_stats)

        # Buttons
        btn_layout = QVBoxLayout()
        
        row1 = QHBoxLayout()
        self.btn_add = QPushButton()
        self.btn_add.clicked.connect(self.browse_files)
        self.btn_remove = QPushButton()
        self.btn_remove.clicked.connect(self.remove_selected_files)
        row1.addWidget(self.btn_add)
        row1.addWidget(self.btn_remove)
        
        row2 = QHBoxLayout()
        self.btn_up = QPushButton()
        self.btn_up.clicked.connect(self.move_item_up)
        self.btn_down = QPushButton()
        self.btn_down.clicked.connect(self.move_item_down)
        row2.addWidget(self.btn_up)
        row2.addWidget(self.btn_down)

        self.btn_clear = QPushButton()
        self.btn_clear.clicked.connect(self.clear_files)

        btn_layout.addLayout(row1)
        btn_layout.addLayout(row2)
        btn_layout.addWidget(self.btn_clear)
        
        left_layout.addLayout(btn_layout)

        # --- Right Panel: Preview & Actions ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Action Buttons
        action_layout = QHBoxLayout()
        self.btn_about = QPushButton()
        self.btn_about.clicked.connect(self.show_about)
        
        self.btn_lang = QPushButton()
        self.btn_lang.clicked.connect(self.toggle_language)
        
        self.btn_merge = QPushButton()
        self.btn_merge.clicked.connect(self.merge_files)
        self.btn_merge.setStyleSheet("font-weight: bold; font-size: 15px; padding: 10px;")
        
        self.btn_save = QPushButton()
        self.btn_save.clicked.connect(self.save_file)
        self.btn_save.setEnabled(False)

        self.btn_print = QPushButton()
        self.btn_print.clicked.connect(self.print_merged_file)
        self.btn_print.setEnabled(False)

        action_layout.addWidget(self.btn_about)
        action_layout.addWidget(self.btn_lang)
        action_layout.addWidget(self.btn_merge)
        action_layout.addWidget(self.btn_save)
        action_layout.addWidget(self.btn_print)
        
        right_layout.addLayout(action_layout)

        # Preview Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_area.setWidget(self.preview_container)
        self.scroll_area.installEventFilter(self)
        
        self.lbl_preview_title = QLabel()
        self.lbl_preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_title.setStyleSheet("font-weight: bold; margin: 5px;")
        
        right_layout.addWidget(self.lbl_preview_title)
        right_layout.addWidget(self.scroll_area)

        # Add panels to splitter
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 850])

        # Status Bar
        self.status_bar = self.statusBar()

    def update_texts(self):
        t = TRANS[self.current_lang]
        self.setWindowTitle(t['window_title'])
        self.btn_add.setText(t['add_files'])
        self.btn_remove.setText(t['remove'])
        self.btn_clear.setText(t['clear'])
        self.btn_up.setText(t['move_up'])
        self.btn_down.setText(t['move_down'])
        self.btn_merge.setText(t['merge'])
        self.btn_save.setText(t['save_pdf'])
        self.btn_print.setText(t['print'])
        self.btn_lang.setText(t['lang_switch'])
        self.btn_about.setText(t['about_btn'])
        self.lbl_preview_title.setText(t['preview_label'])
        self.status_bar.showMessage(t['status_ready'])
        self.update_statistics()

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
        t = TRANS[self.current_lang]
        iterator = QTreeWidgetItemIterator(self.file_list)
        while iterator.value():
            item = iterator.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "page":
                # Reconstruct page text
                page_num = data.get("page_num", 0)
                inv_num = data.get("invoice_num", "")
                inv_date = data.get("invoice_date", "")
                is_invoice = data.get("is_invoice", False)
                
                # Concise display: Page X   Date   Number
                # No labels like "Date:", "No:"
                page_text = f"{t.get('page_prefix', 'Page')} {page_num+1}{t.get('page_suffix', '')}"
                
                if is_invoice:
                    parts = []
                    if inv_date:
                        parts.append(inv_date)
                    if inv_num:
                        parts.append(inv_num)
                    
                    if parts:
                        page_text += "   " + "   ".join(parts)
                
                item.setText(0, page_text)
            iterator += 1

    def add_file_item(self, path):
        t = TRANS[self.current_lang]
        doc = None
        pages = 0
        try:
            # Minimalist: Just filename
            item_text = os.path.basename(path)
            
            doc = fitz.open(path)
            pages = doc.page_count
        except Exception:
            item_text = os.path.basename(path)
            pages = 0
            if doc:
                doc.close()
                doc = None

        # Parent Item (File)
        file_item = QTreeWidgetItem(self.file_list)
        file_item.setText(0, item_text)
        file_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": path})
        file_item.setToolTip(0, path)
        
        # Child Items (Pages)
        if pages > 0 and doc:
            try:
                for i in range(pages):
                    page = doc[i]
                    # 尝试提取发票信息
                    inv_info = PDFProcessor.extract_invoice_info(page)
                    
                    # Concise display
                    page_text = f"{t.get('page_prefix', 'Page')} {i+1}{t.get('page_suffix', '')}"
                    if inv_info["is_invoice"]:
                        parts = []
                        if inv_info["date"]:
                            parts.append(inv_info["date"])
                        if inv_info["number"]:
                            parts.append(inv_info["number"])
                        
                        if parts:
                            page_text += "   " + "   ".join(parts)
                    
                    page_item = QTreeWidgetItem(file_item)
                    page_item.setText(0, page_text)
                    
                    # Store invoice number in data for duplicate checking
                    item_data = {
                        "type": "page", 
                        "path": path, 
                        "page_num": i,
                        "invoice_num": inv_info.get("number", ""),
                        "invoice_date": inv_info.get("date", ""),
                        "is_invoice": inv_info.get("is_invoice", False)
                    }
                    page_item.setData(0, Qt.ItemDataRole.UserRole, item_data)
                    page_item.setCheckState(0, Qt.CheckState.Checked)
            finally:
                doc.close()

        # Default expand the item
        file_item.setExpanded(True)

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
                    inv_num = data.get("invoice_num")
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

    def browse_files(self):
        t = TRANS[self.current_lang]
        files, _ = QFileDialog.getOpenFileNames(self, t['add_files'], "", t['file_filter'])
        if files:
            self.file_list.blockSignals(True)
            try:
                for f in files:
                    self.add_file_item(f)
            finally:
                self.file_list.blockSignals(False)
            self.check_duplicates()
            self.update_statistics()

    def remove_selected_files(self):
        # Only remove top-level items for now to avoid confusion
        item = self.file_list.currentItem()
        if not item:
            return
            
        # If it's a page, remove its parent? Or do nothing?
        # User implies managing files.
        if item.parent():
            # It's a page. Let's select the parent to make it easier to remove the file?
            # Or just ignore.
            pass
        else:
            # It's a file
            index = self.file_list.indexOfTopLevelItem(item)
            self.file_list.takeTopLevelItem(index)
            self.check_duplicates()
            self.update_statistics()
            
        self.clear_preview()

    def clear_files(self):
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

    def move_item_up(self):
        item = self.file_list.currentItem()
        if not item or item.parent():
            return # Only move top-level files
            
        index = self.file_list.indexOfTopLevelItem(item)
        if index > 0:
            item = self.file_list.takeTopLevelItem(index)
            self.file_list.insertTopLevelItem(index - 1, item)
            self.file_list.setCurrentItem(item)

    def move_item_down(self):
        item = self.file_list.currentItem()
        if not item or item.parent():
            return
            
        index = self.file_list.indexOfTopLevelItem(item)
        if index < self.file_list.topLevelItemCount() - 1:
            item = self.file_list.takeTopLevelItem(index)
            self.file_list.insertTopLevelItem(index + 1, item)
            self.file_list.setCurrentItem(item)

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
        
        # Check conflicts
        if self.has_conflicts:
             QMessageBox.warning(self, t['window_title'], t.get('error_conflict', "Duplicate conflicts detected."))
             return

        count = self.file_list.topLevelItemCount()
        if count == 0:
            QMessageBox.warning(self, t['window_title'], t['error_no_files'])
            return

        input_items = []
        for i in range(count):
            file_item = self.file_list.topLevelItem(i)
            # Check if file itself is checked or has checked children
            # If file has children (pages), we respect page checks.
            # If file has no children (weird case), we check file state.
            
            if file_item.childCount() > 0:
                for j in range(file_item.childCount()):
                    page_item = file_item.child(j)
                    if page_item.checkState(0) == Qt.CheckState.Checked:
                        data = page_item.data(0, Qt.ItemDataRole.UserRole)
                        if data:
                            input_items.append((data['path'], data['page_num']))
            else:
                # Fallback for files without page info (shouldn't happen with current logic)
                if file_item.checkState(0) == Qt.CheckState.Checked:
                    data = file_item.data(0, Qt.ItemDataRole.UserRole)
                    if data:
                        input_items.append(data['path'])

        if not input_items:
             QMessageBox.warning(self, t['window_title'], "No pages selected for merge.")
             return

        self.status_bar.showMessage(t['status_processing'])
        QApplication.processEvents()

        try:
            # Use Core Logic - No output path, returns fitz.Document
            if self.temp_merged_doc:
                self.temp_merged_doc.close() # Close previous if exists
            
            # The core logic handles opening files itself
            self.temp_merged_doc = PDFProcessor.merge_half_page_pdfs(input_items)
            
            # Show Preview
            self.show_doc_preview(self.temp_merged_doc)
            
        # Enable actions
            self.btn_save.setEnabled(True)
            self.btn_print.setEnabled(True)
            
            self.status_bar.showMessage(t['status_ready'])
            
        except Exception as e:
            self.status_bar.showMessage(t['status_error'].format(str(e)))
            QMessageBox.critical(self, "Error", str(e))

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
        try:
            # Create a temp file
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            
            self.temp_merged_doc.save(temp_path)
            
            # Open with default system application (Windows)
            os.startfile(temp_path)
            
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