# Wheel Test UI

PySide6 desktop interface for single-wheel and dual-wheel laboratory tests with HEBI actuators.

The application is used to run excavation and deployment tests for the rover wheel prototypes, record live telemetry, and export CSV files for later analysis.

## Project information

Developed by Kaleb Granados Acuna for the Space Robotics Lab, Kyushu Institute of Technology (Kyutech), Japan.

Initial development date: March 2026.

## Current scope

- Start screen with `1 Wheel` and `2 Wheels` choices.
- `1 Wheel` workflow implemented.
- `2 Wheels` movement workflow implemented.
- Left-wheel and right-wheel test modes.
- HEBI motor discovery on the local network.
- Connection by selecting discovered motors from dropdowns.
- Preview mode when no HEBI actuator is connected in the `1 Wheel` workflow.
- Real-motor-only execution in the `2 Wheels` workflow.
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
2. Choose `1 Wheel` or `2 Wheels`.
3. Choose the folder where test data will be saved. The folder is remembered for future sessions.
4. Select a test mode.
5. Enter the test parameters and a file prefix.
6. Refresh and connect to a HEBI motor, or run without a connection in preview mode.
7. Start the test.
8. Stop manually when required, then export deployment data if the selected mode is a deployment test.

The save folder can be changed from either test screen with `Change Save Folder`.

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

## Dual-wheel movement tests

The `2 Wheels` workflow uses two physical wheel assignments:

- `Left Wheel`
- `Right Wheel`

The operator connects each physical wheel to a different HEBI module and sets an independent velocity for each wheel. The test stops by motion time, not by revolutions, to avoid one wheel dragging the other when the two velocities are different.

General fields:

- `Test Number`
- `Direction`
- `Duration`
- `File Prefix`
- `Save Folder`

Direction controls the velocity sign and the front/rear data assignment:

| Direction | Motor velocity sign | FrontWheel CSV source | RearWheel CSV source |
| --- | --- | --- | --- |
| `Clockwise` | Negative | Right Wheel | Left Wheel |
| `Counter clockwise` | Positive | Left Wheel | Right Wheel |

The dual-wheel screen also includes:

- A rover diagram showing which physical wheel maps to `FrontWheel` and `RearWheel`.
- A progress bar under the diagram.
- Per-wheel motor connection controls.
- Per-wheel velocity inputs.
- Per-wheel `Test Wheel` buttons that move the selected actuator slightly and return it to `0 rad`.
- A shared `Set Position to 0 rad` button for both wheels.
- Per-wheel deployment buttons that run the selected wheel at `14 rpm` in the opposite direction from the movement test until `Stop` is pressed.
- Per-wheel collected mass inputs.
- Live effort and power graphs with left/right traces.

The dual-wheel workflow does not simulate motion. Both HEBI actuators must be connected before `Start`.

Dual-wheel movement tests record 1.0 s before motion and 1.0 s after motion. For example, a `Duration` of `12 s` produces 12 s of wheel movement and about 14 s of telemetry in each CSV.

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

In the `2 Wheels` workflow, deployment is used only to move each wheel during mass collection. Deployment runs opposite to the selected movement direction so the wheel can discharge material. Deployment telemetry is not exported as a separate file. Instead, the collected mass entered for each physical wheel is written into the corresponding movement CSV according to the front/rear mapping.

## HEBI behavior

- The app discovers available HEBI modules through `hebi.Lookup()`.
- The selected module is connected by family and module name.
- HEBI feedback is requested at 20 Hz when supported.
- Velocity commands are refreshed continuously while the wheel is moving because HEBI commands expire after the configured command lifetime.
- `Set Position 0 rad` sends a real position command to the connected actuator and refreshes it for up to 8 seconds, or until the measured position is within 0.05 rad.
- If no actuator is connected, the app runs in preview mode with simulated telemetry.
- In the `2 Wheels` workflow, both motors must be connected and the same HEBI module cannot be assigned to both physical wheels.

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

The `2 Wheels` checklist contains:

- `Camera On`
- `Picture Before Mov`
- `Picture After Mov`
- `Optitrack`
- `Position in 0 rad`

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

The dual-wheel screen shows the same telemetry per physical wheel and comparative live graphs for `Left` and `Right`.

## CSV output

CSV files are saved under the selected output folder:

```text
<selected_output_folder>/excavation/
<selected_output_folder>/deployment/
<selected_output_folder>/two_wheels/frontwheel/
<selected_output_folder>/two_wheels/rearwheel/
```

Filenames use this pattern:

```text
<file_prefix>_test<test_number>_<YYYYMMDD_HHMMSS>.csv
<file_prefix>_<YYYYMMDD_HHMMSS>_FrontWheel.csv
<file_prefix>_<YYYYMMDD_HHMMSS>_RearWheel.csv
```

Each CSV contains:

- `test_number`
- `mode`
- `direction`
- `physical_wheel`
- `wheel_role`
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

For single-wheel excavation, `collected_mass_kg` is exported as `0.0000`. For dual-wheel movement, `collected_mass_kg` is the mass entered for the physical wheel that maps to the exported role.

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

- The `1 Wheel` workflow can be tested without hardware through preview mode.
- The `2 Wheels` workflow intentionally requires real HEBI motors.
- The `data/`, `.venv/`, `build/`, `dist/`, `__pycache__/`, and generated PyInstaller spec files are ignored by git.
