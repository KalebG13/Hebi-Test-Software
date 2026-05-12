from __future__ import annotations

import csv
import math
import sys
import time
from pathlib import Path

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QLocale, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wheel_test_app.hebi_service import (
    DiscoveredModule,
    HebiWheelService,
    MODE_CONFIG,
    TelemetrySample,
    TestPlan,
    build_test_plan,
)


LAB_CHECKLIST_ITEMS = [
    "Camera On",
    "OptiTrack On (optional)",
    "Picture after Ex.",
    "Picture after Dep.",
]
TWO_WHEEL_CHECKLIST_ITEMS = [
    "Camera On",
    "Picture Before Mov",
    "Picture After Mov",
    "Optitrack",
    "Position in 0 rad",
]
#Delay durations for the pre-roll and post-roll phases, which capture data before the wheel starts moving and after it stops so the CSV includes the baseline and settling behavior.
PRE_ROLL_SECONDS = 1.0
POST_ROLL_SECONDS = 1.0
TEST_DEFINITION_LABEL_WIDTH = 190
DEFAULT_TEST_NUMBER = 1
DEFAULT_REVOLUTIONS = 2.0
DEFAULT_VELOCITY_RPM = 14.0
TWO_WHEEL_DEPLOYMENT_RPM = 14.0
TWO_WHEEL_WIGGLE_TARGET_RAD = 0.35
TWO_WHEEL_WIGGLE_HOLD_SECONDS = 1.0
TWO_WHEEL_WIGGLE_TIMEOUT_SECONDS = 4.0


def _app_base_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resource_directory() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root)
    return _app_base_directory()


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
    two_wheel_selected = Signal()

    def __init__(self) -> None:
        super().__init__()
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        self.page_layout = QVBoxLayout(content_widget)
        self.page_layout.setContentsMargins(40, 40, 40, 40)
        self.page_layout.setSpacing(24)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("LogoLabel")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_pixmap = self._load_logo_pixmap()
        self._update_logo_pixmap()

        title = QLabel("Wheel Test Bench")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Choose how many wheels will participate in the test.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        self.cards_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.cards_layout.setSpacing(20)

        one_wheel_card, one_wheel_button = self._build_card(
            title="1 Wheel",
            description="Single-wheel mode with full configuration for the first prototype.",
            button_text="Open Single Wheel Test",
        )
        one_wheel_button.clicked.connect(self.single_wheel_selected.emit)

        two_wheel_card, two_wheel_button = self._build_card(
            title="2 Wheels",
            description="Reserved for the dual-wheel workflow.",
            button_text="Open Dual Wheel Test",
        )
        two_wheel_button.clicked.connect(self.two_wheel_selected.emit)

        self.cards_layout.addWidget(one_wheel_card)
        self.cards_layout.addWidget(two_wheel_card)

        self.page_layout.addWidget(self.logo_label)
        self.page_layout.addWidget(title)
        self.page_layout.addWidget(subtitle)
        self.page_layout.addSpacing(12)
        self.page_layout.addLayout(self.cards_layout)
        self.page_layout.addStretch(1)

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)
        self._update_responsive_layout()

    def _load_logo_pixmap(self) -> QPixmap | None:
        figures_dir = _resource_directory() / "fig"
        for file_name in ("srl_logo.jpg", "srl_logo.png", "slr_logo.png"):
            logo_path = figures_dir / file_name
            if not logo_path.exists():
                continue

            pixmap = QPixmap(str(logo_path))
            if pixmap.isNull():
                continue

            return pixmap

        return None

    def _update_logo_pixmap(self) -> None:
        if self.logo_pixmap is None:
            self.logo_label.setText("SRL")
            return

        target_height = max(100, min(260, self.width() // 4))
        scaled = self.logo_pixmap.scaledToHeight(target_height, Qt.SmoothTransformation)
        self.logo_label.setPixmap(scaled)

    def _update_responsive_layout(self) -> None:
        if self.width() < 900:
            self.cards_layout.setDirection(QBoxLayout.TopToBottom)
        else:
            self.cards_layout.setDirection(QBoxLayout.LeftToRight)
        self._update_logo_pixmap()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive_layout()

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
    change_output_directory_requested = Signal()

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
        # Deployment samples are buffered in memory because the CSV is exported
        # only after the operator enters the collected mass.
        self._pending_deployment_plan: TestPlan | None = None
        self._pending_deployment_samples: list[TelemetrySample] = []
        self._max_chart_points = 300
        self._test_phase = "idle"
        self._pending_finish_message = ""
        self._motion_started_at: float | None = None
        self._post_roll_started_at: float | None = None
        self._motion_elapsed_before_post_roll = 0.0
        self._output_directory: Path | None = None

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll_test)
        self.zero_timer = QTimer(self)
        self.zero_timer.setInterval(100)
        self.zero_timer.timeout.connect(self._poll_zero_move)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        root = QVBoxLayout(content_widget)
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

        self.configuration_panel = self._build_configuration_panel()
        self.runtime_panel = self._build_runtime_panel()
        self.content_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.content_layout.setSpacing(20)
        self.content_layout.addWidget(self.configuration_panel, 2)
        self.content_layout.addWidget(self.runtime_panel, 3)

        root.addLayout(toolbar)
        root.addLayout(self.content_layout)

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)

        self._update_derived_fields()
        self._refresh_available_motors()
        self._update_responsive_layout()

    def _fixed_form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFixedWidth(TEST_DEFINITION_LABEL_WIDTH)
        return label

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
        self.test_number_input.setButtonSymbols(QAbstractSpinBox.NoButtons)

        self.revolutions_input = QDoubleSpinBox()
        self.revolutions_input.setRange(0.1, 10000.0)
        self.revolutions_input.setDecimals(2)
        self.revolutions_input.setValue(2.0)
        self.revolutions_input.setSuffix(" rev")
        self.revolutions_input.setButtonSymbols(QAbstractSpinBox.NoButtons)

        self.velocity_input = QDoubleSpinBox()
        self.velocity_input.setRange(0.1, 5000.0)
        self.velocity_input.setDecimals(2)
        self.velocity_input.setValue(14.0) #Max velocity for the first prototype at 35V 5A is around 15 rpm, so 14 rpm gives a little headroom for testing.
        self.velocity_input.setSuffix(" rpm")
        self.velocity_input.setButtonSymbols(QAbstractSpinBox.NoButtons)

        self.mode_input = QComboBox()
        self.mode_input.addItems(list(MODE_CONFIG.keys()))

        self.direction_label = QLabel()
        self.duration_label = QLabel()
        self.velocity_rad_label = QLabel()
        self.file_prefix_input = QLineEdit()
        self.file_prefix_input.setPlaceholderText("Example: Slanted_Grouser")
        self.mass_input = QDoubleSpinBox()
        self.mass_input.setRange(0.0, 1000.0)
        self.mass_input.setDecimals(4)
        self.mass_input.setValue(0.0)
        self.mass_input.setSuffix(" kg")
        self.mass_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.mass_label = QLabel("Collected Mass")
        self.mass_label.setFixedWidth(TEST_DEFINITION_LABEL_WIDTH)

        self.revolutions_input.valueChanged.connect(self._update_derived_fields)
        self.velocity_input.valueChanged.connect(self._update_derived_fields)
        self.mode_input.currentTextChanged.connect(self._update_derived_fields)

        form.addRow(self._fixed_form_label("Test Number"), self.test_number_input)
        form.addRow(self._fixed_form_label("Revolutions"), self.revolutions_input)
        form.addRow(self._fixed_form_label("Velocity"), self.velocity_input)
        form.addRow(self._fixed_form_label("Mode"), self.mode_input)
        form.addRow(self._fixed_form_label("Direction"), self.direction_label)
        form.addRow(self._fixed_form_label("Estimated Time"), self.duration_label)
        form.addRow(self._fixed_form_label("Velocity (rad/s)"), self.velocity_rad_label)
        form.addRow(self._fixed_form_label("File Prefix"), self.file_prefix_input)
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
        self.change_output_directory_button = QPushButton("Change Save Folder")
        self.change_output_directory_button.clicked.connect(self.change_output_directory_requested.emit)
        self.reset_button = QPushButton("Reset Interface")
        self.reset_button.clicked.connect(self._reset_interface)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.zero_button)
        actions.addWidget(self.export_button)
        actions.addWidget(self.change_output_directory_button)
        actions.addWidget(self.reset_button)

        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout.addWidget(test_box)
        layout.addWidget(self._build_checklist_box())
        layout.addWidget(hebi_box)
        layout.addLayout(actions)
        layout.addStretch(1)
        return panel

    def _build_checklist_box(self) -> QGroupBox:
        checklist_box = QGroupBox("Laboratory Checklist")
        checklist_layout = QGridLayout(checklist_box)
        checklist_layout.setHorizontalSpacing(16)
        checklist_layout.setVerticalSpacing(8)

        self.checklist_boxes: list[QCheckBox] = []
        for index, item in enumerate(LAB_CHECKLIST_ITEMS):
            checkbox = QCheckBox(item)
            row = index // 2
            column = index % 2
            checklist_layout.addWidget(checkbox, row, column)
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
            ("Current", "current"),
            ("Accel X", "accel_x"),
            ("Winding Temp", "temperature"),
        ]
        for row, (label_text, key) in enumerate(fields):
            label = QLabel(label_text)
            value = QLabel("--")
            value.setObjectName("TelemetryValue")
            telemetry_grid.addWidget(label, row, 0)
            telemetry_grid.addWidget(value, row, 1)
            self.telemetry_labels[key] = value

        charts = QGroupBox("Live Graphs")
        charts_layout = QHBoxLayout(charts)
        charts_layout.setSpacing(12)
        self.effort_series, self.effort_chart_view = self._build_chart("Effort vs Time", "Time (s)", "Effort (Nm)")
        self.power_series, self.power_chart_view = self._build_chart("Power vs Time", "Time (s)", "Power (W)")
        charts_layout.addWidget(self.effort_chart_view, 1)
        charts_layout.addWidget(self.power_chart_view, 1)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Test messages will appear here.")
        self.log_output.setMaximumHeight(110)

        layout.addWidget(summary)
        layout.addWidget(telemetry)
        layout.addWidget(charts, 1)
        layout.addWidget(self.log_output, 1)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return panel

    def _build_chart(self, title: str, x_title: str, y_title: str) -> tuple[QLineSeries, QChartView]:
        series = QLineSeries()
        chart = QChart()
        chart.addSeries(series)
        chart.setTitle(title)
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)

        axis_x = QValueAxis()
        axis_x.setTitleText(x_title)
        axis_x.setRange(0.0, 10.0)
        axis_x.setLabelFormat("%.1f")

        axis_y = QValueAxis()
        axis_y.setTitleText(y_title)
        axis_y.setRange(0.0, 10.0)
        axis_y.setLabelFormat("%.2f")

        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        chart_view = QChartView(chart)
        chart_view.setMinimumHeight(220)
        return series, chart_view

    def _update_responsive_layout(self) -> None:
        if self.width() < 1200:
            self.content_layout.setDirection(QBoxLayout.TopToBottom)
        else:
            self.content_layout.setDirection(QBoxLayout.LeftToRight)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive_layout()

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
            self.mass_label.setText("Collected Mass(deployment only)")
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

    def set_output_directory(self, output_directory: Path) -> None:
        self._output_directory = output_directory
        self.data_file_label.setText(self._data_file_status_text())
        self._append_log(f"Data will be saved under {self._output_root()}")

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
        if not self._file_prefix():
            QMessageBox.warning(self, "Missing file prefix", "Write a file prefix before starting the test.")
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
            message = "Connected to HEBI actuator. Recording 1.0 s of baseline data before the wheel starts moving."
            self._running_in_preview = False
        else:
            message = "Starting preview mode. Recording 1.0 s of baseline data before the simulated motion starts."
            self._running_in_preview = True

        self._prepare_test_storage(self._current_plan)
        self._reset_charts()
        self._test_started_at = time.monotonic()
        self._test_phase = "pre_roll"
        self._pending_finish_message = ""
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.connect_button.setEnabled(False)
        self.refresh_motors_button.setEnabled(False)
        self.zero_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.execution_label.setText(
            "Pre-test capture: collecting 1.0 s of data before motion starts so the CSV shows the baseline."
        )
        self._append_log(message)
        if self._current_plan.uses_stopwatch:
            self._append_log(
                f"{self._current_plan.test_type} target for the {self._current_plan.wheel_side.lower()} wheel: "
                f"{self._current_plan.velocity_rpm:.2f} rpm. Stopwatch is active until Stop is pressed."
            )
            self.progress_bar.set_value(0)
            self.progress_text.setText("Pre-roll 0.0 / 1.0 s")
        else:
            self._append_log(
                f"{self._current_plan.test_type} target for the {self._current_plan.wheel_side.lower()} wheel: "
                f"{self._current_plan.revolutions:.2f} rev at {self._current_plan.velocity_rpm:.2f} rpm "
                f"for {self._current_plan.duration_seconds:.2f} s."
            )
            self.progress_bar.set_value(0)
            self.progress_text.setText("Pre-roll 0.0 / 1.0 s")
        self.poll_timer.start()

    def _stop_test(self) -> None:
        if self._test_phase == "pre_roll":
            self._complete_test_run("Test cancelled before motion started.")
            return
        self._begin_post_roll("Test stopped by user.")

    def _zero_position(self) -> None:
        if self.poll_timer.isActive():
            QMessageBox.warning(self, "Move to 0 rad", "Stop the current test before moving the wheel to 0 rad.")
            return

        success, message = self.hebi_service.zero_position()
        if success:
            self._append_log(message)
            if self.hebi_service.is_connected:

                # The zero-position command is also refreshed for a short time,
                # otherwise the actuator may not have enough time to reach 0 rad.

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
        sample = self._sample_for_phase(elapsed)

        self._update_telemetry(sample)
        self._update_charts(sample)
        self._record_sample(sample)

        if self._test_phase == "pre_roll" and elapsed >= PRE_ROLL_SECONDS:
            self._begin_motion_phase()
            return

        if self._test_phase == "active" and self._current_plan.duration_seconds is not None:
            active_elapsed = max(0.0, elapsed - PRE_ROLL_SECONDS)
            if active_elapsed >= self._current_plan.duration_seconds:
                self._begin_post_roll("Test completed.")
                return

        if self._test_phase == "post_roll" and self._post_roll_started_at is not None:
            post_roll_elapsed = time.monotonic() - self._post_roll_started_at
            if post_roll_elapsed >= POST_ROLL_SECONDS:
                self._complete_test_run(self._pending_finish_message or "Test completed.")

    def _begin_motion_phase(self) -> None:
        if self._current_plan is None:
            return

        if not self._running_in_preview:
            success, message = self.hebi_service.start_velocity_test(self._current_plan)
            if not success:
                self._abort_test_run("HEBI start failed", message)
                return
            self._append_log(message)

        self._test_phase = "active"
        self._motion_started_at = time.monotonic()
        self.execution_label.setText(
            "Motion phase: the 1.0 s delay is finished, and the wheel command is now active."
        )
        if self._current_plan.uses_stopwatch:
            self.progress_bar.set_value(0)
            self.progress_text.setText("0.0 s")
        else:
            self.progress_bar.set_value(0)
            self.progress_text.setText("0% | 0.0 s")

    def _begin_post_roll(self, message: str) -> None:
        if self._current_plan is None or self._test_started_at is None:
            return

        self.hebi_service.stop()
        self._test_phase = "post_roll"
        self._pending_finish_message = message
        self._post_roll_started_at = time.monotonic()
        self._motion_elapsed_before_post_roll = max(0.0, time.monotonic() - self._test_started_at - PRE_ROLL_SECONDS)
        self.stop_button.setEnabled(False)
        self.execution_label.setText(
            "Post-test capture: collecting 1.0 s of data after stop so the CSV shows the system settling."
        )
        if self._current_plan.duration_seconds is not None:
            self.progress_bar.set_value(100)
        else:
            self.progress_bar.set_value(0)
        self.progress_text.setText("Post-roll 0.0 / 1.0 s")
        self._append_log("Motion stopped. Recording 1.0 s of post-test data before closing the test.")

    def _complete_test_run(self, message: str) -> None:
        elapsed = 0.0
        if self._test_started_at is not None:
            elapsed = time.monotonic() - self._test_started_at

        self.poll_timer.stop()
        self.hebi_service.stop()
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(True)
        self.refresh_motors_button.setEnabled(True)
        self.zero_button.setEnabled(True)
        self._test_phase = "idle"
        self.execution_label.setText(message)
        self._append_log(message)
        if self._current_plan is not None and self._current_plan.duration_seconds is not None:
            final_progress = 100 if self._motion_elapsed_before_post_roll >= self._current_plan.duration_seconds else min(
                100, int((self._motion_elapsed_before_post_roll / self._current_plan.duration_seconds) * 100)
            )
            self.progress_bar.set_value(final_progress)
            self.progress_text.setText(f"{final_progress}% | {elapsed:.1f} s recorded")
        else:
            self.progress_bar.set_value(0)
            self.progress_text.setText(f"{elapsed:.1f} s recorded")

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
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._pending_finish_message = ""
        self._motion_elapsed_before_post_roll = 0.0

    def _abort_test_run(self, title: str, message: str) -> None:
        self.poll_timer.stop()
        self.hebi_service.stop()
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.connect_button.setEnabled(True)
        self.refresh_motors_button.setEnabled(True)
        self.zero_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.execution_label.setText(message)
        self.progress_bar.set_value(0)
        self.progress_text.setText("Ready")
        self._append_log(message)

        abandoned_path = self._current_data_path
        self._close_data_file()
        if abandoned_path is not None and abandoned_path.exists():
            abandoned_path.unlink()
        self._current_data_path = None
        self.data_file_label.setText(self._data_file_status_text())
        self._pending_deployment_plan = None
        self._pending_deployment_samples = []
        self._current_plan = None
        self._test_started_at = None
        self._test_phase = "idle"
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._pending_finish_message = ""
        self._motion_elapsed_before_post_roll = 0.0
        QMessageBox.warning(self, title, message)

    def _reset_interface(self) -> None:
        if self.poll_timer.isActive():
            QMessageBox.warning(self, "Reset interface", "Stop the current test before resetting the interface.")
            return
        if self.zero_timer.isActive():
            QMessageBox.warning(
                self,
                "Reset interface",
                "Wait for the move-to-zero action to finish before resetting the interface.",
            )
            return
        if self._pending_deployment_plan is not None:
            discard = QMessageBox.question(
                self,
                "Reset interface",
                "There is pending deployment data that has not been exported. Discard it and reset the interface?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if discard != QMessageBox.Yes:
                return

        self.hebi_service.stop()
        self._close_data_file()
        self._current_plan = None
        self._test_started_at = None
        self._running_in_preview = False
        self._current_data_path = None
        self._zero_move_started_at = None
        self._pending_deployment_plan = None
        self._pending_deployment_samples = []
        self._test_phase = "idle"
        self._pending_finish_message = ""
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0

        self.test_number_input.setValue(1)
        self.revolutions_input.setValue(2.0)
        self.velocity_input.setValue(14.0)
        self.mode_input.setCurrentIndex(0)
        self.file_prefix_input.clear()
        self._reset_checklist()
        self._reset_charts()
        self.log_output.clear()
        for label in self.telemetry_labels.values():
            label.setText("--")

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.connect_button.setEnabled(True)
        self.refresh_motors_button.setEnabled(True)
        self.zero_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.progress_bar.set_value(0)
        self.progress_text.setText("Ready")
        self.execution_label.setText("Waiting for a test to start.")
        self.data_file_label.setText(self._data_file_status_text())
        self._update_derived_fields()
        self._append_log("Interface reset. Ready for a new excavation/deployment sequence.")

    def _sample_for_phase(self, elapsed: float) -> TelemetrySample:
        if self._current_plan is None:
            raise RuntimeError("No active test plan.")

        if self._test_phase == "pre_roll":
            self.progress_bar.set_value(0)
            self.progress_text.setText(f"Pre-roll {min(elapsed, PRE_ROLL_SECONDS):.1f} / {PRE_ROLL_SECONDS:.1f} s")
            self.execution_label.setText(
                "Pre-test capture: collecting 1.0 s of data before motion starts so the CSV shows the baseline."
            )
            return self._read_or_preview_sample(elapsed, motion_elapsed=0.0, motion_active=False)

        if self._test_phase == "post_roll":
            post_roll_elapsed = 0.0 if self._post_roll_started_at is None else time.monotonic() - self._post_roll_started_at
            if self._current_plan.duration_seconds is not None:
                self.progress_bar.set_value(100)
            else:
                self.progress_bar.set_value(0)
            self.progress_text.setText(
                f"Post-roll {min(post_roll_elapsed, POST_ROLL_SECONDS):.1f} / {POST_ROLL_SECONDS:.1f} s"
            )
            self.execution_label.setText(
                "Post-test capture: collecting 1.0 s of data after stop so the CSV shows the system settling."
            )
            return self._read_or_preview_sample(
                elapsed,
                motion_elapsed=self._motion_elapsed_before_post_roll,
                motion_active=False,
            )

        active_elapsed = max(0.0, elapsed - PRE_ROLL_SECONDS)
        if self._current_plan.duration_seconds is not None:
            progress = min(100, int((active_elapsed / self._current_plan.duration_seconds) * 100))
            self.progress_bar.set_value(progress)
            self.progress_text.setText(f"{progress}% | {active_elapsed:.1f} s")
        else:
            self.progress_bar.set_value(0)
            self.progress_text.setText(f"{active_elapsed:.1f} s")
        self.execution_label.setText(
            f"Motion phase: {self._current_plan.mode} is running. The CSV includes 1.0 s before motion and 1.0 s after stop."
        )
        return self._read_or_preview_sample(elapsed, motion_elapsed=active_elapsed, motion_active=True)

    def _read_or_preview_sample(self, elapsed: float, motion_elapsed: float, motion_active: bool) -> TelemetrySample:
        if self._current_plan is None:
            raise RuntimeError("No active test plan.")

        if self._running_in_preview:
            return self._preview_sample(self._current_plan, elapsed, motion_elapsed, motion_active)

        if motion_active:
            self.hebi_service.refresh_velocity_command(self._current_plan)  # Refresh the command continuously while the wheel is spinning.
        sample = self.hebi_service.read_feedback(elapsed)
        if sample is None:
            return self._preview_sample(self._current_plan, elapsed, motion_elapsed, motion_active)
        return sample

    def _preview_sample(
        self,
        plan: TestPlan,
        elapsed: float,
        motion_elapsed: float,
        motion_active: bool,
    ) -> TelemetrySample:
        if motion_active:
            sample = self.hebi_service.preview_feedback(plan, motion_elapsed)
            sample.elapsed_seconds = elapsed
            return sample

        sample = self.hebi_service.preview_feedback(plan, motion_elapsed)
        sample.elapsed_seconds = elapsed
        sample.velocity_rad_s = 0.0
        sample.effort_nm = 0.0
        sample.current_a = 0.0
        return sample

    def _update_telemetry(self, sample: TelemetrySample) -> None:
        self.telemetry_labels["position"].setText(f"{sample.position_rad:.3f} rad")
        self.telemetry_labels["velocity"].setText(f"{sample.velocity_rad_s:.3f} rad/s")
        self.telemetry_labels["effort"].setText(f"{sample.effort_nm:.3f} Nm")
        self.telemetry_labels["voltage"].setText(f"{sample.voltage_v:.2f} V")
        self.telemetry_labels["current"].setText(f"{sample.current_a:.3f} A")
        self.telemetry_labels["accel_x"].setText(f"{sample.accel_x_m_s2:.3f} m/s^2")
        self.telemetry_labels["temperature"].setText(f"{sample.winding_temperature_c:.2f} C")

    def _update_charts(self, sample: TelemetrySample) -> None:
        self.effort_series.append(sample.elapsed_seconds, sample.effort_nm)
        self.power_series.append(sample.elapsed_seconds, self._power_w(sample))
        self._trim_chart_series(self.effort_series)
        self._trim_chart_series(self.power_series)
        self._update_chart_axes(self.effort_chart_view.chart(), self.effort_series)
        self._update_chart_axes(self.power_chart_view.chart(), self.power_series)

    def _reset_charts(self) -> None:
        self.effort_series.clear()
        self.power_series.clear()
        self._update_chart_axes(self.effort_chart_view.chart(), self.effort_series)
        self._update_chart_axes(self.power_chart_view.chart(), self.power_series)

    def _trim_chart_series(self, series: QLineSeries) -> None:
        while series.count() > self._max_chart_points:
            series.remove(0)

    def _update_chart_axes(self, chart: QChart, series: QLineSeries) -> None:
        axes = chart.axes()
        if len(axes) < 2:
            return

        axis_x = axes[0]
        axis_y = axes[1]
        if series.count() == 0:
            axis_x.setRange(0.0, 10.0)
            axis_y.setRange(0.0, 10.0)
            return

        points = series.points()
        last_x = points[-1].x()
        max_y = max(point.y() for point in points)
        min_y = min(point.y() for point in points)
        axis_x.setRange(max(0.0, last_x - 10.0), max(10.0, last_x))

        if max_y == min_y:
            padding = 1.0 if max_y == 0.0 else abs(max_y) * 0.1
            axis_y.setRange(min_y - padding, max_y + padding)
        else:
            padding = max((max_y - min_y) * 0.1, 0.1)
            axis_y.setRange(min_y - padding, max_y + padding)

    def _prepare_test_storage(self, plan: TestPlan) -> None:
        if plan.uses_stopwatch:
            self._pending_deployment_samples = []
            self._current_data_path = None
            self._close_data_file()
            self.data_file_label.setText(
                f"Deployment data will be exported under {self._data_directory_for_plan(plan)} after you enter the mass."
            )
            return

        self._open_data_file(plan)

    def _open_data_file(self, plan: TestPlan) -> None:
        self._close_data_file()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = self._data_directory_for_plan(plan)
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = self._file_prefix()
        file_path = output_dir / f"{prefix}_test{plan.test_number:03d}_{timestamp}.csv"

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
                "current_a",
                "power_w",
                "accel_x_raw_m_s2",
                "accel_x_m_s2",
                "accel_y_m_s2",
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
                    current_a=sample.current_a,
                    accel_x_raw_m_s2=sample.accel_x_raw_m_s2,
                    accel_x_m_s2=sample.accel_x_m_s2,
                    accel_y_m_s2=sample.accel_y_m_s2,
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
                f"{sample.current_a:.6f}",
                f"{self._power_w(sample):.6f}",
                f"{sample.accel_x_raw_m_s2:.6f}",
                f"{sample.accel_x_m_s2:.6f}",
                f"{sample.accel_y_m_s2:.6f}",
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
        collected_mass_kg = self._collected_mass_kg()
        if collected_mass_kg <= 0.0:
            QMessageBox.warning(
                self,
                "Invalid collected mass",
                "Deployment data cannot be exported with a collected mass of 0 kg.",
            )
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = self._data_directory_for_plan(plan)
        output_dir.mkdir(parents=True, exist_ok=True)
        prefix = self._file_prefix()
        file_path = output_dir / f"{prefix}_test{plan.test_number:03d}_{timestamp}.csv"

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
                    "current_a",
                    "power_w",
                    "accel_x_raw_m_s2",
                    "accel_x_m_s2",
                    "accel_y_m_s2",
                    "winding_temperature_c",
                ]
            )
            for sample in self._pending_deployment_samples:
                writer.writerow(
                    [
                        plan.test_number,
                        plan.mode,
                        f"{collected_mass_kg:.4f}",
                        f"{sample.elapsed_seconds:.3f}",
                        f"{sample.position_rad:.6f}",
                        f"{sample.velocity_rad_s:.6f}",
                        f"{sample.effort_nm:.6f}",
                        f"{sample.voltage_v:.6f}",
                        f"{sample.current_a:.6f}",
                        f"{self._power_w(sample):.6f}",
                        f"{sample.accel_x_raw_m_s2:.6f}",
                        f"{sample.accel_x_m_s2:.6f}",
                        f"{sample.accel_y_m_s2:.6f}",
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

    def _output_root(self) -> Path:
        if self._output_directory is not None:
            return self._output_directory
        return _app_base_directory() / "data"

    def _data_directory_for_plan(self, plan: TestPlan) -> Path:
        return self._output_root() / plan.test_type.lower()

    def _data_file_status_text(self) -> str:
        return f"Output folder: {self._output_root()}"

    def _file_prefix(self) -> str:
        raw_prefix = self.file_prefix_input.text().strip()
        cleaned = raw_prefix.replace(" ", "_")
        safe_chars = []
        for char in cleaned:
            if char.isalnum() or char in {"_", "-"}:
                safe_chars.append(char)
        return "".join(safe_chars)

    def _collected_mass_kg(self) -> float:
        active_plan = self._current_plan if self._current_plan is not None else self._pending_deployment_plan
        if active_plan is None:
            return 0.0
        if not active_plan.uses_stopwatch:
            return 0.0
        return self.mass_input.value()

    def _power_w(self, sample: TelemetrySample) -> float:
        return sample.voltage_v * sample.current_a


class TwoWheelRoverDiagram(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._direction = "Clockwise"
        self._active_side: str | None = None
        self._rotation_angle = 0.0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(70)
        self._animation_timer.timeout.connect(self._advance_animation)
        self.setMinimumHeight(150)
        self.setMaximumHeight(180)

    def set_direction(self, direction: str) -> None:
        self._direction = direction
        self.update()

    def set_active_side(self, side: str | None) -> None:
        self._active_side = side
        if side is None:
            self._animation_timer.stop()
            self._rotation_angle = 0.0
        elif not self._animation_timer.isActive():
            self._animation_timer.start()
        self.update()

    def _advance_animation(self) -> None:
        direction = -1.0 if self._direction == "Clockwise" else 1.0
        self._rotation_angle = (self._rotation_angle + direction * 18.0) % 360.0
        self.update()

    def _role_for_side(self, side: str) -> str:
        if self._direction == "Clockwise":
            return "Front" if side == "right" else "Rear"
        return "Front" if side == "left" else "Rear"

    def paintEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPen

        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        body_width = min(width * 0.58, 380.0)
        body_height = min(height * 0.25, 54.0)
        body_x = (width - body_width) / 2.0
        body_y = height * 0.33
        wheel_size = min(body_width * 0.24, height * 0.32, 70.0)
        left_wheel = QRectF(body_x + body_width * 0.05, body_y + body_height * 0.55, wheel_size, wheel_size)
        right_wheel = QRectF(body_x + body_width * 0.70, body_y + body_height * 0.55, wheel_size, wheel_size)

        painter.setPen(QPen(QColor("#35312b"), 3))
        painter.setBrush(QColor("#f7f2e7"))
        painter.drawRoundedRect(QRectF(body_x, body_y, body_width, body_height), 10, 10)
        painter.drawLine(
            int(body_x + body_width * 0.22),
            int(body_y + body_height),
            int(body_x + body_width * 0.22),
            int(left_wheel.top()),
        )
        painter.drawLine(
            int(body_x + body_width * 0.78),
            int(body_y + body_height),
            int(body_x + body_width * 0.78),
            int(right_wheel.top()),
        )

        self._draw_wheel(painter, left_wheel, "left", "Left", self._role_for_side("left"))
        self._draw_wheel(painter, right_wheel, "right", "Right", self._role_for_side("right"))

        painter.setPen(QColor("#9f2539"))
        painter.drawText(
            QRectF(body_x, body_y - 32, body_width, 24),
            Qt.AlignCenter,
            f"Direction: {self._direction}",
        )
        painter.end()

    def _draw_wheel(self, painter, rect, side: str, side_label: str, role_label: str) -> None:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPen

        active = self._active_side in {side, "both"}
        if active:
            glow_rect = QRectF(rect)
            glow_rect.adjust(-8, -8, 8, 8)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(159, 37, 57, 70))
            painter.drawEllipse(glow_rect)

        painter.setPen(QPen(QColor("#2f2f2f"), 4))
        painter.setBrush(QColor("#3d3d3d"))
        painter.drawEllipse(rect)

        painter.setPen(QPen(QColor("#f1f1f1"), 6))
        center = rect.center()
        spoke_radius = rect.width() * 0.34
        for angle_offset in (0.0, 90.0):
            angle = math.radians(self._rotation_angle + angle_offset)
            dx = math.cos(angle) * spoke_radius
            dy = math.sin(angle) * spoke_radius
            painter.drawLine(
                int(center.x() - dx),
                int(center.y() - dy),
                int(center.x() + dx),
                int(center.y() + dy),
            )

        painter.setPen(QColor("#1c1c1c"))
        label_rect = QRectF(rect.left() - 20, rect.bottom() + 8, rect.width() + 40, 42)
        painter.drawText(label_rect, Qt.AlignCenter, f"{side_label}\n{role_label}")


class TwoWheelTestPage(QWidget):
    back_requested = Signal()
    change_output_directory_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.left_service = HebiWheelService()
        self.right_service = HebiWheelService()
        self.services = {"left": self.left_service, "right": self.right_service}

        self._output_directory: Path | None = None
        self._available_modules: list[DiscoveredModule] = []
        self._connected_modules: dict[str, DiscoveredModule] = {}
        self._main_samples: dict[str, list[TelemetrySample]] = {"left": [], "right": []}
        self._main_started_at: float | None = None
        self._main_timestamp = ""
        self._has_pending_export = False
        self._is_main_running = False
        self._main_phase = "idle"
        self._motion_started_at: float | None = None
        self._post_roll_started_at: float | None = None
        self._motion_elapsed_before_post_roll = 0.0
        self._pending_finish_message = ""
        self._deployment_side: str | None = None
        self._wiggle_side: str | None = None
        self._wiggle_phase = "idle"
        self._wiggle_started_at: float | None = None
        self._zero_started_at: float | None = None
        self._max_chart_points = 300

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll_active_motion)
        self.wiggle_timer = QTimer(self)
        self.wiggle_timer.setInterval(100)
        self.wiggle_timer.timeout.connect(self._poll_wiggle)
        self.zero_timer = QTimer(self)
        self.zero_timer.setInterval(100)
        self.zero_timer.timeout.connect(self._poll_zero_all)

        self.motor_selectors: dict[str, QComboBox] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.velocity_inputs: dict[str, QDoubleSpinBox] = {}
        self.mass_inputs: dict[str, QDoubleSpinBox] = {}
        self.connect_buttons: dict[str, QPushButton] = {}
        self.wiggle_buttons: dict[str, QPushButton] = {}
        self.deployment_buttons: dict[str, QPushButton] = {}
        self.telemetry_labels_by_side: dict[str, dict[str, QLabel]] = {}

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        root = QVBoxLayout(content_widget)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)

        toolbar = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(self.back_requested.emit)
        header = QLabel("Dual Wheel Test")
        header.setObjectName("PageTitle")
        toolbar.addWidget(self.back_button, 0, Qt.AlignLeft)
        toolbar.addWidget(header, 0, Qt.AlignVCenter)
        toolbar.addStretch(1)

        root.addLayout(toolbar)
        root.addWidget(self._build_general_panel())
        root.addWidget(self._build_visual_panel())

        wheels_layout = QBoxLayout(QBoxLayout.LeftToRight)
        wheels_layout.setSpacing(20)
        wheels_layout.addWidget(self._build_wheel_panel("left", "Left Wheel"), 1)
        wheels_layout.addWidget(self._build_wheel_panel("right", "Right Wheel"), 1)
        root.addLayout(wheels_layout)
        root.addWidget(self._build_graph_panel(), 1)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Dual-wheel test messages will appear here.")
        self.log_output.setMaximumHeight(110)
        root.addWidget(self.log_output)

        scroll_area.setWidget(content_widget)
        outer_layout.addWidget(scroll_area)

        self._set_motor_selector_placeholders()
        self._update_role_labels()
        self._update_export_button_state()

    def _build_general_panel(self) -> QGroupBox:
        box = QGroupBox("General Configuration")
        layout = QVBoxLayout(box)
        layout.setSpacing(10)
        columns = QHBoxLayout()
        columns.setSpacing(18)

        setup_box = QGroupBox("Test Setup")
        form = QFormLayout(setup_box)
        form.setSpacing(12)

        self.test_number_input = QSpinBox()
        self.test_number_input.setMinimum(1)
        self.test_number_input.setMaximum(9999)
        self.test_number_input.setValue(DEFAULT_TEST_NUMBER)
        self.test_number_input.setButtonSymbols(QAbstractSpinBox.NoButtons)

        self.direction_input = QComboBox()
        self.direction_input.addItems(["Clockwise", "Counter clockwise"])
        self.direction_input.currentTextChanged.connect(self._update_role_labels)

        self.duration_input = QDoubleSpinBox()
        self.duration_input.setRange(0.1, 3600.0)
        self.duration_input.setDecimals(2)
        self.duration_input.setValue(10.0)
        self.duration_input.setSuffix(" s")
        self.duration_input.setButtonSymbols(QAbstractSpinBox.NoButtons)

        self.file_prefix_input = QLineEdit()
        self.file_prefix_input.setPlaceholderText("Example: Dual_Wheel_Test")

        form.addRow("Test Number", self.test_number_input)
        form.addRow("Direction", self.direction_input)
        form.addRow("Duration", self.duration_input)
        form.addRow("File Prefix", self.file_prefix_input)

        columns.addWidget(setup_box, 1)
        columns.addWidget(self._build_checklist_box(), 1)

        save_row = QWidget()
        save_layout = QHBoxLayout(save_row)
        save_layout.setContentsMargins(0, 0, 0, 0)
        save_layout.setSpacing(10)
        self.save_folder_label = QLabel(self._data_file_status_text())
        self.save_folder_label.setWordWrap(True)
        self.change_output_directory_button = QPushButton("Change Save Folder")
        self.change_output_directory_button.clicked.connect(self.change_output_directory_requested.emit)
        save_layout.addWidget(QLabel("Save Folder"))
        save_layout.addWidget(self.save_folder_label, 1)
        save_layout.addWidget(self.change_output_directory_button)

        layout.addLayout(columns)
        layout.addWidget(save_row)
        return box

    def _build_checklist_box(self) -> QGroupBox:
        checklist_box = QGroupBox("Laboratory Checklist")
        checklist_layout = QGridLayout(checklist_box)
        checklist_layout.setHorizontalSpacing(16)
        checklist_layout.setVerticalSpacing(8)

        self.checklist_boxes: list[QCheckBox] = []
        for index, item in enumerate(TWO_WHEEL_CHECKLIST_ITEMS):
            checkbox = QCheckBox(item)
            row = index // 2
            column = index % 2
            checklist_layout.addWidget(checkbox, row, column)
            self.checklist_boxes.append(checkbox)
        return checklist_box

    def _build_visual_panel(self) -> QGroupBox:
        box = QGroupBox("Wheel Assignment")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        self.rover_diagram = TwoWheelRoverDiagram()
        self.assignment_label = QLabel()
        self.assignment_label.setAlignment(Qt.AlignCenter)
        self.assignment_label.setObjectName("StatusLabel")
        self.progress_bar = ProgressBar()
        self.progress_text = QLabel("Ready")
        self.progress_text.setAlignment(Qt.AlignRight)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.refresh_motors_button = QPushButton("Refresh Motors")
        self.refresh_motors_button.clicked.connect(self._refresh_available_motors)
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_main_motion)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_active_motion)
        self.zero_button = QPushButton("Set Position to 0 rad")
        self.zero_button.clicked.connect(self._zero_all)
        self.export_button = QPushButton("Export CSV")
        self.export_button.clicked.connect(self._export_csv)
        self.reset_button = QPushButton("Reset Interface")
        self.reset_button.clicked.connect(self._reset_interface)
        actions.addWidget(self.refresh_motors_button)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.zero_button)
        actions.addWidget(self.export_button)
        actions.addWidget(self.reset_button)
        layout.addWidget(self.rover_diagram)
        layout.addWidget(self.assignment_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_text)
        layout.addLayout(actions)
        return box

    def _build_wheel_panel(self, side: str, title: str) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        form = QFormLayout()
        form.setSpacing(12)

        motor_row = QWidget()
        motor_layout = QHBoxLayout(motor_row)
        motor_layout.setContentsMargins(0, 0, 0, 0)
        selector = QComboBox()
        connect_button = QPushButton("Connect")
        connect_button.clicked.connect(lambda checked=False, wheel_side=side: self._connect_wheel(wheel_side))
        motor_layout.addWidget(selector, 1)
        motor_layout.addWidget(connect_button)

        status_label = QLabel("Disconnected")
        status_label.setObjectName("StatusLabel")

        velocity_input = QDoubleSpinBox()
        velocity_input.setRange(0.1, 5000.0)
        velocity_input.setDecimals(2)
        velocity_input.setValue(DEFAULT_VELOCITY_RPM)
        velocity_input.setSuffix(" rpm")
        velocity_input.setButtonSymbols(QAbstractSpinBox.NoButtons)

        mass_input = QDoubleSpinBox()
        mass_input.setRange(0.0, 1000.0)
        mass_input.setDecimals(4)
        mass_input.setValue(0.0)
        mass_input.setSuffix(" kg")
        mass_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        mass_input.valueChanged.connect(self._update_export_button_state)

        form.addRow("Motor", motor_row)
        form.addRow("Status", status_label)
        form.addRow("Velocity", velocity_input)
        form.addRow("Collected Mass", mass_input)

        buttons = QHBoxLayout()
        wiggle_button = QPushButton("Test Wheel")
        wiggle_button.clicked.connect(lambda checked=False, wheel_side=side: self._start_wiggle(wheel_side))
        deployment_button = QPushButton("Deployment 14 rpm")
        deployment_button.clicked.connect(lambda checked=False, wheel_side=side: self._start_deployment(wheel_side))
        deployment_button.setEnabled(False)
        buttons.addWidget(wiggle_button)
        buttons.addWidget(deployment_button)

        self.motor_selectors[side] = selector
        self.status_labels[side] = status_label
        self.velocity_inputs[side] = velocity_input
        self.mass_inputs[side] = mass_input
        self.connect_buttons[side] = connect_button
        self.wiggle_buttons[side] = wiggle_button
        self.deployment_buttons[side] = deployment_button
        self.telemetry_labels_by_side[side] = {}

        layout.addLayout(form)
        layout.addLayout(buttons)
        return box

    def _build_graph_panel(self) -> QGroupBox:
        box = QGroupBox("Live Graphs")
        layout = QHBoxLayout(box)
        layout.setSpacing(12)
        self.effort_series_by_side, self.effort_chart_view = self._build_dual_chart("Effort vs Time", "Time (s)", "Effort (Nm)")
        self.power_series_by_side, self.power_chart_view = self._build_dual_chart("Power vs Time", "Time (s)", "Power (W)")
        layout.addWidget(self.effort_chart_view, 1)
        layout.addWidget(self.power_chart_view, 1)
        return box

    def _build_dual_chart(self, title: str, x_title: str, y_title: str) -> tuple[dict[str, QLineSeries], QChartView]:
        chart = QChart()
        chart.setTitle(title)
        chart.legend().setVisible(True)
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)

        axis_x = QValueAxis()
        axis_x.setTitleText(x_title)
        axis_x.setRange(0.0, 10.0)
        axis_x.setLabelFormat("%.1f")

        axis_y = QValueAxis()
        axis_y.setTitleText(y_title)
        axis_y.setRange(0.0, 10.0)
        axis_y.setLabelFormat("%.2f")

        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)

        series_by_side: dict[str, QLineSeries] = {}
        for side, name in (("left", "Left"), ("right", "Right")):
            series = QLineSeries()
            series.setName(name)
            chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
            series_by_side[side] = series

        chart_view = QChartView(chart)
        chart_view.setMinimumHeight(340)
        return series_by_side, chart_view

    def set_output_directory(self, output_directory: Path) -> None:
        self._output_directory = output_directory
        self.save_folder_label.setText(self._data_file_status_text())
        self._append_log(f"Data will be saved under {self._output_root()}")

    def _refresh_available_motors(self) -> None:
        self._available_modules = self.left_service.discover_modules()
        for selector in self.motor_selectors.values():
            selector.clear()
            if not self._available_modules:
                selector.addItem("No motors found on the network", None)
                continue
            for module in self._available_modules:
                stale_suffix = " [stale]" if module.is_stale else ""
                selector.addItem(f"{module.family} / {module.name}{stale_suffix}", module)

        if self._available_modules:
            self._append_log(f"Discovered {len(self._available_modules)} motor(s) on the network.")
        else:
            self._append_log("No HEBI motors were discovered on the network.")

    def _set_motor_selector_placeholders(self) -> None:
        for selector in self.motor_selectors.values():
            selector.clear()
            selector.addItem("Click Refresh Motors", None)

    def _connect_wheel(self, side: str) -> None:
        selected_module = self.motor_selectors[side].currentData()
        if not isinstance(selected_module, DiscoveredModule):
            QMessageBox.warning(self, "HEBI connection", "No motor is selected.")
            return

        other_side = "right" if side == "left" else "left"
        other_module = self._connected_modules.get(other_side)
        if other_module is not None and self._same_module(selected_module, other_module):
            QMessageBox.warning(self, "HEBI connection", "Left and right wheels must use different HEBI modules.")
            return

        success, message = self.services[side].connect(
            family=selected_module.family,
            module_name=selected_module.name,
        )
        self.status_labels[side].setText("Connected" if success else "Disconnected")
        if success:
            self._connected_modules[side] = selected_module
        else:
            self._connected_modules.pop(side, None)
            QMessageBox.warning(self, "HEBI connection", message)
        self._append_log(f"{side.title()} wheel: {message}")

    def _start_main_motion(self) -> None:
        if not self._can_start_new_action():
            return
        if not self._both_wheels_connected():
            QMessageBox.warning(self, "Dual-wheel start", "Connect both left and right HEBI motors before starting.")
            return
        if not self._file_prefix():
            QMessageBox.warning(self, "Missing file prefix", "Write a file prefix before starting the test.")
            return
        if self._has_pending_export:
            QMessageBox.warning(self, "Pending export", "Export the current dual-wheel data or reset the interface before starting a new test.")
            return

        self._main_samples = {"left": [], "right": []}
        self._main_started_at = time.monotonic()
        self._main_timestamp = time.strftime("%Y%m%d_%H%M%S")
        self._is_main_running = True
        self._main_phase = "pre_roll"
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0
        self._pending_finish_message = ""
        self._has_pending_export = False
        self.progress_bar.set_value(0)
        self.progress_text.setText(f"Pre-roll 0.0 / {PRE_ROLL_SECONDS:.1f} s")
        self._reset_charts()

        self._set_controls_running()
        self.rover_diagram.set_active_side(None)
        self._append_log(
            f"Dual-wheel movement armed. Recording {PRE_ROLL_SECONDS:.1f} s before motion, "
            f"{self.duration_input.value():.2f} s of motion, and {POST_ROLL_SECONDS:.1f} s after stop."
        )
        self.poll_timer.start()

    def _start_deployment(self, side: str) -> None:
        if not self._can_start_new_action():
            return
        if not self.services[side].is_connected:
            QMessageBox.warning(self, "Deployment", f"Connect the {side} wheel before deployment.")
            return
        if not self._has_pending_export:
            QMessageBox.warning(self, "Deployment", "Run the main two-wheel movement before deployment.")
            return

        velocity_rad_s = -self._direction_sign() * self._rpm_to_rad_s(TWO_WHEEL_DEPLOYMENT_RPM)
        success, message = self.services[side].set_signed_velocity(velocity_rad_s)
        if not success:
            QMessageBox.warning(self, "Deployment", message)
            return

        self._deployment_side = side
        self.rover_diagram.set_active_side(side)
        self.progress_bar.set_value(0)
        self.progress_text.setText(f"{side.title()} deployment running")
        self._set_controls_running()
        self.stop_button.setEnabled(True)
        self._append_log(f"{side.title()} deployment started at {TWO_WHEEL_DEPLOYMENT_RPM:.2f} rpm.")
        self.poll_timer.start()

    def _stop_active_motion(self) -> None:
        if self._is_main_running:
            if self._main_phase == "pre_roll":
                self._cancel_main_motion("Dual-wheel movement cancelled before motion started.")
            elif self._main_phase == "active":
                self._begin_main_post_roll("Dual-wheel movement stopped by user.")
            return
        if self._deployment_side is not None:
            self._finish_deployment(f"{self._deployment_side.title()} deployment stopped by user.")

    def _poll_active_motion(self) -> None:
        if self._main_started_at is None and self._deployment_side is None:
            return

        if self._is_main_running:
            elapsed = time.monotonic() - self._main_started_at if self._main_started_at is not None else 0.0
            if self._main_phase == "pre_roll":
                self._record_main_samples(elapsed)
                self.progress_bar.set_value(0)
                self.progress_text.setText(f"Pre-roll {min(elapsed, PRE_ROLL_SECONDS):.1f} / {PRE_ROLL_SECONDS:.1f} s")
                if elapsed >= PRE_ROLL_SECONDS:
                    self._begin_main_motion_phase()
                return

            if self._main_phase == "active":
                active_elapsed = 0.0 if self._motion_started_at is None else time.monotonic() - self._motion_started_at
                self._refresh_main_velocity_commands()
                self._record_main_samples(elapsed)
                duration = self.duration_input.value()
                progress = min(100, int((active_elapsed / duration) * 100))
                self.progress_bar.set_value(progress)
                self.progress_text.setText(f"{progress}% | {active_elapsed:.1f} s motion")
                if active_elapsed >= duration:
                    self._begin_main_post_roll("Dual-wheel movement completed.")
                return

            if self._main_phase == "post_roll":
                post_roll_elapsed = 0.0 if self._post_roll_started_at is None else time.monotonic() - self._post_roll_started_at
                self._record_main_samples(elapsed)
                self.progress_bar.set_value(100)
                self.progress_text.setText(
                    f"Post-roll {min(post_roll_elapsed, POST_ROLL_SECONDS):.1f} / {POST_ROLL_SECONDS:.1f} s"
                )
                if post_roll_elapsed >= POST_ROLL_SECONDS:
                    self._finish_main_motion(self._pending_finish_message or "Dual-wheel movement completed.")
                return
            return

        if self._deployment_side is not None:
            side = self._deployment_side
            self.services[side].refresh_signed_velocity(-self._direction_sign() * self._rpm_to_rad_s(TWO_WHEEL_DEPLOYMENT_RPM))
            sample = self.services[side].read_feedback(0.0)
            if sample is not None:
                self._update_wheel_display(side, sample)

    def _begin_main_motion_phase(self) -> None:
        direction_sign = self._direction_sign()
        for side in ("left", "right"):
            velocity_rad_s = direction_sign * self._rpm_to_rad_s(self.velocity_inputs[side].value())
            success, message = self.services[side].set_signed_velocity(velocity_rad_s)
            if not success:
                self._abort_active_motion("Dual-wheel start failed", f"{side.title()} wheel: {message}")
                return

        self._main_phase = "active"
        self._motion_started_at = time.monotonic()
        self.rover_diagram.set_active_side("both")
        self.progress_bar.set_value(0)
        self.progress_text.setText("0% | 0.0 s motion")
        self._append_log(
            f"Motion phase started for {self.duration_input.value():.2f} s. "
            f"Direction: {self.direction_input.currentText()}."
        )

    def _begin_main_post_roll(self, message: str) -> None:
        if self._main_phase != "active":
            return

        for service in self.services.values():
            service.stop()
        self._main_phase = "post_roll"
        self._pending_finish_message = message
        self._post_roll_started_at = time.monotonic()
        self._motion_elapsed_before_post_roll = (
            0.0 if self._motion_started_at is None else max(0.0, time.monotonic() - self._motion_started_at)
        )
        self.rover_diagram.set_active_side(None)
        self.stop_button.setEnabled(False)
        self.progress_bar.set_value(100)
        self.progress_text.setText(f"Post-roll 0.0 / {POST_ROLL_SECONDS:.1f} s")
        self._append_log("Motion stopped. Recording 1.0 s of post-test data before closing the test.")

    def _refresh_main_velocity_commands(self) -> None:
        direction_sign = self._direction_sign()
        for side in ("left", "right"):
            velocity_rad_s = direction_sign * self._rpm_to_rad_s(self.velocity_inputs[side].value())
            self.services[side].refresh_signed_velocity(velocity_rad_s)

    def _record_main_samples(self, elapsed: float) -> None:
        for side in ("left", "right"):
            sample = self.services[side].read_feedback(elapsed)
            if sample is not None:
                self._main_samples[side].append(sample)
                self._update_wheel_display(side, sample)
                self._update_charts(side, sample)

    def _finish_main_motion(self, message: str) -> None:
        self.poll_timer.stop()
        for service in self.services.values():
            service.stop()
        self._is_main_running = False
        self._has_pending_export = True
        self._main_started_at = None
        self._main_phase = "idle"
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0
        self._pending_finish_message = ""
        self.rover_diagram.set_active_side(None)
        self.progress_bar.set_value(100)
        self.progress_text.setText("Movement captured. Run deployment, enter masses, then export.")
        for button in self.deployment_buttons.values():
            button.setEnabled(True)
        self._set_controls_idle()
        self._update_export_button_state()
        self._append_log(message)

    def _cancel_main_motion(self, message: str) -> None:
        self.poll_timer.stop()
        for service in self.services.values():
            service.stop()
        self._is_main_running = False
        self._has_pending_export = False
        self._main_started_at = None
        self._main_phase = "idle"
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0
        self._pending_finish_message = ""
        self._main_samples = {"left": [], "right": []}
        self.rover_diagram.set_active_side(None)
        self.progress_bar.set_value(0)
        self.progress_text.setText("Ready")
        self._set_controls_idle()
        self._append_log(message)

    def _finish_deployment(self, message: str) -> None:
        if self._deployment_side is not None:
            self.services[self._deployment_side].stop()
        self.poll_timer.stop()
        self.rover_diagram.set_active_side(None)
        self._append_log(message)
        self._deployment_side = None
        self.progress_text.setText("Deployment stopped. Enter the collected mass.")
        self._set_controls_idle()
        self._update_export_button_state()

    def _zero_all(self) -> None:
        if not self._can_start_new_action():
            return
        if not self._both_wheels_connected():
            QMessageBox.warning(self, "Set Position to 0 rad", "Connect both wheels before commanding both to 0 rad.")
            return

        for side in ("left", "right"):
            success, message = self.services[side].zero_position()
            self._append_log(f"{side.title()} wheel: {message}")
            if not success:
                QMessageBox.warning(self, "Set Position to 0 rad", message)
                return

        self._zero_started_at = time.monotonic()
        self.progress_text.setText("Moving both actuators to 0.000 rad...")
        self.rover_diagram.set_active_side("both")
        self._set_controls_running()
        self.stop_button.setEnabled(False)
        self.zero_timer.start()

    def _poll_zero_all(self) -> None:
        reached = True
        for side in ("left", "right"):
            self.services[side].refresh_zero_position_command()
            sample = self.services[side].read_feedback(0.0)
            if sample is not None:
                self._update_wheel_display(side, sample)
                if abs(sample.position_rad) > 0.05:
                    reached = False
            else:
                reached = False

        elapsed = 0.0 if self._zero_started_at is None else time.monotonic() - self._zero_started_at
        if reached or elapsed >= 8.0:
            self.zero_timer.stop()
            self._zero_started_at = None
            self.rover_diagram.set_active_side(None)
            self.progress_text.setText("Both actuators reached 0 rad." if reached else "Move to 0 rad timed out.")
            self._append_log(self.progress_text.text())
            self._set_controls_idle()

    def _start_wiggle(self, side: str) -> None:
        if not self._can_start_new_action():
            return
        if not self.services[side].is_connected:
            QMessageBox.warning(self, "Test wheel", f"Connect the {side} wheel before running the test motion.")
            return

        success, message = self.services[side].move_to_position(TWO_WHEEL_WIGGLE_TARGET_RAD)
        if not success:
            QMessageBox.warning(self, "Test wheel", message)
            return

        self._wiggle_side = side
        self._wiggle_phase = "out"
        self._wiggle_started_at = time.monotonic()
        self.rover_diagram.set_active_side(side)
        self.progress_text.setText(f"Testing {side} wheel connection...")
        self._set_controls_running()
        self.stop_button.setEnabled(False)
        self._append_log(f"{side.title()} wheel test motion started.")
        self.wiggle_timer.start()

    def _poll_wiggle(self) -> None:
        if self._wiggle_side is None or self._wiggle_started_at is None:
            return

        side = self._wiggle_side
        elapsed = time.monotonic() - self._wiggle_started_at
        target = TWO_WHEEL_WIGGLE_TARGET_RAD if self._wiggle_phase == "out" else 0.0
        self.services[side].refresh_position_command(target)
        sample = self.services[side].read_feedback(0.0)
        if sample is not None:
            self._update_wheel_display(side, sample)

        if self._wiggle_phase == "out" and elapsed >= TWO_WHEEL_WIGGLE_HOLD_SECONDS:
            self.services[side].move_to_position(0.0)
            self._wiggle_phase = "return"
            self._wiggle_started_at = time.monotonic()
            return

        if self._wiggle_phase == "return":
            reached_zero = sample is not None and abs(sample.position_rad) <= 0.05
            if reached_zero or elapsed >= TWO_WHEEL_WIGGLE_TIMEOUT_SECONDS:
                self.wiggle_timer.stop()
                self.services[side].stop()
                self.rover_diagram.set_active_side(None)
                self._append_log(f"{side.title()} wheel test motion finished.")
                self.progress_text.setText("Wheel test motion finished.")
                self._wiggle_side = None
                self._wiggle_phase = "idle"
                self._wiggle_started_at = None
                self._set_controls_idle()

    def _export_csv(self) -> None:
        if not self._has_pending_export:
            QMessageBox.information(self, "Export CSV", "There is no captured dual-wheel movement to export.")
            return
        for side in ("left", "right"):
            if self.mass_inputs[side].value() <= 0.0:
                QMessageBox.warning(self, "Export CSV", "Enter collected mass for both wheels before exporting.")
                return

        prefix = self._file_prefix()
        if not prefix:
            QMessageBox.warning(self, "Export CSV", "Write a file prefix before exporting.")
            return

        exported_paths: list[Path] = []
        for role in ("FrontWheel", "RearWheel"):
            side = self._side_for_role(role)
            output_dir = self._output_root() / "two_wheels" / role.lower()
            output_dir.mkdir(parents=True, exist_ok=True)
            file_path = output_dir / f"{prefix}_{self._main_timestamp}_{role}.csv"
            self._write_wheel_csv(file_path, side, role)
            exported_paths.append(file_path)

        self._has_pending_export = False
        for button in self.deployment_buttons.values():
            button.setEnabled(False)
        self._reset_checklist()
        self._update_export_button_state()
        self._append_log("Exported dual-wheel CSV files:")
        for path in exported_paths:
            self._append_log(str(path))
        QMessageBox.information(self, "Export CSV", "Dual-wheel CSV files were exported.")

    def _write_wheel_csv(self, file_path: Path, side: str, role: str) -> None:
        with file_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "test_number",
                    "direction",
                    "physical_wheel",
                    "wheel_role",
                    "collected_mass_kg",
                    "elapsed_seconds",
                    "position_rad",
                    "velocity_rad_s",
                    "effort_nm",
                    "voltage_v",
                    "current_a",
                    "power_w",
                    "accel_x_raw_m_s2",
                    "accel_x_m_s2",
                    "accel_y_m_s2",
                    "winding_temperature_c",
                ]
            )
            for sample in self._main_samples[side]:
                writer.writerow(
                    [
                        self.test_number_input.value(),
                        self.direction_input.currentText(),
                        side,
                        role,
                        f"{self.mass_inputs[side].value():.4f}",
                        f"{sample.elapsed_seconds:.3f}",
                        f"{sample.position_rad:.6f}",
                        f"{sample.velocity_rad_s:.6f}",
                        f"{sample.effort_nm:.6f}",
                        f"{sample.voltage_v:.6f}",
                        f"{sample.current_a:.6f}",
                        f"{self._power_w(sample):.6f}",
                        f"{sample.accel_x_raw_m_s2:.6f}",
                        f"{sample.accel_x_m_s2:.6f}",
                        f"{sample.accel_y_m_s2:.6f}",
                        f"{sample.winding_temperature_c:.6f}",
                    ]
                )

    def _reset_interface(self) -> None:
        if self.poll_timer.isActive() or self.wiggle_timer.isActive() or self.zero_timer.isActive():
            QMessageBox.warning(self, "Reset interface", "Stop or wait for the current action before resetting.")
            return
        if self._has_pending_export:
            discard = QMessageBox.question(
                self,
                "Reset interface",
                "There is captured dual-wheel data that has not been exported. Discard it and reset the interface?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if discard != QMessageBox.Yes:
                return

        for service in self.services.values():
            service.stop()
        self._main_samples = {"left": [], "right": []}
        self._main_started_at = None
        self._main_timestamp = ""
        self._has_pending_export = False
        self._is_main_running = False
        self._main_phase = "idle"
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0
        self._pending_finish_message = ""
        self._deployment_side = None
        self._wiggle_side = None
        self._wiggle_phase = "idle"
        self._zero_started_at = None
        self.test_number_input.setValue(DEFAULT_TEST_NUMBER)
        self.direction_input.setCurrentIndex(0)
        self.duration_input.setValue(10.0)
        self.file_prefix_input.clear()
        for side in ("left", "right"):
            self.velocity_inputs[side].setValue(DEFAULT_VELOCITY_RPM)
            self.mass_inputs[side].setValue(0.0)
            for label in self.telemetry_labels_by_side[side].values():
                label.setText("--")
        self._reset_checklist()
        self._reset_charts()
        self.log_output.clear()
        self.progress_bar.set_value(0)
        self.progress_text.setText("Ready")
        self.rover_diagram.set_active_side(None)
        self._set_controls_idle()
        self._update_role_labels()
        self._append_log("Dual-wheel interface reset.")

    def _set_controls_running(self) -> None:
        self.start_button.setEnabled(False)
        self.refresh_motors_button.setEnabled(False)
        self.zero_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.change_output_directory_button.setEnabled(False)
        for button in self.connect_buttons.values():
            button.setEnabled(False)
        for button in self.wiggle_buttons.values():
            button.setEnabled(False)
        for button in self.deployment_buttons.values():
            button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def _set_controls_idle(self) -> None:
        self.start_button.setEnabled(True)
        self.refresh_motors_button.setEnabled(True)
        self.zero_button.setEnabled(True)
        self.reset_button.setEnabled(True)
        self.change_output_directory_button.setEnabled(True)
        for button in self.connect_buttons.values():
            button.setEnabled(True)
        for button in self.wiggle_buttons.values():
            button.setEnabled(True)
        for button in self.deployment_buttons.values():
            button.setEnabled(self._has_pending_export)
        self.stop_button.setEnabled(False)
        self._update_export_button_state()

    def _can_start_new_action(self) -> bool:
        if self.poll_timer.isActive() or self.wiggle_timer.isActive() or self.zero_timer.isActive():
            QMessageBox.warning(self, "Action in progress", "Wait for the current action to finish before starting another one.")
            return False
        return True

    def _abort_active_motion(self, title: str, message: str) -> None:
        self.poll_timer.stop()
        for service in self.services.values():
            service.stop()
        self._is_main_running = False
        self._deployment_side = None
        self._main_started_at = None
        self._main_phase = "idle"
        self._motion_started_at = None
        self._post_roll_started_at = None
        self._motion_elapsed_before_post_roll = 0.0
        self._pending_finish_message = ""
        self.rover_diagram.set_active_side(None)
        self.progress_bar.set_value(0)
        self.progress_text.setText("Ready")
        self._set_controls_idle()
        self._append_log(message)
        QMessageBox.warning(self, title, message)

    def _update_role_labels(self) -> None:
        direction = self.direction_input.currentText() if hasattr(self, "direction_input") else "Clockwise"
        if hasattr(self, "rover_diagram"):
            self.rover_diagram.set_direction(direction)
        if hasattr(self, "assignment_label"):
            self.assignment_label.setText(
                f"FrontWheel: {self._side_for_role('FrontWheel').title()} | "
                f"RearWheel: {self._side_for_role('RearWheel').title()}"
            )

    def _update_export_button_state(self) -> None:
        ready = (
            self._has_pending_export
            and self.mass_inputs.get("left") is not None
            and self.mass_inputs.get("right") is not None
            and self.mass_inputs["left"].value() > 0.0
            and self.mass_inputs["right"].value() > 0.0
        )
        if hasattr(self, "export_button"):
            self.export_button.setEnabled(ready)

    def _update_wheel_display(self, side: str, sample: TelemetrySample) -> None:
        labels = self.telemetry_labels_by_side[side]
        if not labels:
            return
        labels["position"].setText(f"{sample.position_rad:.3f} rad")
        labels["velocity"].setText(f"{sample.velocity_rad_s:.3f} rad/s")
        labels["effort"].setText(f"{sample.effort_nm:.3f} Nm")
        labels["voltage"].setText(f"{sample.voltage_v:.2f} V")
        labels["current"].setText(f"{sample.current_a:.3f} A")
        labels["accel_x"].setText(f"{sample.accel_x_m_s2:.3f} m/s^2")
        labels["temperature"].setText(f"{sample.winding_temperature_c:.2f} C")

    def _update_charts(self, side: str, sample: TelemetrySample) -> None:
        self.effort_series_by_side[side].append(sample.elapsed_seconds, sample.effort_nm)
        self.power_series_by_side[side].append(sample.elapsed_seconds, self._power_w(sample))
        self._trim_chart_series(self.effort_series_by_side[side])
        self._trim_chart_series(self.power_series_by_side[side])
        self._update_dual_chart_axes(self.effort_chart_view.chart(), self.effort_series_by_side)
        self._update_dual_chart_axes(self.power_chart_view.chart(), self.power_series_by_side)

    def _reset_charts(self) -> None:
        for series in self.effort_series_by_side.values():
            series.clear()
        for series in self.power_series_by_side.values():
            series.clear()
        self._update_dual_chart_axes(self.effort_chart_view.chart(), self.effort_series_by_side)
        self._update_dual_chart_axes(self.power_chart_view.chart(), self.power_series_by_side)

    def _trim_chart_series(self, series: QLineSeries) -> None:
        while series.count() > self._max_chart_points:
            series.remove(0)

    def _update_dual_chart_axes(self, chart: QChart, series_by_side: dict[str, QLineSeries]) -> None:
        axes = chart.axes()
        if len(axes) < 2:
            return

        points = []
        for series in series_by_side.values():
            points.extend(series.points())

        axis_x = axes[0]
        axis_y = axes[1]
        if not points:
            axis_x.setRange(0.0, 10.0)
            axis_y.setRange(0.0, 10.0)
            return

        last_x = max(point.x() for point in points)
        max_y = max(point.y() for point in points)
        min_y = min(point.y() for point in points)
        axis_x.setRange(max(0.0, last_x - 10.0), max(10.0, last_x))

        if max_y == min_y:
            padding = 1.0 if max_y == 0.0 else abs(max_y) * 0.1
            axis_y.setRange(min_y - padding, max_y + padding)
        else:
            padding = max((max_y - min_y) * 0.1, 0.1)
            axis_y.setRange(min_y - padding, max_y + padding)

    def _reset_checklist(self) -> None:
        for checkbox in self.checklist_boxes:
            checkbox.setChecked(False)

    def _both_wheels_connected(self) -> bool:
        return self.left_service.is_connected and self.right_service.is_connected

    def _same_module(self, first: DiscoveredModule, second: DiscoveredModule) -> bool:
        return first.family == second.family and first.name == second.name

    def _direction_sign(self) -> int:
        return -1 if self.direction_input.currentText() == "Clockwise" else 1

    def _side_for_role(self, role: str) -> str:
        clockwise = self.direction_input.currentText() == "Clockwise" if hasattr(self, "direction_input") else True
        if role == "FrontWheel":
            return "right" if clockwise else "left"
        return "left" if clockwise else "right"

    def _rpm_to_rad_s(self, rpm: float) -> float:
        return (rpm * 2.0 * 3.141592653589793) / 60.0

    def _output_root(self) -> Path:
        if self._output_directory is not None:
            return self._output_directory
        return _app_base_directory() / "data"

    def _data_file_status_text(self) -> str:
        return f"Output folder: {self._output_root()}"

    def _file_prefix(self) -> str:
        raw_prefix = self.file_prefix_input.text().strip()
        cleaned = raw_prefix.replace(" ", "_")
        safe_chars = []
        for char in cleaned:
            if char.isalnum() or char in {"_", "-"}:
                safe_chars.append(char)
        return "".join(safe_chars)

    def _power_w(self, sample: TelemetrySample) -> float:
        return sample.voltage_v * sample.current_a

    def _append_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {message}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wheel Test UI")
        self.resize(1160, 760)

        self.hebi_service = HebiWheelService()
        self.settings = QSettings("Space Robotics Lab", "Wheel Test UI")
        self.output_directory: Path | None = None

        self.stack = QStackedWidget()
        self.choice_page = WheelChoicePage()
        self.single_wheel_page = SingleWheelTestPage(self.hebi_service)
        self.two_wheel_page = TwoWheelTestPage()
        self.choice_page.single_wheel_selected.connect(self._open_single_wheel)
        self.choice_page.two_wheel_selected.connect(self._open_two_wheel)
        self.single_wheel_page.back_requested.connect(self._open_choice)
        self.single_wheel_page.change_output_directory_requested.connect(self._change_output_directory)
        self.two_wheel_page.back_requested.connect(self._open_choice)
        self.two_wheel_page.change_output_directory_requested.connect(self._change_output_directory)

        self.stack.addWidget(self.choice_page)
        self.stack.addWidget(self.single_wheel_page)
        self.stack.addWidget(self.two_wheel_page)
        self.setCentralWidget(self.stack)
        self._apply_styles()
        self._load_saved_output_directory()

    def _open_choice(self) -> None:
        self.stack.setCurrentWidget(self.choice_page)

    def _open_single_wheel(self) -> None:
        if self.output_directory is None and not self._choose_output_directory():
            return
        self.stack.setCurrentWidget(self.single_wheel_page)

    def _open_two_wheel(self) -> None:
        if self.output_directory is None and not self._choose_output_directory():
            return
        self.stack.setCurrentWidget(self.two_wheel_page)

    def _load_saved_output_directory(self) -> None:
        saved_directory = self.settings.value("output_directory", "", str)
        if not saved_directory:
            return

        candidate = Path(saved_directory)
        if not candidate.exists():
            return

        self.output_directory = candidate
        self.single_wheel_page.set_output_directory(candidate)
        self.two_wheel_page.set_output_directory(candidate)

    def _choose_output_directory(self) -> bool:
        default_directory = str(Path.home())
        if self.output_directory is not None:
            default_directory = str(self.output_directory)

        selected_directory = QFileDialog.getExistingDirectory(
            self,
            "Choose the folder where test data will be saved",
            default_directory,
        )
        if not selected_directory:
            QMessageBox.information(
                self,
                "Output folder required",
                "Choose an output folder before opening a test screen.",
            )
            return False

        target = Path(selected_directory)
        self.output_directory = target
        self.settings.setValue("output_directory", str(target))
        self.single_wheel_page.set_output_directory(target)
        self.two_wheel_page.set_output_directory(target)
        return True

    def _change_output_directory(self) -> None:
        self._choose_output_directory()

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
    dot_locale = QLocale(QLocale.English, QLocale.UnitedStates)
    QLocale.setDefault(dot_locale)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
