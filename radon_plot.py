import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
import datetime
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from PyQt5.QtWidgets import QFileDialog, QApplication
import sys

# Create Qt application
app = QApplication(sys.argv)

# Prompt user to select a file
filename, _ = QFileDialog.getOpenFileName(
    None,
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

# Extract serial number from filename (e.g., IE08RE000855)
serial_number = filename.split('_')[0].split('/')[-1]  # Clean S/N from filename
print(f"Serial number extracted: {serial_number}")

# Load data and detect unit
radon_levels = []
data_count = 0
total_points = 4391
unit = "Bq/m3"  # Default unit
try:
    with open(filename, 'r', encoding='utf-8') as file:
        print("Loading data from file...")
        for line_number, line in enumerate(file, 1):
            line = line.strip()
            if line.startswith("Unit:"):
                unit = line.split("Unit:")[1].strip()  # Extract unit (e.g., pCi/L or Bq/m3)
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
                    radon_levels.append(value)
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

if len(radon_levels) != total_points:
    print(f"Warning: Expected {total_points} data points, found {len(radon_levels)}. Check file format.")

start_datetime = end_datetime - datetime.timedelta(hours=len(radon_levels) - 1)
print(f"Start datetime: {start_datetime}, End datetime: {end_datetime}")

timestamps = [start_datetime + datetime.timedelta(hours=i) for i in range(len(radon_levels))]
print(f"Last timestamp: {timestamps[-1]}")

print("Generating plot...")
try:
    plt.figure(figsize=(12, 6), dpi=120)

    # Define thresholds and colors based on unit
    if unit == "Bq/m3":
        thresholds = [100, 200]
        color_ranges = [(0, 100, "green"), (100, 200, "yellow-orange"), (200, float('inf'), "red")]
    elif unit == "pCi/L":
        thresholds = [2.7, 4.0]
        color_ranges = [(0, 2.7, "green"), (2.7, 4.0, "yellow-orange"), (4.0, float('inf'), "red")]
    else:
        color_ranges = [(0, float('inf'), "blue")]  # Default color if unit is unrecognized

    # Plot data with zone-based coloring and threshold crossing
    for i in range(len(radon_levels) - 1):
        current_value = radon_levels[i]
        next_value = radon_levels[i + 1]
        current_zone = next(zone for zone in color_ranges if zone[0] <= current_value < zone[1])
        next_zone = next(zone for zone in color_ranges if zone[0] <= next_value < zone[1])
        current_color = current_zone[2] if current_zone[2] != "yellow-orange" else "#FFA500"

        if current_zone == next_zone:
            # Same zone, plot the full segment
            plt.plot(timestamps[i:i+2], [current_value, next_value], 
                     color=current_color, linewidth=0.5, label='Radon Levels' if i == 0 else "")
        else:
            # Crossing a threshold, calculate intersection and plot two segments
            for thresh in thresholds:
                if (unit == "Bq/m3" and ((current_value < thresh <= next_value) or (next_value < thresh <= current_value))) or \
                   (unit == "pCi/L" and ((current_value < thresh <= next_value) or (next_value < thresh <= current_value))):
                    if current_value != next_value:  # Avoid division by zero
                        t = (thresh - current_value) / (next_value - current_value)
                        cross_time = timestamps[i] + (timestamps[i+1] - timestamps[i]) * t
                        cross_value = current_value + (next_value - current_value) * t

                        # Plot first segment up to the threshold
                        plt.plot([timestamps[i], cross_time], [current_value, cross_value], 
                                 color=current_color, linewidth=0.5, label='Radon Levels' if i == 0 else "")

                        # Determine next zone color
                        next_color = next_zone[2] if next_zone[2] != "yellow-orange" else "#FFA500"
                        # Plot second segment from the threshold
                        plt.plot([cross_time, timestamps[i+1]], [cross_value, next_value], 
                                 color=next_color, linewidth=0.5)
                    else:
                        plt.plot(timestamps[i:i+2], [current_value, next_value], 
                                 color=current_color, linewidth=0.5, label='Radon Levels' if i == 0 else "")
                    break
            else:
                plt.plot(timestamps[i:i+2], [current_value, next_value], 
                         color=current_color, linewidth=0.5, label='Radon Levels' if i == 0 else "")

    # Plot the last point
    last_value = radon_levels[-1]
    last_color = next(zone[2] for zone in color_ranges if zone[0] <= last_value < zone[1]) if color_ranges[0][2] != "yellow-orange" else "#FFA500"
    plt.plot(timestamps[-1], last_value, 
             color=last_color, linewidth=0.5, marker='o', label='Radon Levels' if len(radon_levels) == 1 else "")

    # Add threshold lines
    for threshold in thresholds:
        plt.axhline(y=threshold, color="#FFA500" if threshold == thresholds[0] else "red", linestyle='--', linewidth=1)

    locator = AutoDateLocator()
    formatter = ConciseDateFormatter(locator)
    plt.gcf().axes[0].xaxis.set_major_locator(locator)
    plt.gcf().axes[0].xaxis.set_major_formatter(formatter)
    plt.gcf().axes[0].set_xlim(timestamps[0], timestamps[-1])
    plt.gcf().autofmt_xdate()

    plt.xlabel('Date and Time')
    plt.ylabel(f'Radon Level ({unit})')  # Dynamic y-label based on detected unit
    plt.title(f'Radon Levels Over Time ({serial_number})', fontsize=14)  # S/N only, larger font
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    print(f"Displaying plot")
    plt.show()
    print("Plot display completed.")
except Exception as e:
    print(f"Error generating plot: {e}")
    sys.exit(1)

sys.exit(app.exec_())