# Changelog

## Data Parsing (Bug Fixes)
- **Fixed core data loading bug**: RD200 export format changed to comma-separated
  (`index,value`) instead of the old `index) value` format, which caused the
  script to load zero data points. Parser rewritten to match the current format.
- **Fixed header parsing**: header fields (`Unit:`, `Total # of Data:`, etc.) are
  now also comma-separated in current exports; parser updated to match.
- **Fixed unit detection**: normalized `Bq/m³` (superscript 3) and `Bq/m3`
  (plain 3) to be treated identically, so risk-zone coloring works regardless
  of which form the export uses.
- **Fixed reading interval**: interval (e.g. "1 hour") is now read from the
  file header instead of being hardcoded, so the script isn't locked to
  1-hour logging intervals.
- **Backward compatible**: still supports the old `index) value` data format
  and old `SERIAL_YYYYMMDD HHMMSS.txt` filename date convention, in case
  older export files are used.

## New Feature: Handles Filenames With No Embedded Date
- Newer RD200 exports (e.g. `SERIAL_LogData_2.txt`) don't include a date/time
  in the filename, which the original script required to place data on the
  timeline.
- App now falls back to the file's last-modified date and prompts with an
  editable dialog to confirm/correct the end date/time before plotting.

## New Feature: Mouse Scroll Wheel Zoom
- Scroll wheel (and trackpad two-finger scroll) now zooms the x-axis in/out,
  centered on the cursor position rather than the plot center.
- Tuned for macOS "natural scrolling" convention (togglable in code via
  `NATURAL_SCROLLING` flag in `on_scroll()` if it ever feels reversed).
- Works alongside the existing Zoom In / Zoom Out buttons and toolbar
  rectangle-zoom.

## New Feature: .csv File Support
- File picker now recognizes `.csv` files in addition to `.txt`, in case
  future exports use that extension. Parsing logic is extension-agnostic.

## Build / Performance Fixes (radon_plot.spec)
- **Fixed extremely slow app startup (1+ minute)**: the original spec built
  in PyInstaller `--onefile` mode, which re-extracts the entire bundle
  (Qt frameworks, numpy, matplotlib) to a temp directory on *every* launch.
  Rebuilt as `--onedir` so extraction happens once at build time, not per-launch.
- **Reduced bundle size**: excluded unused Qt5 modules (WebEngine, QML/Quick,
  Bluetooth, Multimedia, SQL, 3D, etc.) and unused matplotlib backends that
  were being bundled unnecessarily by default hooks.
- Re-enabled UPX compression and binary stripping (safe now that onedir
  removes the extraction-on-launch penalty).

## Robustness
- Added error dialog when no valid data points are found in a selected file,
  instead of failing silently/crashing.
