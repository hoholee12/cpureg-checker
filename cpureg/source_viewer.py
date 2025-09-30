import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QSplitter, QTreeView,
    QTextBrowser, QMenuBar, QMessageBox,
    QDialog, QLineEdit, QPushButton, QHBoxLayout,
    QFormLayout, QFileDialog, QComboBox, QLabel
)
from PySide6.QtGui import QAction, QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, QUrl
from cpureg.cpureg_parser import CpuRegParser

class GenerateDialog(QDialog):
    HISTORY_FILE = "history.txt"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate")
        self.setModal(True)
        self.resize(600, 250)
        layout = QVBoxLayout(self)

        # History dropdown
        self.history_combo = QComboBox()
        self.load_history()
        self.history_combo.currentIndexChanged.connect(self.on_history_selected)
        layout.addWidget(QLabel("History:"))
        layout.addWidget(self.history_combo)

        form_layout = QFormLayout()
        main_path_layout = QHBoxLayout()
        self.main_path_edit = QLineEdit()
        self.browse_btn = QPushButton("Browse")
        main_path_layout.addWidget(self.main_path_edit)
        main_path_layout.addWidget(self.browse_btn)
        form_layout.addRow("Main path to analyze:", main_path_layout)

        self.include_paths_edit = QLineEdit()
        self.include_paths_edit.setPlaceholderText("Separate paths with semicolon ';'")
        form_layout.addRow("Include paths:", self.include_paths_edit)
        layout.addLayout(form_layout)

        button_layout = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.cancel_btn = QPushButton("Cancel")
        button_layout.addWidget(self.generate_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

        self.generate_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.browse_btn.clicked.connect(self.browse_main_path)

    def load_history(self):
        self.history = []
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = []
        self.history_combo.clear()
        for entry in self.history:
            main_path = entry.get("main_path", "")
            include_paths = ";".join(entry.get("include_paths", []))
            self.history_combo.addItem(f"{main_path} | {include_paths}")

    def on_history_selected(self, idx):
        if 0 <= idx < len(self.history):
            entry = self.history[idx]
            self.main_path_edit.setText(entry.get("main_path", ""))
            self.include_paths_edit.setText(";".join(entry.get("include_paths", [])))

    def browse_main_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Main Path")
        if path:
            self.main_path_edit.setText(path)

    def get_paths(self) -> tuple[str, list[str]]:
        main_path = self.main_path_edit.text().strip()
        include_paths = [p.strip() for p in self.include_paths_edit.text().split(';') if p.strip()]
        self.save_to_history(main_path, include_paths)
        return main_path, include_paths

    def save_to_history(self, main_path, include_paths):
        entry = {"main_path": main_path, "include_paths": include_paths}
        # Avoid duplicates
        if entry not in self.history:
            self.history.insert(0, entry)
            # Limit history size
            self.history = self.history[:20]
            try:
                with open(self.HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)
            except Exception:
                pass
        self.load_history()

class SourceViewer(QMainWindow):
    def __init__(self, folder_path="cpureg_workspace/proc_funcbody"):
        super().__init__()

        # get CpuRegParser (for hashed filename)
        self.cpureg = CpuRegParser()

        self.setWindowTitle("Source Viewer")
        self.resize(1000, 600)

        # Menu Bar with layers
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
        splitter = QSplitter(Qt.Horizontal)

        # Custom tree model for grouping
        self.folder_path = os.path.abspath(folder_path)
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeView.SingleSelection)
        self.tree.clicked.connect(self.on_file_selected)
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

    def populate_tree(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Source Files'])
        groups = {}
        for fname in os.listdir(self.folder_path):
            if fname.count('.') < 4 or not fname.endswith('.txt'):
                continue
            parts = fname.split('.')
            src_name = '.'.join(parts[:-4])
            src_ext = parts[-4]
            func_name = parts[-3]
            group_key = f"{src_name}.{src_ext}"
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
        call_list_file = os.path.join("cpureg_workspace", "callstack_gen", f"{func_name}.txt")
        print(f"[DEBUG] Reading call list file: {call_list_file}")
        functions = set()
        if os.path.exists(call_list_file):
            with open(call_list_file, "r", encoding="utf-8") as f:
                for line in f:
                    func = line.strip()
                    print(f"[DEBUG] Call list line: '{func}'")
                    if func:
                        functions.add(func)
        else:
            print(f"[DEBUG] Call list file does not exist: {call_list_file}")
        print(f"[DEBUG] Final call list for '{func_name}': {functions}")
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
                return f'<a href="{cmp_func}"><span style="color:blue;text-decoration:underline;">{func}</span></a>'
            return func

        pattern = r'\b_?\w+\b'
        return re.sub(pattern, repl, content)

    def add_line_numbers(self, content: str) -> str:
        lines = content.splitlines()
        numbered = [
            f'<span style="color:gray;">{str(i+1).rjust(4)}:</span> {line}'
            for i, line in enumerate(lines)
        ]
        return "\n".join(numbered)

    def on_file_selected(self, index):
        item = self.model.itemFromIndex(index)
        if item and item.parent():  # Only leaf nodes (function names)
            full_fname = item.data(Qt.UserRole)
            file_path = os.path.join(self.folder_path, full_fname)
            func_name = item.text()
            self.functions = self.load_call_list(func_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(file_path, "r", errors="replace") as f:
                    content = f.read()
            numbered_content = self.add_line_numbers(content)
            html_content = f'<pre style="white-space: pre-wrap;">{self.highlight_functions(numbered_content)}</pre>'
            self.viewer.setHtml(html_content)

    def on_function_clicked(self, url: QUrl):
        func_name = url.toString()
        # Search for the function in the tree and select it
        for i in range(self.model.rowCount()):
            src_item = self.model.item(i)
            for j in range(src_item.rowCount()):
                func_item = src_item.child(j)
                if func_item.text() == func_name:
                    index = func_item.index()
                    self.tree.setCurrentIndex(index)
                    self.tree.scrollTo(index)
                    self.on_file_selected(index)
                    return
        self.viewer.setHtml(f"<b>Function file not found for: {func_name}</b>")

    def on_generate(self):
        dialog = GenerateDialog(self)
        if dialog.exec():
            main_path, include_paths = dialog.get_paths()
            # Apply the main path to the source tree and viewer
            if main_path and os.path.isdir(main_path):
                self.folder_path = os.path.abspath(main_path)
                self.populate_tree()  # Rebuild tree for new folder
                QMessageBox.information(
                    self,
                    "Generate",
                    f"Main path set to: {main_path}\nInclude paths: {', '.join(include_paths)}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Invalid Path",
                    "The main path you entered does not exist or is not a directory."
                )

    def on_report(self):
        QMessageBox.information(self, "Report", "Report action triggered.")

    def on_about(self):
        QMessageBox.information(self, "About", "Source Viewer\nVersion 1.0")

