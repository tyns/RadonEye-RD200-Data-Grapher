# radon_plot.spec
#
# PyInstaller build spec for the macOS build (--onedir style, per the v1.0
# changelog: a --onefile build was re-extracting the entire bundle on every
# launch, which was the main cause of a slow startup).
#
# This is a newly-generated spec, not a recovered original — I only ever
# had radon_plot.py, not your actual project folder, so a few things below
# are placeholders you'll want to fill in (marked TODO). Everything else is
# built directly from the app's real imports.
#
# Build with:
#   pyinstaller radon_plot.spec
#
# Output: dist/Radon Plot.app

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

APP_NAME = "Radon Plot"

# matplotlib resolves its file-format backends (PDF, SVG, ...) dynamically
# at savefig() time, based on the file extension -- not via a plain `import`
# statement anywhere in radon_plot.py. PyInstaller's static analysis only
# sees actual import statements, so it has no way to know these are needed;
# without listing them explicitly here, Save As -> PDF/SVG throws
# ModuleNotFoundError at runtime in the built app even though it works fine
# running from source (exactly the bug noted in the v1.0 changelog).
hidden_imports = [
    "matplotlib.backends.backend_pdf",
    "matplotlib.backends.backend_svg",
    "matplotlib.backends.backend_agg",   # PNG
    "PIL._tkinter_finder",               # harmless if unused; some Pillow
                                          # versions probe for this at import
                                          # time and PyInstaller can miss it
]

# Trimming unused Qt5 modules and matplotlib backends this app never uses,
# per the v1.0 changelog's bundle-size note. Double check against your
# actual PyQt5 imports before removing any of these if you add features
# that need them later (e.g. QtNetwork if BLE/networking work in v2 ends
# up needing it).
excludes = [
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngine",
    "PyQt5.QtMultimedia",
    "PyQt5.QtMultimediaWidgets",
    "PyQt5.QtNetwork",
    "PyQt5.QtQml",
    "PyQt5.QtQuick",
    "PyQt5.QtSql",
    "PyQt5.QtTest",
    "PyQt5.QtBluetooth",     # remove this if/when the v2 BLE feature lands
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_gtk3agg",
    "matplotlib.backends.backend_gtk3cairo",
    "matplotlib.backends.backend_wx",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_webagg",
    "matplotlib.backends.backend_nbagg",
    "matplotlib.backends.backend_macosx",  # app uses Qt5Agg, not the native
                                            # macOS backend, interactively
    "tkinter",
]

a = Analysis(
    ["radon_plot.py"],
    pathex=[],
    binaries=[],
    datas=[
        # TODO: add an app icon here if you have one, e.g.:
        # ("assets/icon.icns", "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # windowed app, no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # TODO: point this at a .icns file if you have one designed for the app
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

# macOS-only: wraps the --onedir output into a proper .app bundle with an
# Info.plist. This step is skipped entirely on Windows -- per the v1.0
# changelog, the Windows build uses a separate plain PyInstaller command
# instead of this .spec file, specifically because BUNDLE() only works on
# macOS.
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    # TODO: point this at a .icns file if you have one
    icon="AppIcon.icns",
    bundle_identifier="com.github.tyns.radonplot",  # TODO: replace with your own,
                                                  # reverse-domain style, e.g.
                                                  # "com.yourname.radonplot"
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
        # No Bluetooth usage description yet -- this will need to be added
        # (NSBluetoothAlwaysUsageDescription) when the v2 BLE feature lands,
        # or macOS will silently deny Bluetooth access in the packaged app.
    },
)
