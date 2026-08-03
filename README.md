# Radon Plot

A desktop app for visualizing RadonEye RD200 radon monitor data — load an exported log file and get an interactive graph with risk-standard overlays, unit conversion, range selection/averaging, and report export.

## Features

See [CHANGELOG_v1.md](CHANGELOG_v1.md) for the full v1.0 feature list.

- WHO / Health Canada / EPA / and 12 additional national risk standards
- Bq/m³ ⟷ pCi/L unit conversion
- Pan, zoom, and Shift-drag range selection with live averaging
- 24-hour, 30-day, 1-year, and selected-range averages
- Export to PDF, SVG, PNG, or JPEG

## Running from source

```bash
pip install -r requirements.txt
python radon_plot.py
```

## Building a standalone app

**macOS:**
```bash
pyinstaller radon_plot.spec
```
This produces a `.app` bundle in `dist/`. The `.spec` file defines the entry point, bundles hidden imports that PyInstaller can't auto-detect (matplotlib's PDF/SVG export backends), and drives the macOS-specific `.app` packaging step.

**Windows:**
Built via a separate PyInstaller command rather than the `.spec` file, since the `.spec`'s `BUNDLE()` step is macOS-only:
```bash
pyinstaller --onedir --windowed radon_plot.py
```
_(Fill in with your actual Windows build command/flags if this differs — this is a placeholder based on the changelog note.)_

## License

_(Add your license here.)_
