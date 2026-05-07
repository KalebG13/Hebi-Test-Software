from __future__ import annotations

import csv
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
#Delay durations for the pre-roll and post-roll phases, which capture data before the wheel starts moving and after it stops so the CSV includes the baseline and settling behavior.
PRE_ROLL_SECONDS = 1.0
POST_ROLL_SECONDS = 1.0
TEST_DEFINITION_LABEL_WIDTH = 190
DEFAULT_TEST_NUMBER = 1
DEFAULT_REVOLUTIONS = 2.0
DEFAULT_VELOCITY_RPM = 14.0


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
            description="Reserved for the dual-wheel workflow. The screen is not implemented yet.",
            button_text="Coming Soon",
        )
        two_wheel_button.setEnabled(False)

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
        self.choice_page.single_wheel_selected.connect(self._open_single_wheel)
        self.single_wheel_page.back_requested.connect(self._open_choice)
        self.single_wheel_page.change_output_directory_requested.connect(self._change_output_directory)

        self.stack.addWidget(self.choice_page)
        self.stack.addWidget(self.single_wheel_page)
        self.setCentralWidget(self.stack)
        self._apply_styles()
        self._load_saved_output_directory()

    def _open_choice(self) -> None:
        self.stack.setCurrentWidget(self.choice_page)

    def _open_single_wheel(self) -> None:
        if self.output_directory is None and not self._choose_output_directory():
            return
        self.stack.setCurrentWidget(self.single_wheel_page)

    def _load_saved_output_directory(self) -> None:
        saved_directory = self.settings.value("output_directory", "", str)
        if not saved_directory:
            return

        candidate = Path(saved_directory)
        if not candidate.exists():
            return

        self.output_directory = candidate
        self.single_wheel_page.set_output_directory(candidate)

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
                "Choose an output folder before opening the single-wheel test screen.",
            )
            return False

        target = Path(selected_directory)
        self.output_directory = target
        self.settings.setValue("output_directory", str(target))
        self.single_wheel_page.set_output_directory(target)
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
