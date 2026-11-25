from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from abp_rutasegura.abp_presentation.abp_theme import abp_repolish

abp_KINDS = ("success", "warning", "error", "info")
abp__ICONS = {"success": "✓", "warning": "!", "error": "✕", "info": "i"}


def abp_page_title(abp_text: str) -> QLabel:
    abp_label = QLabel(abp_text)
    abp_label.setObjectName("pageTitle")
    return abp_label


def abp_page_help(abp_text: str) -> QLabel:
    abp_label = QLabel(abp_text)
    abp_label.setObjectName("pageHelp")
    abp_label.setWordWrap(True)
    return abp_label


def abp_section_title(abp_text: str) -> QLabel:
    abp_label = QLabel(abp_text)
    abp_label.setObjectName("sectionTitle")
    return abp_label


def abp_muted(abp_text: str = "") -> QLabel:
    abp_label = QLabel(abp_text)
    abp_label.setObjectName("muted")
    abp_label.setWordWrap(True)
    return abp_label


def abp_set_cell(
    abp_table: QTableWidget, abp_row: int, abp_column: int, abp_widget: QWidget
) -> None:
    abp_old = abp_table.cellWidget(abp_row, abp_column)
    if abp_old is not None:
        abp_old.hide()
    abp_table.setCellWidget(abp_row, abp_column, abp_widget)


class abpBanner(QFrame):
    abp_action_triggered = Signal()
    abp_closed = Signal()

    def __init__(self, abp_closable: bool = True, abp_parent: QWidget | None = None) -> None:
        super().__init__(abp_parent)
        self.setObjectName("banner")
        self.abp__kind = "info"
        self.abp_icon_label = QLabel()
        self.abp_icon_label.setObjectName("bannerIcon")
        self.abp_icon_label.setFixedWidth(22)
        self.abp_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.abp_text_label = QLabel()
        self.abp_text_label.setWordWrap(True)
        self.abp_text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.abp_action_button = QPushButton()
        self.abp_action_button.clicked.connect(self.abp_action_triggered)
        self.abp_action_button.setVisible(False)
        self.abp_close_button = QPushButton("×")
        self.abp_close_button.setObjectName("bannerClose")
        self.abp_close_button.setToolTip("Cerrar")
        self.abp_close_button.clicked.connect(self.abp_dismiss)
        self.abp_close_button.setVisible(abp_closable)
        abp_layout = QHBoxLayout(self)
        abp_layout.setContentsMargins(10, 6, 6, 6)
        abp_layout.addWidget(self.abp_icon_label, alignment=Qt.AlignmentFlag.AlignTop)
        abp_layout.addWidget(self.abp_text_label, stretch=1)
        abp_layout.addWidget(self.abp_action_button)
        abp_layout.addWidget(self.abp_close_button, alignment=Qt.AlignmentFlag.AlignTop)
        self.abp__timer = QTimer(self)
        self.abp__timer.setSingleShot(True)
        self.abp__timer.timeout.connect(self.abp_dismiss)
        self.abp__action: Callable[[], None] | None = None
        self.abp_action_triggered.connect(self.abp__run_action)
        self.setVisible(False)

    @property
    def abp_kind(self) -> str:
        return self.abp__kind

    @property
    def abp_text(self) -> str:
        return self.abp_text_label.text()

    def abp_show_message(
        self,
        abp_text: str,
        abp_kind: str = "info",
        *,
        abp_action_text: str = "",
        abp_action: Callable[[], None] | None = None,
        abp_timeout_ms: int = 0,
    ) -> None:
        if abp_kind not in abp_KINDS:
            raise ValueError(f"Tipo de mensaje desconocido: {abp_kind}")
        self.abp__kind = abp_kind
        self.setProperty("kind", abp_kind)
        self.abp_icon_label.setText(abp__ICONS[abp_kind])
        self.abp_text_label.setText(abp_text)
        self.abp__action = abp_action
        self.abp_action_button.setText(abp_action_text)
        self.abp_action_button.setVisible(bool(abp_action_text))
        abp_repolish(self)
        for abp_child in (self.abp_icon_label, self.abp_text_label):
            abp_repolish(abp_child)
        self.setVisible(True)
        self.abp__timer.stop()
        if abp_timeout_ms > 0:
            self.abp__timer.start(abp_timeout_ms)

    def abp_dismiss(self) -> None:
        self.abp__timer.stop()
        abp_was_shown = not self.isHidden()
        self.setVisible(False)
        if abp_was_shown:
            self.abp_closed.emit()

    def abp__run_action(self) -> None:
        if self.abp__action is not None:
            self.abp__action()


class abpMetricCard(QFrame):
    def __init__(self, abp_title: str, abp_parent: QWidget | None = None) -> None:
        super().__init__(abp_parent)
        self.setObjectName("card")
        self.abp_title_label = QLabel(abp_title)
        self.abp_title_label.setObjectName("cardTitle")
        self.abp_value_label = QLabel("—")
        self.abp_value_label.setObjectName("cardValue")
        self.abp_note_label = QLabel()
        self.abp_note_label.setObjectName("cardNote")
        self.abp_note_label.setWordWrap(True)
        abp_layout = QVBoxLayout(self)
        abp_layout.setContentsMargins(12, 8, 12, 10)
        abp_layout.setSpacing(2)
        abp_layout.addWidget(self.abp_title_label)
        abp_layout.addWidget(self.abp_value_label)
        abp_layout.addWidget(self.abp_note_label)
        self.abp_set_value("—")

    @property
    def abp_kind(self) -> str:
        abp_value = self.property("kind")
        return str(abp_value) if abp_value else "info"

    def abp_set_value(self, abp_value: str, abp_note: str = "", abp_kind: str = "info") -> None:
        self.abp_value_label.setText(abp_value)
        self.abp_note_label.setText(abp_note)
        self.abp_note_label.setVisible(bool(abp_note))
        self.setProperty("kind", abp_kind)
        abp_repolish(self)
        abp_repolish(self.abp_value_label)
