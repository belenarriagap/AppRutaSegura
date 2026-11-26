from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_domain.abp_norms import abpNormRule, abpRuleVerification
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS, abpNormsTexts

abp_FILTER_ALL, abp_FILTER_PENDING, abp_FILTER_DONE = range(3)


def abp_state_text(abp_rule: abpNormRule, abp_texts: abpNormsTexts) -> str:
    if not abp_rule.abp_verified:
        return abp_texts.abp_rules_state_pending
    if abp_rule.abp_verified_by and abp_rule.abp_verified_on:
        return abp_texts.abp_rules_state_done_by.format(
            who=abp_rule.abp_verified_by, date=abp_rule.abp_verified_on.strftime("%d/%m/%Y")
        )
    return abp_texts.abp_rules_state_done


class abpRulesDialog(QDialog):
    abp_rules_changed = Signal()

    def __init__(
        self,
        abp_norms: abpNormsService,
        abp_texts: abpNormsTexts = abp_TEXTS.abp_norms,
        *,
        abp_verifier: str = "",
        abp_parent: QWidget | None = None,
    ) -> None:
        super().__init__(abp_parent)
        self.abp__norms = abp_norms
        self.abp__texts = abp_t = abp_texts
        self.abp__rules: list[abpNormRule] = []
        self.setWindowTitle(abp_t.abp_rules_title)
        self.resize(1100, 640)

        abp_help_label = QLabel(abp_t.abp_rules_help)
        abp_help_label.setObjectName("muted")
        abp_help_label.setWordWrap(True)
        self.abp_filter_combo = QComboBox()
        self.abp_filter_combo.addItems(
            [
                abp_t.abp_rules_filter_all,
                abp_t.abp_rules_filter_pending,
                abp_t.abp_rules_filter_done,
            ]
        )
        self.abp_filter_combo.currentIndexChanged.connect(lambda abp__i: self.abp_refresh())
        self.abp_counter_label = QLabel()
        abp_top = QHBoxLayout()
        abp_top.addWidget(self.abp_filter_combo)
        abp_top.addStretch(1)
        abp_top.addWidget(self.abp_counter_label)

        self.abp_table = QTableWidget(0, 4)
        self.abp_table.setHorizontalHeaderLabels(
            [
                abp_t.abp_rules_column_rule,
                abp_t.abp_rules_column_value,
                abp_t.abp_rules_column_citation,
                abp_t.abp_rules_column_state,
            ]
        )
        self.abp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.abp_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.abp_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.abp_table.setAlternatingRowColors(True)
        self.abp_table.verticalHeader().setVisible(False)
        abp_header = self.abp_table.horizontalHeader()
        abp_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for abp_col in (1, 2, 3):
            abp_header.setSectionResizeMode(abp_col, QHeaderView.ResizeMode.ResizeToContents)
        self.abp_table.itemSelectionChanged.connect(self.abp__load_selected)

        self.abp_form_box = QGroupBox(abp_t.abp_rules_form_title)
        self.abp_rule_label = QLabel()
        self.abp_rule_label.setWordWrap(True)
        self.abp_rule_label.setObjectName("sectionTitle")
        self.abp_original_label = QLabel()
        self.abp_original_label.setObjectName("muted")
        self.abp_original_label.setWordWrap(True)
        self.abp_value_spin = QDoubleSpinBox()
        self.abp_value_spin.setDecimals(3)
        self.abp_value_spin.setRange(0.001, 100_000)
        self.abp_no_capacity_check = QCheckBox(abp_t.abp_rules_no_capacity)
        self.abp_no_capacity_check.toggled.connect(
            lambda abp_on: self.abp_value_spin.setEnabled(not abp_on)
        )
        self.abp_norm_edit = QLineEdit()
        self.abp_article_edit = QLineEdit()
        self.abp_source_edit = QLineEdit()
        self.abp_source_edit.setPlaceholderText(abp_t.abp_rules_source_placeholder)
        self.abp_by_edit = QLineEdit(abp_verifier)
        self.abp_date_edit = QDateEdit(QDate.currentDate())
        self.abp_date_edit.setCalendarPopup(True)
        self.abp_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.abp_confirm_check = QCheckBox(abp_t.abp_rules_confirm)
        self.abp_save_button = abp_set_primary(QPushButton(abp_t.abp_rules_save))
        self.abp_save_button.clicked.connect(self.abp_save_current)
        self.abp_reset_button = QPushButton(abp_t.abp_rules_reset)
        self.abp_reset_button.clicked.connect(self.abp_reset_current)
        self.abp_message_label = QLabel()
        self.abp_message_label.setWordWrap(True)
        abp_form = QFormLayout()
        abp_value_row = QHBoxLayout()
        abp_value_row.addWidget(self.abp_value_spin)
        abp_value_row.addWidget(self.abp_no_capacity_check)
        abp_form.addRow(abp_t.abp_rules_value, abp_value_row)
        abp_form.addRow(abp_t.abp_rules_norm, self.abp_norm_edit)
        abp_form.addRow(abp_t.abp_rules_article, self.abp_article_edit)
        abp_form.addRow(abp_t.abp_rules_source, self.abp_source_edit)
        abp_form.addRow(abp_t.abp_rules_by, self.abp_by_edit)
        abp_form.addRow(abp_t.abp_rules_date, self.abp_date_edit)
        abp_buttons = QHBoxLayout()
        abp_buttons.addWidget(self.abp_save_button)
        abp_buttons.addWidget(self.abp_reset_button)
        abp_buttons.addStretch(1)
        abp_box = QVBoxLayout(self.abp_form_box)
        abp_box.addWidget(self.abp_rule_label)
        abp_box.addWidget(self.abp_original_label)
        abp_box.addLayout(abp_form)
        abp_box.addWidget(self.abp_confirm_check)
        abp_box.addLayout(abp_buttons)
        abp_box.addWidget(self.abp_message_label)
        abp_box.addStretch(1)

        abp_splitter = QSplitter()
        abp_splitter.addWidget(self.abp_table)
        abp_splitter.addWidget(self.abp_form_box)
        abp_splitter.setSizes([680, 420])
        abp_layout = QVBoxLayout(self)
        abp_layout.addWidget(abp_help_label)
        abp_layout.addLayout(abp_top)
        abp_layout.addWidget(abp_splitter, stretch=1)
        self.abp_refresh()

    def abp_refresh(self, abp_select: str | None = None) -> None:
        abp_catalog = self.abp__norms.abp_catalog()
        abp_done = sum(1 for abp_r in abp_catalog if abp_r.abp_verified)
        self.abp_counter_label.setText(
            self.abp__texts.abp_rules_counter.format(done=abp_done, total=len(abp_catalog))
        )
        abp_mode = self.abp_filter_combo.currentIndex()
        self.abp__rules = [
            abp_r
            for abp_r in abp_catalog
            if abp_mode == abp_FILTER_ALL or (abp_mode == abp_FILTER_DONE) == abp_r.abp_verified
        ]
        self.abp_table.blockSignals(True)
        self.abp_table.setRowCount(len(self.abp__rules))
        for abp_row, abp_rule in enumerate(self.abp__rules):
            abp_name = (
                abp_rule.abp_description
                if not abp_rule.abp_label
                else f"{abp_rule.abp_label} — {abp_rule.abp_description}"
            )
            abp_cells = (
                abp_name,
                abp_rule.abp_value_text,
                abp_rule.abp_citation,
                abp_state_text(abp_rule, self.abp__texts),
            )
            for abp_col, abp_text in enumerate(abp_cells):
                abp_item = QTableWidgetItem(abp_text)
                abp_item.setToolTip(abp_rule.abp_id)
                if abp_col == 3 and not abp_rule.abp_verified:
                    abp_font = abp_item.font()
                    abp_font.setBold(True)
                    abp_item.setFont(abp_font)
                self.abp_table.setItem(abp_row, abp_col, abp_item)
        self.abp_table.blockSignals(False)
        abp_target = next(
            (abp_i for abp_i, abp_r in enumerate(self.abp__rules) if abp_r.abp_id == abp_select), 0
        )
        if self.abp__rules:
            self.abp_table.selectRow(abp_target)
        self.abp__load_selected()

    @property
    def abp_visible_rules(self) -> list[abpNormRule]:
        return list(self.abp__rules)

    def abp_select_rule(self, abp_rule_id: str) -> None:
        if all(abp_r.abp_id != abp_rule_id for abp_r in self.abp__rules):
            self.abp_filter_combo.setCurrentIndex(abp_FILTER_ALL)
        self.abp_refresh(abp_select=abp_rule_id)

    def abp_current_rule(self) -> abpNormRule | None:
        abp_rows = self.abp_table.selectionModel().selectedRows()
        if not abp_rows or abp_rows[0].row() >= len(self.abp__rules):
            return None
        return self.abp__rules[abp_rows[0].row()]

    def abp__load_selected(self) -> None:
        abp_rule = self.abp_current_rule()
        self.abp_form_box.setEnabled(abp_rule is not None)
        if abp_rule is None:
            return
        abp_original = self.abp__norms.abp_original(abp_rule.abp_id)
        self.abp_rule_label.setText(abp_rule.abp_label or abp_rule.abp_description)
        self.abp_original_label.setText(
            self.abp__texts.abp_rules_original.format(
                value=abp_original.abp_value_text, citation=abp_original.abp_citation
            )
        )
        abp_occupancy = abp_rule.abp_kind == "indice_ocupacion"
        self.abp_no_capacity_check.setVisible(abp_occupancy)
        self.abp_no_capacity_check.setChecked(abp_occupancy and abp_rule.abp_value is None)
        self.abp_value_spin.setSuffix(f" {abp_rule.abp_unit}" if abp_rule.abp_unit else "")
        if abp_rule.abp_value is not None:
            self.abp_value_spin.setValue(abp_rule.abp_value)
        self.abp_norm_edit.setText(abp_rule.abp_norm)
        self.abp_article_edit.setText(abp_rule.abp_article)
        self.abp_source_edit.setText(abp_rule.abp_source)
        if abp_rule.abp_verified_by:
            self.abp_by_edit.setText(abp_rule.abp_verified_by)
        if abp_rule.abp_verified_on:
            abp_d = abp_rule.abp_verified_on
            self.abp_date_edit.setDate(QDate(abp_d.year, abp_d.month, abp_d.day))
        self.abp_confirm_check.setChecked(False)
        self.abp_reset_button.setEnabled(abp_rule.abp_verified)
        self.abp_message_label.setText("")

    def abp_save_current(self) -> bool:
        abp_t = self.abp__texts
        abp_rule = self.abp_current_rule()
        if abp_rule is None:
            return False
        if not self.abp_confirm_check.isChecked():
            return self.abp__fail(abp_t.abp_rules_need_confirm)
        if not self.abp_by_edit.text().strip():
            return self.abp__fail(abp_t.abp_rules_need_name)
        abp_qdate = self.abp_date_edit.date()
        abp_value = None if self.abp_no_capacity_check.isChecked() else self.abp_value_spin.value()
        try:
            abp_verification = abpRuleVerification(
                abp_rule_id=abp_rule.abp_id,
                abp_value=abp_value,
                abp_norm=self.abp_norm_edit.text(),
                abp_article=self.abp_article_edit.text(),
                abp_source=self.abp_source_edit.text(),
                abp_verified=True,
                abp_verified_by=self.abp_by_edit.text(),
                abp_verified_on=date(abp_qdate.year(), abp_qdate.month(), abp_qdate.day()),
            )
            abp_saved = self.abp__norms.abp_verify_rule(abp_verification)
        except (ValueError, abpUserFacingError) as abp_exc:
            return self.abp__fail(
                abp_exc.abp_message if isinstance(abp_exc, abpUserFacingError) else str(abp_exc)
            )
        self.abp_refresh(abp_select=abp_rule.abp_id)
        self.abp_message_label.setStyleSheet("")
        self.abp_message_label.setText(
            abp_t.abp_rules_saved.format(rule=abp_saved.abp_label or abp_saved.abp_description)
        )
        self.abp_rules_changed.emit()
        return True

    def abp_reset_current(self) -> None:
        abp_rule = self.abp_current_rule()
        if abp_rule is None:
            return
        self.abp__norms.abp_reset_rule(abp_rule.abp_id)
        self.abp_refresh(abp_select=abp_rule.abp_id)
        self.abp_rules_changed.emit()

    def abp__fail(self, abp_message: str) -> bool:
        self.abp_message_label.setStyleSheet("font-weight: bold;")
        self.abp_message_label.setText(abp_message)
        return False
