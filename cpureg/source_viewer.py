import sys
import time
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QSplitter, QTreeView,
    QTextBrowser, QMenuBar, QMessageBox,
    QDialog, QLineEdit, QPushButton, QHBoxLayout,
    QFormLayout, QFileDialog, QComboBox, QLabel, QListWidget
)
from PySide6.QtGui import QAction, QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, QUrl
from cpureg.cpureg_parser import CpuRegParser
from cpureg.cpureg_checker import CpuRegApp # for check_gcc

class GenerateDialog(QDialog):
    HISTORY_FILE = "history.txt"

    def __init__(self, parent=None, cpureg_parser=None):
        super().__init__(parent)
        self.setWindowTitle("Generate")
        self.setModal(True)
        self.resize(600, 300)
        layout = QVBoxLayout(self)

        self.cpureg = cpureg_parser if cpureg_parser else CpuRegParser()

        # History select list
        layout.addWidget(QLabel("History:"))
        self.history_list = QListWidget()
        self.history_list.currentRowChanged.connect(self.on_history_selected)
        layout.addWidget(self.history_list)

        form_layout = QFormLayout()

        # Include paths input with explorer and add button
        include_path_layout = QHBoxLayout()
        self.include_path_edit = QLineEdit()
        self.include_browse_btn = QPushButton("Browse")
        self.include_add_btn = QPushButton("Add")
        include_path_layout.addWidget(self.include_path_edit)
        include_path_layout.addWidget(self.include_browse_btn)
        include_path_layout.addWidget(self.include_add_btn)
        form_layout.addRow("Include path:", include_path_layout)

        # List of accumulated include paths
        self.include_paths_list = QListWidget()
        self.include_paths_list.itemDoubleClicked.connect(self.on_include_path_double_clicked)
        form_layout.addRow("Selected include paths:", self.include_paths_list)

        # Target platform input
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(self.cpureg.supported_platforms)
        form_layout.addRow("Target platform:", self.platform_combo)

        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.generate_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.include_browse_btn.clicked.connect(self.browse_include_path)
        self.include_add_btn.clicked.connect(self.add_include_path)

        # Now it's safe to call load_history
        self.load_history()

    def load_history(self):
        from PySide6.QtWidgets import QListWidgetItem
        self.history = []
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        if hasattr(self, "history_list"):
            self.history_list.clear()
            for entry in self.history:
                include_paths = ";".join(entry.get("include_paths", []))
                platform = entry.get("platform")
                if platform is None and self.platform_combo.count() > 0:
                    platform = self.platform_combo.itemText(0)
                elif platform is None:
                    platform = ""
                item = QListWidgetItem(include_paths + " | " + platform)
                self.history_list.addItem(item)

    def on_history_selected(self, idx):
        if 0 <= idx < len(self.history):
            entry = self.history[idx]
            self.include_paths_list.clear()
            for path in entry.get("include_paths", []):
                self.include_paths_list.addItem(path)
            platform = entry.get("platform")
            if platform is None:
                # Default to first supported platform if not present
                platform = self.platform_combo.itemText(0)
            platform_idx = self.platform_combo.findText(platform)
            if platform_idx >= 0:
                self.platform_combo.setCurrentIndex(platform_idx)

    def browse_include_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Include Path")
        if path:
            self.include_path_edit.setText(path)

    def add_include_path(self):
        path = self.include_path_edit.text().strip()
        if path and path not in [self.include_paths_list.item(i).text() for i in range(self.include_paths_list.count())]:
            self.include_paths_list.addItem(path)
        self.include_path_edit.clear()

    def on_include_path_double_clicked(self, item):
        # Remove from list and put in the browse input box
        self.include_path_edit.setText(item.text())
        row = self.include_paths_list.row(item)
        self.include_paths_list.takeItem(row)

    def get_paths(self) -> tuple[list[str], str]:
        include_paths = [self.include_paths_list.item(i).text() for i in range(self.include_paths_list.count())]
        platform = self.platform_combo.currentText()
        self.save_to_history(include_paths, platform)
        return include_paths, platform

    def save_to_history(self, include_paths, platform):
        entry = {"include_paths": include_paths, "platform": platform}
        if entry not in self.history:
            self.history.insert(0, entry)
            self.history = self.history[:20]
            try:
                with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception:
                pass
        self.load_history()

class SourceViewer(QMainWindow):
    
    dark_stylesheet = """
QWidget {
    background-color: #232629;
    color: #f0f0f0;
}
QLineEdit, QTextEdit, QTextBrowser, QListWidget, QComboBox {
    background-color: #2b2b2b;
    color: #f0f0f0;
    border: 1px solid #444;
}
QMenuBar, QMenu, QMenu::item {
    background-color: #232629;
    color: #f0f0f0;
}
QTreeView {
    background-color: #232629;
    color: #f0f0f0;
    alternate-background-color: #2b2b2b;
}
QPushButton {
    background-color: #444;
    color: #f0f0f0;
    border: 1px solid #666;
    border-radius: 3px;
    padding: 3px 8px;
}
QPushButton:hover {
    background-color: #555;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #232629;
}
"""

    def __init__(self, folder_path=None):
        super().__init__()

        self.cpureg = CpuRegParser()
        # Use cpureg_parser's workspace path instead of hardcoded path
        self.folder_path = folder_path if folder_path else self.cpureg.proc_funcbody_dir
        
        # Ensure workspace folders exist using the existing cleanup function
        if not os.path.exists(self.folder_path):
            self.cpureg.parse_workspace_cleanup()
        
        self.setWindowTitle("Source Viewer")
        self.resize(1000, 600)

        # Function navigation path and bar
        self.function_path = []
        self.path_bar = QLineEdit()
        self.path_bar.setReadOnly(True)
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedWidth(60)
        self.back_btn.clicked.connect(self.on_back)

        # Menu Bar with layers (unchanged)
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)
        file_menu = menubar.addMenu("File")
        tools_menu = menubar.addMenu("Tools")
        about_action = QAction("About", self)
        quit_action = QAction("Quit", self)
        file_menu.addAction(about_action)
        file_menu.addAction(quit_action)
        generate_action = QAction("Generate", self)
        report_action = QAction("Report", self)
        tools_menu.addAction(generate_action)
        tools_menu.addAction(report_action)
        generate_action.triggered.connect(self.on_generate)
        report_action.triggered.connect(self.on_report)
        about_action.triggered.connect(self.on_about)
        quit_action.triggered.connect(self.close)

        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)

        # Add path bar and back button at the top
        path_bar_layout = QHBoxLayout()
        path_bar_layout.addWidget(self.path_bar)
        path_bar_layout.addWidget(self.back_btn)
        layout.addLayout(path_bar_layout)

        splitter = QSplitter(Qt.Horizontal)
        self.folder_path = os.path.abspath(self.folder_path)
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeView.SingleSelection)
        self.tree.clicked.connect(lambda idx: self.on_file_selected(idx, True))
        self.tree.setColumnWidth(0, 200)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Source Files'])
        self.tree.setModel(self.model)
        self.populate_tree()

        self.viewer = QTextBrowser()
        self.viewer.setOpenLinks(False)
        self.viewer.anchorClicked.connect(self.on_function_clicked)
        self.viewer.setLineWrapMode(QTextBrowser.WidgetWidth)

        splitter.addWidget(self.tree)
        splitter.addWidget(self.viewer)
        splitter.setSizes([200, 800])
        layout.addWidget(splitter)
        self.setCentralWidget(main_widget)

        self.functions = set()  # will be set per file

    def update_path_bar(self):
        self.path_bar.setText(" \u2192 ".join(self.function_path))

    def populate_tree(self):
        time.sleep(1)
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Source Files'])
        
        # Ensure folder exists before trying to list it
        if not os.path.exists(self.folder_path):
            return
        
        groups = {}
        for fname in os.listdir(self.folder_path):
            if fname.count('.') < 4 or not fname.endswith('.txt'):
                continue
            parts = fname.split('.')
            src_name = '.'.join(parts[:-4])
            src_ext = parts[-4]
            func_name = parts[-3]
            group_key = src_name + "." + src_ext
            groups.setdefault(group_key, []).append((func_name, fname))
        for src_file, funcs in sorted(groups.items()):
            src_item = QStandardItem(src_file)
            src_item.setEditable(False)
            for func_name, full_fname in sorted(funcs):
                func_item = QStandardItem(func_name)
                func_item.setEditable(False)
                func_item.setData(full_fname, Qt.UserRole)
                src_item.appendRow(func_item)
            self.model.appendRow(src_item)
            self.tree.setExpanded(src_item.index(), True)

    def load_call_list(self, func_name: str) -> set[str]:
        # Use cpureg_parser's funcname_hashgen method
        call_list_file = os.path.join(self.cpureg.callstack_gen_dir, self.cpureg.funcname_hashgen(func_name))
        print("[DEBUG] Reading call list file: " + call_list_file)
        functions = set()
        if os.path.exists(call_list_file):
            with open(call_list_file, "r", encoding="utf-8") as f:
                for line in f:
                    func = line.strip()
                    print("[DEBUG] Call list line: '" + func + "'")
                    if func:
                        functions.add(func)
        else:
            print("[DEBUG] Call list file does not exist: " + call_list_file)
        print("[DEBUG] Final call list for '" + func_name + "': " + str(functions))
        return functions

    def highlight_functions(self, content: str) -> str:
        import re
        if not self.functions:
            return content

        func_set = set()
        for f in self.functions:
            func_set.add(f)
            if not f.startswith('_'):
                func_set.add('_' + f)

        def repl(match):
            func = match.group(0)
            cmp_func = func.lstrip('_')
            if cmp_func in self.functions or func in self.functions or func in func_set:
                # Yellow text for highlight, no background
                return (
                    '<a href="' + cmp_func + '">'
                    '<span style="color:#ffe066; font-weight:bold;">' + func + '</span>'
                    '</a>'
                )
            return func

        pattern = r'\b_?\w+\b'
        return re.sub(pattern, repl, content)

    def add_line_numbers(self, content: str) -> str:
        lines = content.splitlines()
        numbered = [
            '<span style="color:gray;">' + str(i+1).rjust(4) + ':</span> ' + line
            for i, line in enumerate(lines)
        ]
        return "\n".join(numbered)

    def on_file_selected(self, index, reset_path=True):
        item = self.model.itemFromIndex(index)
        if item and item.parent():  # Only leaf nodes (function names)
            func_name = item.text()
            if reset_path:
                self.function_path = [func_name]
                self.update_path_bar()
            full_fname = item.data(Qt.UserRole)
            file_path = os.path.join(self.folder_path, full_fname)
            self.functions = self.load_call_list(func_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", errors="replace") as f:
                    content = f.read()
            numbered_content = self.add_line_numbers(content)
            html_content = '<pre style="white-space: pre-wrap;">' + self.highlight_functions(numbered_content) + '</pre>'
            self.viewer.setHtml(html_content)

    def on_function_clicked(self, url: QUrl):
        func_name = url.toString()
        # Add to navigation path only if not already last
        if not self.function_path or self.function_path[-1] != func_name:
            self.function_path.append(func_name)
        self.update_path_bar()
        # Search for the function in the tree and select it
        for i in range(self.model.rowCount()):
            src_item = self.model.item(i)
            for j in range(src_item.rowCount()):
                func_item = src_item.child(j)
                if func_item.text() == func_name:
                    index = func_item.index()
                    self.tree.setCurrentIndex(index)
                    self.tree.scrollTo(index)
                    self.on_file_selected(index, reset_path=False)
                    return
        self.viewer.setHtml("<b>Function file not found for: " + func_name + "</b>")

    def on_back(self):
        if len(self.function_path) > 1:
            self.function_path.pop()
            self.update_path_bar()
            prev_func = self.function_path[-1]
            # Search for the function in the tree and select it
            for i in range(self.model.rowCount()):
                src_item = self.model.item(i)
                for j in range(src_item.rowCount()):
                    func_item = src_item.child(j)
                    if func_item.text() == prev_func:
                        index = func_item.index()
                        self.tree.setCurrentIndex(index)
                        self.tree.scrollTo(index)
                        self.on_file_selected(index, reset_path=False)
                        return

    def on_generate(self):
        # Pass the cpureg instance to avoid duplicate instantiation
        dialog = GenerateDialog(self, self.cpureg)
        if dialog.exec():
            include_paths, target_platform = dialog.get_paths()
            try:
                CpuRegApp().check_gcc()
                srcpaths = self.cpureg.parse_per_target_platform(target_platform, include_paths)
                self.cpureg.parse_workspace_cleanup()
                self.cpureg.parse_functions(srcpaths, include_paths)
                self.populate_tree()
                # Reset source view after generate
                self.viewer.clear()
                self.function_path = []
                self.update_path_bar()
                QMessageBox.information(
                    self,
                    "Generate",
                    "Generation finished!\nInclude paths: " + ", ".join(include_paths) + "\nPlatform: " + target_platform
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Generate Error",
                    "An error occurred during generation:\n" + str(e)
                )

    def on_report(self):
        QMessageBox.information(self, "Report", "Report action triggered.")

    def on_about(self):
        QMessageBox.information(self, "About", "Source Viewer\nVersion 1.0")


