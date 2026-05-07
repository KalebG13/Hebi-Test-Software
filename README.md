# Wheel Test UI

PySide6 desktop interface for single-wheel laboratory tests with a HEBI actuator.

The application is used to run excavation and deployment tests for the rover wheel prototypes, record live telemetry, and export CSV files for later analysis.

## Project information

Developed by Kaleb Granados Acuna for the Space Robotics Lab, Kyushu Institute of Technology (Kyutech), Japan.

Initial development date: March 2026.

## Current scope

- Start screen with `1 Wheel` and `2 Wheels` choices.
- `1 Wheel` workflow implemented.
- `2 Wheels` workflow reserved and disabled.
- Left-wheel and right-wheel test modes.
- HEBI motor discovery on the local network.
- Connection by selecting one discovered motor from the dropdown.
- Preview mode when no HEBI actuator is connected.
- Start/stop test execution.
- `Set Position 0 rad` command for the actuator.
- Visual laboratory checklist.
- Live telemetry panel.
- Live effort and power graphs.
- CSV export for excavation and deployment data.
- User-selected save folder stored between sessions.

## Requirements

Install the Python packages listed in `requirements.txt`:

- `hebi-py==2.13.1`
- `matplotlib==3.10.8`
- `pynput==1.8.1`
- `PySide6==6.11.0`

## Setup

Create the virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```powershell
python -m pip install -r requirements.txt
```

## Run

From an activated virtual environment:

```powershell
python main.py
```

Or run the helper script, which uses `.venv\Scripts\python.exe` directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

If a required dependency is missing, `main.py` prints a short hint showing how to run the project with the local virtual environment.

## Application flow

1. Open the application.
2. Choose `1 Wheel`.
3. Choose the folder where test data will be saved. The folder is remembered for future sessions.
4. Select a test mode.
5. Enter the test parameters and a file prefix.
6. Refresh and connect to a HEBI motor, or run without a connection in preview mode.
7. Start the test.
8. Stop manually when required, then export deployment data if the selected mode is a deployment test.

The save folder can be changed from the single-wheel screen with `Change Save Folder`.

## Test definition fields

- `Test Number`: numeric test identifier.
- `Revolutions`: target revolutions for excavation tests only.
- `Velocity`: wheel velocity in rpm.
- `Mode`: wheel side and test type.
- `Direction`: derived automatically from the mode.
- `Estimated Time`: computed for excavation, stopwatch/manual stop for deployment.
- `Velocity (rad/s)`: derived from rpm.
- `File Prefix`: required prefix for the CSV filename. Spaces are converted to underscores and unsupported filename characters are removed.
- `Collected Mass`: used only when exporting deployment data.

Default values:

- `Test Number`: `1`
- `Revolutions`: `2.0 rev`
- `Velocity`: `14.0 rpm`

## Test modes

The current single-wheel workflow supports four modes:

| Mode | Type | Direction label | Motor velocity sign |
| --- | --- | --- | --- |
| `Left Wheel - Excavation` | Excavation | Clockwise | Negative |
| `Left Wheel - Deployment` | Deployment | Counter clockwise | Positive |
| `Right Wheel - Excavation` | Excavation | Counter clockwise | Positive |
| `Right Wheel - Deployment` | Deployment | Clockwise | Negative |

The motor velocity is converted from rpm to rad/s:

```text
velocity [rad/s] = rpm * 2 * pi / 60
```

## Excavation tests

Excavation tests use a fixed target duration calculated from revolutions and rpm:

```text
time [s] = revolutions / rpm * 60
```

Execution phases:

1. `Pre-roll`: records 1.0 s of baseline telemetry before motion.
2. `Motion`: sends the velocity command until the calculated duration is reached.
3. `Post-roll`: stops the motor and records 1.0 s of settling telemetry.

CSV data is written during the test.

## Deployment tests

Deployment tests use a stopwatch workflow:

- Revolutions are not used.
- The wheel runs until the operator presses `Stop`.
- The app records 1.0 s before motion and 1.0 s after stop.
- Samples are kept in memory after the run.
- The operator enters `Collected Mass`.
- The operator clicks `Export Deployment CSV`.

Deployment data cannot be exported with a collected mass of `0 kg`.

## HEBI behavior

- The app discovers available HEBI modules through `hebi.Lookup()`.
- The selected module is connected by family and module name.
- HEBI feedback is requested at 20 Hz when supported.
- Velocity commands are refreshed continuously while the wheel is moving because HEBI commands expire after the configured command lifetime.
- `Set Position 0 rad` sends a real position command to the connected actuator and refreshes it for up to 8 seconds, or until the measured position is within 0.05 rad.
- If no actuator is connected, the app runs in preview mode with simulated telemetry.

Optional environment variables:

- `HEBI_FAMILY`
- `HEBI_MODULE_NAME`

These are loaded by the HEBI service, but the current UI connects using the selected discovered module.

## Laboratory checklist

The checklist is visual only. It does not block the test.

- `Camera On`
- `OptiTrack On (optional)`
- `Picture after Ex.`
- `Picture after Dep.`

The checklist is reset after completed excavation runs and after deployment data is exported. `Reset Interface` also clears the checklist, current inputs, charts, telemetry labels, logs, and pending deployment samples.

## Runtime display

The single-wheel screen shows:

- Runtime summary and progress.
- Current data file or output folder.
- Position.
- Velocity.
- Effort.
- Voltage.
- Current.
- Acceleration X.
- Winding temperature.
- Live `Effort vs Time` graph.
- Live `Power vs Time` graph.
- Test log messages.

Power is computed as:

```text
power [W] = voltage [V] * current [A]
```

## CSV output

CSV files are saved under the selected output folder:

```text
<selected_output_folder>/excavation/
<selected_output_folder>/deployment/
```

Filenames use this pattern:

```text
<file_prefix>_test<test_number>_<YYYYMMDD_HHMMSS>.csv
```

Each CSV contains:

- `test_number`
- `mode`
- `collected_mass_kg`
- `elapsed_seconds`
- `position_rad`
- `velocity_rad_s`
- `effort_nm`
- `voltage_v`
- `current_a`
- `power_w`
- `accel_x_raw_m_s2`
- `accel_x_m_s2`
- `accel_y_m_s2`
- `winding_temperature_c`

For excavation, `collected_mass_kg` is exported as `0.0000`.

The corrected X acceleration subtracts the gravity constant used by the app:

```text
accel_x_m_s2 = accel_x_raw_m_s2 - (-9.8)
```

## Project structure

```text
main.py                         Application entry point
run_app.ps1                     Windows launcher using the local virtual environment
requirements.txt                Python dependencies
wheel_test_app/main_window.py   PySide6 UI and test workflow
wheel_test_app/hebi_service.py  HEBI discovery, commands, telemetry, and preview samples
fig/slr_logo.png                Logo asset used by the start screen
data/                           Local generated CSV output, ignored by git
```

## Notes

- The implemented workflow is single-wheel only.
- The first screen still includes a disabled `2 Wheels` option for future work.
- The app can be tested without hardware through preview mode.
- The `data/`, `.venv/`, `build/`, `dist/`, `__pycache__/`, and generated PyInstaller spec files are ignored by git.
