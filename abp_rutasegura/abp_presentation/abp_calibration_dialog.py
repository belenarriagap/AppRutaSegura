from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QDate, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_calibration_service import abpCalibrationService
from abp_rutasegura.abp_domain.abp_calibration import abpCalibrationResult
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill, abpScenario
from abp_rutasegura.abp_presentation.abp_qt_support import abpBackgroundJob
from abp_rutasegura.abp_presentation.abp_simulation_viewer import abp_format_time
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpCalibrationTexts


class abpCalibrationDialog(QDialog):
    abp_calibrated = Signal(object)
    abp_failed = Signal(str)
    abp_applied = Signal()

    def __init__(
        self,
        abp_calibration: abpCalibrationService,
        abp_project_id: int,
        abp_plan: abpFloorPlan | list[abpFloorPlan],
        abp_scenario: abpScenario,
        *,
        abp_grid: tuple[Sequence[float], Sequence[float]] | None = None,
        abp_texts: abpCalibrationTexts = abp_TEXTS.abp_calibration,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__calibration = abp_calibration
        self.abp__project_id = abp_project_id
        self.abp__plan = abp_plan
        self.abp__scenario = abp_scenario
        self.abp__grid = abp_grid
        self.abp__texts = abp_texts
        self.abp_calibration_result: abpCalibrationResult | None = None
        self.abp_job: abpBackgroundJob | None = None
        self.setWindowTitle(abp_texts.abp_title)
        self.resize(560, 520)

        abp_help_label = QLabel(abp_texts.abp_help)
        abp_help_label.setWordWrap(True)
        self.abp_date_edit = QDateEdit(QDate.currentDate())
        self.abp_date_edit.setCalendarPopup(True)
        self.abp_participants_spin = QSpinBox()
        self.abp_participants_spin.setRange(1, 20_000)
        self.abp_participants_spin.setValue(max(1, abp_scenario.abp_total_occupants))
        self.abp_minutes_spin = QSpinBox()
        self.abp_minutes_spin.setRange(0, 120)
        self.abp_minutes_spin.setSuffix(abp_texts.abp_minutes)
        self.abp_seconds_spin = QSpinBox()
        self.abp_seconds_spin.setRange(0, 59)
        self.abp_seconds_spin.setSuffix(abp_texts.abp_seconds)
        abp_time_row = QHBoxLayout()
        abp_time_row.addWidget(self.abp_minutes_spin)
        abp_time_row.addWidget(self.abp_seconds_spin)
        abp_time_row.addStretch(1)
        abp_form = QFormLayout()
        abp_form.addRow(abp_texts.abp_date, self.abp_date_edit)
        abp_form.addRow(abp_texts.abp_participants, self.abp_participants_spin)
        abp_form.addRow(abp_texts.abp_total_time, abp_time_row)
        self.abp_exit_spins: dict[str, QSpinBox] = {}
        abp_exits_form = QFormLayout()
        abp_plans = abp_plan if isinstance(abp_plan, list) else [abp_plan]
        for abp_exit_ in (abp_e for abp_p in abp_plans for abp_e in abp_p.abp_exits):
            if not abp_exit_.abp_confirmed:
                continue
            abp_spin = QSpinBox()
            abp_spin.setRange(0, 7200)
            abp_spin.setSuffix(abp_texts.abp_seconds)
            self.abp_exit_spins[abp_exit_.abp_name] = abp_spin
            abp_exits_form.addRow(f"{abp_exit_.abp_name}:", abp_spin)

        self.abp_progress = QProgressBar()
        self.abp_progress.setRange(0, 100)
        self.abp_progress.setVisible(False)
        self.abp_status_label = QLabel()
        self.abp_result_label = QLabel()
        self.abp_result_label.setWordWrap(True)
        abp_bold = QFont(self.abp_result_label.font())
        abp_bold.setBold(True)
        self.abp_result_label.setFont(abp_bold)
        self.abp_run_button = abp_set_primary(QPushButton(abp_texts.abp_run))
        self.abp_run_button.clicked.connect(self.abp_start)
        self.abp_cancel_button = QPushButton(abp_texts.abp_cancel)
        self.abp_cancel_button.clicked.connect(self.abp_cancel)
        self.abp_cancel_button.setEnabled(False)
        self.abp_apply_button = QPushButton(abp_texts.abp_apply)
        self.abp_apply_button.clicked.connect(self.abp_apply)
        self.abp_apply_button.setEnabled(False)
        abp_close_button = QPushButton(abp_texts.abp_close)
        abp_close_button.clicked.connect(self.reject)
        abp_buttons = QHBoxLayout()
        for abp_button in (self.abp_run_button, self.abp_cancel_button, self.abp_apply_button):
            abp_buttons.addWidget(abp_button)
        abp_buttons.addStretch(1)
        abp_buttons.addWidget(abp_close_button)

        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_help_label)
        abp_layout.addLayout(abp_form)
        if self.abp_exit_spins:
            abp_per_exit = QLabel(abp_texts.abp_per_exit)
            abp_per_exit.setWordWrap(True)
            abp_layout.addWidget(abp_per_exit)
            abp_layout.addLayout(abp_exits_form)
        abp_layout.addLayout(abp_buttons)
        abp_layout.addWidget(self.abp_progress)
        abp_layout.addWidget(self.abp_status_label)
        abp_layout.addWidget(self.abp_result_label)
        abp_layout.addStretch(1)

    def abp_set_drill(self, abp_drill: abpRealDrill) -> None:
        abp_d = abp_drill.abp_drill_date
        self.abp_date_edit.setDate(QDate(abp_d.year, abp_d.month, abp_d.day))
        self.abp_participants_spin.setValue(abp_drill.abp_participants)
        abp_minutes, abp_seconds = divmod(round(abp_drill.abp_total_time_s), 60)
        self.abp_minutes_spin.setValue(abp_minutes)
        self.abp_seconds_spin.setValue(abp_seconds)
        abp_times = dict(abp_drill.abp_time_per_exit_s)
        for abp_name, abp_spin in self.abp_exit_spins.items():
            abp_spin.setValue(round(abp_times.get(abp_name, 0)))

    def abp_drill(self) -> abpRealDrill:
        abp_total = self.abp_minutes_spin.value() * 60 + self.abp_seconds_spin.value()
        abp_per_exit = tuple(
            (abp_name, float(abp_spin.value()))
            for abp_name, abp_spin in self.abp_exit_spins.items()
            if abp_spin.value() > 0
        )
        return abpRealDrill(
            abp_drill_date=self.abp_date_edit.date().toPython(),
            abp_participants=self.abp_participants_spin.value(),
            abp_total_time_s=float(max(abp_total, 1)),
            abp_time_per_exit_s=abp_per_exit,
        )

    def abp_start(self) -> None:
        if self.abp_job is not None and self.abp_job.abp_running:
            return
        if self.abp_minutes_spin.value() * 60 + self.abp_seconds_spin.value() == 0:
            self.abp_status_label.setText(self.abp__texts.abp_missing_time)
            self.abp_failed.emit(self.abp__texts.abp_missing_time)
            return
        abp_drill = self.abp_drill()
        abp_service, abp_project_id, abp_plan, abp_scenario = (
            self.abp__calibration,
            self.abp__project_id,
            self.abp__plan,
            self.abp__scenario,
        )
        abp_extra: dict[str, Any] = {}
        if self.abp__grid is not None:
            abp_extra = {
                "abp_reaction_factors": self.abp__grid[0],
                "abp_speed_factors": self.abp__grid[1],
            }

        def abp_work(
            abp_report: Callable[[float], None], abp_should_cancel: Callable[[], bool]
        ) -> object:
            return abp_service.abp_calibrate(
                abp_project_id,
                abp_plan,
                abp_scenario,
                abp_drill,
                abp_progress=abp_report,
                abp_should_cancel=abp_should_cancel,
                **abp_extra,
            )

        self.abp_job = abpBackgroundJob(abp_work, self)
        self.abp_job.abp_progress.connect(self.abp__on_progress)
        self.abp_job.abp_done.connect(self.abp__on_done)
        self.abp_job.abp_failed.connect(self.abp__on_failed)
        self.abp_job.abp_cancelled.connect(self.abp__on_cancelled)
        self.abp_calibration_result = None
        self.abp_result_label.setText("")
        self.abp_apply_button.setEnabled(False)
        self.abp__set_running(True)
        self.abp_job.abp_start()

    def abp_cancel(self) -> None:
        if self.abp_job is not None:
            self.abp_job.abp_cancel()

    def abp_apply(self) -> None:
        if self.abp_calibration_result is None:
            return
        self.abp__calibration.abp_apply(self.abp_calibration_result)
        self.abp_apply_button.setEnabled(False)
        self.abp_status_label.setText(self.abp__texts.abp_applied)
        self.abp_applied.emit()

    def abp__on_progress(self, abp_fraction: float) -> None:
        self.abp_progress.setValue(round(100 * abp_fraction))
        self.abp_status_label.setText(
            self.abp__texts.abp_running.format(percent=100 * abp_fraction)
        )

    def abp__on_done(self, abp_result: object) -> None:
        self.abp__set_running(False)
        if not isinstance(abp_result, abpCalibrationResult):
            return
        self.abp_calibration_result = abp_result
        abp_t = self.abp__texts
        abp_text = abp_t.abp_result.format(
            before=abp_result.abp_total_error_before,
            after=abp_result.abp_total_error_after,
            reaction=abp_result.abp_best.abp_reaction_factor,
            speed=abp_result.abp_best.abp_speed_factor,
            simulated=abp_format_time(abp_result.abp_best.abp_total_time_s),
            observed=abp_format_time(abp_result.abp_observed_total_s),
        )
        abp_verdict = (
            abp_t.abp_target_met if abp_result.abp_meets_target else abp_t.abp_target_missed
        )
        self.abp_result_label.setText(f"{abp_text}\n{abp_verdict}")
        self.abp_status_label.setText("")
        self.abp_apply_button.setEnabled(True)
        self.abp_calibrated.emit(abp_result)

    def abp__on_failed(self, abp_message: str) -> None:
        self.abp__set_running(False)
        self.abp_status_label.setText(abp_message)
        self.abp_failed.emit(abp_message)

    def abp__on_cancelled(self) -> None:
        self.abp__set_running(False)
        self.abp_status_label.setText(self.abp__texts.abp_cancelled)

    def abp__set_running(self, abp_running: bool) -> None:
        self.abp_run_button.setEnabled(not abp_running)
        self.abp_cancel_button.setEnabled(abp_running)
        self.abp_progress.setVisible(abp_running)
        self.abp_progress.setValue(0)
