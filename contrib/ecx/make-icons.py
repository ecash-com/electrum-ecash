#!/usr/bin/env python3
"""Regenerate every derivable app icon from one master image.

    python3 contrib/ecx/make-icons.py path/to/master.png [--dry-run]

Master should be square, >=1024x1024, RGBA with a transparent background.

Writes into electrum/gui/icons/, keeping upstream's filenames so no code or
packaging file has to change.

Does NOT touch (they are artwork, not scalings -- see FORK.md):
    electrum_text.png            wordmark, contains lettering
    electrum_darkblue.svg        vector source
    electrum_lightblue.svg       vector source
    electrumb.png                non-square, revealer plugin
"""
import subprocess, sys, tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("needs Pillow:  .venv/bin/pip install Pillow")

ICONS = Path(__file__).resolve().parents[2] / "electrum" / "gui" / "icons"

# name -> size. Square PNG scalings.
PNGS = {
    "electrum.png": 128,                       # Linux (pixmaps, hicolor) + in-app window/taskbar
    "electrum_launcher.png": 136,
    "electrum_presplash.png": 512,             # Android splash + QML About
    "android_electrum_icon_legacy.png": 192,   # Android launcher
    "electrum_darkblue_1.png": 67,             # terms-of-use wizard
}
TRAY = {"electrum_dark_icon.png": 32, "electrum_light_icon.png": 32}
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]     # Windows
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]  # macOS


def load(src: Path) -> Image.Image:
    im = Image.open(src).convert("RGBA")
    if im.width != im.height:
        print(f"  ! master is {im.width}x{im.height}, not square -- results will be distorted")
    if im.width < 1024:
        print(f"  ! master is {im.width}px; 1024+ recommended (macOS uses a 1024 slice)")
    return im


def scale(im, size):
    return im.resize((size, size), Image.LANCZOS)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry-run" in sys.argv
    if not args:
        sys.exit(__doc__)
    src = Path(args[0])
    if not src.is_file():
        sys.exit(f"no such file: {src}")

    im = load(src)
    print(f"master: {src}  {im.width}x{im.height}")
    if dry:
        print("(dry run -- nothing written)")

    for name, size in {**PNGS, **TRAY}.items():
        out = ICONS / name
        print(f"  {name:36} {size}x{size}")
        if not dry:
            scale(im, size).save(out, "PNG")

    print(f"  {'electrum.ico':36} {ICO_SIZES}")
    if not dry:
        scale(im, 256).save(ICONS / "electrum.ico", format="ICO",
                            sizes=[(s, s) for s in ICO_SIZES])

    print(f"  {'electrum.icns':36} {ICNS_SIZES}")
    if not dry:
        with tempfile.TemporaryDirectory() as td:
            iconset = Path(td) / "icon.iconset"
            iconset.mkdir()
            for s in ICNS_SIZES:
                scale(im, s).save(iconset / f"icon_{s}x{s}.png", "PNG")
                scale(im, s * 2).save(iconset / f"icon_{s}x{s}@2x.png", "PNG")
            subprocess.run(["iconutil", "-c", "icns", str(iconset),
                            "-o", str(ICONS / "electrum.icns")], check=True)

    print("\nNOT regenerated (artwork, not scalings):")
    for n in ("electrum_text.png", "electrum_darkblue.svg",
              "electrum_lightblue.svg", "electrumb.png"):
        print(f"  {n}")
    print("\nNote: electrum_dark_icon.png / electrum_light_icon.png are the system-tray")
    print("icons and upstream ships them as two DIFFERENT images (one tuned for dark")
    print("menu bars, one for light). Both are written from the same master here, so")
    print("check contrast on both themes and hand-supply variants if needed.")


if __name__ == "__main__":
    main()
