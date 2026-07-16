import matplotlib
print(f"Matplotlib version: {matplotlib.__version__}")
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import numpy as np
import datetime
import os
import re
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from matplotlib.collections import LineCollection
from PyQt5.QtWidgets import QFileDialog, QApplication, QMainWindow, QVBoxLayout, QWidget, QInputDialog, QMessageBox
from matplotlib.widgets import Button
from matplotlib.patches import Patch
import sys

# Create Qt application
app = QApplication(sys.argv)


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


# Create main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Radon Plot")

        # Prompt user to select a file
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select RadonEye RD200 Data File",
            "",
            "RadonEye Data Files (*.txt *.csv);;Text files (*.txt);;CSV files (*.csv);;All files (*.*)"
        )

        if not filename:
            print("No file selected. Exiting.")
            sys.exit(1)

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
                default_dt = datetime.datetime.fromtimestamp(mtime)
            except OSError:
                default_dt = datetime.datetime.now()

            default_str = default_dt.strftime('%Y-%m-%d %H:%M:%S')
            text, ok = QInputDialog.getText(
                self,
                "Confirm End Date/Time",
                "This file's name doesn't contain a timestamp, so the date/time\n"
                "of the LAST data point can't be determined automatically.\n\n"
                "Enter it below (defaults to the file's last-modified time):\n"
                "Format: YYYY-MM-DD HH:MM:SS",
                text=default_str
            )
            if not ok:
                print("No end date/time provided. Exiting.")
                sys.exit(1)
            try:
                end_datetime = datetime.datetime.strptime(text.strip(), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                QMessageBox.warning(self, "Invalid Date", "Couldn't parse that date/time. Using file's last-modified time instead.")
                end_datetime = default_dt

        print(f"Serial number extracted: {serial_number}")

        # Load data and detect unit/format
        self.radon_levels = []
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
                            self.radon_levels.append(value)
                            data_count += 1
                            if data_count % 1000 == 0:
                                print(f"Parsed {data_count} values...")
                        except ValueError as e:
                            print(f"Failed to parse line {line_number}: '{line}' - Error: {e}")
                        continue

                print(f"Loaded {data_count} data points.")
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)

        if total_points is not None and len(self.radon_levels) != total_points:
            print(f"Warning: Expected {total_points} data points, found {len(self.radon_levels)}. Check file format.")

        if len(self.radon_levels) == 0:
            QMessageBox.critical(self, "No Data Found", "Couldn't find any data points in this file. Please check the file format.")
            sys.exit(1)

        self.radon_levels = np.array(self.radon_levels)
        start_datetime = end_datetime - interval_delta * (len(self.radon_levels) - 1)
        self.timestamps = np.array([start_datetime + interval_delta * i for i in range(len(self.radon_levels))])
        # Convert timestamps to Matplotlib date numbers
        self.timestamp_nums = mdates.date2num(self.timestamps)
        print(f"Start datetime: {start_datetime}, End datetime: {end_datetime}")

        print("Generating plot...")
        self.init_ui(unit, serial_number)

    def init_ui(self, unit, serial_number):
        # Create figure and canvas
        self.figure = Figure(figsize=(12, 6), dpi=120)
        self.canvas = FigureCanvas(self.figure)

        # Create layout
        layout = QVBoxLayout()
        # Add toolbar at the top
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)

        # Add canvas below the toolbar
        layout.addWidget(self.canvas)

        # Create widget with layout
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # Create main axes for the plot
        self.ax = self.figure.add_subplot(111)

        # Adjust margins to reserve space at the top for buttons
        self.figure.subplots_adjust(top=0.85)  # Leaves 15% of figure height at the top

        # Define thresholds and colors based on unit
        if unit == "Bq/m3":
            thresholds = [100, 200]
            color_map = [(0, 100, mcolors.to_rgb("green")),
                         (100, 200, mcolors.to_rgb("#FFA500")),
                         (200, float('inf'), mcolors.to_rgb("red"))]
            legend_labels = ['0 to 100 Bq/m³ (Low)', '100 to 200 Bq/m³ (Elevated)', '>200 Bq/m³ (High)']
        elif unit == "pCi/L":
            thresholds = [2.7, 4.0]
            color_map = [(0, 2.7, mcolors.to_rgb("green")),
                         (2.7, 4.0, mcolors.to_rgb("#FFA500")),
                         (4.0, float('inf'), mcolors.to_rgb("red"))]
            legend_labels = ['0 to 2.7 pCi/L (Low)', '2.7 to 4.0 pCi/L (Elevated)', '>4.0 pCi/L (High)']
        else:
            thresholds = [float('inf')]
            color_map = [(0, float('inf'), mcolors.to_rgb("blue"))]
            legend_labels = ['All Values']

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

        # Add threshold lines
        for threshold in thresholds:
            self.ax.axhline(y=threshold, color="#FFA500" if threshold == thresholds[0] else "red", linestyle='--', linewidth=1)

        locator = AutoDateLocator()
        formatter = ConciseDateFormatter(locator)
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(formatter)
        self.ax.set_xlim(self.timestamp_nums[0], self.timestamp_nums[-1])
        self.figure.autofmt_xdate()

        self.ax.set_xlabel('Date and Time')
        self.ax.set_ylabel(f'Radon Level ({unit})')
        self.ax.set_title(f'Radon Levels Over Time ({serial_number})', fontsize=14)

        # Create custom color legend with "RISK CATEGORY" title, moved to upper-right with adjusted padding
        legend_patches = [Patch(color=color, label=label) for color, label in zip([c[2] for c in color_map], legend_labels)]
        self.ax.legend(handles=legend_patches, loc='upper right', title='RISK CATEGORY', fontsize=7, bbox_to_anchor=(0.99, 0.99), borderpad=1.35, handletextpad=0.75, labelspacing=0.7, framealpha=0.95)

        self.ax.grid(True)

        # Finalize the plot layout before adding buttons
        self.figure.tight_layout()

        # Get the finalized axes position
        ax_pos = self.ax.get_position()
        ax_right = ax_pos.x1  # Right edge of the axes in figure coordinates
        ax_top = ax_pos.y1    # Top edge of the axes in figure coordinates

        # Define button dimensions
        button_width = 0.1
        button_height = 0.05
        gap = 0.01  # Spacing between buttons

        # Place "Zoom Out" with its right edge aligned to ax_right, raised above graph edge
        left_out = ax_right - button_width
        bottom_out = ax_top + 0.01  # Raise buttons slightly above the graph edge
        ax_zoom_out = self.figure.add_axes([left_out, bottom_out, button_width, button_height])
        self.button_zoom_out = Button(ax_zoom_out, 'Zoom Out')
        self.button_zoom_out.on_clicked(self.zoom_out)

        # Place "Zoom In" to the left of "Zoom Out" with a small gap
        left_in = left_out - button_width - gap
        ax_zoom_in = self.figure.add_axes([left_in, bottom_out, button_width, button_height])
        self.button_zoom_in = Button(ax_zoom_in, 'Zoom In')
        self.button_zoom_in.on_clicked(self.zoom_in)

        # Enable MOVE tool (pan) by default
        self.toolbar.pan()

        # Enable mouse scroll wheel zoom (zooms toward the cursor position)
        self.canvas.mpl_connect('scroll_event', self.on_scroll)

        # Ensure the canvas is updated
        self.canvas.draw()

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

    def zoom_in(self, event):
        # Zoom in by 10% centered on the current view, only on x-axis
        ax = self.ax
        xlim = ax.get_xlim()
        xcenter = (xlim[0] + xlim[1]) / 2
        xwidth = (xlim[1] - xlim[0]) * 0.9
        ax.set_xlim(xcenter - xwidth / 2, xcenter + xwidth / 2)
        self.canvas.draw()

    def zoom_out(self, event):
        # Zoom out by 10% centered on the current view, only on x-axis
        ax = self.ax
        xlim = ax.get_xlim()
        xcenter = (xlim[0] + xlim[1]) / 2
        xwidth = (xlim[1] - xlim[0]) * 1.1
        ax.set_xlim(xcenter - xwidth / 2, xcenter + xwidth / 2)
        self.canvas.draw()

# Create and show the main window
if __name__ == '__main__':
    window = MainWindow()
    window.show()
    print("Debug: After plt.show()")
    print("Plot display completed.")
    sys.exit(app.exec_())
