"""Look and feel: a Windows XP "Luna" style for ttk, DPI awareness, and scaling helpers."""
from __future__ import annotations
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import matplotlib

THEMES = {"xp": "Windows XP (Luna)", "system": "System default"}
SCALE = 1.0

BG = "#ECE9D8"          # the classic beige window colour
FACE = "#F4F3EE"
BLUE, BLUE_DARK, ORANGE = "#316AC5", "#003C74", "#F8B330"
FIELD_BORDER, GROUP_BORDER, GROUP_TITLE = "#7F9DB9", "#D0D0BF", "#0046D5"
_original: dict = {}


def enable_dpi_awareness() -> None:
    """Call before the first Tk window is created (Windows only)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def px(value: float) -> int:
    return int(round(value * SCALE))


def init_scale(root: tk.Tk) -> float:
    global SCALE
    try:
        SCALE = max(1.0, min(3.0, root.winfo_fpixels("1i") / 96.0))
    except tk.TclError:
        SCALE = 1.0
    if SCALE > 1.01 and not getattr(ttk.Treeview, "_scaled", False):      # table columns are set in pixels
        original = ttk.Treeview.column

        def column(self, column, option=None, **kw):
            for key in ("width", "minwidth"):
                if key in kw:
                    kw[key] = px(kw[key])
            return original(self, column, option, **kw)

        ttk.Treeview.column = column
        ttk.Treeview._scaled = True
    return SCALE


def _font_face(root) -> str:
    families = set(tkfont.families(root))
    for name in ("Tahoma", "Segoe UI", "Verdana", "DejaVu Sans"):
        if name in families:
            return name
    return tkfont.nametofont("TkDefaultFont", root).actual("family")


def apply(root: tk.Tk, name: str) -> None:
    style = ttk.Style(root)
    if not _original:
        _original["theme"] = style.theme_use()
        _original["fonts"] = {n: tkfont.nametofont(n, root).actual() for n in
                              ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont")}
        _original["fig"] = matplotlib.rcParams["figure.facecolor"]
    if name != "xp":
        style.theme_use(_original["theme"])
        for n, spec in _original["fonts"].items():
            tkfont.nametofont(n, root).configure(**spec)
        root.configure(background=style.lookup("TFrame", "background") or root.cget("background"))
        matplotlib.rcParams["figure.facecolor"] = _original["fig"]
        _install_wheel_guard(root)
        return

    face = _font_face(root)
    for n in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(n, root).configure(family=face, size=9)
    style.theme_use("clam")
    root.configure(background=BG)
    root.option_add("*Menu.background", BG)
    root.option_add("*Menu.activeBackground", BLUE)
    root.option_add("*Menu.activeForeground", "white")
    root.option_add("*Text.background", "white")
    root.option_add("*Text.selectBackground", BLUE)
    root.option_add("*Listbox.selectBackground", BLUE)
    root.option_add("*TCombobox*Listbox.selectBackground", BLUE)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    root.option_add("*TCombobox*Listbox.background", "white")

    c = style.configure
    m = style.map
    c(".", background=BG, foreground="#000000", fieldbackground="white", troughcolor="#F3F2EA",
      bordercolor=GROUP_BORDER, lightcolor="white", darkcolor=GROUP_BORDER, focuscolor=BG,
      selectbackground=BLUE, selectforeground="white", insertcolor="black")
    m(".", foreground=[("disabled", "#ACA899")])

    c("TButton", background=FACE, bordercolor=BLUE_DARK, lightcolor="white", darkcolor="#D6D0C5",
      relief="raised", borderwidth=1, padding=(px(10), px(3)), anchor="center", focuscolor=FACE)
    m("TButton",
      background=[("pressed", "#E3E0D3"), ("disabled", "#F4F3EE"), ("active", "#FFF8E5")],
      bordercolor=[("disabled", "#C9C7BA")],
      lightcolor=[("pressed", "#D6D0C5"), ("active", "#FFF0CF")],
      darkcolor=[("pressed", "#FFFFFF"), ("active", ORANGE)],
      relief=[("pressed", "sunken")])
    c("Toolbutton", padding=px(3))

    for entry in ("TEntry", "TSpinbox", "TCombobox"):
        c(entry, fieldbackground="white", bordercolor=FIELD_BORDER, lightcolor="white", darkcolor=FIELD_BORDER,
          padding=px(2), selectbackground=BLUE, selectforeground="white")
        m(entry, bordercolor=[("focus", BLUE), ("disabled", "#C9C7BA")],
          fieldbackground=[("disabled", "#F4F3EE"), ("readonly", "white")],
          foreground=[("disabled", "#ACA899")])
    c("TCombobox", arrowcolor="#4D6185", background="#C1D2EE", arrowsize=px(14))
    m("TCombobox", background=[("active", "#B0C9F4"), ("pressed", "#9DB9EB")],
      selectbackground=[("readonly", "white")], selectforeground=[("readonly", "black")])
    c("TSpinbox", arrowcolor="#4D6185", background="#C1D2EE", arrowsize=px(12))
    m("TSpinbox", background=[("active", "#B0C9F4")])

    for check in ("TCheckbutton", "TRadiobutton"):
        c(check, indicatorbackground="white", indicatorforeground="#21A121", indicatormargin=px(3))
        m(check, indicatorbackground=[("disabled", "#F4F3EE")], background=[("active", BG)])

    c("TLabelframe", background=BG, bordercolor=GROUP_BORDER, lightcolor=BG, darkcolor=BG, relief="solid")
    c("TLabelframe.Label", background=BG, foreground=GROUP_TITLE)

    c("TNotebook", background=BG, bordercolor="#919B9C", lightcolor="white", darkcolor="#919B9C",
      tabmargins=(px(2), px(4), px(2), 0))
    c("TNotebook.Tab", background="#F1EFE2", foreground="#000000", bordercolor="#919B9C",
      lightcolor="white", darkcolor="#D6D2C2", padding=(px(9), px(3)))
    m("TNotebook.Tab",
      background=[("selected", "#FCFCFE"), ("active", "#FFF3D1")],
      lightcolor=[("selected", "#F8A830"), ("active", ORANGE)],
      expand=[("selected", (px(1), px(2), px(1), 0))])

    c("Treeview", background="white", fieldbackground="white", bordercolor=FIELD_BORDER, rowheight=px(20),
      lightcolor="white", darkcolor=FIELD_BORDER)
    m("Treeview", background=[("selected", BLUE)], foreground=[("selected", "white")])
    c("Treeview.Heading", background="#EBEADB", foreground="#000000", bordercolor="#C5C2B8",
      lightcolor="white", darkcolor="#D6D2C2", relief="raised", padding=(px(4), px(3)))
    m("Treeview.Heading", background=[("active", "#FFF3D1")])

    for orient in ("Vertical", "Horizontal"):
        c(f"{orient}.TScrollbar", background="#C1D2EE", troughcolor="#F3F2EA", bordercolor="#98B3E3",
          lightcolor="#E3ECFC", darkcolor="#98B3E3", arrowcolor="#4D6185", arrowsize=px(15), gripcount=0)
        m(f"{orient}.TScrollbar", background=[("active", "#B0C9F4"), ("pressed", "#9DB9EB")])
    c("Sash", sashthickness=px(6), gripcount=0, background=BG)
    c("TPanedwindow", background=BG)
    c("TSeparator", background="#C5C2B8")
    c("TProgressbar", background="#3EB43E", troughcolor="white", bordercolor=FIELD_BORDER)

    matplotlib.rcParams["figure.facecolor"] = BG
    _install_wheel_guard(root)


def restyle_figures(*panels) -> None:
    """Make already-created matplotlib figures follow the current theme."""
    colour = matplotlib.rcParams["figure.facecolor"]
    for panel in panels:
        fig = getattr(panel, "figure", None)
        if fig is not None:
            fig.set_facecolor(colour)
            panel.canvas.draw_idle()


def restyle_canvases(widget) -> None:
    """Plain tk Canvases (scrolling forms) don't follow ttk styles; recolour them."""
    colour = ttk.Style(widget).lookup("TFrame", "background") or BG
    stack = [widget]
    while stack:
        w = stack.pop()
        stack.extend(w.winfo_children())
        if w.winfo_class() == "Canvas" and getattr(w, "_themed", True) and not hasattr(w, "get_tk_widget"):
            try:
                if w.cget("highlightthickness") == 0 and not w.cget("relief") == "solid":
                    w.configure(background=colour)
            except tk.TclError:
                pass


def _install_wheel_guard(root) -> None:
    """Scrolling the wheel over a drop-down must scroll the form, not silently change its value."""
    def guard(event):
        from gui import parameter_form
        scroll = parameter_form.ACTIVE_SCROLL
        if scroll is not None:
            scroll(event)
        return "break"
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        root.bind_class("TCombobox", seq, guard)


def paint_toolbar(toolbar) -> None:
    """The matplotlib toolbar is made of plain tk widgets; match them to the window colour."""
    colour = matplotlib.rcParams["figure.facecolor"]
    for w in [toolbar, *toolbar.winfo_children()]:
        try:
            w.configure(background=colour)
            if w.winfo_class() in ("Button", "Checkbutton", "Radiobutton"):
                w.configure(activebackground=colour, highlightbackground=colour)
        except tk.TclError:
            pass
