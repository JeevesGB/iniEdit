from __future__ import annotations
import tkinter as tk

DELAY_MS = 550

class ToolTip:
    def __init__(self, widget, text: str, wrap: int = 320):
        self.widget, self.text, self.wrap = widget, text, wrap
        self._after: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        if self.text:
            self._after = self.widget.after(DELAY_MS, self._show)

    def _show(self):
        self._after = None
        try:
            x = self.widget.winfo_pointerx() + 14
            y = self.widget.winfo_pointery() + 18
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_attributes("-topmost", True)
            tk.Label(tip, text=self.text, justify="left", wraplength=self.wrap, background="#FFFFE1",
                     foreground="#000000", relief="solid", borderwidth=1, padx=5, pady=3).pack()
            tip.wm_geometry(f"+{x}+{y}")
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _hide(self, _event=None):
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

def attach(widget, text: str) -> ToolTip:
    return ToolTip(widget, text)

def attach_by_text(root, tips: dict[str, str]) -> None:
    stack = [root]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        try:
            text = str(w.cget("text")).strip()
        except tk.TclError:
            continue
        if text in tips:
            ToolTip(w, tips[text])
