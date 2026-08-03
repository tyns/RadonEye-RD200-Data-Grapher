# Changelog — v1.0

## Data & Parsing
- Fixed core data loading: RD200 export format changed to comma-separated (`index,value`) instead of the old `index) value` format — parser rewritten to match.
- Header parsing updated for comma-separated fields (`Unit:`, `Total # of Data:`, etc.).
- Unit detection normalized so `Bq/m³` and `Bq/m3` are treated identically.
- Logging interval read from the file header instead of hardcoded, so non-hourly intervals work too.
- Backward compatible with the old data format and old filename date convention.
- Handles filenames with no embedded date (e.g. `SERIAL_LogData_2.txt`) via a fallback dialog, defaulting to the file's last-modified time rounded to the nearest hour.
- `.csv` files now selectable alongside `.txt` in the file picker.
- Error dialog shown if no valid data points are found, instead of failing silently.
- **New: "Load Data" toolbar button** loads a different RD200 file without restarting the app — reuses the exact same parsing logic as startup, rebuilds the unit dropdown to match the new file's native unit (including the case where the new file's unit is unrecognized), and clears any active range selection, since it wouldn't correspond to anything in the new data.

## Risk Standards & Units
- Selectable **Risk Standard** dropdown: WHO, Canada (Health Canada), USA (EPA), plus Australia, China, Finland, France, Germany, Ireland, New Zealand, Norway, South Korea, Sweden, Switzerland, and the UK — WHO/Canada/USA pinned to the top, rest alphabetical. *(Note: the 12 additional countries use good-faith figures from commonly published national guidance, not independently verified against each regulator's current official documentation — worth confirming directly if being relied on for a real decision.)*
- Selectable **Display Unit** dropdown (Bq/m³ / pCi/L) that converts the actual data values live, not just the threshold lines.
- Graph title, legend, axis label, and threshold lines all update dynamically with both dropdowns.
- Proper superscript "³" in Bq/m³ everywhere it's displayed — axis label, legend, hover tooltip, title, and all four averages cards — instead of a plain trailing "3". Purely cosmetic; every internal comparison/conversion still uses the plain "Bq/m3" string, unaffected.

## Graph Interaction
- Unified single mouse tool (no more switching between Pan/Zoom):
  - Drag = pan
  - Right-drag = interactive zoom
  - Click = zoom in one step, centered on the click
  - Right-click = zoom out one step
  - Scroll wheel = zoom
  - **Shift + drag** = select a date range for averaging; Shift-drag near an existing selection's edge resizes that edge, always snapping to the nearest actual reading (no in-between positions)
- Minimum zoom width capped at 6 hours (hourly data doesn't benefit from going narrower).
- **Home button moved off the toolbar** into a floating button pinned over the plot's own top-left corner, rather than sharing the toolbar row with Load/Save. Resets to the full dataset view reliably; position tracks the plot correctly across window resizes.
- Hover tooltip shows the exact timestamp (12-hour format) and reading value at any point on the line, with bold/larger styling on the reading, and flips position automatically near screen edges so it's never clipped.
- The plot's border now always draws on top of the data points/line, instead of points near the edge occasionally drawing over it.

## Averages & Range Selection
- Four always-visible stat cards: 24-Hour, 30-Day, 1-Year, and Selected Range averages, each in its own bordered card with a bold, large readout.
- 1-Year average notes if less than a full year of data is available (e.g. "only 60d avail.").
- Selected Range card shows the average, exact date/time range, and reading count for a Shift-dragged selection; keeps a permanent "(Hold Shift and drag...)" reminder visible both before and after a selection is made, so it's never a one-time hint you can forget.
- All four cards are locked to a single fixed height from the start (measured against the tallest possible content), so the row never resizes or shifts when a selection is made or cleared.
- While Shift-dragging, a small square date/time tag appears above each end of the selection, connected to the exact boundary by a vertical tick line — updates live as the selection is fine-tuned, so there's no need to release and check the stats card just to see the exact edges chosen.

## Axis & Date Display
- 12-hour AM/PM time format throughout (ticks, tooltip, corner labels), with leading zeros stripped ("7:00 PM" not "07:00 PM").
- Custom date-tick formatting: hour ticks show no minutes (data is always on the hour); day ticks show month + day + year; month ticks show month + year (e.g. "Jan 2026"), including January and any day-level tick landing on the 1st of a month (neither collapses to a bare year/month anymore).
- Tick positions are now anchored to fixed, calendar-independent points at every zoom level — hour, day, and month/year — so dragging the graph no longer shifts which hours/days/months get labeled, and without the uneven gaps that a naive "snap to the 1st/8th/15th/22nd" approach produces across month boundaries.
- **Left/right "bookend" bars**: solid colored strips along the graph's actual left/right edges (not the window edges) showing the visible date *and time* range on a single line, with rotated text (mirrored left/right, precisely centered both along the bar and across its width) and the y-axis tick marks and numbers pushed just outside them so nothing overlaps. These tick marks now stay correctly positioned during pan/zoom instead of only updating on a full redraw.
- Retired the separate "Showing: [start] – [end]" subtitle under the title — redundant now that the corner bars show the same information (plus time), and removing it freed up room to fix a title/tooltip crowding issue at the same time.

## Layout & Sizing
- All margins (top, bottom, left, right) now hold a constant physical size regardless of window size, instead of stretching disproportionately when the window is resized.
- Graph now claims all extra space when the window is resized taller/wider; the toolbar and stat cards stay a fixed height.
- Minimum window size locked to whatever size the app opens at — can be made bigger, never smaller.
- The "DATE AND TIME" axis title is pinned to a fixed physical distance from the window's bottom edge, so it no longer shifts up or down depending on whether the tick labels above it happen to be one line or two.
- All chart text sizing and spacing tuned for readability (dropdown fonts, title spacing, card text size).

## Export & Reporting
- Toolbar's Save button now exports a full report — the graph *and* the averages row together — instead of just the bare matplotlib canvas.
- Supports PDF (default), SVG, PNG, and JPEG. PDF and SVG are genuine vector output (real paths and text, not a rasterized screenshot), built directly through matplotlib's own export backend with a matching stats panel drawn alongside the plot.
- PDF text uses the standard PDF "Core 14" fonts (Helvetica, etc.) rather than an embedded font, avoiding font-substitution and kerning issues that showed up with matplotlib's default embedding options. The visual tradeoff is a Helvetica-style look in exports rather than the app's on-screen DejaVu Sans — a reasonable, standard look for this kind of report.
- Default export filename: `RD200_<serial number>_<today's date>`.
- Long selected-range date/time text automatically shrinks to fit its card rather than overflowing the border.
- The "Hold Shift and drag..." interaction reminder is left out of exports — it doesn't apply to a static file.

## Toolbar & Icons
- Trimmed toolbar to Load Data / Save (Export) only, plus the floating Home button over the plot — down from the original Home / Pan / Zoom / Save.
- Load, Export, and Home all use custom-drawn, consistent line-art icons (a folder outline, a tray with an outward arrow, and a simple house) instead of a mix of matplotlib's bundled icon and the OS's native file-picker icon.
- Descriptive tooltips throughout.

## Build / Performance
- Fixed extremely slow app startup: original PyInstaller `--onefile` build re-extracted the whole bundle on every launch; rebuilt as `--onedir`.
- Reduced bundle size by excluding unused Qt5 modules and matplotlib backends.
- Fixed Save As → PDF/SVG/PS/PGF throwing `ModuleNotFoundError` (matplotlib's export backends need to be explicitly bundled; PyInstaller can't detect they're needed automatically).

## Known limitations / honest notes
- The 12 additional country risk standards beyond WHO/Canada/EPA are not independently verified — see note above.
- Windows build is produced via a separate PyInstaller command (not the `.spec` file, since `.spec`'s `BUNDLE()` step is macOS-only); keep both in sync manually if you add new hidden imports or excludes.
- Exported PDF/SVG pages are sized to exactly match the app window's proportions rather than a standard page size (Letter/A4) — fine for on-screen viewing or "fit to page" printing, but not a standard physical size out of the box.
