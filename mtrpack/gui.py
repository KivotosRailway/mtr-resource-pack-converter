"""Small desktop front end around the same converter API."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .converter import ConvertError, convert, inspect_pack


def main():
    root = tk.Tk()
    root.title("MTR 3.2 ↔ 4.0 资源包转换器")
    root.geometry("740x460")
    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    variables = {key: tk.StringVar() for key in ("input", "output", "template", "map")}
    target = tk.StringVar(value="4.0")
    partial = tk.BooleanVar()

    def choose(key, output=False):
        if output:
            value = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("ZIP", "*.zip")])
        else:
            value = filedialog.askopenfilename(filetypes=[("ZIP / JSON", "*.zip *.json"), ("All", "*.*")])
        if value:
            variables[key].set(value)

    for row, (key, label) in enumerate((("input", "输入资源包 ZIP"), ("output", "输出 ZIP"),
                                         ("template", "4.0 车辆模板 JSON/ZIP"),
                                         ("map", "3.2 基础车型映射 JSON"))):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=6)
        ttk.Entry(frame, textvariable=variables[key]).grid(row=row, column=1, sticky="ew", padx=10)
        ttk.Button(frame, text="选择", command=lambda k=key: choose(k, k == "output")).grid(row=row, column=2)

    ttk.Label(frame, text="目标格式").grid(row=4, column=0, sticky="w", pady=10)
    ttk.Combobox(frame, values=("4.0", "3.2"), textvariable=target,
                 state="readonly", width=10).grid(row=4, column=1, sticky="w", padx=10)
    ttk.Checkbutton(frame, text="允许部分转换（会保留原始定义备份并生成报告）",
                    variable=partial).grid(row=5, column=0, columnspan=3, sticky="w")

    result = tk.Text(frame, height=9, wrap="word", state="disabled")
    result.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=12)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(7, weight=1)

    def show(data):
        result.configure(state="normal")
        result.delete("1.0", "end")
        result.insert("end", data)
        result.configure(state="disabled")

    def run():
        try:
            mapping = None
            if variables["map"].get():
                with open(variables["map"].get(), encoding="utf-8") as file:
                    mapping = json.load(file)
                if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                             for k, v in mapping.items()):
                    raise ConvertError("基础车型映射必须是字符串到字符串的 JSON 对象")
            report = convert(variables["input"].get(), variables["output"].get(), target=target.get(),
                             template=variables["template"].get() or None, base_map=mapping,
                             allow_partial=partial.get())
            show(json.dumps(report, ensure_ascii=False, indent=2))
            messagebox.showinfo("转换完成", "资源包和转换报告已写入输出目录。")
        except (ConvertError, OSError, ValueError) as exc:
            show(str(exc))
            messagebox.showerror("转换未完成", str(exc))

    ttk.Button(frame, text="检测输入", command=lambda: _inspect()).grid(row=6, column=0, sticky="w", pady=8)
    ttk.Button(frame, text="开始转换", command=run).grid(row=6, column=2, sticky="e", pady=8)

    def _inspect():
        try:
            show(json.dumps(inspect_pack(variables["input"].get()), ensure_ascii=False, indent=2))
        except (ConvertError, OSError) as exc:
            show(str(exc))

    root.mainloop()
