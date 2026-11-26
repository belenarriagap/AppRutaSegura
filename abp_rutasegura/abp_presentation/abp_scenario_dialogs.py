from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_simulation_service import abpSimulationRun
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_scenario import abp_FACTOR_RANGE, abp_MAX_RUNS, abpScenario
from abp_rutasegura.abp_presentation.abp_simulation_viewer import (
    abp_format_time,
    abpSimulationViewer,
)
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpScenarioTexts, abpSimulationTexts

abpImage = npt.NDArray[np.uint8]


@dataclass(frozen=True)
class abpScenarioChoice:
    abp_name: str
    abp_percent: int
    abp_blocked: frozenset[str]
    abp_description: str = ""
    abp_reaction_factor: float = 1.0
    abp_speed_factor: float = 1.0
    abp_runs: int = 1


(
    abp_TEMPLATE_CUSTOM,
    abp_TEMPLATE_CROWD,
    abp_TEMPLATE_BLOCKED,
    abp_TEMPLATE_SLOW_REACTION,
    abp_TEMPLATE_SLOW_WALK,
) = range(5)


class abpScenarioDialog(QDialog):
    def __init__(
        self,
        abp_exit_names: Sequence[str],
        abp_base_total: int,
        *,
        abp_name: str = "",
        abp_percent: int = 100,
        abp_blocked: frozenset[str] = frozenset(),
        abp_editing: bool = False,
        abp_description: str = "",
        abp_reaction_factor: float = 1.0,
        abp_speed_factor: float = 1.0,
        abp_runs: int = 1,
        abp_texts: abpScenarioTexts = abp_TEXTS.abp_scenarios,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.abp__base_total = abp_base_total
        self.abp__exit_names = list(abp_exit_names)
        self.setWindowTitle(
            abp_texts.abp_dialog_edit_title if abp_editing else abp_texts.abp_dialog_new_title
        )
        self.setMinimumWidth(520)

        self.abp_template_combo = QComboBox()
        self.abp_template_combo.addItems(abp_texts.abp_templates)
        self.abp_template_combo.setVisible(not abp_editing)
        self.abp_template_combo.currentIndexChanged.connect(self.abp_apply_template)
        self.abp_name_edit = QLineEdit(abp_name)
        self.abp_description_edit = QLineEdit(abp_description)
        self.abp_description_edit.setPlaceholderText(abp_texts.abp_description_placeholder)

        self.abp_percent_spin = QSpinBox()
        self.abp_percent_spin.setRange(10, 500)
        self.abp_percent_spin.setSingleStep(10)
        self.abp_percent_spin.setSuffix(" %")
        self.abp_percent_spin.setValue(abp_percent)
        self.abp_result_label = QLabel()
        self.abp_result_label.setObjectName("muted")
        self.abp_percent_spin.valueChanged.connect(self.abp__update_result)

        self.abp_exits_list = QListWidget()
        self.abp_exits_list.setMaximumHeight(110)
        for abp_exit_name in abp_exit_names:
            abp_item = QListWidgetItem(abp_exit_name)
            abp_item.setFlags(abp_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            abp_checked = abp_exit_name in abp_blocked
            abp_item.setCheckState(
                Qt.CheckState.Checked if abp_checked else Qt.CheckState.Unchecked
            )
            self.abp_exits_list.addItem(abp_item)

        abp_low, abp_high = abp_FACTOR_RANGE
        self.abp_reaction_spin = abp__factor_spin(abp_reaction_factor, abp_low, abp_high)
        self.abp_speed_spin = abp__factor_spin(abp_speed_factor, abp_low, abp_high)
        self.abp_runs_spin = QSpinBox()
        self.abp_runs_spin.setRange(1, abp_MAX_RUNS)
        self.abp_runs_spin.setValue(abp_runs)

        def abp_section(abp_title: str) -> QLabel:
            abp_label = QLabel(abp_title)
            abp_label.setObjectName("sectionTitle")
            return abp_label

        def abp_hint(abp_text: str) -> QLabel:
            abp_label = QLabel(abp_text)
            abp_label.setObjectName("muted")
            abp_label.setWordWrap(True)
            return abp_label

        abp_general = QFormLayout()
        if not abp_editing:
            abp_general.addRow(abp_texts.abp_template, self.abp_template_combo)
            abp_general.addRow("", abp_hint(abp_texts.abp_template_hint))
        abp_general.addRow(abp_texts.abp_name, self.abp_name_edit)
        abp_general.addRow(abp_texts.abp_description, self.abp_description_edit)
        abp_people = QFormLayout()
        abp_people.addRow(abp_texts.abp_occupancy, self.abp_percent_spin)
        abp_people.addRow("", self.abp_result_label)
        abp_behavior = QFormLayout()
        abp_behavior.addRow(abp_texts.abp_reaction_factor, self.abp_reaction_spin)
        abp_behavior.addRow("", abp_hint(abp_texts.abp_reaction_hint))
        abp_behavior.addRow(abp_texts.abp_speed_factor, self.abp_speed_spin)
        abp_behavior.addRow("", abp_hint(abp_texts.abp_speed_hint))
        abp_precision = QFormLayout()
        abp_precision.addRow(abp_texts.abp_runs, self.abp_runs_spin)
        abp_precision.addRow("", abp_hint(abp_texts.abp_runs_hint))

        abp_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        abp_buttons.accepted.connect(self.accept)
        abp_buttons.rejected.connect(self.reject)
        abp_layout = QVBoxLayout(self)
        abp_layout.addLayout(abp_general)
        abp_layout.addWidget(abp_section(abp_texts.abp_section_people))
        abp_layout.addLayout(abp_people)
        abp_layout.addWidget(abp_section(abp_texts.abp_section_blocked))
        if not abp_exit_names:
            abp_layout.addWidget(abp_hint(abp_texts.abp_no_exits))
        abp_layout.addWidget(self.abp_exits_list)
        abp_layout.addWidget(abp_section(abp_texts.abp_section_behavior))
        abp_layout.addLayout(abp_behavior)
        abp_layout.addWidget(abp_section(abp_texts.abp_section_runs))
        abp_layout.addLayout(abp_precision)
        abp_layout.addWidget(abp_hint(abp_texts.abp_base_hint))
        abp_layout.addWidget(abp_buttons)
        self.abp__update_result()

    def abp_apply_template(self, abp_index: int) -> None:
        self.abp_percent_spin.setValue(150 if abp_index == abp_TEMPLATE_CROWD else 100)
        self.abp_reaction_spin.setValue(2.0 if abp_index == abp_TEMPLATE_SLOW_REACTION else 1.0)
        self.abp_speed_spin.setValue(0.7 if abp_index == abp_TEMPLATE_SLOW_WALK else 1.0)
        for abp_i in range(self.abp_exits_list.count()):
            abp_block = abp_index == abp_TEMPLATE_BLOCKED and abp_i == 0
            self.abp_exits_list.item(abp_i).setCheckState(
                Qt.CheckState.Checked if abp_block else Qt.CheckState.Unchecked
            )
        if abp_index != abp_TEMPLATE_CUSTOM and not self.abp_name_edit.text().strip():
            abp_label = self.abp__texts.abp_templates[abp_index]
            if abp_index == abp_TEMPLATE_BLOCKED and self.abp__exit_names:
                abp_label = f"{self.abp__exit_names[0]} bloqueada"
            self.abp_name_edit.setText(abp_label.split(":")[0].split(" (")[0])

    def abp_choice(self) -> abpScenarioChoice:
        abp_blocked = {
            self.abp_exits_list.item(abp_i).text()
            for abp_i in range(self.abp_exits_list.count())
            if self.abp_exits_list.item(abp_i).checkState() == Qt.CheckState.Checked
        }
        return abpScenarioChoice(
            abp_name=self.abp_name_edit.text().strip(),
            abp_percent=self.abp_percent_spin.value(),
            abp_blocked=frozenset(abp_blocked),
            abp_description=self.abp_description_edit.text().strip(),
            abp_reaction_factor=round(self.abp_reaction_spin.value(), 2),
            abp_speed_factor=round(self.abp_speed_spin.value(), 2),
            abp_runs=self.abp_runs_spin.value(),
        )

    def abp_values(self) -> tuple[str, int, frozenset[str]]:
        abp_c = self.abp_choice()
        return abp_c.abp_name, abp_c.abp_percent, abp_c.abp_blocked

    def abp__update_result(self) -> None:
        abp_count = round(self.abp__base_total * self.abp_percent_spin.value() / 100)
        self.abp_result_label.setText(
            self.abp__texts.abp_occupancy_result.format(count=abp_count, base=self.abp__base_total)
        )


def abp__factor_spin(abp_value: float, abp_low: float, abp_high: float) -> QDoubleSpinBox:
    abp_spin = QDoubleSpinBox()
    abp_spin.setRange(abp_low, abp_high)
    abp_spin.setDecimals(2)
    abp_spin.setSingleStep(0.1)
    abp_spin.setValue(abp_value)
    return abp_spin


def abp__signed(abp_seconds: float) -> str:
    abp_sign = "+" if abp_seconds > 0 else "−" if abp_seconds < 0 else "±"
    return abp_sign + abp_format_time(abs(abp_seconds))


def abp_comparison_rows(
    abp_a: tuple[abpScenario, abpSimulationRun],
    abp_b: tuple[abpScenario, abpSimulationRun],
    abp_texts: abpScenarioTexts,
) -> list[tuple[str, str, str, str]]:
    (abp_sa, abp_ra), (abp_sb, abp_rb) = abp_a, abp_b
    abp_rows = [
        (
            abp_texts.abp_row_people,
            str(abp_sa.abp_total_occupants),
            str(abp_sb.abp_total_occupants),
            f"{abp_sb.abp_total_occupants - abp_sa.abp_total_occupants:+d}",
        ),
        (
            abp_texts.abp_row_blocked,
            ", ".join(sorted(abp_sa.abp_blocked_exits)) or abp_texts.abp_none,
            ", ".join(sorted(abp_sb.abp_blocked_exits)) or abp_texts.abp_none,
            "",
        ),
        (
            abp_texts.abp_row_total,
            abp_format_time(abp_ra.abp_result.abp_total_time_s),
            abp_format_time(abp_rb.abp_result.abp_total_time_s),
            abp__signed(abp_rb.abp_result.abp_total_time_s - abp_ra.abp_result.abp_total_time_s),
        ),
        (
            abp_texts.abp_row_evacuated,
            f"{abp_ra.abp_result.abp_agents_evacuated} / {abp_ra.abp_result.abp_agents_total}",
            f"{abp_rb.abp_result.abp_agents_evacuated} / {abp_rb.abp_result.abp_agents_total}",
            "",
        ),
        (
            abp_texts.abp_row_bottlenecks,
            str(len(abp_ra.abp_result.abp_bottlenecks)),
            str(len(abp_rb.abp_result.abp_bottlenecks)),
            f"{len(abp_rb.abp_result.abp_bottlenecks) - len(abp_ra.abp_result.abp_bottlenecks):+d}",
        ),
    ]
    for abp_label, abp_fraction in ((abp_texts.abp_row_half, 0.5), (abp_texts.abp_row_ninety, 0.9)):
        abp_ta, abp_tb = (
            abp_ra.abp_result.abp_time_to_evacuate(abp_fraction),
            abp_rb.abp_result.abp_time_to_evacuate(abp_fraction),
        )
        abp_rows.insert(
            3 if abp_fraction == 0.5 else 4,
            (
                abp_label,
                abp_format_time(abp_ta) if abp_ta is not None else "—",
                abp_format_time(abp_tb) if abp_tb is not None else "—",
                abp__signed(abp_tb - abp_ta) if abp_ta is not None and abp_tb is not None else "",
            ),
        )
    if (abp_sa.abp_reaction_factor, abp_sa.abp_speed_factor) != (1.0, 1.0) or (
        abp_sb.abp_reaction_factor,
        abp_sb.abp_speed_factor,
    ) != (1.0, 1.0):
        abp_rows.insert(
            2,
            (
                abp_texts.abp_row_factors,
                f"{abp_sa.abp_reaction_factor:g} / {abp_sa.abp_speed_factor:g}",
                f"{abp_sb.abp_reaction_factor:g} / {abp_sb.abp_speed_factor:g}",
                "",
            ),
        )
    abp_stats_a, abp_stats_b = abp_ra.abp_statistics, abp_rb.abp_statistics
    if abp_stats_a is not None or abp_stats_b is not None:
        abp_mean_a = (
            abp_stats_a.abp_total_mean_s if abp_stats_a else abp_ra.abp_result.abp_total_time_s
        )
        abp_mean_b = (
            abp_stats_b.abp_total_mean_s if abp_stats_b else abp_rb.abp_result.abp_total_time_s
        )
        abp_p95_a = (
            abp_stats_a.abp_total_p95_s if abp_stats_a else abp_ra.abp_result.abp_total_time_s
        )
        abp_p95_b = (
            abp_stats_b.abp_total_p95_s if abp_stats_b else abp_rb.abp_result.abp_total_time_s
        )
        abp_rows.append(
            (
                abp_texts.abp_row_mean,
                abp_format_time(abp_mean_a),
                abp_format_time(abp_mean_b),
                abp__signed(abp_mean_b - abp_mean_a),
            )
        )
        abp_rows.append(
            (
                abp_texts.abp_row_p95,
                abp_format_time(abp_p95_a),
                abp_format_time(abp_p95_b),
                abp__signed(abp_p95_b - abp_p95_a),
            )
        )
    abp_times_a = dict(abp_ra.abp_result.abp_time_per_exit_s)
    abp_times_b = dict(abp_rb.abp_result.abp_time_per_exit_s)
    for abp_name in sorted(set(abp_times_a) | set(abp_times_b)):
        abp_ta, abp_tb = abp_times_a.get(abp_name), abp_times_b.get(abp_name)
        abp_diff = abp__signed(abp_tb - abp_ta) if abp_ta is not None and abp_tb is not None else ""
        abp_rows.append(
            (
                abp_texts.abp_row_exit.format(name=abp_name),
                abp_format_time(abp_ta) if abp_ta is not None else abp_texts.abp_not_used,
                abp_format_time(abp_tb) if abp_tb is not None else abp_texts.abp_not_used,
                abp_diff,
            )
        )
    return abp_rows


class abpComparisonDialog(QDialog):
    def __init__(
        self,
        abp_scenarios: Sequence[abpScenario],
        abp_load_run: Callable[[str], abpSimulationRun | None],
        abp_floors: Sequence[tuple[abpFloorPlan, abpImage | None]],
        *,
        abp_texts: abpScenarioTexts = abp_TEXTS.abp_scenarios,
        abp_sim_texts: abpSimulationTexts = abp_TEXTS.abp_simulation,
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__texts = abp_texts
        self.setWindowTitle(abp_texts.abp_compare_title)
        self.resize(1300, 850)
        self.abp__runs: dict[str, tuple[abpScenario, abpSimulationRun]] = {}
        for abp_scenario in abp_scenarios:
            abp_run = abp_load_run(abp_scenario.abp_name)
            if abp_run is not None:
                self.abp__runs[abp_scenario.abp_name] = (abp_scenario, abp_run)
        abp_names = list(self.abp__runs)
        self.abp_combos = (QComboBox(), QComboBox())
        self.abp_viewers = (abpSimulationViewer(abp_sim_texts), abpSimulationViewer(abp_sim_texts))
        abp_sides = QHBoxLayout()
        for abp_k, (abp_combo, abp_viewer) in enumerate(
            zip(self.abp_combos, self.abp_viewers, strict=True)
        ):
            abp_combo.addItems(abp_names)
            if len(abp_names) > abp_k:
                abp_combo.setCurrentIndex(abp_k)
            abp_combo.currentIndexChanged.connect(self.abp__refresh)
            abp_viewer.abp_set_floors(list(abp_floors))
            abp_column = QVBoxLayout()
            abp_column.addWidget(QLabel("A" if abp_k == 0 else "B"))
            abp_column.addWidget(abp_combo)
            abp_column.addWidget(abp_viewer, stretch=1)
            abp_sides.addLayout(abp_column)
        self.abp_table = QTableWidget(0, 4)
        self.abp_table.setHorizontalHeaderLabels(
            [abp_texts.abp_metric, "A", "B", abp_texts.abp_difference]
        )
        self.abp_table.horizontalHeader().setStretchLastSection(True)
        self.abp_play_button = QPushButton(abp_texts.abp_play_both)
        self.abp_play_button.clicked.connect(self.abp_play_both)
        self.abp_message = QLabel(abp_texts.abp_compare_need_two if len(abp_names) < 2 else "")
        abp_layout = QVBoxLayout(self)
        abp_layout.addLayout(abp_sides, stretch=3)
        abp_layout.addWidget(self.abp_play_button)
        abp_layout.addWidget(self.abp_message)
        abp_layout.addWidget(self.abp_table, stretch=1)
        self.abp__refresh()

    @property
    def abp_available(self) -> list[str]:
        return list(self.abp__runs)

    def abp_play_both(self) -> None:
        for abp_viewer in self.abp_viewers:
            abp_viewer.abp_set_time(0.0)
            abp_viewer.abp_play()

    def abp__refresh(self) -> None:
        abp_chosen = [self.abp__runs.get(abp_c.currentText()) for abp_c in self.abp_combos]
        for abp_viewer, abp_data in zip(self.abp_viewers, abp_chosen, strict=True):
            if abp_data is None:
                abp_viewer.abp_set_run(None, None, 1.0)
            else:
                abp_run = abp_data[1]
                abp_viewer.abp_set_run(
                    abp_run.abp_trajectories, abp_run.abp_result, abp_run.abp_scale_m_per_px
                )
        self.abp_play_button.setEnabled(all(abp_d is not None for abp_d in abp_chosen))
        self.abp_table.setRowCount(0)
        if abp_chosen[0] is None or abp_chosen[1] is None:
            return
        abp_rows = abp_comparison_rows(abp_chosen[0], abp_chosen[1], self.abp__texts)
        self.abp_table.setRowCount(len(abp_rows))
        for abp_r, abp_row in enumerate(abp_rows):
            for abp_c, abp_text in enumerate(abp_row):
                self.abp_table.setItem(abp_r, abp_c, QTableWidgetItem(abp_text))
        self.abp_table.resizeColumnsToContents()
