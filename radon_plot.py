import matplotlib
print(f"Matplotlib version: {matplotlib.__version__}")
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.backend_bases import MouseButton
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import numpy as np
import datetime
import os
import re
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from matplotlib.collections import LineCollection
from dateutil.rrule import YEARLY, MONTHLY, DAILY
import matplotlib.ticker as mticker
from PyQt5.QtWidgets import QFileDialog, QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QInputDialog, QMessageBox, QComboBox, QLabel, QSizePolicy, QAction, QPushButton
from PyQt5.QtCore import Qt, QRectF, QPointF, QSize
from PyQt5.QtGui import QPainter, QPen, QIcon, QPixmap, QColor, QPainterPath
from matplotlib.patches import Patch, Rectangle
from matplotlib.lines import Line2D
import sys

# Create Qt application
app = QApplication(sys.argv)


def _make_line_icon(draw_fn, size=24, stroke=1.8, color="#404040"):
    """Render a small custom icon by calling draw_fn(painter, size) with a
    QPainter set up for a plain black-outline, no-fill look — matplotlib's
    own bundled toolbar icons (used for Save originally, still used for
    other trimmed-out buttons) are simple line-art pictograms in the same
    spirit, so custom icons (Load Data, Export, and the overlay Home
    button) are drawn to match that style rather than pulling in a
    mismatched OS-native icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(stroke)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    draw_fn(painter, size)
    painter.end()
    return QIcon(pixmap)


def _draw_folder_icon(painter, size):
    """Simple open-folder outline for the Load Data button."""
    m = size * 0.16
    painter.drawRect(QRectF(m, size * 0.38, size - 2 * m, size * 0.42))
    tab = QPainterPath()
    tab.moveTo(m, size * 0.38)
    tab.lineTo(m, size * 0.24)
    tab.lineTo(size * 0.46, size * 0.24)
    tab.lineTo(size * 0.56, size * 0.38)
    painter.drawPath(tab)


def _draw_export_icon(painter, size):
    """A tray with an arrow pointing up and out of it — reads as
    "export"/"send out" rather than the traditional floppy-disk "save"
    icon, which is what a Save button used to look like here."""
    m = size * 0.16
    painter.drawRect(QRectF(m, size * 0.66, size - 2 * m, size * 0.2))
    painter.drawLine(QPointF(size * 0.5, size * 0.14), QPointF(size * 0.5, size * 0.58))
    arrow = QPainterPath()
    arrow.moveTo(size * 0.32, size * 0.32)
    arrow.lineTo(size * 0.5, size * 0.14)
    arrow.lineTo(size * 0.68, size * 0.32)
    painter.drawPath(arrow)


def _draw_home_icon(painter, size):
    """Simple house outline for the overlay "reset view" button."""
    roof = QPainterPath()
    roof.moveTo(size * 0.14, size * 0.52)
    roof.lineTo(size * 0.5, size * 0.16)
    roof.lineTo(size * 0.86, size * 0.52)
    painter.drawPath(roof)
    painter.drawRect(QRectF(size * 0.23, size * 0.5, size * 0.54, size * 0.36))
    painter.drawRect(QRectF(size * 0.44, size * 0.63, size * 0.12, size * 0.23))


def _build_trimmed_toolitems():
    """Keep only Save as a visible toolbar button. There's no separate
    Pan/Zoom toggle anymore — dragging, clicking, and shift-dragging all
    work all the time (see TrimmedNavigationToolbar below), so there's
    nothing to switch between. Built as a standalone function rather than
    inline in the class body, since list comprehensions in a class body
    can't see other class-level names."""
    kept = {'Save'}
    tooltip_overrides = {
        'Save': "Export the graph as an image or document (PNG, PDF, SVG, and more)",
    }
    return [
        (name, tooltip_overrides.get(name, desc), icon, callback)
        for name, desc, icon, callback in NavigationToolbar.toolitems
        if name in kept
    ]


class TrimmedNavigationToolbar(NavigationToolbar):
    """Same toolbar as matplotlib's default, minus buttons that don't add
    value for this app: Back/Forward (redundant with Home), Pan/Zoom
    (merged into always-on mouse behavior — see press_pan/release_pan
    below), Subplots (can desync layout), and Customize (built for
    editing individual Line2D curves — this app draws a LineCollection,
    which that dialog doesn't handle well). Home has moved off the
    toolbar entirely, into a floating button pinned over the plot's own
    top-left corner (see the home_overlay_button setup below).

    Mouse behavior (active at all times, no mode switching required):
      - Drag (left button): pan
      - Right-drag: matplotlib's built-in interactive zoom
      - Click (no drag): zoom in one step, centered on the click
      - Right-click (no drag): zoom out one step
      - Shift + drag: select a date range (see MainWindow.begin_range_drag)
      - Shift + drag near an existing selection's edge: resize that edge
      - Scroll wheel: zoom
    """
    toolitems = _build_trimmed_toolitems()

    def __init__(self, canvas, parent, *args, **kwargs):
        super().__init__(canvas, parent, *args, **kwargs)
        # The MainWindow instance — used to hand off shift-drag range
        # selection, since that needs access to the loaded data (timestamps,
        # readings) that only the host window has.
        self.host = parent
        self._click_zoom_start = None
        self._shift_drag_active = False

        # "Load Data" button, added directly as a QAction rather than
        # through toolitems/matplotlib's bundled icon set — matplotlib
        # doesn't ship an "open file" icon. Drawn as a simple line-art
        # folder icon (_draw_folder_icon) to match the style of Save's
        # icon below and the floating Home button, rather than pulling
        # in a mismatched OS-native icon. Placed first (leftmost).
        load_action = QAction(_make_line_icon(_draw_folder_icon), "Load Data", self)
        load_action.setToolTip("Load a different RadonEye data file")
        load_action.triggered.connect(self.host.load_new_file)
        existing_actions = self.actions()
        if existing_actions:
            self.insertAction(existing_actions[0], load_action)
        else:
            self.addAction(load_action)

        # Override Save's icon (built from toolitems, so it started out
        # as matplotlib's default floppy-disk icon) with an "export"
        # style instead -- a tray with an arrow pointing out of it reads
        # more clearly as "send this out as a file" than a save icon,
        # and matches the Load/Home icons' line-art style.
        for action in self.actions():
            if action.text() == 'Save':
                action.setIcon(_make_line_icon(_draw_export_icon))
                break

        # Floating "reset view" button, positioned over the plot's own
        # top-left corner instead of living in the toolbar row. A plain
        # child widget of the canvas rather than a toolbar action, so it
        # can be positioned freely with move() below. Its (8, 8) offset
        # is relative to the canvas's own top-left corner, not the
        # window — Qt positions child widgets relative to their parent,
        # so this stays pinned there automatically as the window/canvas
        # is resized, with no resize handler needed.
        self.home_overlay_button = QPushButton(canvas)
        self.home_overlay_button.setIcon(_make_line_icon(_draw_home_icon, size=20))
        self.home_overlay_button.setIconSize(QSize(18, 18))
        self.home_overlay_button.setFixedSize(28, 28)
        self.home_overlay_button.setToolTip("Reset the view to show all data points")
        self.home_overlay_button.setCursor(Qt.PointingHandCursor)
        self.home_overlay_button.setStyleSheet(
            "QPushButton { background-color: rgba(255,255,255,0.85); border: 1px solid #999; border-radius: 4px; }"
            "QPushButton:hover { background-color: rgba(255,255,255,1.0); }"
            "QPushButton:pressed { background-color: rgba(230,230,230,1.0); }"
        )
        self.home_overlay_button.clicked.connect(self.home)
        # Positioned relative to the axes' own top-left corner (not just
        # the canvas's), so it lands over the actual plot rather than
        # over the y-axis labels / left edge bar — see
        # MainWindow._position_home_overlay_button, called once the
        # canvas has a real size (raw new-widget sizes aren't reliable
        # this early) and again on every resize.
        self.home_overlay_button.raise_()
        self.home_overlay_button.show()

    def press_pan(self, event):
        # Shift-drag is reserved for range selection — hand off to the
        # host MainWindow entirely and skip normal pan/click-zoom setup.
        if event.button == MouseButton.LEFT and 'shift' in event.modifiers:
            self._shift_drag_active = True
            self.host.begin_range_drag(event)
            return
        self._shift_drag_active = False

        # Remember the click's starting screen position (in pixels) so
        # release_pan can tell a genuine drag apart from a stationary
        # click. Let the normal pan machinery run too, so an actual drag
        # still pans (or, with the right mouse button, does matplotlib's
        # built-in interactive zoom) exactly as before.
        if event.button in (MouseButton.LEFT, MouseButton.RIGHT) and event.x is not None and event.y is not None:
            self._click_zoom_start = (event.button, event.inaxes, event.x, event.y)
        else:
            self._click_zoom_start = None
        super().press_pan(event)

    def save_figure(self, *args):
        """The default NavigationToolbar save action only captures the
        matplotlib canvas itself, leaving out the averages row entirely
        (a separate set of Qt widgets, not part of the figure).

        An earlier version of this fixed that by rendering the whole Qt
        widget (toolbar, plot, averages row) via QPainter/widget.render.
        That's a raster capture, though -- the plot itself, drawn by
        matplotlib's Agg backend inside the canvas, was already a bitmap
        by the time Qt grabbed it, so PDF/SVG exports ended up with a
        rasterized plot embedded in an otherwise-vector file rather than
        true vector paths. See MainWindow.export_report for the fix:
        it draws a matching stats panel directly as matplotlib artists
        and saves through the figure's own savefig, so PDF/SVG stay
        genuinely vector throughout, not just around the edges."""
        serial = getattr(self.host, 'serial_number', None) or 'unit'
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')
        default_name = f"RD200_{serial}_{date_str}"

        path, chosen_filter = QFileDialog.getSaveFileName(
            self, "Save the figure", default_name,
            "PDF Document (*.pdf);;SVG Image (*.svg);;PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)"
        )
        if not path:
            return

        # If the user typed a name with no extension, infer one from
        # whichever filter was active in the dialog (PDF by default)
        ext = os.path.splitext(path)[1].lower()
        if not ext:
            ext = {'PDF': '.pdf', 'SVG': '.svg', 'PNG': '.png', 'JPEG': '.jpg'}.get(
                next((k for k in ('PDF', 'SVG', 'PNG', 'JPEG') if k in chosen_filter), 'PDF'), '.pdf'
            )
            path += ext

        try:
            self.host.export_report(path, ext.lstrip('.'))
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save the file:\n{exc}")

    def release_pan(self, event):
        if self._shift_drag_active:
            self._shift_drag_active = False
            self.host.end_range_drag(event)
            return

        start = self._click_zoom_start
        self._click_zoom_start = None
        # Let the normal pan interaction finish/clean up first. If the
        # mouse never actually moved, this is a harmless no-op.
        super().release_pan(event)

        if not start:
            return
        button, start_ax, x0, y0 = start
        if start_ax is None or event.x is None or event.y is None:
            return
        moved = ((event.x - x0) ** 2 + (event.y - y0) ** 2) ** 0.5
        if moved >= 5:
            return  # a real drag happened — that was a pan/zoom-drag, not a click
        if event.inaxes != start_ax or event.xdata is None:
            return

        try:
            ax = start_ax
            scale_factor = 0.5 if button == MouseButton.LEFT else 2.0  # left=in, right=out
            xlim = ax.get_xlim()
            old_width = xlim[1] - xlim[0]
            new_width = old_width * scale_factor
            rel = (event.xdata - xlim[0]) / old_width if old_width != 0 else 0.5
            ax.set_xlim(event.xdata - new_width * rel, event.xdata + new_width * (1 - rel))
            self.canvas.draw_idle()
        except Exception:
            pass  # fail safe — don't crash the app over a zoom click


def parse_interval_to_timedelta(interval_str):
    """Parse strings like '1 hour', '5 min', '30 minutes' into a timedelta."""
    if not interval_str:
        return datetime.timedelta(hours=1)
    match = re.match(r'\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)', interval_str)
    if not match:
        return datetime.timedelta(hours=1)
    amount = float(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith('h'):
        return datetime.timedelta(hours=amount)
    if unit.startswith('m'):
        return datetime.timedelta(minutes=amount)
    if unit.startswith('s'):
        return datetime.timedelta(seconds=amount)
    if unit.startswith('d'):
        return datetime.timedelta(days=amount)
    return datetime.timedelta(hours=1)


_LEADING_HOUR_ZERO_RE = re.compile(r'(?:(?<=\s)|^)0(\d(?::\d{2})?\s?[APap][Mm])')

# Used to classify x-axis tick labels for styling: month/year boundary
# ticks ("Feb 2025", "2025") are bolded to stand out as the coarser
# reference points; day-level ticks ("Feb 08") stay regular weight so
# they read as finer detail underneath.


class _FixedEpochDayLocator(mticker.Locator):
    """Places ticks at fixed multiples of `interval_days` from a
    constant reference point (day 0 of matplotlib's date numbering),
    rather than relative to the current view's edges.

    This is what SmartAutoDateLocator falls back to at the day/week
    level instead of a plain RRuleLocator. A plain RRuleLocator (even
    without the month-day-restricted anchoring) still computes ticks
    starting from dtstart=dmin -- the current view's left edge -- so as
    that edge shifts during a pan, which absolute days land on ticks
    shifts too. Anchoring to a fixed constant instead of the view's own
    edge gives ticks that never change position while panning, with no
    month-boundary side effects since the stride is calendar-agnostic."""

    def __init__(self, interval_days):
        self.interval_days = interval_days

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        step = self.interval_days
        start_k = np.floor(vmin / step)
        end_k = np.ceil(vmax / step)
        return np.arange(start_k, end_k + 1) * step


class _FixedEpochMonthLocator(mticker.Locator):
    """Month-level counterpart to _FixedEpochDayLocator. Places ticks on
    the 1st of every Nth month, counted from a fixed reference point
    (January of year 0) rather than from whichever month the view
    happens to start in.

    RRuleLocator's plain (non-"nice") mode still anchors its month
    stepping to dtstart=dmin, so for any interval greater than 1 month,
    panning past a month boundary can flip which alternating set of
    months gets ticked -- e.g. Mar/May/Jul/Sep/Nov becoming
    Apr/Jun/Aug/Oct/Dec after only a ~20-day drag. Calendar months have
    irregular lengths, so this can't stride by interval*30 days the way
    the day-level locator does -- it steps by integer month index
    (year*12 + month) instead, which stays exact regardless of how many
    days are in any particular month along the way."""

    def __init__(self, interval_months):
        self.interval_months = max(1, int(interval_months))

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        step = self.interval_months
        dlo = mdates.num2date(vmin)
        dhi = mdates.num2date(vmax)
        lo_idx = dlo.year * 12 + (dlo.month - 1)
        hi_idx = dhi.year * 12 + (dhi.month - 1)
        start_idx = (lo_idx // step) * step
        end_idx = ((hi_idx // step) + 1) * step
        ticks = []
        for idx in range(start_idx, end_idx + step, step):
            year, month0 = divmod(idx, 12)
            ticks.append(mdates.date2num(datetime.datetime(year, month0 + 1, 1)))
        return np.array(ticks)


class SmartAutoDateLocator(AutoDateLocator):
    """AutoDateLocator that only anchors ticks to fixed calendar
    boundaries (interval_multiples=True) at the hour level and finer.

    Anchoring is what keeps hour-level tick labels (e.g. 2am/4am/6am)
    from changing phase while dragging/panning -- without it, tick
    positions are computed relative to the current view's exact edges,
    so a small pan shifts which hours get labeled.

    At the day level and coarser, matplotlib's own anchoring has a
    hardcoded quirk: for a 7-day tick interval it forces ticks onto the
    1st/8th/15th/22nd of each month (see AutoDateLocator.get_locator),
    which produces an uneven gap whenever a month doesn't divide evenly
    by 7, and a tick landing on the 1st gets its day number dropped by
    the formatter's "zero tick" collapsing. But plain unanchored ticks
    (interval_multiples=False) have their own problem: they're still
    computed relative to the view's current edge, so panning shifts
    their phase too -- just without the month-boundary artifact. This
    applies at the month/year level as well: a 2-month interval, say,
    still steps from dtstart=dmin, so panning past a month boundary can
    flip an Mar/May/Jul/Sep/Nov set over to Apr/Jun/Aug/Oct/Dec.

    So at DAILY/MONTHLY/YEARLY frequencies, we sidestep both: pick
    whatever interval size matplotlib's own logic would use (reusing
    its interval selection), but place those ticks on a fixed,
    calendar-agnostic grid via _FixedEpochDayLocator / 
    _FixedEpochMonthLocator instead of relative to the view or a
    monthly/yearly reset point. That's both evenly spaced *and* immune
    to phase drift while panning.

    Frequency selection itself happens independently of the
    interval_multiples flag (it's just used afterward, for how ticks are
    placed within whichever frequency gets chosen), so it's safe to
    delegate to the parent class once with the flag set the way we want
    for this range."""

    def get_locator(self, dmin, dmax):
        self.interval_multiples = True
        locator = super().get_locator(dmin, dmax)
        if self._freq == DAILY:
            self.interval_multiples = False
            base_locator = super().get_locator(dmin, dmax)
            interval = base_locator.rule._construct['interval']
            locator = _FixedEpochDayLocator(interval)
            locator.set_axis(self.axis)
        elif self._freq == MONTHLY:
            self.interval_multiples = False
            base_locator = super().get_locator(dmin, dmax)
            interval = base_locator.rule._construct['interval']
            locator = _FixedEpochMonthLocator(interval)
            locator.set_axis(self.axis)
        elif self._freq == YEARLY:
            self.interval_multiples = False
            base_locator = super().get_locator(dmin, dmax)
            interval = base_locator.rule._construct['interval']
            # Years are just a 12-month stride at the fixed-epoch level
            locator = _FixedEpochMonthLocator(interval * 12)
            locator.set_axis(self.axis)
        return locator


def strip_leading_hour_zero(text):
    """Turn '07:00 PM' / '06 PM' into '7:00 PM' / '6 PM', case-insensitive
    on AM/PM, wherever a time string appears — leading zeros on 12-hour
    clock hours read as slightly odd/robotic ('06 PM' vs '6 PM')."""
    return _LEADING_HOUR_ZERO_RE.sub(r'\1', text)


def format_unit_mathtext(unit):
    """"Bq/m3" -> "Bq/m$^3$" for matplotlib text (title, axis labels,
    legend, hover tooltip, export panel) so the exponent renders as a
    proper superscript instead of a plain trailing digit. Only Bq/m3
    has an exponent to begin with — pCi/L passes through unchanged.
    Kept separate from the plain "Bq/m3"/"pCi/L" strings used for
    threshold lookups and unit-conversion logic (get_authority_zones,
    convert_value, etc.), which must stay exactly as they are for those
    comparisons to keep working."""
    return "Bq/m$^3$" if unit == "Bq/m3" else unit


def format_unit_html(unit):
    """HTML counterpart to format_unit_mathtext, for the Qt rich-text
    stat cards ("Bq/m3" -> "Bq/m<sup>3</sup>")."""
    return "Bq/m<sup>3</sup>" if unit == "Bq/m3" else unit


class HourFriendlyDateFormatter(ConciseDateFormatter):
    """RD200 readings only ever land on the hour, so minute-level tick
    detail is never meaningful. This formatter drops the ':00' from hour
    ticks (via the 'formats' passed in at construction) and strips the
    leading zero matplotlib's strftime leaves on times like '06 PM',
    turning it into a cleaner '6 PM'. Date-level ticks (day/month/year)
    are left untouched."""
    def format_ticks(self, values):
        labels = super().format_ticks(values)
        return [strip_leading_hour_zero(lbl) for lbl in labels]


def normalize_unit(raw_unit):
    """RD200 exports sometimes use a proper superscript 3 (Bq/m³) and
    sometimes a plain '3' (Bq/m3). Normalize so downstream logic
    (which keys off exact strings) always gets one of the two
    recognized forms."""
    if not raw_unit:
        return "Bq/m3"
    cleaned = raw_unit.strip()
    if cleaned.lower().startswith("bq/m"):
        return "Bq/m3"
    if cleaned.lower().startswith("pci/l"):
        return "pCi/L"
    return cleaned


# Standard radon action/reference levels from major authoritative bodies.
# Values are stored as canonical Bq/m3 thresholds; pCi/L values are derived
# using the standard 1 pCi/L = 37 Bq/m3 conversion. These reflect commonly
# published public guidance and are provided for general reference only —
# always verify against the authority's current official guidance for
# anything beyond casual home reference.
BQ_PER_PCI = 37.0
AUTHORITIES = {
    # --- Pinned to the top of the dropdown ---
    'who': {
        'name': 'WHO',
        'low_bq': 100,   # WHO reference level
        'high_bq': 300,  # WHO maximum recommended level where 100 isn't achievable
    },
    'canada': {
        'name': 'Canada (Health Canada)',
        'low_bq': 100,   # informal "elevated, worth monitoring" zone
        'high_bq': 200,  # official Health Canada guideline (remedial action recommended)
    },
    'epa': {
        'name': 'USA (EPA)',
        'low_bq': 2 * BQ_PER_PCI,   # 2 pCi/L — EPA "consider fixing" range starts here
        'high_bq': 4 * BQ_PER_PCI,  # 4 pCi/L — EPA action level
    },
    # --- Everything else, alphabetical by display name ---
    'australia': {
        'name': 'Australia (ARPANSA)',
        'low_bq': 100,
        'high_bq': 200,
    },
    'china': {
        'name': 'China',
        'low_bq': 100,   # new-building limit
        'high_bq': 200,  # existing-building limit
    },
    'finland': {
        'name': 'Finland',
        'low_bq': 200,   # new-building reference
        'high_bq': 300,  # existing-building action level
    },
    'france': {
        'name': 'France (ASN/IRSN)',
        'low_bq': 100,
        'high_bq': 300,
    },
    'germany': {
        'name': 'Germany',
        'low_bq': 100,
        'high_bq': 300,
    },
    'ireland': {
        'name': 'Ireland (EPA)',
        'low_bq': 100,
        'high_bq': 200,
    },
    'new_zealand': {
        'name': 'New Zealand',
        'low_bq': 100,
        'high_bq': 300,
    },
    'norway': {
        'name': 'Norway',
        'low_bq': 100,
        'high_bq': 200,
    },
    'south_korea': {
        'name': 'South Korea',
        'low_bq': 100,
        'high_bq': 148,  # ~4 pCi/L equivalent, common multi-unit housing recommendation
    },
    'sweden': {
        'name': 'Sweden',
        'low_bq': 100,
        'high_bq': 200,
    },
    'switzerland': {
        'name': 'Switzerland',
        'low_bq': 100,
        'high_bq': 300,
    },
    'uk': {
        'name': 'United Kingdom (UKHSA)',
        'low_bq': 100,   # target level
        'high_bq': 200,  # action level
    },
}

# Order the dropdown should present these in: WHO/Canada/US pinned first
# (in that order), then everything else alphabetical by display name.
AUTHORITY_ORDER = ['who', 'canada', 'epa'] + sorted(
    (k for k in AUTHORITIES if k not in ('who', 'canada', 'epa')),
    key=lambda k: AUTHORITIES[k]['name']
)


def get_authority_zones(key, unit):
    """Return (thresholds, color_map, legend_labels, legend_title) for the
    given authority key ('canada', 'who', 'epa') in the given display unit."""
    info = AUTHORITIES[key]
    name = info['name']

    if unit == "pCi/L":
        low = round(info['low_bq'] / BQ_PER_PCI, 1)
        high = round(info['high_bq'] / BQ_PER_PCI, 1)
    else:
        low = info['low_bq']
        high = info['high_bq']

    def fmt(v):
        return f"{v:.1f}" if unit == "pCi/L" else f"{v:.0f}"

    thresholds = [low, high]
    color_map = [(0, low, mcolors.to_rgb("green")),
                 (low, high, mcolors.to_rgb("#FFA500")),
                 (high, float('inf'), mcolors.to_rgb("red"))]

    unit_disp = format_unit_mathtext(unit)

    if key == 'who':
        legend_labels = [
            f"0 to {fmt(low)} {unit_disp} (At/Below WHO Reference Level)",
            f"{fmt(low)} to {fmt(high)} {unit_disp} (Above Reference — Consider Mitigation)",
            f">{fmt(high)} {unit_disp} (Exceeds WHO Maximum Level)",
        ]
    elif key == 'epa':
        legend_labels = [
            f"0 to {fmt(low)} {unit_disp} (Below EPA Action Range)",
            f"{fmt(low)} to {fmt(high)} {unit_disp} (EPA: Consider Fixing)",
            f">{fmt(high)} {unit_disp} (EPA Action Level — Fix Recommended)",
        ]
    elif key == 'canada':
        legend_labels = [
            f"0 to {fmt(low)} {unit_disp} (Low)",
            f"{fmt(low)} to {fmt(high)} {unit_disp} (Elevated — Monitor)",
            f">{fmt(high)} {unit_disp} (Exceeds Health Canada Guideline)",
        ]
    else:
        # Generic wording for the additional countries — good-faith figures
        # from commonly published national guidance, not each authority's
        # own precise legal phrasing
        legend_labels = [
            f"0 to {fmt(low)} {unit_disp} (Low)",
            f"{fmt(low)} to {fmt(high)} {unit_disp} (Elevated — Monitor)",
            f">{fmt(high)} {unit_disp} (Exceeds {name} Guideline)",
        ]

    legend_title = f'RISK CATEGORY ({name})'
    return thresholds, color_map, legend_labels, legend_title


# Create main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Radon Plot")

        result = self._prompt_and_parse_file()
        if result is None:
            print("No file selected. Exiting.")
            sys.exit(1)

        self.radon_levels = result['radon_levels']
        self.timestamps = result['timestamps']
        self.timestamp_nums = result['timestamp_nums']

        print("Generating plot...")
        try:
            self.init_ui(result['unit'], result['serial_number'])
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self, "Error Building Plot",
                f"Something went wrong while building the graph:\n\n{type(e).__name__}: {e}\n\n"
                "Full details were printed to the terminal window."
            )
            sys.exit(1)

    def _prompt_and_parse_file(self):
        """Prompt for a RadonEye data file and parse it, returning a dict
        of {radon_levels, timestamps, timestamp_nums, unit, serial_number}
        — or None if the user cancels or the file can't be used.

        Shared by both the initial startup load (__init__) and later
        reloads via the toolbar's "Load Data" button (load_new_file), so
        the same parsing logic and file-format handling only exists in
        one place. Never calls sys.exit() itself — at startup, the
        caller exits if this returns None (no data to show at all); for
        a reload, the caller just leaves the currently-loaded data as-is
        and lets the user try again."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select RadonEye RD200 Data File",
            "",
            "RadonEye Data Files (*.txt *.csv);;Text files (*.txt);;CSV files (*.csv);;All files (*.*)"
        )
        if not filename:
            return None

        # Extract serial number from filename (first underscore-separated token)
        base_name = os.path.basename(filename)
        serial_number = base_name.split('_')[0] if '_' in base_name else base_name

        # Try to extract an end datetime from the filename using the classic
        # RadonEye export convention: SERIAL_YYYYMMDD HHMMSS.txt
        end_datetime = None
        date_match = re.search(r'(\d{8})[ _](\d{6})', base_name)
        if date_match:
            try:
                date_str, time_str = date_match.group(1), date_match.group(2)
                end_datetime = datetime.datetime(
                    int(date_str[0:4]), int(date_str[4:6]), int(date_str[6:8]),
                    int(time_str[0:2]), int(time_str[2:4]), int(time_str[4:6])
                )
            except ValueError:
                end_datetime = None

        # Newer exports (e.g. "SERIAL_LogData_2.txt") don't embed a date at
        # all, so fall back to the file's last-modified time and let the
        # user confirm/correct it.
        if end_datetime is None:
            try:
                mtime = os.path.getmtime(filename)
                raw_dt = datetime.datetime.fromtimestamp(mtime)
            except OSError:
                raw_dt = datetime.datetime.now()

            # Round to the nearest hour: readings only land on hour
            # boundaries, so showing the file's save time down to the
            # exact second implies more precision than we actually have.
            # The nearest hour to when the file was saved is the best
            # available guess for the last reading's timestamp.
            if raw_dt.minute >= 30:
                default_dt = raw_dt.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
            else:
                default_dt = raw_dt.replace(minute=0, second=0, microsecond=0)

            default_str = default_dt.strftime('%Y-%m-%d %H:%M:%S')
            text, ok = QInputDialog.getText(
                self,
                "Confirm End Date/Time",
                "This file's name doesn't contain a timestamp, so the date/time\n"
                "of the LAST data point can't be determined automatically.\n\n"
                "Enter it below (defaulted to the nearest hour to when the\n"
                "file was saved, since RD200 readings land on hour marks):\n"
                "Format: YYYY-MM-DD HH:MM:SS",
                text=default_str
            )
            if not ok:
                return None
            try:
                end_datetime = datetime.datetime.strptime(text.strip(), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                QMessageBox.warning(self, "Invalid Date", "Couldn't parse that date/time. Using file's last-modified time instead.")
                end_datetime = default_dt

        print(f"Serial number extracted: {serial_number}")

        # Load data and detect unit/format
        radon_levels = []
        data_count = 0
        total_points = None
        unit = "Bq/m3"
        interval_delta = datetime.timedelta(hours=1)

        try:
            with open(filename, 'r', encoding='utf-8-sig') as file:
                print("Loading data from file...")
                for line_number, raw_line in enumerate(file, 1):
                    line = raw_line.strip()
                    if not line:
                        continue

                    # Header lines look like "Key:,Value" or legacy "Key: Value"
                    if line.startswith("Unit:"):
                        unit = normalize_unit(line.split(':', 1)[1].lstrip(',').strip())
                        print(f"Unit detected: {unit}")
                        continue
                    if line.startswith("Total # of Data:"):
                        total_points = int(line.split(':', 1)[1].lstrip(',').strip())
                        print(f"Total data points set to: {total_points}")
                        continue
                    if line.startswith("Data No:"):
                        # legacy exports put the count here instead
                        rest = line.split(':', 1)[1].lstrip(',').strip()
                        if rest.isdigit():
                            total_points = int(rest)
                            print(f"Total data points set to: {total_points}")
                        continue
                    if line.startswith(("Model Name:", "S/N:", "Alarm Threshold:", "Interval:")):
                        if line.startswith("Interval:"):
                            interval_delta = parse_interval_to_timedelta(line.split(':', 1)[1].lstrip(',').strip())
                            print(f"Interval detected: {interval_delta}")
                        continue

                    # Data lines: current export is "index,value"; legacy
                    # export was "index) value [unit]"
                    m = re.match(r'^(\d+)\s*[,)]\s*(-?\d+(?:\.\d+)?)', line)
                    if m:
                        try:
                            value = float(m.group(2))
                            radon_levels.append(value)
                            data_count += 1
                            if data_count % 1000 == 0:
                                print(f"Parsed {data_count} values...")
                        except ValueError as e:
                            print(f"Failed to parse line {line_number}: '{line}' - Error: {e}")
                        continue

                print(f"Loaded {data_count} data points.")
        except Exception as e:
            print(f"Error reading file: {e}")
            QMessageBox.critical(self, "Error Reading File", f"Couldn't read this file:\n\n{e}")
            return None

        if total_points is not None and len(radon_levels) != total_points:
            print(f"Warning: Expected {total_points} data points, found {len(radon_levels)}. Check file format.")

        if len(radon_levels) == 0:
            QMessageBox.critical(self, "No Data Found", "Couldn't find any data points in this file. Please check the file format.")
            return None

        radon_levels = np.array(radon_levels)
        start_datetime = end_datetime - interval_delta * (len(radon_levels) - 1)
        timestamps = np.array([start_datetime + interval_delta * i for i in range(len(radon_levels))])
        timestamp_nums = mdates.date2num(timestamps)
        print(f"Start datetime: {start_datetime}, End datetime: {end_datetime}")

        return {
            'radon_levels': radon_levels,
            'timestamps': timestamps,
            'timestamp_nums': timestamp_nums,
            'unit': unit,
            'serial_number': serial_number,
        }

    def load_new_file(self):
        """Triggered by the toolbar's "Load Data" button — prompts for a
        new RadonEye file and, if one's successfully loaded, swaps it in
        for the currently-displayed data without needing to restart the
        app. Unlike startup, cancelling or an unparseable file just
        leaves whatever's currently on screen untouched rather than
        exiting."""
        result = self._prompt_and_parse_file()
        if result is None:
            return

        self.radon_levels = result['radon_levels']
        self.timestamps = result['timestamps']
        self.timestamp_nums = result['timestamp_nums']
        self.native_unit = result['unit']
        self.native_levels = result['radon_levels'].copy()
        self.display_unit = result['unit']
        self.unit = result['unit']
        self.serial_number = result['serial_number']

        # The unit dropdown's very items (not just its selection) depend
        # on whether the file's unit is recognized — a fixed, disabled
        # single item for an unrecognized unit, or the normal two-way
        # Bq/m3 <-> pCi/L toggle otherwise. Rebuild it fresh rather than
        # just changing the selected index, since the new file's unit
        # situation may not match the old one. Signals blocked during the
        # rebuild since self.display_unit/self.unit are already being set
        # directly above — on_unit_changed firing mid-rebuild would just
        # be redundant (and could fire against a half-built combo box).
        self.unit_combo.blockSignals(True)
        self.unit_combo.clear()
        if self.native_unit in ("Bq/m3", "pCi/L"):
            self.unit_combo.addItem("Bq/m³", "Bq/m3")
            self.unit_combo.addItem("pCi/L", "pCi/L")
            self.unit_combo.setCurrentIndex(0 if self.native_unit == "Bq/m3" else 1)
            self.unit_combo.setEnabled(True)
        else:
            self.unit_combo.addItem(self.native_unit, self.native_unit)
            self.unit_combo.setEnabled(False)
        self.unit_combo.blockSignals(False)

        # A selection from the old dataset has no meaning against the new
        # one (different timestamps entirely) — drop it rather than risk
        # showing a stale/nonsensical selected-range average
        self._last_selection_mask = None
        if getattr(self, '_selection_patch', None) is not None:
            try:
                self._selection_patch.remove()
            except Exception:
                pass
            self._selection_patch = None
        self._clear_range_edge_bubbles()

        self.render_zones()
        self.update_stats_label()
        self.canvas.draw_idle()

    def init_ui(self, unit, serial_number):
        # The unit/values actually present in the file, never changed after
        # load — used as the source of truth for unit conversion
        self.native_unit = unit
        self.native_levels = self.radon_levels.copy()

        # The unit currently being displayed — starts the same as the file's
        # native unit, but can be toggled independently via the dropdown
        self.display_unit = unit
        self.unit = unit

        self.serial_number = serial_number
        self.authority_key = AUTHORITY_ORDER[0]  # default risk standard — matches the dropdown's first entry

        # Shift-drag range selection state
        self._last_selection_mask = None
        self._selection_patch = None
        self._active_drag = None
        self._selection_start_bubble = None
        self._selection_end_bubble = None

        # Create figure and canvas
        self.figure = Figure(figsize=(12, 6), dpi=120)
        self.canvas = FigureCanvas(self.figure)

        # Create layout
        layout = QVBoxLayout()
        layout.setSpacing(0)

        # Toolbar (Home / Pan / Zoom / Save only)
        self.toolbar = TrimmedNavigationToolbar(self.canvas, self)
        # Disable the toolbar's built-in "x=... y=..." coordinate readout —
        # redundant now that hovering shows a proper tooltip with the exact
        # timestamp and reading
        self.toolbar.set_message = lambda s: None

        toolbar_label_style = "font-size: 15pt; font-weight: bold; color: #333; padding-left: 10px;"
        # Equal, generous padding on both sides for both the closed combo
        # box and its dropdown popup list
        h_pad = 16  # horizontal padding, pixels, each side
        combo_style = (
            f"QComboBox {{ font-size: 14pt; padding: 4px {h_pad}px; }}"
            f"QComboBox QAbstractItemView {{ font-size: 14pt; padding: 4px {h_pad}px; }}"
        )

        def size_combo_to_contents(combo):
            """AdjustToContents alone doesn't account for the dropdown
            popup's own padding, which is what was clipping longer entries
            like 'United Kingdom (UKHSA)' in the list even though the
            closed box looked fine. Explicitly measure the widest item's
            text and apply matching padding to both the box and the popup
            so neither clips and the left/right spacing matches."""
            fm = combo.fontMetrics()
            text_width = max(fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count()))
            arrow_and_frame_allowance = 40  # room for the dropdown arrow + border
            full_width = text_width + h_pad * 2 + arrow_and_frame_allowance
            combo.setMinimumWidth(full_width)
            combo.view().setMinimumWidth(full_width)

        risk_label = QLabel("Risk Standard: ")
        risk_label.setStyleSheet(toolbar_label_style)
        self.toolbar.addWidget(risk_label)

        self.authority_combo = QComboBox()
        for auth_key in AUTHORITY_ORDER:
            self.authority_combo.addItem(AUTHORITIES[auth_key]['name'], auth_key)
        self.authority_combo.setStyleSheet(combo_style)
        self.authority_combo.currentIndexChanged.connect(self.on_authority_changed)
        size_combo_to_contents(self.authority_combo)
        self.toolbar.addWidget(self.authority_combo)

        unit_label = QLabel("    Display Unit: ")
        unit_label.setStyleSheet(toolbar_label_style)
        self.toolbar.addWidget(unit_label)

        self.unit_combo = QComboBox()
        if self.native_unit in ("Bq/m3", "pCi/L"):
            self.unit_combo.addItem("Bq/m³", "Bq/m3")
            self.unit_combo.addItem("pCi/L", "pCi/L")
            self.unit_combo.setCurrentIndex(0 if self.native_unit == "Bq/m3" else 1)
        else:
            # Unrecognized unit from the file — conversion isn't defined,
            # so just show it as the sole, fixed option
            self.unit_combo.addItem(self.native_unit, self.native_unit)
            self.unit_combo.setEnabled(False)
        self.unit_combo.setStyleSheet(combo_style)
        self.unit_combo.currentIndexChanged.connect(self.on_unit_changed)
        size_combo_to_contents(self.unit_combo)
        self.toolbar.addWidget(self.unit_combo)

        # Toolbar stays a fixed height regardless of window resizing —
        # only the graph itself should grow
        self.toolbar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self.toolbar, 0)

        # Graph — gets all the extra space on window resize (stretch=1),
        # while every other widget in this layout stays a fixed height
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.canvas, 1)

        # Period-average + selected-range "cards" — all four in one row,
        # each in its own bordered box with a bold, larger readout
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(10, 8, 10, 8)
        stats_row.setSpacing(10)
        self.avg_24h_card = self._make_stat_card()
        self.avg_30d_card = self._make_stat_card()
        self.avg_365d_card = self._make_stat_card()
        self.selection_card = self._make_stat_card()
        stats_row.addWidget(self.avg_24h_card)
        stats_row.addWidget(self.avg_30d_card)
        stats_row.addWidget(self.avg_365d_card)
        stats_row.addWidget(self.selection_card)

        # Lock every card to the same fixed height up front, sized for
        # the tallest content any of them will ever show (the
        # post-selection card, which has 4 lines including the "Hold
        # Shift..." reminder). Without this, the row's height is driven
        # by whatever's in it *right now* -- since the selection card
        # starts life showing its shorter 2-line placeholder tip and
        # only grows to 4 lines once a selection is made, the whole
        # averages row would visibly grow/shift at that moment. Sizing
        # every card to the worst case from the start means nothing
        # ever needs to resize later; the card just centers whatever
        # shorter content it currently has within that fixed space.
        card_max_height = self._measure_max_stat_card_height()
        for card in (self.avg_24h_card, self.avg_30d_card, self.avg_365d_card, self.selection_card):
            card.setFixedHeight(card_max_height)

        stats_container = QWidget()
        stats_container.setLayout(stats_row)
        stats_container.setStyleSheet("background-color: #fafafa; border-top: 1px solid #ddd;")
        # Fixed height — these cards should stay a consistent, readable
        # size no matter how tall the window gets; only the graph grows
        stats_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # A fixed pixel gap here (rather than relying on matplotlib's own
        # internal bottom margin) keeps a consistent visual breathing room
        # between the "DATE AND TIME" title and the averages row, entirely
        # independent of anything happening inside the plot/canvas above it.
        layout.addSpacing(14)
        layout.addWidget(stats_container, 0)

        # Create widget with layout
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # Create main axes for the plot
        self.ax = self.figure.add_subplot(111)

        # Create the left/right bookend bars once, up front — they're
        # figure-level artists that persist across every render_zones
        # rebuild (see _create_edge_bars for why), so they only need to
        # be created a single time here, not inside render_zones itself
        self._create_edge_bars()

        # Adjust margins to reserve space at the top for buttons
        # Note: top/bottom margins are enforced in render_zones (after its
        # tight_layout() call), since tight_layout() would otherwise reset
        # them back to snug defaults on every redraw

        # Draw the plot for the first time using the default authority
        self.render_zones()
        # Position the floating Home button now too (not just on later
        # resizes) — the canvas's size at this point may not be its
        # final laid-out size yet, but this avoids a visible flash at
        # Qt's default (0, 0) child-widget position before the window
        # is actually shown; _on_resize corrects it once real sizing
        # kicks in.
        self._position_home_overlay_button()

    def on_unit_changed(self):
        self.display_unit = self.unit_combo.currentData()
        self.unit = self.display_unit
        self.radon_levels = self.convert_levels(self.native_levels, self.native_unit, self.display_unit)
        self.render_zones()
        self.canvas.draw_idle()

    @staticmethod
    def convert_levels(values, from_unit, to_unit):
        if from_unit == to_unit:
            return values.copy()
        if from_unit == "Bq/m3" and to_unit == "pCi/L":
            return values / BQ_PER_PCI
        if from_unit == "pCi/L" and to_unit == "Bq/m3":
            return values * BQ_PER_PCI
        return values.copy()  # unrecognized combination — pass through unchanged

    def on_authority_changed(self):
        self.authority_key = self.authority_combo.currentData()
        self.render_zones()
        self.canvas.draw_idle()

    def _make_stat_card(self):
        card = QLabel("")
        card.setAlignment(Qt.AlignCenter)
        card.setStyleSheet(
            "background-color: white; border: 1px solid #999; border-radius: 6px; padding: 8px 12px;"
        )
        return card

    def _measure_max_stat_card_height(self):
        """Render the tallest content any stat card will ever show (the
        post-selection card's 4-line layout — title, value, date-range
        meta, and the "Hold Shift..." reminder) into a throwaway card
        using the exact same stylesheet, and return its natural height.
        Called once at startup so every card can be locked to this
        height from the very first render, rather than sizing to
        whatever's showing right now and growing later."""
        probe = self._make_stat_card()
        probe.setText(
            "<div style='text-align:center;'>"
            "<span style='font-size:12pt; font-weight:bold; color:#555;'>SELECTED RANGE AVERAGE</span>"
            "<div style='height:6px;'></div>"
            "<span style='font-size:23pt; font-weight:bold; color:#111;'>999.9 Bq/m<sup>3</sup></span>"
            "<div style='height:2px;'></div>"
            "<span style='font-size:10pt; color:#333;'>2026-01-01 12:00 PM &ndash; 2026-01-01 12:00 PM (9999 readings)</span>"
            "<div style='height:16px;'>&nbsp;</div>"
            "<span style='font-size:11pt; color:#666;'>(Hold Shift and drag to select a different range)</span>"
            "</div>"
        )
        probe.setWordWrap(False)
        height = probe.sizeHint().height()
        probe.deleteLater()
        return height

    def update_stats_label(self):
        last_time = self.timestamps[-1]
        first_time = self.timestamps[0]
        total_days = (last_time - first_time).total_seconds() / 86400

        def period_avg(days):
            cutoff = last_time - datetime.timedelta(days=days)
            mask = self.timestamps >= cutoff
            if not mask.any():
                return None
            return float(self.radon_levels[mask].mean())

        def card_html(title, avg, days_wanted):
            if avg is None:
                value_html = "n/a"
            else:
                covered = min(total_days, days_wanted)
                note = "" if total_days >= days_wanted else f" <span style='font-size:9pt; color:#888;'>({covered:.0f}d avail.)</span>"
                value_html = f"{avg:.1f} {format_unit_html(self.unit)}{note}"
            return (
                f"<div style='text-align:center;'>"
                f"<span style='font-size:12pt; font-weight:bold; color:#555;'>{title}</span>"
                f"<div style='height:6px;'></div>"
                f"<span style='font-size:23pt; font-weight:bold; color:#111;'>{value_html}</span>"
                f"</div>"
            )

        self.avg_24h_card.setText(card_html("24-HOUR AVERAGE", period_avg(1), 1))
        self.avg_30d_card.setText(card_html("30-DAY AVERAGE", period_avg(30), 30))
        self.avg_365d_card.setText(card_html("1-YEAR AVERAGE", period_avg(365), 365))

        # Only reset the selection card's placeholder text the first time —
        # once the user has made a selection, don't overwrite it just
        # because the dropdowns changed (re-render it in the new unit instead)
        if getattr(self, '_last_selection_mask', None) is None:
            self.selection_card.setText(self._selection_tip_html())
        else:
            self._render_selection_card()

    def _compute_export_stat_values(self):
        """Same numbers shown in the on-screen averages cards, computed
        fresh here rather than parsed back out of their HTML — used by
        export_report to build a matching panel drawn as matplotlib
        artists instead of Qt widgets.

        Each card is returned as a dict of its individual lines (title,
        main value, and an optional smaller note/detail/hint) rather
        than one pre-joined string, so _draw_export_stats_panel can give
        each line its own size/weight/color — matching how the on-screen
        HTML cards style the "(365d avail.)" note and the selection
        card's date-range/hint lines distinctly smaller and lighter than
        the main value, instead of everything coming out the same
        bold/large style crammed into a single line."""
        last_time = self.timestamps[-1]
        total_days = (last_time - self.timestamps[0]).total_seconds() / 86400

        def period_avg(days):
            cutoff = last_time - datetime.timedelta(days=days)
            mask = self.timestamps >= cutoff
            if not mask.any():
                return None
            return float(self.radon_levels[mask].mean())

        def card(title, avg, days_wanted):
            if avg is None:
                return {'title': title, 'value': 'n/a'}
            note = None
            if total_days < days_wanted:
                note = f"({total_days:.0f}d avail.)"
            return {'title': title, 'value': f"{avg:.1f} {format_unit_mathtext(self.unit)}", 'note': note}

        cards = [
            card("24-HOUR AVERAGE", period_avg(1), 1),
            card("30-DAY AVERAGE", period_avg(30), 30),
            card("1-YEAR AVERAGE", period_avg(365), 365),
        ]

        mask = getattr(self, '_last_selection_mask', None)
        if mask is not None and mask.any():
            avg = float(self.radon_levels[mask].mean())
            count = int(mask.sum())
            start_dt = strip_leading_hour_zero(self.timestamps[mask][0].strftime('%Y-%m-%d %I:%M %p'))
            end_dt = strip_leading_hour_zero(self.timestamps[mask][-1].strftime('%Y-%m-%d %I:%M %p'))
            cards.append({
                'title': "SELECTED RANGE AVERAGE",
                'value': f"{avg:.1f} {format_unit_mathtext(self.unit)}",
                'detail': f"{start_dt} \u2013 {end_dt} ({count} readings)",
            })
        else:
            cards.append({
                'title': "SELECTED RANGE AVERAGE",
                'value': "\u2013",
            })
        return cards

    def _draw_export_stats_panel(self, stats_height_in):
        """Draw a row of stat boxes as plain matplotlib Rectangle/Text
        artists, positioned in the blank strip reserved at the very
        bottom of the (temporarily enlarged) export figure. Matches the
        on-screen averages row's content, but built from vector
        primitives so it stays real vector output in PDF/SVG exports
        rather than a rasterized copy of the Qt widgets.

        Each card's block of lines is centered around the card's own
        vertical middle, based on how many lines *that* card actually
        has -- a fixed set of y-positions used for every card regardless
        of its line count left short cards (like the 2-line 24-hour
        average) looking top-heavy, since the unused lower slots just
        went blank instead of the content re-centering to fill the space.

        The detail line (selection date range + reading count) varies a
        lot in length depending on what's actually selected, so a fixed
        font size that fits a short range can easily overflow the card's
        width for a longer one. Each line's actual rendered width gets
        measured after being drawn, via the same canvas renderer used
        for on-screen rendering, and shrunk to fit if it's wider than
        the card (with a little side padding) -- rather than guessing a
        size that happens to work for whatever range was tested."""
        fig = self.figure
        fig_w_in, fig_h_in = fig.get_size_inches()
        self._export_stats_artists = []
        try:
            renderer = self.canvas.get_renderer()
        except Exception:
            renderer = None

        left_in = self.LEFT_MARGIN_INCHES
        right_in = self.RIGHT_MARGIN_INCHES
        usable_w_in = fig_w_in - left_in - right_in
        gap_in = 0.15
        n = 4
        card_w_in = (usable_w_in - gap_in * (n - 1)) / n
        card_h_in = max(0.4, stats_height_in - 0.15)
        card_y0_in = (stats_height_in - card_h_in) / 2
        max_text_w_in = card_w_in - 0.16  # a little side padding within the card

        for i, info in enumerate(self._compute_export_stat_values()):
            x0_in = left_in + i * (card_w_in + gap_in)
            x0_frac = x0_in / fig_w_in
            w_frac = card_w_in / fig_w_in
            y0_frac = card_y0_in / fig_h_in
            h_frac = card_h_in / fig_h_in
            cx = x0_frac + w_frac / 2

            rect = Rectangle(
                (x0_frac, y0_frac), w_frac, h_frac, transform=fig.transFigure,
                facecolor='white', edgecolor='#999999', linewidth=1.0, zorder=9
            )
            fig.add_artist(rect)
            self._export_stats_artists.append(rect)

            lines = [
                (info['title'], 9, 'bold', '#555555'),
                (info['value'], 15, 'bold', '#111111'),
            ]
            if info.get('note'):
                lines.append((info['note'], 7, 'normal', '#888888'))
            if info.get('detail'):
                lines.append((info['detail'], 6.5, 'normal', '#666666'))

            line_gap_frac = 0.23
            top_y = 0.5 + line_gap_frac * (len(lines) - 1) / 2
            for j, (text, fontsize, weight, color) in enumerate(lines):
                y_rel = top_y - j * line_gap_frac
                t = fig.text(
                    cx, y0_frac + h_frac * y_rel, text, transform=fig.transFigure,
                    ha='center', va='center', fontsize=fontsize, fontweight=weight,
                    color=color, zorder=10
                )
                self._export_stats_artists.append(t)

                if renderer is not None and text:
                    bbox_in = t.get_window_extent(renderer=renderer).transformed(fig.dpi_scale_trans.inverted())
                    if bbox_in.width > max_text_w_in > 0:
                        t.set_fontsize(max(5.0, fontsize * (max_text_w_in / bbox_in.width)))

    def _clear_export_stats_panel(self):
        for artist in getattr(self, '_export_stats_artists', []):
            try:
                artist.remove()
            except Exception:
                pass
        self._export_stats_artists = []

    def export_report(self, path, fmt):
        """Save the plot plus a stats panel as one file, entirely through
        matplotlib's own savefig — so PDF/SVG come out as true vector
        output (real paths and text, not a rasterized screenshot), and
        PNG/JPEG come out consistent with them rather than a separate
        raster-only code path.

        Works by temporarily growing the figure downward: the existing
        BOTTOM_MARGIN_INCHES grows by exactly the added height, so
        everything above it (the plot, edge bars, tick marks, title)
        keeps the exact same absolute size/position it has on screen —
        _apply_fixed_margins already computes every position from
        instance attributes divided by the figure's current size, so
        just changing that one instance attribute and re-running it
        reflows everything correctly for the new size. The added strip
        at the very bottom is then guaranteed blank, and is exactly
        where the stats panel gets drawn. Both the size and margin are
        restored (and the normal layout re-applied) in `finally`, so
        the on-screen figure is left exactly as it was.

        Also switches the PDF backend to the standard PDF "Core 14"
        fonts (Helvetica et al.) instead of embedding DejaVu Sans.
        Embedding ran into two different problems depending on how it
        was configured: Type 3 (matplotlib's default) embeds glyphs as
        bitmap-like procedures that some PDF viewers substitute with a
        fallback font entirely; Type 42 embeds real outlines but showed
        visibly off kerning in testing. Core 14 fonts sidestep both --
        they're referenced by name rather than embedded, so every PDF
        viewer uses its own correctly-kerned built-in implementation.
        The visual tradeoff is a Helvetica-style look rather than
        DejaVu Sans specifically, which is a reasonable, standard look
        for this kind of report. Doesn't affect PNG/JPEG, which don't
        embed fonts at all.

        One more instance attribute needs the same "add stats_height_in"
        treatment: XLABEL_BOTTOM_OFFSET_INCHES pins the "DATE AND TIME"
        label to a fixed distance from the figure's bottom edge. Left
        unchanged, that fixed distance now lands inside the newly-added
        stats panel strip instead of in the (shifted-up) gap between the
        axes and the panel, overlapping the stats boxes."""
        fig = self.figure
        orig_w_in, orig_h_in = fig.get_size_inches()
        orig_bottom_margin = self.BOTTOM_MARGIN_INCHES
        orig_xlabel_offset = self.XLABEL_BOTTOM_OFFSET_INCHES
        stats_height_in = 1.05
        try:
            fig.set_size_inches(orig_w_in, orig_h_in + stats_height_in, forward=False)
            self.BOTTOM_MARGIN_INCHES = orig_bottom_margin + stats_height_in
            self.XLABEL_BOTTOM_OFFSET_INCHES = orig_xlabel_offset + stats_height_in
            self._apply_fixed_margins()
            self._draw_export_stats_panel(stats_height_in)
            with matplotlib.rc_context({'pdf.fonttype': 42, 'pdf.use14corefonts': True, 'ps.fonttype': 42}):
                fig.savefig(path, format=fmt, facecolor='white')
        finally:
            self._clear_export_stats_panel()
            fig.set_size_inches(orig_w_in, orig_h_in, forward=False)
            self.BOTTOM_MARGIN_INCHES = orig_bottom_margin
            self.XLABEL_BOTTOM_OFFSET_INCHES = orig_xlabel_offset
            self._apply_fixed_margins()
            self.canvas.draw_idle()

    def _selection_tip_html(self):
        return (
            "<div style='text-align:center;'>"
            "<span style='font-size:12pt; font-weight:bold; color:#555;'>SELECTED RANGE AVERAGE</span>"
            "<div style='height:16px;'>&nbsp;</div>"
            "<span style='font-size:11pt; color:#888;'>(Hold Shift and drag on the graph to select a range)</span>"
            "</div>"
        )

    def _render_selection_card(self):
        mask = self._last_selection_mask
        avg = float(self.radon_levels[mask].mean())
        count = int(mask.sum())
        start_dt = strip_leading_hour_zero(self.timestamps[mask][0].strftime('%Y-%m-%d %I:%M %p'))
        end_dt = strip_leading_hour_zero(self.timestamps[mask][-1].strftime('%Y-%m-%d %I:%M %p'))
        self.selection_card.setText(
            f"<div style='text-align:center;'>"
            f"<span style='font-size:12pt; font-weight:bold; color:#555;'>SELECTED RANGE AVERAGE</span>"
            f"<div style='height:6px;'></div>"
            f"<span style='font-size:23pt; font-weight:bold; color:#111;'>{avg:.1f} {format_unit_html(self.unit)}</span>"
            f"<div style='height:2px;'></div>"
            f"<span style='font-size:10pt; color:#333;'>{start_dt} &ndash; {end_dt} ({count} readings)</span>"
            # Once a selection exists, the card's real estate is doing
            # double duty showing actual results — but it's easy to
            # forget how the selection was made in the first place,
            # especially coming back to the app later. Keeping a small
            # reminder here (rather than only showing it before the
            # first selection) means the user never has to hunt for how
            # to make a new one.
            f"<div style='height:16px;'>&nbsp;</div>"
            f"<span style='font-size:11pt; color:#666;'>(Hold Shift and drag to select a different range)</span>"
            f"</div>"
        )

    MIN_ZOOM_HOURS = 6  # never let the visible x-range get narrower than this

    def _on_xlim_changed(self, ax):
        # Re-entrancy guard: the clamp below calls set_xlim(), which would
        # otherwise trigger this same callback again recursively
        if getattr(self, '_clamping_xlim', False):
            self._update_range_subtitle()
            return

        xlim = ax.get_xlim()
        min_width_days = self.MIN_ZOOM_HOURS / 24.0
        width_days = xlim[1] - xlim[0]
        if width_days < min_width_days - 1e-9:
            center = (xlim[0] + xlim[1]) / 2
            new_lo, new_hi = center - min_width_days / 2, center + min_width_days / 2
            # Keep the clamped window within the actual data range
            data_lo, data_hi = self.timestamp_nums[0], self.timestamp_nums[-1]
            if new_lo < data_lo:
                new_lo, new_hi = data_lo, data_lo + min_width_days
            if new_hi > data_hi:
                new_hi, new_lo = data_hi, data_hi - min_width_days
            self._clamping_xlim = True
            try:
                ax.set_xlim(new_lo, new_hi)
            finally:
                self._clamping_xlim = False

        # Fires on every zoom, pan, scroll, and Home — keeps the edge bars'
        # date/time labels permanently in sync with whatever's actually visible
        self._update_range_subtitle()

    def _update_range_subtitle(self):
        xlim = self.ax.get_xlim()
        lo, hi = min(xlim), max(xlim)
        # Clamp to the actual data range — xlim can briefly extend beyond
        # the data during a zoom-out past the edges
        lo = max(lo, self.timestamp_nums[0])
        hi = min(hi, self.timestamp_nums[-1])
        try:
            lo_dt = mdates.num2date(lo)
            hi_dt = mdates.num2date(hi)
            # The "Showing: ..." line under the title was retired in favor
            # of folding the same start/end date *and* time into the
            # existing rotated edge bars beside the graph (see just below)
            # -- one less thing competing for space right under the title,
            # and the edge bars were already showing half of this info.
            if hasattr(self, 'corner_date_left'):
                self.corner_date_left.set_text(strip_leading_hour_zero(lo_dt.strftime('%b %d, %Y %I:%M %p')))
                self.corner_date_right.set_text(strip_leading_hour_zero(hi_dt.strftime('%b %d, %Y %I:%M %p')))
                self._recenter_edge_bar_texts()
        except (ValueError, OverflowError):
            if hasattr(self, 'corner_date_left'):
                self.corner_date_left.set_text("")
                self.corner_date_right.set_text("")
                self._recenter_edge_bar_texts()
        self.canvas.draw_idle()

    # Constant physical padding (inches) above the title and below the
    # date/time label, matching the original look at the app's default
    # window size. Kept as inches (not a fraction) specifically so this
    # whitespace stays visually constant regardless of how tall the window
    # is stretched — a fraction-based margin would otherwise grow right
    # along with the window.
    TOP_MARGIN_INCHES = 0.87  # matches LEFT_MARGIN_INCHES
    BOTTOM_MARGIN_INCHES = 0.96
    LEFT_MARGIN_INCHES = 0.95
    RIGHT_MARGIN_INCHES = 0.15
    EDGE_BAR_WIDTH_INCHES = 0.3  # width of the left/right date "bookend" bars
    # Where the "DATE AND TIME" x-axis title sits, measured from the
    # very bottom of the figure — fixed regardless of how many lines
    # the tick labels below the axes take up. Left as-is (using
    # matplotlib's automatic tick-relative labelpad), the title's
    # vertical position depends on the tick labels' own height, which
    # changes based on the current zoom level (e.g. a single-line
    # "Nov 2025" vs a two-line "Nov 06\n2025"). That made the title
    # visibly shift up and down as you zoomed/panned, and crowded the
    # averages cards below whenever the taller two-line ticks were
    # showing. Pinning it to a fixed distance from the figure's bottom
    # edge instead keeps it stationary and leaves consistent breathing
    # room below it no matter what the tick labels are doing above it.
    XLABEL_BOTTOM_OFFSET_INCHES = 0.20

    def _position_xlabel(self):
        """Pin the "DATE AND TIME" title to a fixed distance from the
        figure's bottom edge (see XLABEL_BOTTOM_OFFSET_INCHES) instead
        of letting matplotlib place it relative to the tick labels'
        own (variable) height. Called after every margin/size change
        (render_zones and _apply_fixed_margins) so it stays correct
        across resizes too, not just full re-renders."""
        if not hasattr(self, 'ax'):
            return
        fig_height_in = self.figure.get_figheight()
        if fig_height_in <= 0:
            return
        y_frac = self.XLABEL_BOTTOM_OFFSET_INCHES / fig_height_in
        self.ax.xaxis.set_label_coords(0.5, y_frac, transform=self.figure.transFigure)

    def _apply_fixed_margins(self):
        fig_height_in = self.figure.get_figheight()
        fig_width_in = self.figure.get_figwidth()
        if fig_height_in <= 0 or fig_width_in <= 0:
            return
        top_frac = 1 - (self.TOP_MARGIN_INCHES / fig_height_in)
        bottom_frac = self.BOTTOM_MARGIN_INCHES / fig_height_in
        # The bookend bars sit outside the plotted data, in a strip
        # immediately next to the axes — so the axes' own left/right edges
        # need to leave room for the bar width on top of the usual margin,
        # or the plot would render underneath the bars instead of beside them
        left_frac = (self.LEFT_MARGIN_INCHES + self.EDGE_BAR_WIDTH_INCHES) / fig_width_in
        right_frac = 1 - ((self.RIGHT_MARGIN_INCHES + self.EDGE_BAR_WIDTH_INCHES) / fig_width_in)
        # Guard rails so a very small window can't invert or collapse the
        # plot area entirely
        top_frac = max(0.5, min(0.95, top_frac))
        bottom_frac = max(0.05, min(0.4, bottom_frac))
        left_frac = max(0.03, min(0.35, left_frac))
        right_frac = max(0.65, min(0.999, right_frac))
        self.figure.subplots_adjust(top=top_frac, bottom=bottom_frac, left=left_frac, right=right_frac)
        self._position_edge_bars()
        self._position_xlabel()

    def _create_edge_bars(self):
        """Create the left/right 'bookend' bars showing the visible date
        range. These are figure-level artists (transform=transFigure), not
        axes-level — that's what lets them sit outside the plotted data
        area, in the margin, rather than overlapping it. Called once from
        init_ui; ax.cla() (which runs on every render_zones rebuild) only
        clears axes-level children, so these persist and just need their
        position/text refreshed afterward via _position_edge_bars."""
        bar_color = '#37474F'
        self.corner_bar_left = Rectangle(
            (0, 0), 0, 0, transform=self.figure.transFigure,
            facecolor=bar_color, edgecolor='none', alpha=0.88, zorder=9, clip_on=False
        )
        self.corner_bar_right = Rectangle(
            (0, 0), 0, 0, transform=self.figure.transFigure,
            facecolor=bar_color, edgecolor='none', alpha=0.88, zorder=9, clip_on=False
        )
        self.figure.add_artist(self.corner_bar_left)
        self.figure.add_artist(self.corner_bar_right)

        # Right side rotated the opposite way (270 vs 90) so the two bars
        # mirror each other rather than both reading in the same direction
        self.corner_date_left = self.figure.text(
            0, 0, "", transform=self.figure.transFigure, ha='center', va='center',
            rotation=90, fontsize=9, fontweight='bold', color='white', zorder=10
        )
        self.corner_date_right = self.figure.text(
            0, 0, "", transform=self.figure.transFigure, ha='center', va='center',
            rotation=270, fontsize=9, fontweight='bold', color='white', zorder=10
        )

    def _position_edge_bars(self):
        """Place the left/right bookend bars flush against the actual
        plotted-data boundary (the axes edge) — not the outer window
        edge — so they read as part of the graph itself. To keep them
        from covering the y-axis tick numbers (which matplotlib draws
        immediately outside the axes edge by default, in the same spot),
        those tick numbers are pushed further out via increased tick
        padding (see the y-axis tick_params call in render_zones),
        freeing up exactly the bar's width right next to the axes for
        the bar to occupy instead. Spans the axes' full height, aligned
        exactly to the axes boundary. Safe to call before the bars exist
        yet (e.g. during the very first render)."""
        if not hasattr(self, 'corner_bar_left'):
            return
        pos = self.ax.get_position()
        fig_width_in = self.figure.get_figwidth()
        bar_w_frac = self.EDGE_BAR_WIDTH_INCHES / fig_width_in if fig_width_in > 0 else 0
        fig_height_in = self.figure.get_figheight()
        # Shrink very slightly inward from the exact axes bounds — the
        # axes spine's own stroke width otherwise makes the bar look
        # about a pixel too tall (over-extending past the actual plotted
        # grid area top/bottom)
        inset_frac = (0.5 / self.figure.dpi) / fig_height_in if fig_height_in > 0 else 0
        bar_y0 = pos.y0 + inset_frac
        bar_height = pos.height - 2 * inset_frac

        # Flush against the actual axes edges — the tick numbers have
        # been pushed further out (see tick_params pad) to leave exactly
        # this much room clear
        self.corner_bar_left.set_bounds(pos.x0 - bar_w_frac, bar_y0, bar_w_frac, bar_height)
        self.corner_bar_right.set_bounds(pos.x1, bar_y0, bar_w_frac, bar_height)

        left_cx = pos.x0 - bar_w_frac / 2
        right_cx = pos.x1 + bar_w_frac / 2

        # Small deliberate push toward the middle of the chart (i.e.
        # toward the plot area, not the outer edge of the window) — a
        # visual-balance tweak on top of the ink-based centering in
        # _recenter_edge_bar_texts. Given as a fraction of the bar's
        # width; increase for a bigger push, flip the sign to push the
        # other way instead.
        EDGE_BAR_TEXT_INWARD_NUDGE_FRACTION = 0.10
        inward_nudge = EDGE_BAR_TEXT_INWARD_NUDGE_FRACTION * bar_w_frac
        left_cx += inward_nudge
        right_cx -= inward_nudge

        cy = pos.y0 + pos.height / 2
        self._edge_bar_left_cx = left_cx
        self._edge_bar_right_cx = right_cx
        self._edge_bar_cy = cy
        self._recenter_edge_bar_texts()

        self._draw_left_tick_marks()

    def _recenter_edge_bar_texts(self):
        """Position the rotated date labels so they're truly centered
        on the bookend bar in both directions — along its length (the
        text's own reading direction before rotation) and across its
        width (the text's own line-height/ascent-descent direction
        before rotation, which becomes the left-right screen axis once
        rotated 90/270 degrees).

        ha='center'/va='center' alone aren't enough here: matplotlib
        centers text using the font's abstract metrics for each of
        those axes (string-width and ascent/descent), not the actual
        ink of the rendered glyphs. That gap is normally too small to
        notice, but once rotated it can show up as a visible offset in
        either direction — along the bar's length or across its width
        — and how far off depends on the specific font/platform.

        To make this robust, we measure the actual rendered bounding
        box after an initial center placement, then nudge the anchor by
        however far that real ink is from the target center on both
        axes. Called after every position/text change (see
        _position_edge_bars and _update_range_subtitle) so it stays
        correct across resizes and as the date text itself changes."""
        if not hasattr(self, 'corner_date_left'):
            return
        cy = getattr(self, '_edge_bar_cy', None)
        left_cx = getattr(self, '_edge_bar_left_cx', None)
        right_cx = getattr(self, '_edge_bar_right_cx', None)
        if cy is None or left_cx is None or right_cx is None:
            return
        try:
            renderer = self.canvas.get_renderer()
        except Exception:
            renderer = None
        for text_artist, cx in ((self.corner_date_left, left_cx), (self.corner_date_right, right_cx)):
            # Start from the font-metric center as a baseline
            text_artist.set_position((cx, cy))
            if renderer is None or not text_artist.get_text():
                continue
            bbox = text_artist.get_window_extent(renderer=renderer)
            bbox_fig = bbox.transformed(self.figure.transFigure.inverted())
            actual_center_x = (bbox_fig.x0 + bbox_fig.x1) / 2
            actual_center_y = (bbox_fig.y0 + bbox_fig.y1) / 2
            offset_x = cx - actual_center_x
            offset_y = cy - actual_center_y
            text_artist.set_position((cx + offset_x, cy + offset_y))

    def _draw_left_tick_marks(self):
        """Draw the y-axis tick marks ourselves, as figure-level Line2D
        artists — the same layer the bookend bar lives in — so they're
        guaranteed to render correctly relative to the bar regardless of
        zorder quirks between axes-level and figure-level artists (see
        the note in render_zones where the built-in tick marks are
        hidden). Drawn in the gap between the bar's outer edge and the
        tick numbers. Old marks are removed and redrawn each call, since
        the number of ticks and their y-positions change with the view."""
        for line in getattr(self, '_manual_tick_lines', []):
            try:
                line.remove()
            except Exception:
                pass
        self._manual_tick_lines = []

        if not hasattr(self, 'corner_bar_left'):
            return

        pos = self.ax.get_position()
        fig_width_in = self.figure.get_figwidth()
        if fig_width_in <= 0:
            return
        bar_outer_x = pos.x0 - (self.EDGE_BAR_WIDTH_INCHES / fig_width_in)
        mark_len_frac = (8.0 / 72) / fig_width_in  # 8pt visible tick mark

        ymin, ymax = self.ax.get_ylim()
        if ymax == ymin:
            return
        for tick_val in self.ax.get_yticks():
            if tick_val < ymin or tick_val > ymax:
                continue
            y_frac = pos.y0 + ((tick_val - ymin) / (ymax - ymin)) * pos.height
            line = Line2D(
                [bar_outer_x - mark_len_frac, bar_outer_x], [y_frac, y_frac],
                transform=self.figure.transFigure, color='#333333',
                linewidth=1.2, zorder=9.5, clip_on=False
            )
            self.figure.add_artist(line)
            self._manual_tick_lines.append(line)

    def _on_resize(self, event):
        self._apply_fixed_margins()
        self._position_home_overlay_button()
        self.canvas.draw_idle()

    def _position_home_overlay_button(self):
        """Place the floating Home button just inside the axes' own
        top-left corner, rather than the canvas widget's — the canvas
        includes a substantial left margin for the y-axis labels and
        the dark rotated-date edge bar, so anchoring to the canvas's
        raw top-left would land the button over those instead of over
        the actual plot.

        ax.get_position() gives the axes' bounding box as a figure
        FRACTION (0-1), which is resolution/DPI-independent — no need
        to reconcile matplotlib's display-coordinate space (device
        pixels, origin bottom-left) against Qt's own widget coordinate
        space (logical pixels, origin top-left); just multiply the
        fraction directly by the canvas's own logical width/height,
        flipping the y-fraction since figure-fraction increases upward
        while Qt's widget coordinates increase downward.

        Called once (from init_ui, after the toolbar/canvas exist) and
        again on every resize: the axes' fixed inches-based margins
        (see _apply_fixed_margins) work out to a constant pixel offset
        most of the time, but the guard-rail clamps in there for very
        small windows mean it isn't *always* perfectly constant, so
        this stays correct rather than assuming so."""
        toolbar = getattr(self, 'toolbar', None)
        button = getattr(toolbar, 'home_overlay_button', None)
        if button is None:
            return
        pos = self.ax.get_position()
        w = self.canvas.width()
        h = self.canvas.height()
        margin = 8
        x = pos.x0 * w + margin
        y = (1 - pos.y1) * h + margin
        button.move(int(x), int(y))

    def _on_ylim_changed(self, ax):
        # Fires whenever the visible y-range actually changes (drag-pan,
        # the right-drag interactive zoom box, or programmatic set_ylim
        # calls). Redraw the manual tick marks so they stay lined up with
        # the tick number labels, which matplotlib repositions on its own.
        self._draw_left_tick_marks()
        self.canvas.draw_idle()

    def _on_draw_style_ticks(self, event):
        # Re-entrancy guard: forcing a redraw inside a draw_event handler
        # would otherwise trigger this same handler again recursively
        if getattr(self, '_styling_ticks', False):
            return
        self._styling_ticks = True
        try:
            changed = False
            for label in self.ax.get_xticklabels():
                text = label.get_text()
                text_upper = text.upper()
                is_time = ('AM' in text_upper) or ('PM' in text_upper)

                # No bold anywhere anymore — every tick (time, day, month,
                # year, including January) is regular weight. Size still
                # distinguishes the coarser date-level ticks from the
                # finer time-level ones.
                desired_weight = 'normal'
                desired_size = 9 if is_time else 10

                if label.get_fontweight() != desired_weight or label.get_fontsize() != desired_size:
                    label.set_fontweight(desired_weight)
                    label.set_fontsize(desired_size)
                    changed = True

            if changed:
                self.canvas.draw()
        finally:
            self._styling_ticks = False

    def _current_selection_bounds(self):
        """Return (xmin, xmax) in data coords for the current selection, or
        None if nothing is selected. Derived from the stored mask rather
        than kept as separate state, so there's a single source of truth."""
        if self._last_selection_mask is None:
            return None
        xs = self.timestamp_nums[self._last_selection_mask]
        return float(xs.min()), float(xs.max())

    def _update_range_preview(self, ax, x0, x1):
        """Draw (or redraw) the shaded selection region, plus a small
        date/time bubble above each edge — used both for live feedback
        while shift-dragging and to restore everything after
        render_zones() rebuilds the axes (ax.cla() wipes prior artists)."""
        if self._selection_patch is not None:
            try:
                self._selection_patch.remove()
            except Exception:
                pass  # already gone, e.g. after an ax.cla() rebuild
            self._selection_patch = None
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        self._selection_patch = ax.axvspan(lo, hi, color='steelblue', alpha=0.25, zorder=2)
        self._update_range_edge_bubbles(ax, lo, hi)
        self.canvas.draw_idle()

    def _update_range_edge_bubbles(self, ax, lo, hi):
        """Small floating labels showing the exact date/time at each edge
        of the current selection, so it's easy to fine-tune the range
        width without having to release and check the stats card. Reuses
        the same tooltip look, minus the rounded corners (square here).

        Positioned via annotate's points-offset rather than a plain
        axes-fraction y — axes-fraction scales with the axes' pixel
        height, which changes as the window is resized (Qt keeps DPI
        fixed and resizes the figure itself), so a fraction-based offset
        drifts relative to the title's pad (which is points-based, i.e. a
        fixed physical size) and can end up crowding or overlapping the
        title at some window sizes. Anchoring the offset to points
        instead keeps a constant, guaranteed gap no matter how the
        window is stretched — same approach the old "Showing: ..."
        subtitle used before it was retired in favor of this.

        Centered directly above its edge (ha='center'), with a straight
        vertical tick line connecting down to that exact x-position —
        annotate's own arrow (a plain line, no arrowhead) does this
        automatically, running from the xy anchor to the bottom-center
        of the bubble.

        Single line (date and time together), not two -- with two lines,
        the bubble's own height plus its 14pt offset was tall enough to
        reach into the title's own reserved vertical space above the
        axes, so the two would visibly overlap whenever a bubble
        happened to land under the title's actual text (easy to miss in
        testing, since it only shows up depending on where the selection
        edges land relative to the title's horizontal extent -- a narrow
        early selection can look fine while a wider one overlaps). One
        line keeps the bubble short enough to stay clear with real
        margin, verified against the title's own rendered bbox rather
        than guessed."""
        for attr in ('_selection_start_bubble', '_selection_end_bubble'):
            bubble = getattr(self, attr, None)
            if bubble is not None:
                try:
                    bubble.remove()
                except Exception:
                    pass  # already gone, e.g. after an ax.cla() rebuild
                setattr(self, attr, None)

        def label_for(xval):
            dt = mdates.num2date(xval)
            return strip_leading_hour_zero(dt.strftime('%b %d, %Y %I:%M %p'))

        common_style = dict(
            xycoords=('data', 'axes fraction'), xytext=(0, 14), textcoords='offset points',
            ha='center', va='bottom', fontsize=8.5,
            bbox=dict(boxstyle="square,pad=0.3", fc="white", ec="steelblue", alpha=0.95),
            arrowprops=dict(arrowstyle='-', color='steelblue', linewidth=1.3, shrinkA=0, shrinkB=2),
            zorder=12, annotation_clip=False
        )
        self._selection_start_bubble = ax.annotate(label_for(lo), xy=(lo, 1.0), **common_style)
        self._selection_end_bubble = ax.annotate(label_for(hi), xy=(hi, 1.0), **common_style)

    def _clear_range_edge_bubbles(self):
        for attr in ('_selection_start_bubble', '_selection_end_bubble'):
            bubble = getattr(self, attr, None)
            if bubble is not None:
                try:
                    bubble.remove()
                except Exception:
                    pass
                setattr(self, attr, None)

    def _clear_selection(self):
        self._last_selection_mask = None
        if self._selection_patch is not None:
            try:
                self._selection_patch.remove()
            except Exception:
                pass
            self._selection_patch = None
        self._clear_range_edge_bubbles()
        self.selection_card.setText(self._selection_tip_html())
        self.canvas.draw_idle()

    def _apply_selection_range(self, xmin, xmax):
        mask = (self.timestamp_nums >= xmin) & (self.timestamp_nums <= xmax)
        if not mask.any():
            self.selection_card.setText(
                "<div style='text-align:center;'>"
                "<span style='font-size:12pt; font-weight:bold; color:#555;'>SELECTED RANGE AVERAGE</span>"
                "<div style='height:6px;'></div>"
                "<span style='font-size:11pt; color:#c00;'>No data points in that range</span>"
                "</div>"
            )
            return
        self._last_selection_mask = mask
        self._update_range_preview(self.ax, xmin, xmax)
        self._render_selection_card()

    def _snap_range_x(self, ax, xdata, event_x):
        """Snap a shift-drag range-selection endpoint to the nearest
        actual data point, always -- there's no "in between" position,
        so a selection's bounds are guaranteed to land exactly on real
        readings rather than some arbitrary point along the line
        between them.

        This used to also have a stronger pull toward the nearest
        gridline before falling back to a point, but that fought fine
        adjustments near a gridline (the selection would rather lock
        onto the gridline than let go for a nearby point), so it's
        gone -- point-snapping alone is both simpler and easier to
        control precisely."""
        if xdata is None:
            return xdata
        if len(self.timestamp_nums) == 0:
            return xdata

        # Nearest neighbor in a sorted array is always one of the two
        # points bracketing the insertion index
        idx = np.searchsorted(self.timestamp_nums, xdata)
        candidates = [i for i in (idx - 1, idx) if 0 <= i < len(self.timestamp_nums)]
        best_idx = min(candidates, key=lambda i: abs(self.timestamp_nums[i] - xdata))
        return self.timestamp_nums[best_idx]

    def begin_range_drag(self, event):
        """Called by TrimmedNavigationToolbar when a Shift+left-click-drag
        starts. If the click landed near an edge of an existing selection,
        that edge is resized (the opposite edge stays put); otherwise a
        brand-new selection starts at the click point."""
        ax = event.inaxes
        if ax is None or event.xdata is None or event.x is None or event.y is None:
            self._active_drag = None
            return

        anchor = event.xdata
        grabbed_edge = False
        bounds = self._current_selection_bounds()
        if bounds is not None:
            xmin, xmax = bounds
            x0_disp = ax.transData.transform((xmin, 0))[0]
            x1_disp = ax.transData.transform((xmax, 0))[0]
            edge_px = 8  # pixels — how close a click needs to be to grab an edge
            if abs(event.x - x0_disp) <= edge_px:
                anchor = xmax  # grabbing the left edge — right edge stays fixed
                grabbed_edge = True
            elif abs(event.x - x1_disp) <= edge_px:
                anchor = xmin  # grabbing the right edge — left edge stays fixed
                grabbed_edge = True
        if not grabbed_edge:
            # Brand-new selection (no existing one, or click landed away
            # from both edges) — snap the starting edge too, not just the
            # one being actively dragged, so both ends of a fresh
            # selection get the same gridline/point affinity. An edge
            # grab skips this since xmax/xmin there are already an
            # established (and already-snapped) selection bound.
            anchor = self._snap_range_x(ax, anchor, event.x)

        cid = self.canvas.mpl_connect('motion_notify_event', self._on_range_drag_motion)
        self._active_drag = {'ax': ax, 'anchor': anchor, 'press_x': event.x, 'press_y': event.y, 'cid': cid}
        live_x = self._snap_range_x(ax, event.xdata, event.x)
        self._update_range_preview(ax, anchor, live_x)

    def _on_range_drag_motion(self, event):
        drag = self._active_drag
        if drag is None or event.inaxes != drag['ax'] or event.xdata is None:
            return
        live_x = self._snap_range_x(drag['ax'], event.xdata, event.x)
        self._update_range_preview(drag['ax'], drag['anchor'], live_x)

    def end_range_drag(self, event):
        """Called by TrimmedNavigationToolbar when the Shift-drag mouse
        button is released. A drag that barely moved (a near-stationary
        Shift-click) clears the selection instead of committing a
        near-zero-width range."""
        drag = self._active_drag
        self._active_drag = None
        if drag is None:
            return
        self.canvas.mpl_disconnect(drag['cid'])

        if event.inaxes == drag['ax'] and event.xdata is not None:
            end_x = self._snap_range_x(drag['ax'], event.xdata, event.x)
        else:
            end_x = drag['anchor']
        moved_px = 0.0
        if event.x is not None and event.y is not None:
            moved_px = ((event.x - drag['press_x']) ** 2 + (event.y - drag['press_y']) ** 2) ** 0.5

        if moved_px < 5:
            self._clear_selection()
            return

        xmin, xmax = sorted((drag['anchor'], end_x))
        self._apply_selection_range(xmin, xmax)

    def render_zones(self):
        # Clear the axes completely and rebuild — needed since the risk
        # standard (and therefore threshold lines, colors, and legend) can
        # change at any time via the dropdown
        self.ax.cla()

        thresholds, color_map, legend_labels, legend_title = get_authority_zones(self.authority_key, self.unit)

        # Create and split segments at zone boundaries for both ascending and descending
        all_segments = []
        all_colors = []
        for i in range(len(self.radon_levels) - 1):
            start_time = self.timestamp_nums[i]
            end_time = self.timestamp_nums[i + 1]
            start_value = self.radon_levels[i]
            end_value = self.radon_levels[i + 1]

            if start_value == end_value:
                # No transition, add single segment
                all_segments.append([[start_time, start_value], [end_time, end_value]])
                for low, high, color in color_map:
                    if low <= start_value < high:
                        all_colors.append(color)
                        break
                continue

            # Initial segment
            current_start = [start_time, start_value]
            segments_in_step = []
            colors_in_step = []

            while True:
                crossed = False
                for threshold in sorted(thresholds):
                    # Check if the segment crosses the threshold
                    if (current_start[1] > threshold and end_value < threshold) or (current_start[1] < threshold and end_value > threshold):
                        crossed = True
                        direction = "descending" if current_start[1] > threshold else "ascending"
                        if end_value != current_start[1]:  # Avoid division by zero
                            t = (threshold - current_start[1]) / (end_value - current_start[1])
                            if 0 < t < 1:  # Crossing occurs within the segment
                                intersect_time = start_time + t * (end_time - start_time)
                                intersect_value = threshold
                                # Add segment up to the intersection
                                segments_in_step.append([current_start, [intersect_time, intersect_value]])
                                # Color based on the starting value of this segment
                                for low, high, color in color_map:
                                    if low <= current_start[1] < high:
                                        colors_in_step.append(color)
                                        break
                                # Update current_start to the intersection point
                                current_start = [intersect_time, intersect_value]
                                # Determine the color for the next segment based on direction
                                if direction == "descending":
                                    # Next segment enters the zone below the threshold
                                    for low, high, color in color_map:
                                        if high == threshold:  # Zone where threshold is the upper bound
                                            next_color = color
                                            break
                                else:  # ascending
                                    # Next segment enters the zone above the threshold
                                    for low, high, color in color_map:
                                        if low == threshold:  # Zone where threshold is the lower bound
                                            next_color = color
                                            break
                                break  # Handle one crossing at a time
                if not crossed:
                    # No more crossings, add the final segment
                    segments_in_step.append([current_start, [end_time, end_value]])
                    # Color based on the starting value of this segment
                    for low, high, color in color_map:
                        if low <= current_start[1] < high:
                            colors_in_step.append(color)
                            break
                    break
                else:
                    # Add the segment after the crossing with the determined color
                    segments_in_step.append([current_start, [end_time, end_value]])
                    colors_in_step.append(next_color)
                    break  # Exit after handling the crossing

            all_segments.extend(segments_in_step)
            all_colors.extend(colors_in_step)

        segments = np.array(all_segments, dtype=object)
        colors = all_colors

        # Create LineCollection without label
        lc = LineCollection(segments, colors=colors, linewidth=0.5)
        self.ax.add_collection(lc)

        # Add a small marker at every actual data point, colored to match
        # its risk zone, so hover targets are visible on the graph
        point_colors = []
        for val in self.radon_levels:
            for low, high, color in color_map:
                if low <= val < high:
                    point_colors.append(color)
                    break
            else:
                point_colors.append(color_map[-1][2])
        self.point_scatter = self.ax.scatter(
            self.timestamp_nums, self.radon_levels,
            s=6, c=point_colors, zorder=3, edgecolors='none'
        )

        # The default spine zorder (2.5) sits just below the scatter
        # points' zorder (3), so data points near the left/bottom edge
        # get drawn over the plot border instead of the border sitting
        # cleanly on top of them. Bump the spines above the scatter so
        # the border always reads as a clean line, not a dotted one.
        for spine in self.ax.spines.values():
            spine.set_zorder(4)

        # Add threshold lines
        for threshold in thresholds:
            self.ax.axhline(y=threshold, color="#FFA500" if threshold == thresholds[0] else "red", linestyle='--', linewidth=1)

        # SmartAutoDateLocator anchors ticks to fixed boundaries (so
        # dragging doesn't shift which hours get labeled) only at the
        # hour level and finer, and falls back to plain even spacing at
        # the day level and coarser (avoiding matplotlib's hardcoded
        # 1st/8th/15th/22nd-of-month anchoring, which produces uneven
        # gaps around month boundaries at the day/week zoom level — see
        # SmartAutoDateLocator's docstring for the full story).
        locator = SmartAutoDateLocator()
        # Custom formats: day level shows month+day on one line and the
        # year on a second line beneath it ("May 08" / "2026") — compact,
        # and gives year context even when zoomed in far enough that only
        # day-level ticks are visible. Hour level drops minutes entirely
        # (data is always on the hour) and uses 12-hour AM/PM instead of
        # 24-hour. Order matches ConciseDateFormatter's levels: [year,
        # month, day, hour, minute, second] — minute/second levels are
        # effectively unreachable now that zoom is capped at a 6-hour
        # minimum width (see _on_xlim_changed), but kept simplified too
        # just in case.
        formats = ['%Y', '%b %Y', '%b %d\n%Y', '%I %p', '%I %p', '%S.%f']
        # ConciseDateFormatter's default "zero tick" behavior collapses
        # January's month tick down to just the bare year ("2026"),
        # dropping "Jan" — on the theory that the coarser level above
        # already conveys it. We want the opposite: January should keep
        # showing "Jan 2026" like every other month, so the year-change
        # point reads clearly rather than looking like a missing label.
        # Same idea for a day-level tick landing on the 1st of a month
        # (e.g. via SmartAutoDateLocator's even day-level spacing): it
        # should still show "Apr 01" rather than collapsing to just
        # "Apr 2026", or it reads like a coarser-granularity tick that
        # skipped the day number entirely.
        zero_formats = [''] + formats[:-1]
        zero_formats[1] = formats[1]  # was formats[0] ('%Y') — keep the month
        zero_formats[2] = formats[2]  # was formats[1] ('%b %Y') — keep the day
        formatter = HourFriendlyDateFormatter(locator, formats=formats, zero_formats=zero_formats)
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(formatter)
        self.ax.set_xlim(self.timestamp_nums[0], self.timestamp_nums[-1])
        self.figure.autofmt_xdate()

        # ConciseDateFormatter normally draws a small "2025" / "Jul 2025"
        # label in the bottom-right corner once zoomed in enough that all
        # visible ticks share that year/month. Hide it — the rotated edge
        # bars beside the graph already show the full start/end date and
        # time at all times, making this redundant.
        self.ax.xaxis.get_offset_text().set_visible(False)

        self.ax.set_xlabel('DATE AND TIME', fontsize=11, fontweight='bold', labelpad=15)
        self.ax.set_ylabel(f'RADON LEVEL ({format_unit_mathtext(self.unit)})', fontsize=11, fontweight='bold', labelpad=15)
        self.ax.set_title(f'Radon Levels Over Time ({self.serial_number})', fontsize=16, fontweight='bold', pad=34)

        # Built-in tick marks are axes-level children, while our bookend
        # bar is a figure-level artist — those two layers don't reliably
        # respect zorder comparisons against each other in matplotlib (an
        # axes' children get composited as a unit), so a long built-in
        # tick mark meant to poke through the bar can end up invisible,
        # painted over regardless of its zorder. Hidden here (length=0);
        # _draw_left_tick_marks below draws real tick marks ourselves, as
        # figure-level artists in the same layer as the bar, sidestepping
        # the issue entirely. 'pad' still controls the number's distance
        # from the axes edge, independent of the (now zero) tick length.
        tick_label_pad = self.EDGE_BAR_WIDTH_INCHES * 72 + 14
        self.ax.tick_params(axis='y', pad=tick_label_pad, length=0)

        # "Bookend" bars along the left/right edges showing the visible
        # date range — figure-level artists (see _create_edge_bars, called
        # once from init_ui) that live outside the axes entirely, so they
        # sit beside the plotted data rather than overlapping it. ax.cla()
        # only clears axes-level children, so these persist across every
        # render_zones rebuild; just keep their position/text in sync here.
        self._position_edge_bars()

        # Reserve extra headroom above the data so the highest reading is
        # never hidden behind the risk-category legend, which sits in the
        # upper-right corner. Without this, a peak that lands on the right
        # side of the visible range can land directly under the legend
        # panel. self.ax.get_ylim() at this point already reflects
        # matplotlib's autoscale over the plotted data and threshold lines
        # (including its default ~5% margins), so we just push the top
        # of that range up further. This runs on every render_zones call,
        # and since it happens before toolbar.update()/push_current()
        # below, the padded range becomes the view that "Home" resets to.
        LEGEND_HEADROOM_FRACTION = 0.25  # fraction of the y-axis reserved above the data
        auto_ymin, auto_ymax = self.ax.get_ylim()
        data_span = auto_ymax - auto_ymin
        if data_span <= 0:
            data_span = max(abs(auto_ymax), 1.0)
        padded_ymax = auto_ymin + data_span / (1 - LEGEND_HEADROOM_FRACTION)
        self.ax.set_ylim(auto_ymin, padded_ymax)

        # Create custom color legend, title reflects the selected authority
        legend_patches = [Patch(color=color, label=label) for color, label in zip([c[2] for c in color_map], legend_labels)]
        self.ax.legend(handles=legend_patches, loc='upper right', title=legend_title, fontsize=7, bbox_to_anchor=(0.99, 0.99), borderpad=1.35, handletextpad=0.75, labelspacing=0.7, framealpha=0.95)

        self.ax.grid(True)

        # Finalize the plot layout
        self.figure.tight_layout()
        # tight_layout() snugs margins to content on every redraw, which
        # would undo any manual spacing — so enforce the extra breathing
        # room above the title and below the date/time label as an
        # override applied right after it, each time. Uses a fixed
        # physical (inch) padding rather than a fixed fraction — see
        # _apply_fixed_margins for why.
        self._apply_fixed_margins()

        # ax.cla() wipes annotations, so the hover tooltip needs to be
        # recreated every time the zones (and therefore the axes) are rebuilt.
        # Two separate pieces: the date/time in plain style, and the reading
        # value in bold/larger text so it stands out at a glance.
        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="gray", alpha=0.95),
            arrowprops=dict(arrowstyle="->"), zorder=10
        )
        self.annot.set_visible(False)

        self.annot_value = self.ax.annotate(
            "", xy=(0, 0), xytext=(15, 29), textcoords="offset points",
            fontsize=13, fontweight='bold',
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="gray", alpha=0.95),
            zorder=11
        )
        self.annot_value.set_visible(False)

        # Refresh the toolbar's navigation history so "Home" always resets
        # to the current full-data view — without this, switching the Risk
        # Standard or Display Unit dropdown could leave Home pointing at a
        # stale view from before the change. update() only clears the
        # stack; push_current() is what actually seeds it with a "home"
        # entry to restore to (missing this was why Home stopped working).
        self.toolbar.update()
        self.toolbar.push_current()

        # Update the period-average readouts (24hr / 30-day / 1-year)
        self.update_stats_label()

        # ax.cla() (just above, in this same rebuild) wiped any previous
        # selection shading artist (and edge-date bubbles) — redraw them
        # from the persisted mask so an active shift-drag selection
        # survives switching the Risk Standard or Display Unit dropdown
        self._selection_patch = None
        self._selection_start_bubble = None
        self._selection_end_bubble = None
        bounds = self._current_selection_bounds()
        if bounds is not None:
            self._update_range_preview(self.ax, bounds[0], bounds[1])

        # ax.cla() also disconnects any previously-connected callbacks, so
        # reconnect the one that keeps the edge bars' date/time labels in
        # sync with the visible range on every zoom/pan/scroll/Home
        self.ax.callbacks.connect('xlim_changed', self._on_xlim_changed)
        self._update_range_subtitle()

        # The manual left-edge tick marks (_draw_left_tick_marks) are
        # figure-level artists positioned from the current ylim — they
        # don't automatically track it the way the built-in tick number
        # labels do. Without this, dragging/zooming in a way that shifts
        # the y-axis leaves the tick marks visually stuck at their old
        # spots while the numbers beside them move, so they drift out of
        # alignment. Reconnected here since ax.cla() drops callbacks.
        self.ax.callbacks.connect('ylim_changed', self._on_ylim_changed)

        # Event connections only need to be created once, the first time
        # the plot is drawn — not on every dropdown change
        if not hasattr(self, '_events_connected'):
            self._events_connected = True

            # Enable MOVE tool (pan) by default
            self.toolbar.pan()

            # Enable mouse scroll wheel zoom (zooms toward the cursor position)
            self.canvas.mpl_connect('scroll_event', self.on_scroll)

            # Hover tooltip: connected once; on_hover always reads the
            # current self.annot, so this stays correct even after
            # render_zones() recreates the annotation later
            self.canvas.mpl_connect('motion_notify_event', self.on_hover)

            # Bold the date-level x-axis ticks (day/month/year) so they
            # stand out from the regular-weight, slightly smaller time
            # ticks (hour). Tick label Text objects are only finalized
            # during an actual draw, and get regenerated on every zoom/pan,
            # so this re-applies on every draw via the event hook rather
            # than being a one-time pass.
            self.canvas.mpl_connect('draw_event', self._on_draw_style_ticks)

            # Recompute the fixed-inch margins live as the window is
            # dragged bigger/smaller, not just the next time render_zones()
            # happens to run (e.g. from a dropdown change)
            self.canvas.mpl_connect('resize_event', self._on_resize)

        # Ensure the canvas is updated
        self.canvas.draw()

    def on_hover(self, event):
        # Hide the tooltip if the cursor isn't over the plot at all
        if event.inaxes != self.ax or event.xdata is None:
            if self.annot.get_visible():
                self.annot.set_visible(False)
                self.canvas.draw_idle()
            return

        # Narrow down to a handful of nearby points first (data is sorted
        # by time), then check pixel distance only for those — avoids
        # transforming all ~8,000+ points on every mouse move
        idx_guess = np.searchsorted(self.timestamp_nums, event.xdata)
        lo = max(0, idx_guess - 3)
        hi = min(len(self.timestamp_nums), idx_guess + 4)

        best_idx = None
        best_dist = None
        for i in range(lo, hi):
            xi, yi = self.ax.transData.transform((self.timestamp_nums[i], self.radon_levels[i]))
            dist = np.hypot(xi - event.x, yi - event.y)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = i

        # Only show the tooltip if the cursor is genuinely close to a point
        # (within ~12 pixels), not just anywhere on the graph
        if best_idx is not None and best_dist <= 12:
            x = self.timestamp_nums[best_idx]
            y = self.radon_levels[best_idx]
            timestamp_str = strip_leading_hour_zero(self.timestamps[best_idx].strftime('%Y-%m-%d %I:%M %p'))

            # Flip the tooltip left/right and up/down depending on which
            # edge of the plot the cursor is near, so it never gets clipped
            # by the window's borders
            ax_bbox = self.ax.get_window_extent()
            near_right = event.x > ax_bbox.x0 + 0.75 * ax_bbox.width
            near_top = event.y > ax_bbox.y0 + 0.75 * ax_bbox.height  # display y grows upward

            x_offset = -15 if near_right else 15
            y_offset = -15 if near_top else 15
            ha = 'right' if near_right else 'left'
            va = 'top' if near_top else 'bottom'

            # Stack the bold value box further out in the same direction
            # the timestamp box is offset, so they read as one unit
            stack_gap = 26
            value_y_offset = y_offset - stack_gap if near_top else y_offset + stack_gap

            self.annot.xy = (x, y)
            self.annot.xyann = (x_offset, y_offset)
            self.annot.set_horizontalalignment(ha)
            self.annot.set_verticalalignment(va)
            self.annot.set_text(timestamp_str)
            self.annot.set_visible(True)

            self.annot_value.xy = (x, y)
            self.annot_value.xyann = (x_offset, value_y_offset)
            self.annot_value.set_horizontalalignment(ha)
            self.annot_value.set_verticalalignment(va)
            self.annot_value.set_text(f"{y:g} {format_unit_mathtext(self.unit)}")
            self.annot_value.set_visible(True)

            self.canvas.draw_idle()
        elif self.annot.get_visible():
            self.annot.set_visible(False)
            self.annot_value.set_visible(False)
            self.canvas.draw_idle()

    def on_scroll(self, event):
        # Only zoom when the cursor is over the plot area
        if event.inaxes != self.ax or event.xdata is None:
            return

        ax = self.ax
        xlim = ax.get_xlim()
        xdata = event.xdata

        # macOS "natural scrolling" (default for trackpads/Magic Mouse)
        # reverses what 'up'/'down' feel like versus a traditional mouse
        # wheel. Set to False if scrolling ever feels backwards again
        # (e.g. after toggling natural scrolling off, or on a mouse that
        # doesn't follow it).
        NATURAL_SCROLLING = True

        if event.button == 'up':
            scale_factor = 1.1 if NATURAL_SCROLLING else 0.9
        elif event.button == 'down':
            scale_factor = 0.9 if NATURAL_SCROLLING else 1.1
        else:
            return

        # Keep the point under the cursor fixed while zooming, same as most
        # map/graphing apps, rather than always zooming on the center
        old_width = xlim[1] - xlim[0]
        new_width = old_width * scale_factor
        rel = (xdata - xlim[0]) / old_width if old_width != 0 else 0.5
        new_xlim = (xdata - new_width * rel, xdata + new_width * (1 - rel))
        ax.set_xlim(new_xlim)
        self.canvas.draw_idle()

    def showEvent(self, event):
        super().showEvent(event)
        # Lock the minimum window size to whatever size it happens to be
        # the first time it's actually shown (its natural/default opening
        # size) — after that, the window can be made bigger but never
        # smaller than this. Guarded so this only fires once; showEvent
        # can fire more than once (e.g. minimize/restore).
        if not getattr(self, '_min_size_locked', False):
            self._min_size_locked = True
            self.setMinimumSize(self.size())

# Create and show the main window
if __name__ == '__main__':
    window = MainWindow()
    window.show()
    print("Debug: After plt.show()")
    print("Plot display completed.")
    sys.exit(app.exec_())
