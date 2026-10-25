"""Rewrite the app icon as a clean multi-size .ico for PyInstaller (called by build.bat).

    python build_icon.py <in.ico> <out.ico>
"""
import sys

from PIL import Image

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

src, dst = sys.argv[1], sys.argv[2]
ico = Image.open(src)
largest = max(ico.info.get("sizes", {ico.size}), key=lambda s: s[0])
ico.size = largest
img = ico.convert("RGBA")
if img.size != (256, 256):
    img = img.resize((256, 256), Image.LANCZOS)
img.save(dst, format="ICO", sizes=SIZES)
print("icon written:", dst)
