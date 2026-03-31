from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wheel_test_app.hebi_service import (
    DiscoveredModule,
    HebiWheelService,
    TelemetrySample,
    TestPlan,
    build_test_plan,
)


LAB_CHECKLIST_ITEMS = [
    "Camera On",
    "OptiTrack On (optional)",
    "Picture after Ex.",
]


class ProgressBar(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self._value = 0
        self.setFixedHeight(16)
        self.setObjectName("ProgressBar")

    def set_value(self, value: int) -> None:
        self._value = max(0, min(100, value))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QPainter

        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f3d6db"))
        painter.drawRoundedRect(self.rect(), 8, 8)

        fill_width = int(self.width() * (self._value / 100.0))
        if fill_width > 0:
            fill_rect = QRect(0, 0, fill_width, self.height())
            painter.setBrush(QColor("#9F2539"))
            painter.drawRoundedRect(fill_rect, 8, 8)
        painter.end()


class WheelChoicePage(QWidget):
    single_wheel_selected = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)

        logo_label = QLabel()
        logo_label.setObjectName("LogoLabel")
        logo_label.setAlignment(Qt.AlignCenter)
        self._set_logo_pixmap(logo_label)

        title = QLabel("Wheel Test Bench")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Choose how many wheels will participate in the test.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        one_wheel_card, one_wheel_button = self._build_card(
            title="1 Wheel",
            description="Single-wheel mode with full configuration for the first prototype.",
            button_text="Open Single Wheel Test",
        )
        one_wheel_button.clicked.connect(self.single_wheel_selected.emit)

        two_wheel_card, two_wheel_button = self._build_card(
            title="2 Wheels",
            description="Reserved for the dual-wheel workflow. The screen is not implemented yet.",
            button_text="Coming Soon",
        )
        two_wheel_button.setEnabled(False)

        cards_layout.addWidget(one_wheel_card)
        cards_layout.addWidget(two_wheel_card)

        layout.addWidget(logo_label)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addLayout(cards_layout)
        layout.addStretch(1)

    def _set_logo_pixmap(self, label: QLabel) -> None:
        figures_dir = Path(__file__).resolve().parent.parent / "fig"
        for file_name in ("srl_logo.jpg", "srl_logo.png", "slr_logo.png"):
            logo_path = figures_dir / file_name
            if not logo_path.exists():
                continue

            pixmap = QPixmap(str(logo_path))
            if pixmap.isNull():
                continue

            scaled = pixmap.scaledToHeight(350, Qt.SmoothTransformation)
            label.setPixmap(scaled)
            return

        label.setText("SRL")

    def _build_card(self, title: str, description: str, button_text: str) -> tuple[QFrame, QPushButton]:
        frame = QFrame()
        frame.setObjectName("ChoiceCard")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setSpacing(14)

        heading = QLabel(title)
        heading.setObjectName("CardTitle")
        details = QLabel(description)
        details.setWordWrap(True)
        details.setObjectName("CardDescription")
        button = QPushButton(button_text)
        button.setMinimumHeight(44)

        frame_layout.addWidget(heading)
        frame_layout.addWidget(details)
        frame_layout.addStretch(1)
        frame_layout.addWidget(button)
        return frame, button


class SingleWheelTestPage(QWidget):
    back_requested = Signal()

    def __init__(self, hebi_service: HebiWheelService) -> None:
        super().__init__()
        self.hebi_service = hebi_service
        self._current_plan: TestPlan | None = None
        self._test_started_at: float | None = None
        self._running_in_preview = False
        self._data_file_handle = None
        self._csv_writer = None
        self._current_data_path: Path | None = None
        self._zero_move_started_at: float | None = None
        self._pending_deployment_plan: TestPlan | None = None
        self._pending_deployment_samples: list[TelemetrySample] = []

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll_test)
        self.zero_timer = QTimer(self)
        self.zero_timer.setInterval(100)
        self.zero_timer.timeout.connect(self._poll_zero_move)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)

        toolbar = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested.emit)
        header = QLabel("Single Wheel Test")
        header.setObjectName("PageTitle")
        toolbar.addWidget(self.back_button, 0, Qt.AlignLeft)
        toolbar.addWidget(header, 0, Qt.AlignVCenter)
        toolbar.addStretch(1)

        content = QHBoxLayout()
        content.setSpacing(20)
        content.addWidget(self._build_configuration_panel(), 2)
        content.addWidget(self._build_runtime_panel(), 3)

        root.addLayout(toolbar)
        root.addLayout(content)

        self._update_derived_fields()
        self._refresh_available_motors()

    def _build_configuration_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(18)

        test_box = QGroupBox("Test Definition")
        form = QFormLayout(test_box)
        form.setSpacing(12)

        self.test_number_input = QSpinBox()
        self.test_number_input.setMinimum(1)
        self.test_number_input.setMaximum(9999)
        self.test_number_input.setValue(1)

        self.revolutions_input = QDoubleSpinBox()
        self.revolutions_input.setRange(0.1, 10000.0)
        self.revolutions_input.setDecimals(2)
        self.revolutions_input.setValue(5.0)
        self.revolutions_input.setSuffix(" rev")

        self.velocity_input = QDoubleSpinBox()
        self.velocity_input.setRange(0.1, 5000.0)
        self.velocity_input.setDecimals(2)
        self.velocity_input.setValue(30.0)
        self.velocity_input.setSuffix(" rpm")

        self.mode_input = QComboBox()
        self.mode_input.addItems(["Excavation", "Deployment"])

        self.direction_label = QLabel()
        self.duration_label = QLabel()
        self.velocity_rad_label = QLabel()
        self.mass_input = QDoubleSpinBox()
        self.mass_input.setRange(0.0, 1000.0)
        self.mass_input.setDecimals(4)
        self.mass_input.setValue(0.0)
        self.mass_input.setSuffix(" kg")
        self.mass_label = QLabel("Collected Mass")

        self.revolutions_input.valueChanged.connect(self._update_derived_fields)
        self.velocity_input.valueChanged.connect(self._update_derived_fields)
        self.mode_input.currentTextChanged.connect(self._update_derived_fields)

        form.addRow("Test Number", self.test_number_input)
        form.addRow("Revolutions", self.revolutions_input)
        form.addRow("Velocity", self.velocity_input)
        form.addRow("Mode", self.mode_input)
        form.addRow("Direction", self.direction_label)
        form.addRow("Estimated Time", self.duration_label)
        form.addRow("Velocity (rad/s)", self.velocity_rad_label)
        form.addRow(self.mass_label, self.mass_input)

        hebi_box = QGroupBox("HEBI Connection")
        hebi_form = QFormLayout(hebi_box)
        hebi_form.setSpacing(12)

        motor_row = QWidget()
        motor_row_layout = QHBoxLayout(motor_row)
        motor_row_layout.setContentsMargins(0, 0, 0, 0)
        motor_row_layout.setSpacing(8)

        self.motor_selector = QComboBox()
        self.refresh_motors_button = QPushButton("Refresh")
        self.refresh_motors_button.clicked.connect(self._refresh_available_motors)
        motor_row_layout.addWidget(self.motor_selector, 1)
        motor_row_layout.addWidget(self.refresh_motors_button)

        self.hebi_status_label = QLabel("Disconnected")
        self.hebi_status_label.setObjectName("StatusLabel")
        self.connect_button = QPushButton("Connect Selected Motor")
        self.connect_button.clicked.connect(self._connect_hebi)

        hebi_form.addRow("Available Motors", motor_row)
        hebi_form.addRow("Status", self.hebi_status_label)
        hebi_form.addRow("", self.connect_button)

        actions = QHBoxLayout()
        self.start_button = QPushButton("Start Test")
        self.start_button.clicked.connect(self._start_test)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_test)
        self.zero_button = QPushButton("Set Position 0 rad")
        self.zero_button.clicked.connect(self._zero_position)
        self.export_button = QPushButton("Export Deployment CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_pending_deployment_data)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.zero_button)
        actions.addWidget(self.export_button)

        layout.addWidget(test_box)
        layout.addWidget(self._build_checklist_box())
        layout.addWidget(hebi_box)
        layout.addLayout(actions)
        layout.addStretch(1)
        return panel

    def _build_checklist_box(self) -> QGroupBox:
        checklist_box = QGroupBox("Laboratory Checklist")
        checklist_layout = QVBoxLayout(checklist_box)
        checklist_layout.setSpacing(8)

        self.checklist_boxes: list[QCheckBox] = []
        for item in LAB_CHECKLIST_ITEMS:
            checkbox = QCheckBox(item)
            checklist_layout.addWidget(checkbox)
            self.checklist_boxes.append(checkbox)

        return checklist_box

    def _build_runtime_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(18)

        summary = QGroupBox("Runtime Summary")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setSpacing(10)
        self.execution_label = QLabel("Waiting for a test to start.")
        self.execution_label.setWordWrap(True)
        self.progress_bar = ProgressBar()
        self.progress_text = QLabel("Ready")
        self.data_file_label = QLabel("No data file created yet.")
        self.data_file_label.setWordWrap(True)
        summary_layout.addWidget(self.execution_label)
        summary_layout.addWidget(self.progress_bar)
        summary_layout.addWidget(self.progress_text, 0, Qt.AlignRight)
        summary_layout.addWidget(self.data_file_label)

        telemetry = QGroupBox("Current Telemetry")
        telemetry_grid = QGridLayout(telemetry)
        telemetry_grid.setHorizontalSpacing(18)
        telemetry_grid.setVerticalSpacing(10)

        self.telemetry_labels: dict[str, QLabel] = {}
        fields = [
            ("Position", "position"),
            ("Velocity", "velocity"),
            ("Effort", "effort"),
            ("Voltage", "voltage"),
            ("Winding Temp", "temperature"),
        ]
        for row, (label_text, key) in enumerate(fields):
            label = QLabel(label_text)
            value = QLabel("--")
            value.setObjectName("TelemetryValue")
            telemetry_grid.addWidget(label, row, 0)
            telemetry_grid.addWidget(value, row, 1)
            self.telemetry_labels[key] = value

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Test messages will appear here.")

        layout.addWidget(summary)
        layout.addWidget(telemetry)
        layout.addWidget(self.log_output, 1)
        return panel

    def _update_derived_fields(self) -> None:
        try:
            plan = build_test_plan(
                test_number=self.test_number_input.value(),
                revolutions=self.revolutions_input.value(),
                velocity_rpm=self.velocity_input.value(),
                mode=self.mode_input.currentText(),
            )
        except ValueError:
            self.direction_label.setText("--")
            self.duration_label.setText("--")
            self.velocity_rad_label.setText("--")
            return

        self.direction_label.setText(plan.direction_label)
        self.revolutions_input.setEnabled(not plan.uses_stopwatch)
        self.mass_input.setEnabled(plan.uses_stopwatch)
        if plan.uses_stopwatch:
            self.duration_label.setText("Stopwatch / manual stop")
            self.mass_label.setText("Collected Mass")
        else:
            self.duration_label.setText(f"{plan.duration_seconds:.2f} s")
            self.mass_label.setText("Collected Mass (deployment only)")
        self.velocity_rad_label.setText(f"{plan.velocity_rad_s:.3f} rad/s")

    def _refresh_available_motors(self) -> None:
        self.motor_selector.clear()
        modules = self.hebi_service.discover_modules()
        if not modules:
            self.motor_selector.addItem("No motors found on the network", None)
            self._append_log("No HEBI motors were discovered on the network.")
            return

        for module in modules:
            stale_suffix = " [stale]" if module.is_stale else ""
            label = f"{module.family} / {module.name}{stale_suffix}"
            self.motor_selector.addItem(label, module)

        self._append_log(f"Discovered {len(modules)} motor(s) on the network.")

    def _connect_hebi(self) -> None:
        selected_module = self.motor_selector.currentData()
        if not isinstance(selected_module, DiscoveredModule):
            QMessageBox.warning(self, "HEBI connection", "No motor is selected.")
            return

        success, message = self.hebi_service.connect(
            family=selected_module.family,
            module_name=selected_module.name,
        )
        self.hebi_status_label.setText("Connected" if success else "Disconnected")
        self._append_log(message)
        if not success:
            QMessageBox.warning(self, "HEBI connection", message)

    def _start_test(self) -> None:
        if self.zero_timer.isActive():
            QMessageBox.warning(self, "Move to 0 rad", "Wait for the wheel to finish moving to 0 rad before starting a test.")
            return
        if self._pending_deployment_plan is not None:
            QMessageBox.warning(self, "Pending deployment export", "Export the previous deployment data before starting a new test.")
            return

        try:
            self._current_plan = build_test_plan(
                test_number=self.test_number_input.value(),
                revolutions=self.revolutions_input.value(),
                velocity_rpm=self.velocity_input.value(),
                mode=self.mode_input.currentText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid test configuration", str(exc))
            return

        if self.hebi_service.is_connected:
            success, message = self.hebi_service.start_velocity_test(self._current_plan)
            if not success:
                self._close_data_file()
                QMessageBox.warning(self, "HEBI start failed", message)
                return
            self._running_in_preview = False
        else:
            message = "Starting preview mode. Connect a HEBI actuator to stream live feedback."
            self._running_in_preview = True

        self._prepare_test_storage(self._current_plan)
        self._test_started_at = time.monotonic()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.connect_button.setEnabled(False)
        self.refresh_motors_button.setEnabled(False)
        self.zero_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.execution_label.setText(
            f"Running Test #{self._current_plan.test_number}: {self._current_plan.mode} / "
            f"{self._current_plan.direction_label.lower()}."
        )
        self._append_log(message)
        if self._current_plan.uses_stopwatch:
            self._append_log(
                f"Deployment target: {self._current_plan.velocity_rpm:.2f} rpm. Stopwatch is active until Stop is pressed."
            )
            self.progress_bar.set_value(0)
            self.progress_text.setText("0.0 s")
        else:
            self._append_log(
                f"Excavation target: {self._current_plan.revolutions:.2f} rev at {self._current_plan.velocity_rpm:.2f} rpm "
                f"for {self._current_plan.duration_seconds:.2f} s."
            )
            self.progress_bar.set_value(0)
            self.progress_text.setText("0%")
        self.poll_timer.start()

    def _stop_test(self) -> None:
        self._finish_test("Test stopped by user.")

    def _zero_position(self) -> None:
        if self.poll_timer.isActive():
            QMessageBox.warning(self, "Move to 0 rad", "Stop the current test before moving the wheel to 0 rad.")
            return

        success, message = self.hebi_service.zero_position()
        if success:
            self._append_log(message)
            if self.hebi_service.is_connected:
                self._zero_move_started_at = time.monotonic()
                self.zero_button.setEnabled(False)
                self.execution_label.setText("Moving actuator to 0.000 rad...")
                self.zero_timer.start()
        else:
            QMessageBox.warning(self, "Move to 0 rad", message)

    def _poll_zero_move(self) -> None:
        self.hebi_service.refresh_zero_position_command()
        sample = self.hebi_service.read_feedback(0.0)
        if sample is not None:
            self._update_telemetry(sample)
            if abs(sample.position_rad) <= 0.05:
                self.zero_timer.stop()
                self.zero_button.setEnabled(True)
                self.execution_label.setText("Actuator reached 0.000 rad.")
                self._append_log("Actuator reached 0.000 rad.")
                return

        if self._zero_move_started_at is not None and (time.monotonic() - self._zero_move_started_at) >= 8.0:
            self.zero_timer.stop()
            self.zero_button.setEnabled(True)
            self.execution_label.setText("Move to 0 rad timed out.")
            self._append_log("Move to 0 rad timed out before reaching the tolerance window.")

    def _poll_test(self) -> None:
        if self._current_plan is None or self._test_started_at is None:
            return

        elapsed = time.monotonic() - self._test_started_at
        if self._current_plan.duration_seconds is not None:
            progress = min(100, int((elapsed / self._current_plan.duration_seconds) * 100))
            self.progress_bar.set_value(progress)
            self.progress_text.setText(f"{progress}% | {elapsed:.1f} s")
        else:
            self.progress_bar.set_value(0)
            self.progress_text.setText(f"{elapsed:.1f} s")

        if self._running_in_preview:
            sample = self.hebi_service.preview_feedback(self._current_plan, elapsed)
        else:
            self.hebi_service.refresh_velocity_command(self._current_plan)
            sample = self.hebi_service.read_feedback(elapsed)
            if sample is None:
                sample = self.hebi_service.preview_feedback(self._current_plan, elapsed)

        self._update_telemetry(sample)
        self._record_sample(sample)

        if self._current_plan.duration_seconds is not None and elapsed >= self._current_plan.duration_seconds:
            self._finish_test("Test completed.")

    def _finish_test(self, message: str) -> None:
        elapsed = 0.0
        if self._test_started_at is not None:
            elapsed = time.monotonic() - self._test_started_at

        self.poll_timer.stop()
        self.hebi_service.stop()
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(True)
        self.refresh_motors_button.setEnabled(True)
        self.zero_button.setEnabled(True)
        self.execution_label.setText(message)
        self._append_log(message)
        if self._current_plan is not None and self._current_plan.duration_seconds is not None:
            final_progress = 100 if message == "Test completed." else min(
                100, int((elapsed / self._current_plan.duration_seconds) * 100)
            )
            self.progress_bar.set_value(final_progress)
            self.progress_text.setText(f"{final_progress}% | {elapsed:.1f} s")
        else:
            self.progress_bar.set_value(0)
            self.progress_text.setText(f"{elapsed:.1f} s")

        if self._current_data_path is not None:
            self._append_log(f"Data saved to {self._current_data_path}")
            self.data_file_label.setText(f"Data file: {self._current_data_path}")

        if self._current_plan is not None and self._current_plan.uses_stopwatch:
            self.start_button.setEnabled(False)
            self.export_button.setEnabled(True)
            self._pending_deployment_plan = self._current_plan
            self.data_file_label.setText("Deployment data captured. Enter the mass and click 'Export Deployment CSV'.")
        else:
            self.start_button.setEnabled(True)
            self._close_data_file()
            self._reset_checklist()

        self._current_plan = None
        self._test_started_at = None

    def _update_telemetry(self, sample: TelemetrySample) -> None:
        self.telemetry_labels["position"].setText(f"{sample.position_rad:.3f} rad")
        self.telemetry_labels["velocity"].setText(f"{sample.velocity_rad_s:.3f} rad/s")
        self.telemetry_labels["effort"].setText(f"{sample.effort_nm:.3f} Nm")
        self.telemetry_labels["voltage"].setText(f"{sample.voltage_v:.2f} V")
        self.telemetry_labels["temperature"].setText(f"{sample.winding_temperature_c:.2f} C")

    def _prepare_test_storage(self, plan: TestPlan) -> None:
        if plan.uses_stopwatch:
            self._pending_deployment_samples = []
            self._current_data_path = None
            self._close_data_file()
            self.data_file_label.setText("Deployment data will be exported after you enter the mass.")
            return

        self._open_data_file(plan)

    def _open_data_file(self, plan: TestPlan) -> None:
        self._close_data_file()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).resolve().parent.parent / "data" / plan.mode.lower()
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"test_{plan.test_number:03d}_{timestamp}.csv"

        self._data_file_handle = file_path.open("w", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._data_file_handle)
        self._csv_writer.writerow(
            [
                "test_number",
                "mode",
                "collected_mass_kg",
                "elapsed_seconds",
                "position_rad",
                "velocity_rad_s",
                "effort_nm",
                "voltage_v",
                "winding_temperature_c",
            ]
        )
        self._current_data_path = file_path
        self.data_file_label.setText(f"Data file: {file_path}")

    def _record_sample(self, sample: TelemetrySample) -> None:
        if self._current_plan is None:
            return

        if self._current_plan.uses_stopwatch:
            self._pending_deployment_samples.append(
                TelemetrySample(
                    elapsed_seconds=sample.elapsed_seconds,
                    position_rad=sample.position_rad,
                    velocity_rad_s=sample.velocity_rad_s,
                    effort_nm=sample.effort_nm,
                    voltage_v=sample.voltage_v,
                    winding_temperature_c=sample.winding_temperature_c,
                )
            )
            return

        if self._csv_writer is None:
            return

        self._csv_writer.writerow(
            [
                self._current_plan.test_number,
                self._current_plan.mode,
                f"{self._collected_mass_kg():.4f}",
                f"{sample.elapsed_seconds:.3f}",
                f"{sample.position_rad:.6f}",
                f"{sample.velocity_rad_s:.6f}",
                f"{sample.effort_nm:.6f}",
                f"{sample.voltage_v:.6f}",
                f"{sample.winding_temperature_c:.6f}",
            ]
        )
        if self._data_file_handle is not None:
            self._data_file_handle.flush()

    def _export_pending_deployment_data(self) -> None:
        if self._pending_deployment_plan is None:
            QMessageBox.information(self, "Export deployment CSV", "There is no pending deployment data to export.")
            return

        plan = self._pending_deployment_plan
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).resolve().parent.parent / "data" / plan.mode.lower()
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"test_{plan.test_number:03d}_{timestamp}.csv"

        with file_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "test_number",
                    "mode",
                    "collected_mass_kg",
                    "elapsed_seconds",
                    "position_rad",
                    "velocity_rad_s",
                    "effort_nm",
                    "voltage_v",
                    "winding_temperature_c",
                ]
            )
            for sample in self._pending_deployment_samples:
                writer.writerow(
                    [
                        plan.test_number,
                        plan.mode,
                        f"{self._collected_mass_kg():.4f}",
                        f"{sample.elapsed_seconds:.3f}",
                        f"{sample.position_rad:.6f}",
                        f"{sample.velocity_rad_s:.6f}",
                        f"{sample.effort_nm:.6f}",
                        f"{sample.voltage_v:.6f}",
                        f"{sample.winding_temperature_c:.6f}",
                    ]
                )

        self._current_data_path = file_path
        self.data_file_label.setText(f"Data file: {file_path}")
        self._append_log(f"Deployment data exported to {file_path}")
        self._pending_deployment_plan = None
        self._pending_deployment_samples = []
        self.export_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self._reset_checklist()

    def _close_data_file(self) -> None:
        if self._data_file_handle is not None:
            self._data_file_handle.close()
        self._data_file_handle = None
        self._csv_writer = None

    def _append_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")

    def _reset_checklist(self) -> None:
        for checkbox in self.checklist_boxes:
            checkbox.setChecked(False)
        self.mass_input.setValue(0.0)

    def _collected_mass_kg(self) -> float:
        active_plan = self._current_plan if self._current_plan is not None else self._pending_deployment_plan
        if active_plan is None:
            return 0.0
        if not active_plan.uses_stopwatch:
            return 0.0
        return self.mass_input.value()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wheel Test UI")
        self.resize(1160, 760)

        self.hebi_service = HebiWheelService()

        self.stack = QStackedWidget()
        self.choice_page = WheelChoicePage()
        self.single_wheel_page = SingleWheelTestPage(self.hebi_service)
        self.choice_page.single_wheel_selected.connect(self._open_single_wheel)
        self.single_wheel_page.back_requested.connect(self._open_choice)

        self.stack.addWidget(self.choice_page)
        self.stack.addWidget(self.single_wheel_page)
        self.setCentralWidget(self.stack)
        self._apply_styles()

    def _open_choice(self) -> None:
        self.stack.setCurrentWidget(self.choice_page)

    def _open_single_wheel(self) -> None:
        self.stack.setCurrentWidget(self.single_wheel_page)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f4f1ea;
                color: #1c1c1c;
                font-family: "Segoe UI";
                font-size: 13px;
            }
            QMainWindow {
                background: #efe8dc;
            }
            QFrame#ChoiceCard, QGroupBox {
                background: #fffaf0;
                border: 1px solid #d6cdbd;
                border-radius: 16px;
            }
            QLabel#PageTitle {
                font-size: 28px;
                font-weight: 700;
                color: #9f2539;
            }
            QLabel#PageSubtitle {
                color: #4a4a4a;
                font-size: 15px;
            }
            QLabel#LogoLabel {
                color: #9f2539;
                font-size: 40px;
                font-weight: 800;
            }
            QLabel#CardTitle {
                font-size: 20px;
                font-weight: 700;
                color: #9f2539;
            }
            QLabel#CardDescription, QLabel#StatusLabel {
                color: #57534e;
            }
            QLabel#TelemetryValue {
                font-weight: 700;
                color: #9f2539;
            }
            QGroupBox {
                margin-top: 10px;
                padding-top: 10px;
                font-weight: 700;
            }
            QGroupBox::title {
                left: 12px;
                top: -2px;
                subcontrol-origin: margin;
            }
            QPushButton {
                background: #9f2539;
                color: white;
                border: none;
                border-radius: 12px;
                padding: 10px 16px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #7f1d2d;
            }
            QPushButton:disabled {
                background: #d8b6bd;
                color: #fff7f8;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
                background: white;
                border: 1px solid #cdc4b5;
                border-radius: 10px;
                padding: 8px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {
                border: 1px solid #9f2539;
            }
            """
        )


def run() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
