from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Any

try:
    import hebi
except ImportError:  # pragma: no cover
    hebi = None


MODE_TO_DIRECTION = {
    "Excavation": ("Clockwise", -1),
    "Deployment": ("Counter clockwise", 1),
}


@dataclass(slots=True)
class DiscoveredModule:
    family: str
    name: str
    mac_address: str
    is_stale: bool


@dataclass(slots=True)
class TestPlan:
    test_number: int
    revolutions: float | None
    velocity_rpm: float
    mode: str
    direction_label: str
    direction_sign: int
    duration_seconds: float | None
    velocity_rad_s: float
    uses_stopwatch: bool


@dataclass(slots=True)
class TelemetrySample:
    elapsed_seconds: float
    position_rad: float
    velocity_rad_s: float
    effort_nm: float
    voltage_v: float
    winding_temperature_c: float


def build_test_plan(
    test_number: int,
    revolutions: float,
    velocity_rpm: float,
    mode: str,
) -> TestPlan:
    if velocity_rpm <= 0:
        raise ValueError("Velocity must be greater than 0 rpm.")
    if mode not in MODE_TO_DIRECTION:
        raise ValueError(f"Unsupported mode: {mode}")

    direction_label, direction_sign = MODE_TO_DIRECTION[mode]
    uses_stopwatch = mode == "Deployment"
    if uses_stopwatch:
        target_revolutions = None
        duration_seconds = None
    else:
        if revolutions <= 0:
            raise ValueError("Revolutions must be greater than 0.")
        target_revolutions = revolutions
        duration_seconds = (revolutions / velocity_rpm) * 60.0

    velocity_rad_s = (velocity_rpm * 2.0 * math.pi) / 60.0
    return TestPlan(
        test_number=test_number,
        revolutions=target_revolutions,
        velocity_rpm=velocity_rpm,
        mode=mode,
        direction_label=direction_label,
        direction_sign=direction_sign,
        duration_seconds=duration_seconds,
        velocity_rad_s=velocity_rad_s,
        uses_stopwatch=uses_stopwatch,
    )


class HebiWheelService:
    def __init__(self) -> None:
        self.default_family = os.getenv("HEBI_FAMILY", "")
        self.default_module_name = os.getenv("HEBI_MODULE_NAME", "")
        self._lookup: Any | None = None
        self._group: Any | None = None
        self._command: Any | None = None
        self._feedback: Any | None = None
        self._zero_position_rad = 0.0
        self._last_raw_position_rad = 0.0

    @property
    def is_connected(self) -> bool:
        return self._group is not None

    def discover_modules(self) -> list[DiscoveredModule]:
        if hebi is None:
            return []

        if self._lookup is None:
            self._lookup = hebi.Lookup()
            time.sleep(2.0)

        modules: list[DiscoveredModule] = []
        for entry in self._lookup.entrylist:
            modules.append(
                DiscoveredModule(
                    family=entry.family,
                    name=entry.name,
                    mac_address=str(entry.mac_address),
                    is_stale=bool(getattr(entry, "is_stale", False)),
                )
            )

        modules.sort(key=lambda module: (module.family.lower(), module.name.lower()))
        return modules

    def connect(self, family: str, module_name: str, timeout_ms: int = 4000) -> tuple[bool, str]:
        if hebi is None:
            return False, "hebi-py is not installed in this environment."
        if not family.strip() or not module_name.strip():
            return False, "HEBI family and module name are required."

        if self._lookup is None:
            self._lookup = hebi.Lookup()
            time.sleep(2.0)

        group = self._lookup.get_group_from_names(family.strip(), module_name.strip(), timeout_ms=timeout_ms)
        if group is None:
            self._group = None
            self._command = None
            self._feedback = None
            return False, f"Module '{module_name}' in family '{family}' was not found."

        group.command_lifetime = 500
        try:
            group.feedback_frequency = 20.0
        except AttributeError:
            pass

        self._group = group
        self._command = hebi.GroupCommand(group.size)
        self._feedback = hebi.GroupFeedback(group.size)
        self._zero_position_rad = 0.0
        self._last_raw_position_rad = 0.0
        return True, f"Connected to {family}/{module_name}."

    def start_velocity_test(self, plan: TestPlan) -> tuple[bool, str]:
        if not self.is_connected or self._group is None or self._command is None:
            return False, "No HEBI actuator connected. The UI can still run in preview mode."

        sent = self._send_velocity_command(plan)
        if not sent:
            return False, "Failed to send the wheel velocity command."
        return True, "Wheel command sent to HEBI actuator."

    def refresh_velocity_command(self, plan: TestPlan) -> bool:
        if not self.is_connected or self._group is None or self._command is None:
            return False

        return self._send_velocity_command(plan)

    def _send_velocity_command(self, plan: TestPlan) -> bool:
        self._command.clear()
        self._command.velocity = [plan.direction_sign * plan.velocity_rad_s]
        return self._group.send_command(self._command)

    def zero_position(self) -> tuple[bool, str]:
        if self.is_connected and self._group is not None and self._command is not None:
            self._zero_position_rad = 0.0
            sent = self._send_position_command(0.0)
            if sent:
                return True, "Actuator commanded to move to 0.000 rad."
            return False, "Failed to send the 0.000 rad position command."

        self._zero_position_rad = 0.0
        self._last_raw_position_rad = 0.0
        return True, "Preview position reset to 0.000 rad."

    def refresh_zero_position_command(self) -> bool:
        if not self.is_connected or self._group is None or self._command is None:
            return False
        return self._send_position_command(0.0)

    def stop(self) -> None:
        if not self.is_connected or self._group is None or self._command is None:
            return
        self._command.clear()
        self._command.velocity = [0.0]
        self._group.send_command(self._command)

    def read_feedback(self, elapsed_seconds: float) -> TelemetrySample | None:
        if not self.is_connected or self._group is None:
            return None

        feedback = self._group.get_next_feedback(timeout_ms=10, reuse_fbk=self._feedback)
        if feedback is None:
            return None

        raw_position = _first_value(feedback.position)
        self._last_raw_position_rad = raw_position

        return TelemetrySample(
            elapsed_seconds=elapsed_seconds,
            position_rad=raw_position - self._zero_position_rad,
            velocity_rad_s=_first_value(feedback.velocity),
            effort_nm=_first_value(feedback.effort),
            voltage_v=_first_value(feedback.voltage),
            winding_temperature_c=_first_value(getattr(feedback, "motor_winding_temperature", None)),
        )

    def preview_feedback(self, plan: TestPlan, elapsed_seconds: float) -> TelemetrySample:
        signed_velocity = plan.direction_sign * plan.velocity_rad_s
        progress = min(1.0, elapsed_seconds / plan.duration_seconds) if plan.duration_seconds else 0.0
        raw_position = signed_velocity * elapsed_seconds
        self._last_raw_position_rad = raw_position
        return TelemetrySample(
            elapsed_seconds=elapsed_seconds,
            position_rad=raw_position - self._zero_position_rad,
            velocity_rad_s=signed_velocity,
            effort_nm=0.8 + abs(signed_velocity) * 0.05,
            voltage_v=48.0 - (progress * 0.5),
            winding_temperature_c=28.0 + (progress * 6.0),
        )

    def _send_position_command(self, target_position_rad: float) -> bool:
        self._command.clear()
        self._command.position = [target_position_rad]
        self._command.velocity = [0.0]
        return bool(self._group.send_command(self._command))


def _first_value(raw: Any) -> float:
    if raw is None:
        return 0.0
    if hasattr(raw, "__len__"):
        if len(raw) == 0:
            return 0.0
        return float(raw[0])
    return float(raw)
