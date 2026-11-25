from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox

from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_plan import abpRoom

abpRoomTypeHandler = Callable[[abpUseType, str], None]


def abp_room_type_combo(
    abp_norms: abpNormsService,
    abp_room: abpRoom,
    abp_first_use: abpUseType,
    abp_on_change: abpRoomTypeHandler,
) -> QComboBox:
    abp_combo = QComboBox()
    for abp_use, abp_category, abp_label in abp_norms.abp_room_types(abp_first_use):
        abp_combo.addItem(abp_label, f"{abp_use.value}|{abp_category}")
    abp_current = f"{abp_room.abp_use.value}|{abp_norms.abp_effective_category(abp_room)}"
    abp_combo.setCurrentIndex(max(0, abp_combo.findData(abp_current)))

    def abp_changed(abp__index: int) -> None:
        abp_use, abp_category = str(abp_combo.currentData()).split("|", 1)
        abp_on_change(abpUseType(abp_use), abp_category)

    abp_combo.currentIndexChanged.connect(abp_changed)
    return abp_combo
