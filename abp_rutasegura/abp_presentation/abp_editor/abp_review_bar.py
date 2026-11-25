from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget

from abp_rutasegura.abp_domain.abp_enums import abpElementType
from abp_rutasegura.abp_presentation.abp_theme import abp_set_primary
from abp_rutasegura.abp_resources.abp_texts import abpEditorTexts


class abpReviewBar(QFrame):
    abp_answered = Signal(str)

    def __init__(self, abp_texts: abpEditorTexts, abp_parent: QWidget | None = None) -> None:
        super().__init__(abp_parent)
        self.setObjectName("card")
        self.abp__texts = abp_texts
        self.abp_question_label = QLabel()
        self.abp_question_label.setStyleSheet("font-weight: 600;")
        self.abp_progress = QProgressBar()
        self.abp_progress.setFixedWidth(110)
        self.abp_yes_button = abp_set_primary(QPushButton(abp_texts.abp_review_yes))
        self.abp_no_button = QPushButton(abp_texts.abp_review_no)
        self.abp_skip_button = QPushButton(abp_texts.abp_review_skip)
        self.abp_close_button = QPushButton(abp_texts.abp_review_close)
        self.abp_yes_button.setShortcut(QKeySequence(Qt.Key.Key_Return))
        self.abp_no_button.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        self.abp_skip_button.setShortcut(QKeySequence(Qt.Key.Key_Right))
        for abp_button, abp_answer in (
            (self.abp_yes_button, "si"),
            (self.abp_no_button, "no"),
            (self.abp_skip_button, "saltar"),
            (self.abp_close_button, "fin"),
        ):
            abp_button.clicked.connect(
                lambda _=False, abp_a=abp_answer: self.abp_answered.emit(abp_a)
            )
        self.abp_all_button = QPushButton(abp_texts.abp_review_all)
        self.abp_all_button.clicked.connect(lambda: self.abp_answered.emit("todos"))
        self.abp_other_buttons: list[QPushButton] = []
        self.abp__layout = QHBoxLayout(self)
        self.abp__layout.setContentsMargins(10, 6, 10, 6)
        self.abp__layout.addWidget(self.abp_progress)
        self.abp__layout.addWidget(self.abp_question_label, stretch=1)
        for abp_button in (
            self.abp_yes_button,
            self.abp_all_button,
            self.abp_no_button,
            self.abp_skip_button,
            self.abp_close_button,
        ):
            self.abp__layout.addWidget(abp_button)

    def abp_show_item(
        self,
        abp_kind: abpElementType,
        abp_number: int,
        abp_total: int,
        abp_others: Iterable[abpElementType],
    ) -> None:
        abp_t = self.abp__texts
        abp_names = dict(abp_t.abp_kind_names)
        abp_name = abp_names.get(abp_kind.value, abp_kind.value).lower()
        abp_article = (
            abp_t.abp_review_masculine
            if abp_kind is abpElementType.abp_OBSTACLE
            else abp_t.abp_review_feminine
        )
        self.abp_question_label.setText(
            abp_t.abp_review_question.format(
                number=abp_number, total=abp_total, article=abp_article, kind=abp_name
            )
        )
        abp_opening = abp_kind in (abpElementType.abp_DOOR, abpElementType.abp_EXIT)
        self.abp_no_button.setText(abp_t.abp_review_no_wall if abp_opening else abp_t.abp_review_no)
        self.abp_all_button.setVisible(abp_kind is abpElementType.abp_OBSTACLE)
        self.abp_progress.setMaximum(abp_total)
        self.abp_progress.setValue(abp_number - 1)
        self.abp_progress.setFormat(f"{abp_number} / {abp_total}")
        for abp_button in self.abp_other_buttons:
            self.abp__layout.removeWidget(abp_button)
            abp_button.deleteLater()
        self.abp_other_buttons = []
        for abp_other in abp_others:
            if abp_opening and abp_other is abpElementType.abp_WALL:
                continue
            abp_label = abp_t.abp_review_other.format(
                kind=abp_names.get(abp_other.value, abp_other.value).lower()
            )
            abp_button = QPushButton(abp_label)
            abp_button.clicked.connect(
                lambda _=False, abp_a=abp_other.value: self.abp_answered.emit(abp_a)
            )
            self.abp__layout.insertWidget(
                self.abp__layout.indexOf(self.abp_skip_button), abp_button
            )
            self.abp_other_buttons.append(abp_button)
