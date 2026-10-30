from __future__ import annotations
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
import matplotlib

THEMES = {
    "win95": "Windows 95",
    "xp": "Windows XP",
    "vista": "Windows Vista",
    "win7": "Windows 7",
    "system": "System default",
}

# Classic clam palettes. Keys match the colours the rest of the app reads.
PALETTES = {
    "win95": {
        "bg": "#C0C0C0", "face": "#C0C0C0", "blue": "#000080", "blue_dark": "#000000",
        "orange": "#000080", "field": "#808080", "group": "#808080", "title": "#000000",
        "tab": "#C0C0C0", "tab_sel": "#C0C0C0", "heading": "#C0C0C0", "scroll": "#C0C0C0",
        "scroll_border": "#808080", "progress": "#000080", "disabled": "#808080",
        "select_fg": "white", "arrow": "#000000", "active": "#DFDFDF",
        "font": ("MS Sans Serif", "Tahoma", "Verdana", "DejaVu Sans"), "size": 8,
    },
    "xp": {
        "bg": "#ECE9D8", "face": "#F4F3EE", "blue": "#316AC5", "blue_dark": "#003C74",
        "orange": "#F8B330", "field": "#7F9DB9", "group": "#D0D0BF", "title": "#0046D5",
        "tab": "#F1EFE2", "tab_sel": "#FCFCFE", "heading": "#EBEADB", "scroll": "#C1D2EE",
        "scroll_border": "#98B3E3", "progress": "#3EB43E", "disabled": "#ACA899",
        "select_fg": "white", "arrow": "#4D6185", "active": "#FFF8E5",
        "font": ("Tahoma", "Segoe UI", "Verdana", "DejaVu Sans"), "size": 9,
    },
    "vista": {
        "bg": "#F0F4F8", "face": "#FFFFFF", "blue": "#3399FF", "blue_dark": "#1C4F8C",
        "orange": "#6CB6FF", "field": "#A6C8E6", "group": "#C5D6E8", "title": "#1C4F8C",
        "tab": "#E7F0F8", "tab_sel": "#FFFFFF", "heading": "#D6E6F5", "scroll": "#D0E4F7",
        "scroll_border": "#8FB4D6", "progress": "#3399FF", "disabled": "#A0A8B0",
        "select_fg": "white", "arrow": "#1C4F8C", "active": "#E4F2FF",
        "font": ("Segoe UI", "Tahoma", "Verdana", "DejaVu Sans"), "size": 9,
    },
    "win7": {
        "bg": "#F0F0F0", "face": "#F7F7F7", "blue": "#3399FF", "blue_dark": "#1F4E79",
        "orange": "#5BA3E0", "field": "#ABADB3", "group": "#D4D4D4", "title": "#1F4E79",
        "tab": "#E8E8E8", "tab_sel": "#FFFFFF", "heading": "#E5E5E5", "scroll": "#E1E1E1",
        "scroll_border": "#BCBCBC", "progress": "#06B025", "disabled": "#A0A0A0",
        "select_fg": "white", "arrow": "#505050", "active": "#E5F3FF",
        "font": ("Segoe UI", "Tahoma", "Verdana", "DejaVu Sans"), "size": 9,
    },
}

SCALE = 1.0
BG = PALETTES["xp"]["bg"]
BLUE = PALETTES["xp"]["blue"]
_original: dict = {}
_active = "xp"


def enable_dpi_awareness() -> None:
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
    if SCALE > 1.01 and not getattr(ttk.Treeview, "_scaled", False):
        original = ttk.Treeview.column

        def column(self, column, option=None, **kw):
            for key in ("width", "minwidth"):
                if key in kw:
                    kw[key] = px(kw[key])
            return original(self, column, option, **kw)

        ttk.Treeview.column = column
        ttk.Treeview._scaled = True
    return SCALE


def _font_face(root, names: tuple[str, ...]) -> str:
    families = set(tkfont.families(root))
    for name in names:
        if name in families:
            return name
    return tkfont.nametofont("TkDefaultFont", root).actual("family")


def apply(root: tk.Tk, name: str) -> None:
    global BG, BLUE, _active
    style = ttk.Style(root)
    if not _original:
        _original["theme"] = style.theme_use()
        _original["fonts"] = {n: tkfont.nametofont(n, root).actual() for n in
                              ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont")}
        _original["fig"] = matplotlib.rcParams["figure.facecolor"]
    if name == "system" or name not in PALETTES:
        style.theme_use(_original["theme"])
        for n, spec in _original["fonts"].items():
            tkfont.nametofont(n, root).configure(**spec)
        root.configure(background=style.lookup("TFrame", "background") or root.cget("background"))
        matplotlib.rcParams["figure.facecolor"] = _original["fig"]
        BG = root.cget("background")
        BLUE = "#316AC5"
        _active = "system"
        _install_wheel_guard(root)
        return

    p = PALETTES[name]
    BG, BLUE, _active = p["bg"], p["blue"], name
    face = _font_face(root, p["font"])
    for n in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        tkfont.nametofont(n, root).configure(family=face, size=p["size"])
    style.theme_use("clam")
    root.configure(background=p["bg"])
    root.option_add("*Menu.background", p["bg"])
    root.option_add("*Menu.activeBackground", p["blue"])
    root.option_add("*Menu.activeForeground", p["select_fg"])
    root.option_add("*Text.background", "white")
    root.option_add("*Text.selectBackground", p["blue"])
    root.option_add("*Listbox.selectBackground", p["blue"])
    root.option_add("*TCombobox*Listbox.selectBackground", p["blue"])
    root.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])
    root.option_add("*TCombobox*Listbox.background", "white")

    c = style.configure
    m = style.map
    c(".", background=p["bg"], foreground="#000000", fieldbackground="white", troughcolor=p["bg"],
      bordercolor=p["group"], lightcolor="white", darkcolor=p["group"], focuscolor=p["bg"],
      selectbackground=p["blue"], selectforeground=p["select_fg"], insertcolor="black")
    m(".", foreground=[("disabled", p["disabled"])])

    c("TButton", background=p["face"], bordercolor=p["blue_dark"], lightcolor="white", darkcolor=p["group"],
      relief="raised", borderwidth=1, padding=(px(10), px(3)), anchor="center", focuscolor=p["face"])
    m("TButton",
      background=[("pressed", p["heading"]), ("disabled", p["face"]), ("active", p["active"])],
      bordercolor=[("disabled", p["group"])],
      relief=[("pressed", "sunken")])
    c("Toolbutton", padding=px(3))

    for entry in ("TEntry", "TSpinbox", "TCombobox"):
        c(entry, fieldbackground="white", bordercolor=p["field"], lightcolor="white", darkcolor=p["field"],
          padding=px(2), selectbackground=p["blue"], selectforeground=p["select_fg"])
        m(entry, bordercolor=[("focus", p["blue"]), ("disabled", p["group"])],
          fieldbackground=[("disabled", p["face"]), ("readonly", "white")],
          foreground=[("disabled", p["disabled"])])
    c("TCombobox", arrowcolor=p["arrow"], background=p["scroll"], arrowsize=px(14))
    m("TCombobox", background=[("active", p["active"]), ("pressed", p["scroll"])],
      selectbackground=[("readonly", "white")], selectforeground=[("readonly", "black")])
    c("TSpinbox", arrowcolor=p["arrow"], background=p["scroll"], arrowsize=px(12))
    m("TSpinbox", background=[("active", p["active"])])

    for check in ("TCheckbutton", "TRadiobutton"):
        c(check, indicatorbackground="white", indicatorforeground=p["progress"], indicatormargin=px(3))
        m(check, indicatorbackground=[("disabled", p["face"])], background=[("active", p["bg"])])

    c("TLabelframe", background=p["bg"], bordercolor=p["group"], lightcolor=p["bg"], darkcolor=p["bg"], relief="solid")
    c("TLabelframe.Label", background=p["bg"], foreground=p["title"])

    c("TNotebook", background=p["bg"], bordercolor=p["group"], lightcolor="white", darkcolor=p["group"],
      tabmargins=(px(2), px(4), px(2), 0))
    c("TNotebook.Tab", background=p["tab"], foreground="#000000", bordercolor=p["group"],
      lightcolor="white", darkcolor=p["group"], padding=(px(9), px(3)))
    m("TNotebook.Tab",
      background=[("selected", p["tab_sel"]), ("active", p["active"])],
      lightcolor=[("selected", p["orange"]), ("active", p["orange"])],
      expand=[("selected", (px(1), px(2), px(1), 0))])

    c("Treeview", background="white", fieldbackground="white", bordercolor=p["field"], rowheight=px(20),
      lightcolor="white", darkcolor=p["field"])
    m("Treeview", background=[("selected", p["blue"])], foreground=[("selected", p["select_fg"])])
    c("Treeview.Heading", background=p["heading"], foreground="#000000", bordercolor=p["group"],
      lightcolor="white", darkcolor=p["group"], relief="raised", padding=(px(4), px(3)))
    m("Treeview.Heading", background=[("active", p["active"])])

    for orient in ("Vertical", "Horizontal"):
        c(f"{orient}.TScrollbar", background=p["scroll"], troughcolor=p["bg"], bordercolor=p["scroll_border"],
          lightcolor="white", darkcolor=p["scroll_border"], arrowcolor=p["arrow"], arrowsize=px(15), gripcount=0)
        m(f"{orient}.TScrollbar", background=[("active", p["active"]), ("pressed", p["scroll_border"])])
    c("Sash", sashthickness=px(6), gripcount=0, background=p["bg"])
    c("TPanedwindow", background=p["bg"])
    c("TSeparator", background=p["group"])
    c("TProgressbar", background=p["progress"], troughcolor="white", bordercolor=p["field"])

    matplotlib.rcParams["figure.facecolor"] = p["bg"]
    _install_wheel_guard(root)


def restyle_figures(*panels) -> None:
    colour = matplotlib.rcParams["figure.facecolor"]
    for panel in panels:
        fig = getattr(panel, "figure", None)
        if fig is not None:
            fig.set_facecolor(colour)
            panel.canvas.draw_idle()


def restyle_canvases(widget) -> None:
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
    def guard(event):
        from gui import parameter_form
        scroll = parameter_form.ACTIVE_SCROLL
        if scroll is not None:
            scroll(event)
        return "break"
    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        root.bind_class("TCombobox", seq, guard)


def paint_toolbar(toolbar) -> None:
    colour = matplotlib.rcParams["figure.facecolor"]
    for w in [toolbar, *toolbar.winfo_children()]:
        try:
            w.configure(background=colour)
            if w.winfo_class() in ("Button", "Checkbutton", "Radiobutton"):
                w.configure(activebackground=colour, highlightbackground=colour)
        except tk.TclError:
            pass
