import sys
import os
import json
import sqlite3
import time
import keyboard
import pyperclip
import pyautogui

from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QDialog, QTextEdit, QFileDialog, 
    QListWidget, QListWidgetItem, QSystemTrayIcon, QMenu
)

DB_FILE = "quick_replies.db"
LEGACY_JSON = "saved_replies.json"

class DatabaseManager:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.init_db()
        self.migrate_json_if_exists()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shortcut TEXT UNIQUE NOT NULL,
                    message TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def migrate_json_if_exists(self):
        if os.path.exists(LEGACY_JSON):
            try:
                with open(LEGACY_JSON, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                with self.get_connection() as conn:
                    for shortcut, message in data.items():
                        conn.execute(
                            "INSERT OR IGNORE INTO replies (shortcut, message, usage_count) VALUES (?, ?, 0)",
                            (shortcut, message)
                        )
                    conn.commit()
            except Exception as e:
                print(f"Migration error: {e}")

    def get_all_replies(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id, shortcut, message, usage_count FROM replies ORDER BY shortcut COLLATE NOCASE ASC")
            return [dict(row) for row in cursor.fetchall()]

    def add_reply(self, shortcut, message):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO replies (shortcut, message, usage_count) VALUES (?, ?, 0) ON CONFLICT(shortcut) DO UPDATE SET message=excluded.message",
                (shortcut, message)
            )
            conn.commit()

    def update_reply(self, shortcut, message):
        self.add_reply(shortcut, message)

    def delete_reply(self, shortcut):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM replies WHERE shortcut = ?", (shortcut,))
            conn.commit()

    def increment_usage(self, shortcut):
        with self.get_connection() as conn:
            conn.execute("UPDATE replies SET usage_count = usage_count + 1 WHERE shortcut = ?", (shortcut,))
            conn.commit()

    def export_to_json(self, filepath):
        replies = self.get_all_replies()
        data = {r["shortcut"]: r["message"] for r in replies}
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def import_from_json(self, filepath):
        with open(filepath, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
            if content.endswith(","):
                content = content[:-1]
            data = json.loads(content)
        for shortcut, message in data.items():
            self.add_reply(shortcut, message)


class ShortcutEngine(QThread):
    open_popup_signal = Signal()

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.paused = False
        self._running = True

    def run(self):
        try:
            # Global shortcut Alt+Q and single-key backtick trigger (` key above Tab)
            keyboard.add_hotkey('alt+q', self.on_hotkey, suppress=True)
            keyboard.add_hotkey('`', self.on_hotkey, suppress=True)
        except Exception as e:
            print(f"Hotkey registration error: {e}")

        while self._running:
            time.sleep(0.1)

    def on_hotkey(self):
        if not self.paused:
            self.open_popup_signal.emit()

    def stop(self):
        self._running = False
        try:
            keyboard.unhook_all()
        except:
            pass


class EditReplyDialog(QDialog):
    def __init__(self, parent=None, shortcut="", message=""):
        super().__init__(parent)
        self.setWindowTitle("Quick Reply Details")
        self.setFixedSize(380, 260)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; font-family: 'Segoe UI'; color: #0F172A; }
            QLabel { font-size: 12px; font-weight: bold; color: #0F172A; }
            QLineEdit, QTextEdit {
                background-color: #F8FAFC; border: 1px solid #E2E8F0;
                border-radius: 6px; padding: 6px; font-size: 12px; color: #0F172A;
            }
            QLineEdit:focus, QTextEdit:focus { border: 1px solid #2563EB; }
            QPushButton { border-radius: 6px; padding: 6px 14px; font-weight: bold; font-size: 12px; border: none; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Shortcut Keyword:"))
        self.shortcut_input = QLineEdit(shortcut)
        self.shortcut_input.setPlaceholderText("e.g. hello, price")
        if shortcut:
            self.shortcut_input.setReadOnly(True)
            self.shortcut_input.setStyleSheet("background-color: #E2E8F0; color: #64748B;")
        layout.addWidget(self.shortcut_input)

        layout.addWidget(QLabel("Reply Message:"))
        self.message_input = QTextEdit()
        self.message_input.setPlainText(message)
        layout.addWidget(self.message_input)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #F1F5F9; color: #64748B;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("background-color: #2563EB; color: #FFFFFF;")
        save_btn.clicked.connect(self.validate_and_accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def validate_and_accept(self):
        sc = self.shortcut_input.text().strip().replace("/", "")
        msg = self.message_input.toPlainText().strip()
        if not sc or not msg:
            QMessageBox.warning(self, "Validation Error", "Both fields are required.")
            return
        self.shortcut_text = sc
        self.message_text = msg
        self.accept()


class QuickPopup(QWidget):
    reply_selected = Signal(str, str)

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget {
                background-color: #FFFFFF; color: #0F172A;
                font-family: 'Segoe UI'; border-radius: 12px; border: 1px solid #CBD5E1;
            }
            QLineEdit {
                background-color: #F8FAFC; border: 1px solid #E2E8F0;
                border-radius: 6px; padding: 6px 12px; font-size: 13px; color: #0F172A;
            }
            QLineEdit:focus { border: 1px solid #0F172A; }
            QListWidget { background-color: #FFFFFF; border: none; outline: none; font-size: 12px; }
            QListWidget::item {
                padding: 5px 8px; border-bottom: 1px solid #F1F5F9; border-radius: 4px;
            }
            QListWidget::item:selected { background-color: #F1F5F9; color: #0F172A; font-weight: bold; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        title_lbl = QLabel("⚡ Quick Replies Pro")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #0F172A; border: none;")
        esc_lbl = QLabel("Esc to close")
        esc_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; border: none;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(esc_lbl)
        layout.addLayout(header_layout)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type here to filter...")
        self.search_input.textChanged.connect(self.filter_list)
        self.search_input.returnPressed.connect(self.select_current_item)
        top_row.addWidget(self.search_input)

        self.add_btn = QPushButton("+ Add")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #0F172A; color: #FFFFFF; border: none;
                border-radius: 6px; padding: 6px 16px; font-weight: bold; font-size: 12px;
            }
            QPushButton:hover { background-color: #1E293B; }
        """)
        top_row.addWidget(self.add_btn)
        layout.addLayout(top_row)

        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.itemActivated.connect(self.select_current_item)
        layout.addWidget(self.list_widget)

        footer_lbl = QLabel("Interactive concept — select a result to copy its message.")
        footer_lbl.setStyleSheet("font-size: 10px; color: #94A3B8; border: none;")
        layout.addWidget(footer_lbl)

        self.populate_list("")

    def populate_list(self, query=""):
        self.list_widget.clear()

        if not query.strip():
            self.list_widget.hide()
            self.adjustSize()
            return

        self.list_widget.show()
        replies = self.db.get_all_replies()
        q = query.lower()
        match_count = 0
        for r in replies:
            if q in r["shortcut"].lower():
                clean_msg = r["message"].replace("\n", " ")
                display_str = f"/{r['shortcut']}: {clean_msg}"
                item = QListWidgetItem(display_str)
                item.setData(Qt.UserRole, r)
                self.list_widget.addItem(item)
                match_count += 1

        if match_count > 0:
            self.list_widget.setCurrentRow(0)
            self.list_widget.setFixedHeight(min(match_count * 28, 140))
        else:
            self.list_widget.setFixedHeight(30)

        self.adjustSize()

    def filter_list(self, text):
        self.populate_list(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Backspace and len(self.search_input.text()) == 0:
            self.close()
        elif event.key() == Qt.Key_Down:
            row = self.list_widget.currentRow()
            if row < self.list_widget.count() - 1:
                self.list_widget.setCurrentRow(row + 1)
        elif event.key() == Qt.Key_Up:
            row = self.list_widget.currentRow()
            if row > 0:
                self.list_widget.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(event)

    def select_current_item(self, item=None):
        if not item:
            item = self.list_widget.currentItem()
        if item:
            data = item.data(Qt.UserRole)
            shortcut = data["shortcut"]
            message = data["message"]
            self.db.increment_usage(shortcut)
            self.hide()

            pyperclip.copy(message)
            pyautogui.hotkey('ctrl', 'v')

            self.reply_selected.emit(shortcut, message)

    def showEvent(self, event):
        super().showEvent(event)
        self.search_input.clear()
        self.populate_list("")
        self.search_input.setFocus()

        screen = self.screen().geometry()
        self.move(
            int(screen.width() / 2 - self.width() / 2),
            int(screen.height() / 3 - self.height() / 2)
        )


class DashboardWindow(QMainWindow):
    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager
        self.setWindowTitle("Quick Replies Pro - Dashboard")
        self.resize(750, 480)
        self.setStyleSheet("""
            QMainWindow { background-color: #F8FAFC; font-family: 'Segoe UI'; color: #0F172A; }
            QLabel { color: #0F172A; }
            QPushButton { font-family: 'Segoe UI'; border-radius: 6px; font-weight: bold; border: none; padding: 6px 12px; }
            QTableWidget {
                background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px;
                gridline-color: #F1F5F9; font-size: 12px; color: #0F172A; outline: none;
            }
            QHeaderView::section {
                background-color: #F8FAFC; color: #64748B; font-weight: bold; border: none;
                border-bottom: 1px solid #E2E8F0; padding: 8px; font-size: 11px;
            }
            QLineEdit {
                background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px;
                padding: 6px 10px; font-size: 12px; color: #0F172A;
            }
            QLineEdit:focus { border: 1px solid #2563EB; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(12)

        top_bar = QHBoxLayout()
        title_container = QVBoxLayout()
        title_lbl = QLabel("⚡ Quick Replies Pro")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #0F172A;")
        sub_lbl = QLabel("Manage your quick replies")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        title_container.addWidget(title_lbl)
        title_container.addWidget(sub_lbl)
        top_bar.addLayout(title_container)

        top_bar.addStretch()

        self.stats_lbl = QLabel()
        self.stats_lbl.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 6px 10px; font-size: 11px; font-weight: bold; color: #2563EB;")
        top_bar.addWidget(self.stats_lbl)

        main_layout.addLayout(top_bar)

        action_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search...")
        self.search_input.textChanged.connect(self.load_table_data)
        self.search_input.setFixedWidth(220)
        action_bar.addWidget(self.search_input)

        action_bar.addStretch()

        import_btn = QPushButton("Import")
        import_btn.setStyleSheet("background-color: #FFFFFF; color: #475569; border: 1px solid #E2E8F0;")
        import_btn.clicked.connect(self.import_json)
        action_bar.addWidget(import_btn)

        export_btn = QPushButton("Export")
        export_btn.setStyleSheet("background-color: #FFFFFF; color: #475569; border: 1px solid #E2E8F0;")
        export_btn.clicked.connect(self.export_json)
        action_bar.addWidget(export_btn)

        add_btn = QPushButton("+ New")
        add_btn.setStyleSheet("background-color: #0F172A; color: #FFFFFF;")
        add_btn.clicked.connect(self.add_reply_action)
        action_bar.addWidget(add_btn)

        main_layout.addLayout(action_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Shortcut", "Reply Message", "Uses", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        main_layout.addWidget(self.table)

        self.load_table_data()

    def load_table_data(self):
        query = self.search_input.text().lower()
        replies = self.db.get_all_replies()

        filtered = [r for r in replies if query in r["shortcut"].lower() or query in r["message"].lower()]

        self.table.setRowCount(len(filtered))
        total_uses = sum(r["usage_count"] for r in replies)
        self.stats_lbl.setText(f"Total: {len(replies)}  •  Uses: {total_uses}")

        for row_idx, r in enumerate(filtered):
            sc_item = QTableWidgetItem(f"/{r['shortcut']}")
            sc_item.setData(Qt.UserRole, r["shortcut"])
            self.table.setItem(row_idx, 0, sc_item)

            self.table.setItem(row_idx, 1, QTableWidgetItem(r["message"]))

            cnt_item = QTableWidgetItem(str(r["usage_count"]))
            cnt_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, cnt_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(4)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet("background-color: #EFF6FF; color: #2563EB; font-size: 10px; padding: 3px 6px;")
            edit_btn.clicked.connect(lambda checked, shortcut=r["shortcut"], msg=r["message"]: self.edit_reply_action(shortcut, msg))
            action_layout.addWidget(edit_btn)

            del_btn = QPushButton("Del")
            del_btn.setStyleSheet("background-color: #FEF2F2; color: #DC2626; font-size: 10px; padding: 3px 6px;")
            del_btn.clicked.connect(lambda checked, shortcut=r["shortcut"]: self.delete_reply_action(shortcut))
            action_layout.addWidget(del_btn)

            self.table.setCellWidget(row_idx, 3, action_widget)

    def add_reply_action(self):
        dlg = EditReplyDialog(self)
        dlg.setWindowIcon(self.windowIcon())
        if dlg.exec():
            self.db.add_reply(dlg.shortcut_text, dlg.message_text)
            self.load_table_data()

    def edit_reply_action(self, shortcut, message):
        dlg = EditReplyDialog(self, shortcut, message)
        dlg.setWindowIcon(self.windowIcon())
        if dlg.exec():
            self.db.update_reply(dlg.shortcut_text, dlg.message_text)
            self.load_table_data()

    def delete_reply_action(self, shortcut):
        confirm = QMessageBox.question(self, "Confirm Delete", f"Delete '/{shortcut}'?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            self.db.delete_reply(shortcut)
            self.load_table_data()

    def export_json(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Export", "replies.json", "JSON Files (*.json)")
        if filepath:
            self.db.export_to_json(filepath)

    def import_json(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON Files (*.json)")
        if filepath:
            try:
                self.db.import_from_json(filepath)
                self.load_table_data()
                QMessageBox.information(self, "Success", "Quick replies imported successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to import JSON: {e}")


class QuickRepliesApp:
    def __init__(self):
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        self.app_icon = self.create_lightning_icon()
        self.qt_app.setWindowIcon(self.app_icon)

        self.db = DatabaseManager()

        self.dashboard = DashboardWindow(self.db)
        self.dashboard.setWindowIcon(self.app_icon)

        self.popup = QuickPopup(self.db)
        self.popup.setWindowIcon(self.app_icon)
        self.popup.add_btn.clicked.connect(self.open_dashboard_from_popup)

        self.engine = ShortcutEngine(self.db)
        self.engine.open_popup_signal.connect(self.trigger_popup_safe)
        self.engine.start()

        self.setup_tray()

    def create_lightning_icon(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        painter.setPen(QColor("#F59E0B"))
        font = QFont("Segoe UI Emoji", 32)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "⚡")
        painter.end()
        return QIcon(pixmap)

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(self.app_icon)
        self.tray_icon.setToolTip("Quick Replies Pro")

        tray_menu = QMenu()
        dash_action = QAction("Dashboard", tray_menu)
        dash_action.triggered.connect(self.show_dashboard)
        tray_menu.addAction(dash_action)

        tray_menu.addSeparator()
        exit_action = QAction("Exit", tray_menu)
        exit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_popup()

    def trigger_popup_safe(self):
        QTimer.singleShot(0, self.toggle_popup)

    def toggle_popup(self):
        if self.popup.isVisible():
            self.popup.hide()
        else:
            self.popup.show()
            self.popup.raise_()
            self.popup.activateWindow()

    def show_dashboard(self):
        self.dashboard.load_table_data()
        self.dashboard.show()
        self.dashboard.raise_()
        self.dashboard.activateWindow()

    def open_dashboard_from_popup(self):
        self.popup.hide()
        self.show_dashboard()

    def quit_app(self):
        self.engine.stop()
        self.tray_icon.hide()
        sys.exit(0)

    def run(self):
        sys.exit(self.qt_app.exec())


if __name__ == "__main__":
    app = QuickRepliesApp()
    app.run()