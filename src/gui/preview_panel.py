from __future__ import annotations
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# INI-style highlighting for GT3R car / mod / maker files
_RE_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[;#].*)?$")
_RE_COMMENT = re.compile(r"[;#].*$")
_RE_KV = re.compile(r"^(\s*)([^:=\s][^:=]*?)(\s*=\s*)(.*)$")
_RE_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_RE_NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?\b")


class PreviewPanel(ttk.Frame):
    def __init__(self, master, file_titles: dict[str, str]):
        super().__init__(master, padding=6)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.texts: dict[str, tk.Text] = {}
        self.names: dict[str, ttk.Label] = {}
        self.mode_btns: dict[str, ttk.Button] = {}
        self.editable: dict[str, bool] = {}
        self.ids = list(file_titles)
        for fid, title in file_titles.items():
            page = ttk.Frame(self.notebook, padding=4)
            page.columnconfigure(0, weight=1)
            page.rowconfigure(1, weight=1)

            bar = ttk.Frame(page)
            bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
            name = ttk.Label(bar, text="", foreground="#777777")
            name.pack(side="left")

            mode_btn = ttk.Button(
                bar, text="Make editable",
                command=lambda f=fid: self.toggle_editable(f),
            )
            mode_btn.pack(side="right")
            ttk.Button(bar, text="Save this file as…", command=lambda f=fid: self.save_one(f)).pack(
                side="right", padx=(0, 6))
            ttk.Button(bar, text="Copy", command=lambda f=fid: self.copy(f)).pack(side="right", padx=(0, 6))

            text = tk.Text(
                page, wrap="none", font=("Consolas", 11),
                state="disabled", undo=True, maxundo=100,
                background="#1e1e1e", foreground="#d4d4d4",
                insertbackground="#ffffff",
                selectbackground="#264f78",
                relief="flat", borderwidth=0,
                padx=8, pady=6,
            )
            self._configure_tags(text)
            ysb = ttk.Scrollbar(page, orient="vertical", command=text.yview)
            xsb = ttk.Scrollbar(page, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
            text.grid(row=1, column=0, sticky="nsew")
            ysb.grid(row=1, column=1, sticky="ns")
            xsb.grid(row=2, column=0, sticky="ew")

            # Re-highlight after edits when editable
            text.bind("<<Modified>>", lambda e, f=fid: self._on_modified(f))

            self.notebook.add(page, text=title)
            self.texts[fid] = text
            self.names[fid] = name
            self.mode_btns[fid] = mode_btn
            self.editable[fid] = False

    def _configure_tags(self, text: tk.Text) -> None:
        text.tag_configure("section", foreground="#569cd6", font=("Consolas", 11, "bold"))
        text.tag_configure("key", foreground="#9cdcfe")
        text.tag_configure("equals", foreground="#d4d4d4")
        text.tag_configure("value", foreground="#ce9178")
        text.tag_configure("number", foreground="#b5cea8")
        text.tag_configure("hex", foreground="#d7ba7d")
        text.tag_configure("comment", foreground="#6a9955")
        text.tag_configure("error", foreground="#f44747")

    def _highlight(self, text: tk.Text) -> None:
        content = text.get("1.0", "end-1c")
        for tag in ("section", "key", "equals", "value", "number", "hex", "comment", "error"):
            text.tag_remove(tag, "1.0", "end")

        for i, line in enumerate(content.splitlines(), start=1):
            start = f"{i}.0"
            # full-line comment
            stripped = line.lstrip()
            if stripped.startswith(";") or (
                stripped.startswith("#") and "=" not in stripped and "[" not in stripped
            ):
                text.tag_add("comment", start, f"{i}.end")
                continue

            sm = _RE_SECTION.match(line)
            if sm:
                text.tag_add("section", start, f"{i}.end")
                # comment after section header
                cm = _RE_COMMENT.search(line)
                if cm and cm.start() > 0:
                    text.tag_add("comment", f"{i}.{cm.start()}", f"{i}.end")
                continue

            km = _RE_KV.match(line)
            if km:
                indent, key, eq, rest = km.group(1), km.group(2), km.group(3), km.group(4)
                pos = len(indent)
                text.tag_add("key", f"{i}.{pos}", f"{i}.{pos + len(key)}")
                pos += len(key)
                text.tag_add("equals", f"{i}.{pos}", f"{i}.{pos + len(eq)}")
                pos += len(eq)
                val_start = pos
                # trailing comment on value line
                cm = _RE_COMMENT.search(rest)
                if cm:
                    val_part = rest[: cm.start()]
                    text.tag_add("value", f"{i}.{val_start}", f"{i}.{val_start + len(val_part)}")
                    text.tag_add("comment", f"{i}.{val_start + cm.start()}", f"{i}.end")
                    self._highlight_value_tokens(text, i, val_start, val_part)
                else:
                    text.tag_add("value", f"{i}.{val_start}", f"{i}.end")
                    self._highlight_value_tokens(text, i, val_start, rest)
                continue

            # bare comment or unknown
            cm = _RE_COMMENT.search(line)
            if cm:
                text.tag_add("comment", f"{i}.{cm.start()}", f"{i}.end")

    def _highlight_value_tokens(self, text: tk.Text, line: int, base: int, value: str) -> None:
        for m in _RE_HEX.finditer(value):
            text.tag_add("hex", f"{line}.{base + m.start()}", f"{line}.{base + m.end()}")
        for m in _RE_NUMBER.finditer(value):
            # don't recolour inside hex
            span = value[m.start(): m.end()]
            if span.startswith("#"):
                continue
            text.tag_add("number", f"{line}.{base + m.start()}", f"{line}.{base + m.end()}")

    def _on_modified(self, fid: str) -> None:
        text = self.texts[fid]
        if not text.edit_modified():
            return
        text.edit_modified(False)
        if self.editable.get(fid):
            self._highlight(text)

    def toggle_editable(self, fid: str) -> None:
        text = self.texts[fid]
        making_editable = not self.editable.get(fid, False)
        self.editable[fid] = making_editable
        if making_editable:
            text.configure(state="normal")
            self.mode_btns[fid].configure(text="Make read-only")
            self._highlight(text)
        else:
            text.configure(state="normal")
            self._highlight(text)
            text.configure(state="disabled")
            self.mode_btns[fid].configure(text="Make editable")

    def show(self, fid: str, content: str, rel_path: str | None) -> None:
        text = self.texts[fid]
        was_editable = self.editable.get(fid, False)
        # Preserve edit mode; only replace content when not mid-edit, or always refresh from forms
        text.configure(state="normal")
        yview = text.yview()
        text.delete("1.0", "end")
        text.insert("1.0", content)
        self._highlight(text)
        text.edit_modified(False)
        if not was_editable:
            text.configure(state="disabled")
        text.yview_moveto(yview[0])
        self.names[fid].configure(text=rel_path or "(file name not known yet)")
        self.mode_btns[fid].configure(text="Make read-only" if was_editable else "Make editable")

    def show_disabled(self, fid: str) -> None:
        self.editable[fid] = False
        self.show(fid, "", None)
        self.names[fid].configure(text="Not included in this mod.")
        self.mode_btns[fid].configure(text="Make editable")

    def content(self, fid: str) -> str:
        return self.texts[fid].get("1.0", "end-1c")

    def copy(self, fid: str):
        self.clipboard_clear()
        self.clipboard_append(self.content(fid))
        self.update()

    def save_one(self, fid: str):
        content = self.content(fid)
        if not content.strip():
            messagebox.showinfo("Nothing to save", "This file is not included in the mod.", parent=self)
            return
        initial = (self.names[fid].cget("text") or "file.ini").split("/")[-1]
        path = filedialog.asksaveasfilename(
            title="Save .ini", defaultextension=".ini",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")],
            initialfile=initial, parent=self,
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(content)
            except OSError as exc:
                messagebox.showerror("Save failed", str(exc), parent=self)
