#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jun 19 10:53:11 2025

@author: skirk
"""

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from tkcalendar import DateEntry
from datetime import datetime
import platform
import traceback

# Global variables
DF1 = pd.DataFrame()
STARTDATE = None
ENDDATE = None

FONT_NAME = "Helvetica" if platform.system() == "Sequoia" else "Wells Fargo Sans"
BUTTON_FONT = (FONT_NAME, 10)
DEFAULT_SIZE = "800x700"

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
        except Exception as e:
            traceback.print_exc()

if __name__ == '__main__':
    app = GetUpstreamApp()
    app.lift()  # Bring window to front on macOS
    app.mainloop()
