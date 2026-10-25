from __future__ import annotations
import tkinter as tk
from tkinter import ttk

GUIDE = [
    ("h", "What this tool does"),
    ("p", "A GT3-revisited car mod is a folder of small .ini text files plus a 3D model and some pictures. "
          "This tool writes the .ini files from forms, so you never have to hand-edit them, and it helps "
          "you add the model and make the dealer pictures. The preview tab always shows exactly what will "
          "be written."),
    ("h", "The order to work in"),
    ("b", "1. Start a new mod (or open an existing one). A new mod gets its folder and sub-folders straight away."),
    ("b", "2. Mod tab: the mod's name, author and version."),
    ("b", "3. Car tab: who the car is (label, name, maker, donor), then its size, engine, gearbox and tyres. "
          "Fields marked * must be filled in. Anything you leave blank is borrowed from the donor car."),
    ("b", "4. Torque curve tab: the engine's power curve (rpm and Nm points). The graph updates as you edit."),
    ("b", "5. Paints tab (optional): the colours offered in the garage."),
    ("b", "6. Model tools tab: add your .glb body, fill in its measured sizes, and make the dealer pictures."),
    ("b", "7. Preview tab: check the finished files, then press Save (Ctrl+S)."),
    ("h", "Words you will see"),
    ("b", "Mod folder name (id): the folder's name. Use a-z, 0-9 and _ only. It identifies the mod."),
    ("b", "Label: the car's unique id. The car's .ini file is named after it. Never change it once the "
          "mod is shared, because saves and replays use it. It can't be the same as a car on the disc."),
    ("b", "Donor: a car from the disc that lends your car its suspension, steering and tyre type."),
    ("b", "Maker: the brand. A maker file (maker tab) is only needed for a brand the disc doesn't have."),
    ("b", "Priority: if two mods provide the same file or car, the higher number wins."),
    ("b", "Torque curve: how much pulling force the engine makes at each rpm."),
    ("h", "Finding and fixing problems"),
    ("b", "Red text under a field says what is wrong. A warning sign on a tab means something in it needs attention."),
    ("b", "The Problems button lists everything at once. Double-click an entry to jump to it."),
    ("b", "Problems are warnings only: you can always save and come back to them later."),
    ("h", "Where things are saved"),
    ("b", "The label under the toolbar shows the mod folder. \"Open folder\" shows it in your file browser."),
    ("b", "Inside it: mod.ini, makers/, cars/, images/ and models/. Save only rewrites .ini files; "
          "your pictures and models are never touched."),
    ("b", "Opening an existing mod keeps any entries the tool doesn't know about, but your own hand-written "
          "comments are replaced by the standard ones."),
]


class GuideWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Quick guide")
        self.geometry("640x620")
        self.transient(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        text = tk.Text(self, wrap="word", padx=16, pady=12, relief="flat", cursor="arrow", spacing3=4)
        scroll = ttk.Scrollbar(self, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        text.tag_configure("h", font=("TkDefaultFont", 12, "bold"), spacing1=12, spacing3=4)
        text.tag_configure("b", lmargin1=16, lmargin2=32)
        for kind, line in GUIDE:
            text.insert("end", line + "\n", kind)
        text.configure(state="disabled")
        ttk.Button(self, text="Close", command=self.destroy).grid(row=1, column=0, columnspan=2, pady=8)
        self.bind("<Escape>", lambda _e: self.destroy())
