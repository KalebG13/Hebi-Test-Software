# Wheel Test UI

PySide6 interface for single-wheel laboratory tests with a HEBI actuator.

## Project Information

Developed by Kaleb Granados Acuna for the Space Robotics Lab, Kyushu Institute of Technology (Kyutech), Japan.

Initial development date: March 2026.

## Installed packages

- `PySide6`
- `hebi-py`
- `matplotlib`
- `pynput`

## Run

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Or:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_app.ps1
```

## Current scope

- First screen to choose `1 wheel` or `2 wheels`
- `1 wheel` workflow implemented
- HEBI motor discovery on the local network
- Connect by selecting an available motor from the dropdown
- Start / stop wheel tests
- `Move to 0 rad` command for the actuator
- Laboratory checklist for visual/manual verification
- Live telemetry panel
- CSV export for excavation and deployment
- Preview mode when no actuator is connected

## Test modes

### Excavation

- User inputs:
  - `Test Number`
  - `Revolutions`
  - `Velocity (rpm)`
- Direction:
  - clockwise
  - negative motor velocity
- Test duration is computed automatically:

```text
time [s] = revolutions / rpm * 60
```

- Data is exported directly to:

```text
data/excavation/
```

### Deployment

- User inputs:
  - `Test Number`
  - `Velocity (rpm)`
  - `Collected Mass (kg)` after the test
- Direction:
  - counter clockwise
  - positive motor velocity
- No predicted duration is used
- Runtime is measured with a stopwatch until the user presses `Stop`
- Data is kept in memory until the operator enters the collected mass and presses `Export Deployment CSV`
- Data is exported to:

```text
data/deployment/
```

## Laboratory checklist

The checklist is visual only. It does not block the test.

- `Camera On`
- `OptiTrack On (optional)`
- `Picture after Ex.`

The checklist is cleared automatically after each completed or stopped test.

## Data exported to CSV

Each CSV contains:

- `test_number`
- `mode`
- `collected_mass_kg`
- `elapsed_seconds`
- `position_rad`
- `velocity_rad_s`
- `effort_nm`
- `voltage_v`
- `winding_temperature_c`

For excavation, `collected_mass_kg` is exported as `0.0000`.

## Notes

- The app currently implements the single-wheel workflow only.
- The `Move to 0 rad` action sends a real position command to the actuator.
- If no motor is connected, the UI can still be tested in preview mode.
