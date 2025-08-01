# RadonEye RD200 Data Grapher

This project provides a tool to graph data from the RadonEye RD200 device. It can be run as a precompiled executable or as a Python script.

## Precompiled Versions
- **Mac**: Download `radon_plot.app` from the [Releases](https://github.com/tyns/RadonEye-RD200-Data-Grapher/releases) page (if available).
  - Double-click the `.app` file to run. No installation required.
- **Windows**: Download `radon_plot.exe` from the [Releases](https://github.com/tyns/RadonEye-RD200-Data-Grapher/releases) page (if available).
  - Double-click the `.exe` file to run. No installation required.

## Running from Source (Python Script)
If you prefer to run the Python script (`radon_plot.py`), follow these steps:

### Prerequisites
- **Python 3.6 or higher**: Install from [python.org](https://www.python.org/downloads/).
- **Required Libraries**:
  - `matplotlib` (for plotting)
  - `numpy` (for data handling)
  - Install them via pip:
    ```bash
    pip3 install matplotlib numpy
    ```
  - Note: Check `radon_plot.py` for any additional dependencies and install them similarly (e.g., `pip3 install <library>`).

### Instructions
1. **Clone the Repository**:
   - Use Git:
     ```bash
     git clone https://github.com/tyns/RadonEye-RD200-Data-Grapher.git
     cd RadonEye-RD200-Data-Grapher
     ```
   - Or download the ZIP from the GitHub page and extract it.

2. **Run the Script**:
   - Open a terminal in the project folder.
   - Execute:
     ```bash
     python3 radon_plot.py
     ```
   - This assumes your data files (e.g., `.txt` from the RadonEye) are in the same directory or specified in the script.

### Notes
- Ensure your RadonEye data files (e.g., `IE08RE000863_20250731 164749.txt`) are accessible to the script.
- For precompiled versions, check the Releases page for updates. Contributions or issues can be reported via GitHub.