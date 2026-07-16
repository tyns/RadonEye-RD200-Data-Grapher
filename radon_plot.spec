# -*- mode: python ; coding: utf-8 -*-

# Modules/Qt components matplotlib's Qt5Agg backend + this app never use.
# Excluding these keeps PyInstaller's PyQt5 hook from bundling the entire
# Qt suite (which is where most of the 184MB comes from).
excluded_modules = [
    'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets', 'PyQt5.QtQuick3D',
    'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtLocation',
    'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtDesigner', 'PyQt5.QtHelp',
    'PyQt5.QtNetworkAuth', 'PyQt5.QtRemoteObjects',
    'PyQt5.QtSensors', 'PyQt5.QtSerialPort', 'PyQt5.QtSvg', 'PyQt5.QtXml',
    'PyQt5.QtXmlPatterns', 'PyQt5.Qt3DCore', 'PyQt5.Qt3DRender',
    'PyQt5.Qt3DInput', 'PyQt5.Qt3DLogic', 'PyQt5.Qt3DAnimation', 'PyQt5.Qt3DExtras',
    'PyQt5.QtWinExtras', 'PyQt5.QtMacExtras',
    # Unused matplotlib backends (only Qt5Agg is used)
    'matplotlib.backends.backend_tkagg', 'matplotlib.backends.backend_gtk3agg',
    'matplotlib.backends.backend_gtk3cairo', 'matplotlib.backends.backend_wxagg',
    'matplotlib.backends.backend_webagg', 'matplotlib.backends.backend_pgf',
    # Other common unused heavy libraries pulled in by pip environments
    'tkinter', 'PySide2', 'PySide6', 'IPython', 'notebook', 'pytest',
]

a = Analysis(
    ['radon_plot.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='radon_plot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='radon_plot',
)
app = BUNDLE(
    coll,
    name='radon_plot.app',
    icon=None,
    bundle_identifier=None,
)
