import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
import datetime
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from PyQt5.QtWidgets import QFileDialog, QApplication
import sys
import time

print(f"Starting app at {time.time()}")
# Create Qt application
app = QApplication(sys.argv)

print(f"Opening file dialog at {time.time()}")
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

print(f"Selected file: {filename} at {time.time()}")

# Record start time
print(f"Script started at: {datetime.datetime.now().strftime('%H:%M:%S')}")

# Extract date and hour from filename
date_str = filename.split('_')[-1][:8]
year = int(date_str[:4])
month = int(date_str[4:6])
day = int(date_str[6:8])
time_str = filename.split()[-1] if ' ' in filename else filename.split('_')[-1][8:14]
hour = int(time_str[:2])
end_datetime = datetime.datetime(year, month, day, hour, 0, 0)
print(f"End datetime set to: {end_datetime}")

# Load data
radon_levels = []
data_count = 0
total_points = 4391
try:
    with open(filename, 'r', encoding='utf-8') as file:
        print("Loading data from file...")
        for line_number, line in enumerate(file, 1):
            line = line.strip()
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
    plt.plot(timestamps, radon_levels, label='Radon Levels (Bq/m³)', color='#1E90FF', linewidth=0.5)

    locator = AutoDateLocator()
    formatter = ConciseDateFormatter(locator)
    plt.gcf().axes[0].xaxis.set_major_locator(locator)
    plt.gcf().axes[0].xaxis.set_major_formatter(formatter)
    plt.gcf().axes[0].set_xlim(timestamps[0], timestamps[-1])
    plt.gcf().autofmt_xdate()

    plt.xlabel('Date and Time')
    plt.ylabel('Radon Level (Bq/m³)')
    plt.title('Radon Levels Over Time')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    print(f"Displaying plot at {time.time()}")
    plt.show()
    print("Plot display completed.")
except Exception as e:
    print(f"Error generating plot: {e}")
    sys.exit(1)

sys.exit(app.exec_())