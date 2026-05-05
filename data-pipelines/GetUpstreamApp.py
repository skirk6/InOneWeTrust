#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 19 10:53:11 2025

@author: skirk
"""

import pandas as pd
from datetime import datetime
import platform
import traceback
import sys

# ---------------------------------------------------------------------------
# GUI backend detection — try tkinter first, fall back to PyQt5
#
# tkcalendar is a separate pip package: install it automatically if tkinter
# itself is present but tkcalendar is missing.  Only fall back to PyQt5 when
# the tkinter stdlib module is genuinely unavailable on this Python install.
# ---------------------------------------------------------------------------
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk, simpledialog
    try:
        from tkcalendar import DateEntry
    except ImportError:
        import subprocess
        print("tkcalendar not found — attempting install...")
        installed = False
        for pip_args in (
            [sys.executable, "-m", "pip", "install", "--user", "tkcalendar"],
            [sys.executable, "-m", "pip", "install", "tkcalendar"],
        ):
            try:
                subprocess.check_call(pip_args)
                installed = True
                break
            except subprocess.CalledProcessError:
                continue
        if installed:
            from tkcalendar import DateEntry
        else:
            print("tkcalendar install failed — falling back to PyQt5.")
            raise ImportError("tkcalendar unavailable")
    GUI_BACKEND = 'tkinter'
except ImportError:
    GUI_BACKEND = 'pyqt5'

# ---------------------------------------------------------------------------
# Global variables
# ---------------------------------------------------------------------------
DF1 = pd.DataFrame()
STARTDATE = None
ENDDATE = None

FONT_NAME = "Helvetica" if platform.system() == "Sequoia" else "Wells Fargo Sans"
BUTTON_FONT = (FONT_NAME, 10)
DEFAULT_SIZE = "800x700"

# ===========================================================================
# TKINTER IMPLEMENTATION
# ===========================================================================
if GUI_BACKEND == 'tkinter':

    class CustomDateEntry(DateEntry):
        def __init__(self, master=None, **kwargs):
            super().__init__(master, **kwargs)
            self._default_date = self.get_date()
            self.delete(0, tk.END)

        def get_date_if_set(self):
            if not self.get():
                return None
            return super().get_date()

    class GetUpstreamApp(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("Get Upstream App")
            self.geometry(DEFAULT_SIZE)
            self.minsize(800, 600)
            self.resizable(True, True)

            self.file_path = None
            self.df = None

            self.option_add("*Font", BUTTON_FONT)
            self.protocol("WM_DELETE_WINDOW", self.exit_app)
            self.create_widgets()

        def create_widgets(self):
            file_frame = ttk.LabelFrame(self, text="Import Excel File")
            file_frame.pack(fill="x", padx=10, pady=5)

            ttk.Button(file_frame, text="Browse", command=self.browse_file, width=10).pack(side="left", padx=10, pady=5)
            self.sheet_selector = ttk.Combobox(file_frame, state="readonly")
            self.sheet_selector.pack(side="left", padx=10, pady=5)
            self.sheet_selector.bind("<<ComboboxSelected>>", self.load_sheet)

            date_frame = ttk.LabelFrame(self, text="Select Date Range")
            date_frame.pack(fill="x", padx=10, pady=5)

            ttk.Label(date_frame, text="Start Date:").pack(side="left", padx=5)
            self.start_date_entry = CustomDateEntry(date_frame, date_pattern='yyyy-mm-dd')
            self.start_date_entry.pack(side="left", padx=5)

            ttk.Label(date_frame, text="End Date:").pack(side="left", padx=5)
            self.end_date_entry = CustomDateEntry(date_frame, date_pattern='yyyy-mm-dd')
            self.end_date_entry.pack(side="left", padx=5)

            ttk.Button(date_frame, text="Set Dates", command=self.set_dates, width=10).pack(side="left", padx=5)

            column_frame = ttk.LabelFrame(self, text="Select Column(s)")
            column_frame.pack(fill="x", padx=10, pady=5)

            self.column_selector = tk.Listbox(column_frame, selectmode="multiple", exportselection=0, height=5)
            self.column_selector.pack(side="left", padx=10, pady=5)
            self.column_selector.bind("<<ListboxSelect>>", self.display_unique_values)

            self.column_rename_entry = ttk.Entry(column_frame)
            self.column_rename_entry.pack(side="left", padx=5)
            ttk.Button(column_frame, text="Rename Column", command=self.rename_column, width=10).pack(side="left", padx=5)

            values_frame = ttk.LabelFrame(self, text="Unique Column Values")
            values_frame.pack(fill="both", expand=True, padx=10, pady=5)

            self.text_display = tk.Text(values_frame, wrap="word")
            self.text_display.pack(fill="both", expand=True)

            action_frame = ttk.Frame(self)
            action_frame.pack(fill="x", padx=10, pady=10)

            ttk.Button(action_frame, text="Set DF1", command=self.set_df1, width=10).pack(side="left", padx=5)
            ttk.Button(action_frame, text="Clear", command=self.clear_all, width=10).pack(side="left", padx=5)
            ttk.Button(action_frame, text="Exit", command=self.exit_app, width=10).pack(side="left", padx=5)

        def browse_file(self):
            try:
                self.file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
                if self.file_path:
                    xls = pd.ExcelFile(self.file_path)
                    self.sheet_selector['values'] = xls.sheet_names
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to browse file: {e}")

        def load_sheet(self, event):
            try:
                sheet = self.sheet_selector.get()
                self.df = pd.read_excel(self.file_path, sheet_name=sheet)
                self.column_selector.delete(0, tk.END)
                for col in self.df.columns:
                    self.column_selector.insert(tk.END, col)
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to load sheet: {e}")

        def display_unique_values(self, event):
            try:
                selection = self.column_selector.curselection()
                if not selection or self.df is None:
                    return
                self.text_display.delete("1.0", tk.END)
                for index in selection:
                    col = self.column_selector.get(index)
                    unique_values = self.df[col].dropna().unique()
                    self.text_display.insert(tk.END, f"{col} Unique Values:\n")
                    for val in unique_values:
                        self.text_display.insert(tk.END, f"{val}\n")
                    self.text_display.insert(tk.END, "\n")
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Unable to display unique values: {e}")

        def rename_column(self):
            try:
                if self.df is None:
                    messagebox.showwarning("Warning", "No spreadsheet loaded.")
                    return

                selection = self.column_selector.curselection()
                if not selection:
                    messagebox.showwarning("Warning", "Please select at least one column to rename.")
                    return

                new_name = self.column_rename_entry.get().strip()
                if not new_name:
                    new_name = simpledialog.askstring("Rename Column", "Enter new header name(s) (comma-separated):")

                if new_name:
                    new_names = [n.strip().replace(" ", "_") for n in new_name.split(",")]
                    if len(new_names) != len(selection):
                        messagebox.showwarning("Invalid Input", "Number of new names must match number of selected columns.")
                        return
                    for idx, new_col in zip(selection, new_names):
                        old_name = self.column_selector.get(idx)
                        if old_name in self.df.columns:
                            self.df.rename(columns={old_name: new_col}, inplace=True)
                    self.column_selector.delete(0, tk.END)
                    for col in self.df.columns:
                        self.column_selector.insert(tk.END, col)
                    messagebox.showinfo("Renamed", "Column(s) renamed successfully.")
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to rename column(s): {e}")

        def set_df1(self):
            global DF1
            try:
                selection = self.column_selector.curselection()
                if self.df is not None and not self.df.empty and selection:
                    selected_columns = [self.column_selector.get(i) for i in selection]
                    df_trimmed = self.df[selected_columns].copy()
                    for col in df_trimmed.select_dtypes(include='object').columns:
                        df_trimmed[col] = df_trimmed[col].astype(str).str.strip()
                    DF1 = df_trimmed
                    messagebox.showinfo("Success", "DF1 has been set globally using selected columns. You can now use DF1 in your session.")
                else:
                    messagebox.showwarning("Warning", "No data or columns selected to set as DF1.")
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to set DF1: {e}")

        def set_dates(self):
            global STARTDATE, ENDDATE
            try:
                STARTDATE = self.start_date_entry.get_date_if_set()
                ENDDATE = self.end_date_entry.get_date_if_set()

                if (STARTDATE and not ENDDATE) or (ENDDATE and not STARTDATE):
                    messagebox.showwarning("Missing Date", "Both STARTDATE and ENDDATE must be selected.")
                    return

                if STARTDATE and ENDDATE and STARTDATE > ENDDATE:
                    messagebox.showwarning("Invalid Range", "STARTDATE cannot be after ENDDATE.")
                    return

                if STARTDATE and ENDDATE:
                    messagebox.showinfo("Dates Set", f"STARTDATE: {STARTDATE}\nENDDATE: {ENDDATE}")
                else:
                    messagebox.showinfo("Dates Set", "No dates selected.")
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to set dates: {e}")

        def clear_all(self):
            try:
                self.geometry(DEFAULT_SIZE)
                self.file_path = None
                self.df = None
                self.sheet_selector.set("")
                self.sheet_selector['values'] = []
                self.column_selector.delete(0, tk.END)
                self.column_rename_entry.delete(0, tk.END)
                self.text_display.delete("1.0", tk.END)
                self.start_date_entry.delete(0, tk.END)
                self.end_date_entry.delete(0, tk.END)
                global DF1, STARTDATE, ENDDATE
                DF1 = pd.DataFrame()
                STARTDATE = None
                ENDDATE = None
                messagebox.showinfo("Cleared", "Application state has been reset.")
            except Exception as e:
                traceback.print_exc()
                messagebox.showerror("Error", f"Failed to clear data: {e}")

        def exit_app(self):
            try:
                self.destroy()
            except Exception:
                traceback.print_exc()

# ===========================================================================
# PYQT5 IMPLEMENTATION
# ===========================================================================
else:
    import os
    _has_display = bool(
        os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')
    )
    if not _has_display:
        print(
            "\nError: tkinter/tkcalendar is unavailable and no GUI display was found "
            "(DISPLAY and WAYLAND_DISPLAY are both unset).\n\n"
            "Fix options:\n"
            "  [Recommended] Install tkcalendar via apt:\n"
            "      sudo apt install python3-tkcalendar\n\n"
            "  [Alternative] Set your display before running:\n"
            "      export DISPLAY=:0\n\n"
            "  [SSH] Enable X11 forwarding:\n"
            "      ssh -X user@host"
        )
        sys.exit(1)

    def _ensure_pyqt5():
        try:
            from PyQt5 import QtWidgets  # noqa: F401
        except ImportError:
            import subprocess
            print("PyQt5 not found — installing...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "PyQt5"])
            print("PyQt5 installed successfully.")

    _ensure_pyqt5()

    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget,
        QVBoxLayout, QHBoxLayout,
        QGroupBox, QPushButton, QComboBox, QListWidget,
        QTextEdit, QLineEdit, QLabel,
        QFileDialog, QMessageBox, QInputDialog, QDateEdit,
    )
    from PyQt5.QtCore import QDate, Qt

    class ClearableDateEdit(QDateEdit):
        """QDateEdit that treats its minimum date as 'no date selected'."""

        _EMPTY = QDate(1900, 1, 1)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setCalendarPopup(True)
            self.setDisplayFormat("yyyy-MM-dd")
            self.setMinimumDate(self._EMPTY)
            self.setSpecialValueText(" ")  # blank display when at minimum
            self.setDate(self._EMPTY)

        def get_date_if_set(self):
            if self.date() == self._EMPTY:
                return None
            return self.date().toPyDate()

        def clear_date(self):
            self.setDate(self._EMPTY)

    class GetUpstreamApp(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Get Upstream App")
            self.resize(800, 700)
            self.setMinimumSize(800, 600)

            self.file_path = None
            self.df = None

            central = QWidget()
            self.setCentralWidget(central)
            self.main_layout = QVBoxLayout(central)

            self.create_widgets()

        def create_widgets(self):
            # --- File import ---
            file_group = QGroupBox("Import Excel File")
            file_layout = QHBoxLayout()

            browse_btn = QPushButton("Browse")
            browse_btn.setFixedWidth(80)
            browse_btn.clicked.connect(self.browse_file)
            file_layout.addWidget(browse_btn)

            self.sheet_selector = QComboBox()
            self.sheet_selector.currentIndexChanged.connect(self.load_sheet)
            file_layout.addWidget(self.sheet_selector)
            file_layout.addStretch()

            file_group.setLayout(file_layout)
            self.main_layout.addWidget(file_group)

            # --- Date range ---
            date_group = QGroupBox("Select Date Range")
            date_layout = QHBoxLayout()

            date_layout.addWidget(QLabel("Start Date:"))
            self.start_date_entry = ClearableDateEdit()
            date_layout.addWidget(self.start_date_entry)

            date_layout.addWidget(QLabel("End Date:"))
            self.end_date_entry = ClearableDateEdit()
            date_layout.addWidget(self.end_date_entry)

            set_dates_btn = QPushButton("Set Dates")
            set_dates_btn.setFixedWidth(80)
            set_dates_btn.clicked.connect(self.set_dates)
            date_layout.addWidget(set_dates_btn)
            date_layout.addStretch()

            date_group.setLayout(date_layout)
            self.main_layout.addWidget(date_group)

            # --- Column selection ---
            column_group = QGroupBox("Select Column(s)")
            column_layout = QHBoxLayout()

            self.column_selector = QListWidget()
            self.column_selector.setSelectionMode(QListWidget.MultiSelection)
            self.column_selector.setFixedHeight(100)
            self.column_selector.itemSelectionChanged.connect(self.display_unique_values)
            column_layout.addWidget(self.column_selector)

            self.column_rename_entry = QLineEdit()
            column_layout.addWidget(self.column_rename_entry)

            rename_btn = QPushButton("Rename Column")
            rename_btn.clicked.connect(self.rename_column)
            column_layout.addWidget(rename_btn)

            column_group.setLayout(column_layout)
            self.main_layout.addWidget(column_group)

            # --- Unique values ---
            values_group = QGroupBox("Unique Column Values")
            values_layout = QVBoxLayout()

            self.text_display = QTextEdit()
            self.text_display.setReadOnly(True)
            values_layout.addWidget(self.text_display)

            values_group.setLayout(values_layout)
            self.main_layout.addWidget(values_group)

            # --- Action buttons ---
            action_widget = QWidget()
            action_layout = QHBoxLayout()

            for label, slot in [("Set DF1", self.set_df1), ("Clear", self.clear_all), ("Exit", self.exit_app)]:
                btn = QPushButton(label)
                btn.setFixedWidth(80)
                btn.clicked.connect(slot)
                action_layout.addWidget(btn)

            action_layout.addStretch()
            action_widget.setLayout(action_layout)
            self.main_layout.addWidget(action_widget)

        def browse_file(self):
            try:
                file_path, _ = QFileDialog.getOpenFileName(
                    self, "Open Excel File", "", "Excel files (*.xlsx *.xls)"
                )
                if file_path:
                    self.file_path = file_path
                    xls = pd.ExcelFile(file_path)
                    self.sheet_selector.blockSignals(True)
                    self.sheet_selector.clear()
                    self.sheet_selector.addItems(xls.sheet_names)
                    self.sheet_selector.blockSignals(False)
                    if xls.sheet_names:
                        self.load_sheet(0)
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to browse file: {e}")

        def load_sheet(self, index):
            try:
                sheet = self.sheet_selector.currentText()
                if not sheet or not self.file_path:
                    return
                self.df = pd.read_excel(self.file_path, sheet_name=sheet)
                self.column_selector.clear()
                for col in self.df.columns:
                    self.column_selector.addItem(str(col))
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to load sheet: {e}")

        def display_unique_values(self):
            try:
                selected_items = self.column_selector.selectedItems()
                if not selected_items or self.df is None:
                    return
                self.text_display.clear()
                for item in selected_items:
                    col = item.text()
                    unique_values = self.df[col].dropna().unique()
                    self.text_display.append(f"{col} Unique Values:")
                    for val in unique_values:
                        self.text_display.append(str(val))
                    self.text_display.append("")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Unable to display unique values: {e}")

        def rename_column(self):
            try:
                if self.df is None:
                    QMessageBox.warning(self, "Warning", "No spreadsheet loaded.")
                    return

                selected_items = self.column_selector.selectedItems()
                if not selected_items:
                    QMessageBox.warning(self, "Warning", "Please select at least one column to rename.")
                    return

                new_name = self.column_rename_entry.text().strip()
                if not new_name:
                    new_name, ok = QInputDialog.getText(
                        self, "Rename Column", "Enter new header name(s) (comma-separated):"
                    )
                    if not ok:
                        return

                if new_name:
                    new_names = [n.strip().replace(" ", "_") for n in new_name.split(",")]
                    if len(new_names) != len(selected_items):
                        QMessageBox.warning(self, "Invalid Input", "Number of new names must match number of selected columns.")
                        return
                    for item, new_col in zip(selected_items, new_names):
                        old_name = item.text()
                        if old_name in self.df.columns:
                            self.df.rename(columns={old_name: new_col}, inplace=True)
                    self.column_selector.clear()
                    for col in self.df.columns:
                        self.column_selector.addItem(str(col))
                    QMessageBox.information(self, "Renamed", "Column(s) renamed successfully.")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to rename column(s): {e}")

        def set_df1(self):
            global DF1
            try:
                selected_items = self.column_selector.selectedItems()
                if self.df is not None and not self.df.empty and selected_items:
                    selected_columns = [item.text() for item in selected_items]
                    df_trimmed = self.df[selected_columns].copy()
                    for col in df_trimmed.select_dtypes(include='object').columns:
                        df_trimmed[col] = df_trimmed[col].astype(str).str.strip()
                    DF1 = df_trimmed
                    QMessageBox.information(self, "Success", "DF1 has been set globally using selected columns. You can now use DF1 in your session.")
                else:
                    QMessageBox.warning(self, "Warning", "No data or columns selected to set as DF1.")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to set DF1: {e}")

        def set_dates(self):
            global STARTDATE, ENDDATE
            try:
                STARTDATE = self.start_date_entry.get_date_if_set()
                ENDDATE = self.end_date_entry.get_date_if_set()

                if (STARTDATE and not ENDDATE) or (ENDDATE and not STARTDATE):
                    QMessageBox.warning(self, "Missing Date", "Both STARTDATE and ENDDATE must be selected.")
                    return

                if STARTDATE and ENDDATE and STARTDATE > ENDDATE:
                    QMessageBox.warning(self, "Invalid Range", "STARTDATE cannot be after ENDDATE.")
                    return

                if STARTDATE and ENDDATE:
                    QMessageBox.information(self, "Dates Set", f"STARTDATE: {STARTDATE}\nENDDATE: {ENDDATE}")
                else:
                    QMessageBox.information(self, "Dates Set", "No dates selected.")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to set dates: {e}")

        def clear_all(self):
            try:
                self.resize(800, 700)
                self.file_path = None
                self.df = None
                self.sheet_selector.blockSignals(True)
                self.sheet_selector.clear()
                self.sheet_selector.blockSignals(False)
                self.column_selector.clear()
                self.column_rename_entry.clear()
                self.text_display.clear()
                self.start_date_entry.clear_date()
                self.end_date_entry.clear_date()
                global DF1, STARTDATE, ENDDATE
                DF1 = pd.DataFrame()
                STARTDATE = None
                ENDDATE = None
                QMessageBox.information(self, "Cleared", "Application state has been reset.")
            except Exception as e:
                traceback.print_exc()
                QMessageBox.critical(self, "Error", f"Failed to clear data: {e}")

        def exit_app(self):
            try:
                self.close()
            except Exception:
                traceback.print_exc()

        def closeEvent(self, event):
            event.accept()

# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == '__main__':
    if GUI_BACKEND == 'tkinter':
        app = GetUpstreamApp()
        app.lift()
        app.mainloop()
    else:
        qt_app = QApplication(sys.argv)
        window = GetUpstreamApp()
        window.show()
        sys.exit(qt_app.exec_())
