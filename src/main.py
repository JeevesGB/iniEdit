"""GT3 Mod Creator entry point.  Run:  python main.py"""

import sys

try:
    import matplotlib  # noqa: F401
except ImportError:
    raise SystemExit("Matplotlib is required.\nInstall it with: python -m pip install -r requirements.txt")

from gui.app import ModCreatorApp


def main():
    ModCreatorApp().mainloop()


if __name__ == "__main__":
    sys.exit(main())
