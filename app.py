"""
Simple Git Clone Manager - PySide6 / PyQt5 single-file app

Features implemented for your request (sample JSON + Add Project):
- Left sidebar + toolbar (folder, clone, refresh, add project icons)
- Light theme (with optional dark toggle)
- Three-step selection: Category (dev/localization) -> Project -> Component
- Destination folder chooser
- Clone using system git (subprocess) running in background thread
- Live logs shown in the UI
- Auto-creates a sample `repos.json` if missing (you asked for sample JSON)
- Add Project dialog: add a new project + component and save to repos.json

How to run:
1. Install dependencies:
   pip install PySide6
   (or pip install PyQt5)
2. Ensure `git` is installed and on PATH
3. Save this file as `app.py` next to no `repos.json` (a sample will be created)
4. Run: python app.py


"""
from __future__ import annotations
import json
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any

# Try PySide6 then PyQt5
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
        QPushButton, QListWidget, QListWidgetItem, QLabel, QStackedWidget,
        QComboBox, QTextEdit, QFileDialog, QMessageBox, QLineEdit, QSizePolicy, QDialog
    )
    from PySide6.QtGui import QAction, QIcon
    from PySide6.QtCore import Qt, QSize, QThread, Signal
    FRAMEWORK = "PySide6"
except Exception:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
        QPushButton, QListWidget, QListWidgetItem, QLabel, QStackedWidget,
        QComboBox, QTextEdit, QFileDialog, QMessageBox, QLineEdit, QSizePolicy, QDialog
    )
    from PyQt5.QtGui import QAction, QIcon
    from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal as Signal
    FRAMEWORK = "PyQt5"

CONFIG_FILE = Path("repos.json")
SAMPLE_CONFIG = {
    "dev": {
        "ProjectA": {
            "Test": "https://github.com/abhisheksainiofficial7060/testrepo.git",
            "Component2": "https://github.com/user/projectA-component2.git"
        },
        "ProjectB": {
            "Component1": "https://github.com/user/projectB-component1.git"
        }
    },
    "localization": {
        "ProjectA": {
            "ui": "https://github.com/user/localization-projectA-ui.git",
            "strings": "https://github.com/user/localization-projectA-strings.git"
        }
    }
}


class CloneThread(QThread):
    log = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, url: str, dest: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self._stopped = False

    def run(self):
        dest_path = Path(self.dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self.log.emit(f"Starting clone: {self.url} -> {self.dest}\n")

        try:
            proc = subprocess.Popen([
                "git", "clone", self.url, str(self.dest)
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            assert proc.stdout is not None
            for line in proc.stdout:
                if self._stopped:
                    proc.kill()
                    self.log.emit("Clone aborted by user.\n")
                    self.finished_signal.emit(False, "aborted")
                    return
                self.log.emit(line.rstrip())

            ret = proc.wait()
            if ret == 0:
                self.log.emit("Clone completed successfully.\n")
                self.finished_signal.emit(True, "success")
            else:
                self.log.emit(f"git exited with code {ret}\n")
                self.finished_signal.emit(False, f"exit {ret}")

        except FileNotFoundError:
            self.log.emit("Error: 'git' not found. Please install Git and ensure it is on PATH.\n")
            self.finished_signal.emit(False, "git-not-found")
        except Exception as e:
            self.log.emit(f"Unexpected error: {e}\n")
            self.finished_signal.emit(False, str(e))

    def stop(self):
        self._stopped = True


class SimpleCloneManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Git Clone Manager")
        self.setMinimumSize(900, 560)

        self.repos = self.load_or_create_config()

        # Theme
        self.dark_mode = False
        self.apply_light_theme()

        # Toolbar
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Toolbar actions (using emoji as simple icons)
        open_action = QAction("📁", self)
        open_action.setToolTip("Open destination folder")
        open_action.triggered.connect(self.open_destination_folder)
        toolbar.addAction(open_action)

        clone_action = QAction("🌀", self)
        clone_action.setToolTip("Clone selected component")
        clone_action.triggered.connect(self.clone_button_clicked)
        toolbar.addAction(clone_action)

        refresh_action = QAction("🔄", self)
        refresh_action.setToolTip("Refresh projects")
        refresh_action.triggered.connect(self.refresh_projects)
        toolbar.addAction(refresh_action)

        # Add Project action
        addproj_action = QAction("➕", self)
        addproj_action.setToolTip("Add new project")
        addproj_action.triggered.connect(self.add_project_dialog)
        toolbar.addAction(addproj_action)

        toolbar.addSeparator()
        theme_action = QAction("🌙", self)
        theme_action.setToolTip("Toggle light/dark theme")
        theme_action.triggered.connect(self.toggle_theme)
        toolbar.addAction(theme_action)

        # Left sidebar (projects quick list) - will show categories as headers
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(220)
        self.sidebar.itemClicked.connect(self.on_sidebar_item_clicked)

        # Right content area - top: selection controls, middle: components list, bottom: logs
        content = QWidget()
        content_layout = QVBoxLayout()

        # Selection row
        sel_layout = QHBoxLayout()
        sel_layout.setContentsMargins(6, 6, 6, 6)
        sel_layout.setSpacing(10)

        self.cat_combo = QComboBox()
        self.cat_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.cat_combo.addItems(sorted(self.repos.keys()))
        self.cat_combo.currentTextChanged.connect(self.on_category_change)

        self.project_combo = QComboBox()
        self.project_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.project_combo.currentTextChanged.connect(self.on_project_change)

        self.component_combo = QComboBox()
        self.component_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        sel_layout.addWidget(QLabel("Category:"))
        sel_layout.addWidget(self.cat_combo)
        sel_layout.addWidget(QLabel("Project:"))
        sel_layout.addWidget(self.project_combo)
        sel_layout.addWidget(QLabel("Component:"))
        sel_layout.addWidget(self.component_combo)

        # Destination chooser
        dest_layout = QHBoxLayout()
        dest_layout.setContentsMargins(6, 0, 6, 6)
        dest_layout.setSpacing(8)
        self.dest_line = QLineEdit(str(Path.cwd() / "cloned"))
        self.dest_line.setPlaceholderText("Destination folder")
        dest_btn = QPushButton("Browse")
        dest_btn.setFixedWidth(90)
        dest_btn.clicked.connect(self.browse_dest)

        clone_btn = QPushButton("Clone")
        clone_btn.setFixedHeight(38)
        clone_btn.setMinimumWidth(120)
        clone_btn.clicked.connect(self.clone_button_clicked)
        clone_btn.setStyleSheet(self.primary_button())
        clone_btn.setObjectName("CloneButton")
        self.clone_btn = clone_btn

        dest_layout.addWidget(QLabel("Destination:"))
        dest_layout.addWidget(self.dest_line)
        dest_layout.addWidget(dest_btn)
        dest_layout.addWidget(clone_btn)

        # Logs
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(220)

        content_layout.addLayout(sel_layout)
        content_layout.addLayout(dest_layout)
        content_layout.addWidget(QLabel("Logs:"))
        content_layout.addWidget(self.log_view)
        content.setLayout(content_layout)

        # Main layout with sidebar + content
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(content)
        main_widget.setLayout(main_layout)

        self.setCentralWidget(main_widget)

        # Clone thread holder
        self.clone_thread: CloneThread | None = None

        # Populate UI
        self.populate_sidebar()
        # initialize combos
        if self.cat_combo.count() > 0:
            self.cat_combo.setCurrentIndex(0)
            self.on_category_change(self.cat_combo.currentText())

        # show framework in status bar
        self.statusBar().showMessage(f"Using: {FRAMEWORK}")

    # ----------------- UI helpers -----------------
    def primary_button(self):
        return """
            QPushButton {
                background-color: #1976D2;
                color: white;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #1565C0; }
            QPushButton:pressed { background-color: #0D47A1; }
        """

    def append_log(self, text: str):
        self.log_view.append(text)
        # autoscroll
        self.log_view.ensureCursorVisible()

    # ----------------- Config -----------------
    def load_or_create_config(self) -> Dict[str, Any]:
        if not CONFIG_FILE.exists():
            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(SAMPLE_CONFIG, f, indent=2)
            QMessageBox.information(self, "Sample Config Created",
                                    f"repos.json was not found and a sample has been created at {CONFIG_FILE.resolve()}\n\nPlease update it with your repo links.")
            return SAMPLE_CONFIG

        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            QMessageBox.critical(self, "Config Error", f"Failed to read repos.json: {e}")
            return SAMPLE_CONFIG

    # ----------------- Sidebar & Refresh -----------------
    def populate_sidebar(self):
        self.sidebar.clear()
        # Show categories as disabled items and projects under them
        for cat in sorted(self.repos.keys()):
            cat_item = QListWidgetItem(cat.upper())
            cat_item.setFlags(Qt.ItemIsEnabled)
            cat_item.setData(Qt.UserRole, ("category", cat))
            self.sidebar.addItem(cat_item)
            for proj in sorted(self.repos[cat].keys()):
                proj_item = QListWidgetItem(f"  {proj}")
                proj_item.setData(Qt.UserRole, ("project", cat, proj))
                self.sidebar.addItem(proj_item)

    def refresh_projects(self):
        self.repos = self.load_or_create_config()
        self.populate_sidebar()
        # reload combos for selected category
        cur_cat = self.cat_combo.currentText()
        self.cat_combo.clear()
        self.cat_combo.addItems(sorted(self.repos.keys()))
        if cur_cat and cur_cat in self.repos:
            self.cat_combo.setCurrentText(cur_cat)
        self.append_log("Refreshed project list from repos.json")

    def on_sidebar_item_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return
        if data[0] == "project":
            _, cat, proj = data
            # set combos
            self.cat_combo.setCurrentText(cat)
            self.project_combo.setCurrentText(proj)
            self.on_project_change(proj)

    # ----------------- Combo handlers -----------------
    def on_category_change(self, text: str):
        self.project_combo.clear()
        if text and text in self.repos:
            self.project_combo.addItems(sorted(self.repos[text].keys()))
            if self.project_combo.count() > 0:
                self.project_combo.setCurrentIndex(0)
                self.on_project_change(self.project_combo.currentText())

    def on_project_change(self, text: str):
        self.component_combo.clear()
        cat = self.cat_combo.currentText()
        proj = text
        if cat and proj and cat in self.repos and proj in self.repos[cat]:
            self.component_combo.addItems(sorted(self.repos[cat][proj].keys()))

    # ----------------- Destination -----------------
    def browse_dest(self):
        d = QFileDialog.getExistingDirectory(self, "Choose destination folder", str(Path.cwd()))
        if d:
            self.dest_line.setText(d)

    def open_destination_folder(self):
        dest = self.dest_line.text().strip()
        if not dest:
            QMessageBox.warning(self, "No destination", "Please select a destination folder first.")
            return
        p = Path(dest)
        if not p.exists():
            QMessageBox.warning(self, "Not found", "Destination folder does not exist.")
            return
        # open in file explorer
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(p)])
        elif sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(p)])
        else:
            subprocess.Popen(["xdg-open", str(p)])

    # ----------------- Clone -----------------
    def clone_button_clicked(self):
        cat = self.cat_combo.currentText()
        proj = self.project_combo.currentText()
        comp = self.component_combo.currentText()

        if not cat or not proj or not comp:
            QMessageBox.warning(self, "Selection required", "Please select category, project and component.")
            return

        try:
            url = self.repos[cat][proj][comp]
        except Exception:
            QMessageBox.critical(self, "Error", "Repo URL not found in config for selected item.")
            return

        dest = self.dest_line.text().strip()
        if not dest:
            QMessageBox.warning(self, "Destination required", "Please select a destination folder.")
            return

        # by default clone into dest/project/component folder
        dest_path = Path(dest) / proj / comp

        if dest_path.exists() and any(dest_path.iterdir()):
            r = QMessageBox.question(self, "Destination Not Empty",
                                     f"The destination folder {dest_path} already exists and is not empty. Overwrite?",
                                     QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.Yes:
                try:
                    if dest_path.is_dir():
                        shutil.rmtree(dest_path)
                    else:
                        dest_path.unlink()
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to clear destination: {e}")
                    return
            else:
                return

        # run clone in thread
        self.clone_btn.setEnabled(False)
        self.append_log(f"Cloning {url} into {dest_path} ...")
        self.clone_thread = CloneThread(url, str(dest_path))
        self.clone_thread.log.connect(lambda t: self.append_log(t))
        self.clone_thread.finished_signal.connect(self.clone_finished)
        self.clone_thread.start()

    def clone_finished(self, success: bool, info: str):
        self.append_log(f"Clone finished. success={success}, info={info}")
        QMessageBox.information(self, "Clone Finished", f"Finished: success={success}, info={info}")
        self.clone_btn.setEnabled(True)
        # refresh sidebar so new folder can be visible if desired

    # ----------------- Add Project -----------------
    def add_project_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add New Project")
        dlg_layout = QVBoxLayout()
        form_layout = QHBoxLayout()

        left_v = QVBoxLayout()
        left_v.addWidget(QLabel("Repo Type:"))
        left_v.addWidget(QLabel("Project Name:"))
        left_v.addWidget(QLabel("Component Name:"))
        left_v.addWidget(QLabel("Repo URL:"))

        right_v = QVBoxLayout()
        type_combo = QComboBox()
        type_combo.addItems(sorted(self.repos.keys()))
        proj_edit = QLineEdit()
        comp_edit = QLineEdit()
        url_edit = QLineEdit()

        right_v.addWidget(type_combo)
        right_v.addWidget(proj_edit)
        right_v.addWidget(comp_edit)
        right_v.addWidget(url_edit)

        form_layout.addLayout(left_v)
        form_layout.addLayout(right_v)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(lambda: self.save_new_project(type_combo.currentText(), proj_edit.text().strip(), comp_edit.text().strip(), url_edit.text().strip(), dialog))
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)

        dlg_layout.addLayout(form_layout)
        dlg_layout.addLayout(btn_layout)
        dialog.setLayout(dlg_layout)
        dialog.exec()

    def save_new_project(self, repo_type: str, project_name: str, component_name: str, repo_url: str, dialog: QDialog):
        if not project_name or not component_name or not repo_url:
            QMessageBox.warning(self, "Validation", "Please fill all fields.")
            return

        # normalize repo_type key
        repo_type_key = repo_type
        if repo_type_key not in self.repos:
            self.repos[repo_type_key] = {}

        if project_name not in self.repos[repo_type_key]:
            self.repos[repo_type_key][project_name] = {}

        # add/update component URL
        self.repos[repo_type_key][project_name][component_name] = repo_url

        # write back to file
        try:
            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.repos, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to write repos.json: {e}")
            return

        self.append_log(f"Added project: {repo_type_key}/{project_name}/{component_name}\n")
        QMessageBox.information(self, "Saved", "Project added successfully.")
        dialog.accept()
        # refresh UI
        self.refresh_projects()
        # select the newly added project/component
        self.cat_combo.setCurrentText(repo_type_key)
        self.project_combo.setCurrentText(project_name)
        self.component_combo.setCurrentText(component_name)

    # ----------------- Theme -----------------
    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            self.apply_dark_theme()
        else:
            self.apply_light_theme()

    def apply_light_theme(self):
        self.setStyleSheet("""
            QWidget { background: #F6F6F6; color: #333; font-family: Segoe UI, Arial; }
            QLabel { font-size: 14px; }
            QComboBox, QLineEdit { background: #FFFFFF; border: 1px solid #D0D0D0; padding: 6px; border-radius: 6px; }
            QListWidget { background: #FFFFFF; border-right: 1px solid #E8E8E8; }
            QTextEdit { background: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 6px; }
            QToolBar { background: #FFFFFF; border-bottom: 1px solid #E8E8E8; }
            QPushButton#CloneButton { background-color: #4CAF50; color: white; font-weight: 600; }
            QPushButton#CloneButton:hover { background-color: #43A047; }
        """)

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget { background: #121212; color: #EEEEEE; font-family: Segoe UI, Arial; }
            QComboBox, QLineEdit { background: #1E1E1E; border: 1px solid #333; padding: 6px; border-radius: 6px; color: #EEE; }
            QListWidget { background: #1E1E1E; border-right: 1px solid #2a2a2a; }
            QTextEdit { background: #111; border: 1px solid #222; border-radius: 6px; color: #EEE; }
            QToolBar { background: #1E1E1E; border-bottom: 1px solid #222; }
            QPushButton#CloneButton { background-color: #4CAF50; color: white; font-weight: 600; }
            QPushButton#CloneButton:hover { background-color: #43A047; }
        """)


def main():
    app = QApplication(sys.argv)
    w = SimpleCloneManager()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
