import matplotlib
print(f"Matplotlib version: {matplotlib.__version__}")
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
import matplotlib.dates as mdates
import numpy as np
import datetime
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from matplotlib.collections import LineCollection
from PyQt5.QtWidgets import QFileDialog, QApplication, QMainWindow, QVBoxLayout, QWidget
from matplotlib.widgets import Button
from matplotlib.patches import Patch
import sys

# Create Qt application
app = QApplication(sys.argv)

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
            "Text files (*.txt);;All files (*.*)"
        )

        if not filename:
            print("No file selected. Exiting.")
            sys.exit(1)

        # Extract date and hour from filename
        date_str = filename.split('_')[-1][:8]
        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        time_str = filename.split()[-1] if ' ' in filename else filename.split('_')[-1][8:14]
        hour = int(time_str[:2])
        end_datetime = datetime.datetime(year, month, day, hour, 0, 0)

        # Extract serial number from filename
        serial_number = filename.split('_')[0].split('/')[-1]
        print(f"Serial number extracted: {serial_number}")

        # Load data and detect unit
        self.radon_levels = []
        data_count = 0
        total_points = 4391
        unit = "Bq/m3"
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                print("Loading data from file...")
                for line_number, line in enumerate(file, 1):
                    line = line.strip()
                    if line.startswith("Unit:"):
                        unit = line.split("Unit:")[1].strip()
                        print(f"Unit detected: {unit}")
                        continue
                    if line.startswith("Data No:"):
                        total_points = int(line.split()[-1])
                        print(f"Total data points set to: {total_points}")
                        continue
                    if any(line.startswith(f"{i})") for i in range(1, total_points + 1)) and data_count < total_points:
                        try:
                            value_str = line.split(')', 1)[1].strip()
                            value = float(value_str.split()[0])
                            self.radon_levels.append(value)
                            data_count += 1
                            if data_count % 1000 == 0:
                                print(f"Parsed {data_count} values...")
                        except (ValueError, IndexError) as e:
                            print(f"Failed to parse line {line_number}: '{line}' - Error: {e}")
                            continue
                    if data_count >= total_points:
                        print(f"Loaded {data_count} data points.")
                        break
        except Exception as e:
            print(f"Error reading file: {e}")
            sys.exit(1)

        if len(self.radon_levels) != total_points:
            print(f"Warning: Expected {total_points} data points, found {len(self.radon_levels)}. Check file format.")

        self.radon_levels = np.array(self.radon_levels)
        start_datetime = end_datetime - datetime.timedelta(hours=len(self.radon_levels) - 1)
        self.timestamps = np.array([start_datetime + datetime.timedelta(hours=i) for i in range(len(self.radon_levels))])
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

        # Ensure the canvas is updated
        self.canvas.draw()

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