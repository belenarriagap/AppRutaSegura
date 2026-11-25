from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import QDate
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_norms import abpRuleVerification
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpRoom
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_scenario import abpScenario
from abp_rutasegura.abp_engines.abp_vision.abp_images import abp_write_png
from abp_rutasegura.abp_presentation.abp_main_window import abpMainWindow
from abp_rutasegura.abp_presentation.abp_project_dialogs import abpProjectDetailsDialog
from abp_rutasegura.abp_presentation.abp_rules_dialog import (
    abp_FILTER_DONE,
    abp_FILTER_PENDING,
    abpRulesDialog,
)
from abp_tests.abp_fixtures.abp_simple_plans import abp_rect, abp_two_rooms

abp_DETAILS = abpProject(
    abp_name="Restaurante Vintage",
    abp_use=abpUseType.abp_COMMERCE,
    abp_address="Av. Larco 123",
    abp_district="Miraflores",
    abp_province="Lima",
    abp_department="Lima",
    abp_responsible="Ana Pérez",
    abp_responsible_role="Administradora",
    abp_phone="999 888 777",
    abp_email="ana@ejemplo.pe",
    abp_schedule="Viernes y sábados de 20:00 a 23:00",
    abp_notes="Local de dos ambientes",
)


class abpTestProjectDetails:
    def abp_test_create_update_and_logo(self, abp_services: abpAppServices, tmp_path: Path) -> None:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "  Restaurante Vintage ",
            abpUseType.abp_COMMERCE,
            "Av. Larco 123",
            abp_details=abp_DETAILS,
        )
        abp_saved = abp_services.abp_projects.abp_get_project(abp_project_id)
        assert abp_saved.abp_name == "Restaurante Vintage"
        assert abp_saved.abp_full_address == "Av. Larco 123 · Miraflores, Lima, Lima"
        assert (abp_saved.abp_responsible, abp_saved.abp_email, abp_saved.abp_schedule) == (
            "Ana Pérez",
            "ana@ejemplo.pe",
            "Viernes y sábados de 20:00 a 23:00",
        )
        abp_services.abp_projects.abp_update_project(
            abp_project_id, dataclasses.replace(abp_saved, abp_phone=" 01 444 ")
        )
        assert abp_services.abp_projects.abp_get_project(abp_project_id).abp_phone == "01 444"
        with pytest.raises(ValueError, match="correo"):
            dataclasses.replace(abp_saved, abp_email="x")
        abp_logo = abp_services.abp_projects.abp_set_logo(abp_project_id, b"\x89PNG fake", ".PNG")
        assert abp_logo.abp_logo_path is not None
        assert Path(abp_logo.abp_logo_path).read_bytes() == b"\x89PNG fake"
        assert (
            abp_services.abp_projects.abp_get_project(abp_project_id).abp_logo_path
            == abp_logo.abp_logo_path
        )
        abp_imported = abp_services.abp_archive.abp_import_bytes(
            abp_services.abp_archive.abp_export_bytes(abp_project_id)
        )
        abp_copy = abp_services.abp_projects.abp_get_project(abp_imported)
        assert abp_copy.abp_district == "Miraflores"
        assert abp_copy.abp_responsible_role == "Administradora"
        assert abp_copy.abp_logo_path is not None
        assert Path(abp_copy.abp_logo_path).read_bytes() == b"\x89PNG fake"
        abp_removed = abp_services.abp_projects.abp_set_logo(abp_project_id, None)
        assert abp_removed.abp_logo_path is None
        assert not Path(abp_logo.abp_logo_path).exists()

    def abp_test_dialog(self, qtbot: QtBot, tmp_path: Path) -> None:
        abp_dialog = abpProjectDetailsDialog(abp_DETAILS)
        qtbot.addWidget(abp_dialog)
        assert abp_dialog.abp_district_edit.text() == "Miraflores"
        abp_dialog.abp_schedule_edit.setText("Todos los días")
        abp_dialog.abp_email_edit.setText("mal")
        abp_dialog.accept()
        assert "correo" in abp_dialog.abp_error_label.text()
        abp_dialog.abp_email_edit.setText("ok@local.pe")
        abp_project = abp_dialog.abp_project()
        assert abp_project.abp_schedule == "Todos los días"
        assert abp_project.abp_created_at == abp_DETAILS.abp_created_at
        abp_image = tmp_path / "logo.png"
        abp_write_png(abp_image, np.full((20, 40, 3), 30, np.uint8))
        assert abp_dialog.abp_set_logo_file(abp_image)
        assert isinstance(abp_dialog.abp_logo_change, tuple)
        abp_bad = tmp_path / "x.png"
        abp_bad.write_bytes(b"no")
        assert not abp_dialog.abp_set_logo_file(abp_bad)
        abp_dialog.abp_remove_logo()
        assert abp_dialog.abp_logo_change == b""

    def abp_test_window(self, qtbot: QtBot, abp_services: abpAppServices) -> None:
        abp_window = abpMainWindow(abp_services)
        qtbot.addWidget(abp_window)
        assert not abp_window.abp_details_action.isEnabled()
        abp_project_id = abp_window.abp_create_project(
            "Tienda", abpUseType.abp_COMMERCE, abp_details=abp_DETAILS
        )
        assert abp_project_id is not None
        assert (
            abp_services.abp_projects.abp_get_project(abp_project_id).abp_district == "Miraflores"
        )
        assert abp_window.abp_apply_project_details(
            dataclasses.replace(abp_DETAILS, abp_name="Vintage 2")
        )
        assert "Vintage 2" in abp_window.windowTitle()
        assert abp_window.abp_message_banner.abp_kind == "success"


class abpTestCategories:
    @pytest.mark.parametrize(
        ("abp_name", "abp_use", "abp_expected"),
        [
            ("Baños", abpUseType.abp_COMMERCE, "banos"),
            ("SS.HH. varones", abpUseType.abp_EDUCATION, "banos"),
            ("Cocina", abpUseType.abp_OFFICE, "cocina"),
            ("COMEDORES", abpUseType.abp_COMMERCE, "mesas"),
            ("Comedor", abpUseType.abp_EDUCATION, "comedor"),
            ("Patio central", abpUseType.abp_EDUCATION, "patio"),
            ("Almacén", abpUseType.abp_COMMERCE, "deposito"),
            ("Pasillo 2", abpUseType.abp_OFFICE, "pasillo"),
            ("Aula 3", abpUseType.abp_EDUCATION, "aula"),
            ("Sala familiar", abpUseType.abp_COMMERCE, ""),
        ],
    )
    def abp_test_suggestion_by_name(
        self, abp_name: str, abp_use: abpUseType, abp_expected: str
    ) -> None:
        assert abpNormsService().abp_suggest_category(abp_name, abp_use) == abp_expected

    def abp_test_bathrooms_and_patios_do_not_add_capacity(self) -> None:
        abp_plan = dataclasses.replace(
            abp_two_rooms(),
            abp_rooms=(
                abpRoom("Baños", abpUseType.abp_COMMERCE, abp_rect(0, 0, 6, 6)),
                abpRoom("Tienda", abpUseType.abp_COMMERCE, abp_rect(6, 0, 6, 6)),
            ),
        )
        abp_evaluation = abpNormsService().abp_evaluate(abp_plan, None)
        abp_bath, abp_shop = abp_evaluation.abp_capacities
        assert abp_bath.abp_category == "banos"
        assert abp_bath.abp_capacity is None
        assert abp_shop.abp_capacity is not None
        assert abp_evaluation.abp_total_capacity == abp_shop.abp_capacity
        abp_chosen = dataclasses.replace(
            abp_plan,
            abp_rooms=(
                dataclasses.replace(abp_plan.abp_rooms[0], abp_category="tienda"),
                abp_plan.abp_rooms[1],
            ),
        )
        assert (
            abpNormsService().abp_evaluate(abp_chosen, None).abp_capacities[0].abp_category
            == "tienda"
        )


class abpTestRuleVerification:
    def abp_test_service(self, abp_services: abpAppServices) -> None:
        abp_norms = abp_services.abp_norms
        abp_before = next(
            abp_r for abp_r in abp_norms.abp_catalog() if abp_r.abp_id == "EVA-PUERTA-MINIMO"
        )
        assert not abp_before.abp_verified
        assert abp_before.abp_value_text == "0.9 m"
        abp_verification = abpRuleVerification(
            "EVA-PUERTA-MINIMO",
            1.0,
            "RNE A.130",
            "Art. 5",
            abp_source="D.S. de prueba",
            abp_verified_by="Ing. Ruiz",
            abp_verified_on=date(2026, 11, 11),
        )
        abp_after = abp_norms.abp_verify_rule(abp_verification)
        assert abp_after.abp_verified
        assert (abp_after.abp_value, abp_after.abp_verified_by) == (1.0, "Ing. Ruiz")
        abp_evaluation = abp_norms.abp_evaluate(
            abp_two_rooms(), abpScenario("x", 1, (abpOccupancy("Aula 1", "adulto", 1),))
        )
        abp_rule = next(
            abp_r for abp_r in abp_evaluation.abp_rules_used if abp_r.abp_id == "EVA-PUERTA-MINIMO"
        )
        assert abp_rule.abp_verified
        assert any(
            "mínimo es 1.00 m" in abp_o.abp_description for abp_o in abp_evaluation.abp_observations
        )
        assert next(
            abp_r
            for abp_r in abpNormsService(abp_db=abp_services.abp_database).abp_catalog()
            if abp_r.abp_verified
        ).abp_id
        abp_norms.abp_reset_rule("EVA-PUERTA-MINIMO")
        assert not next(
            abp_r for abp_r in abp_norms.abp_catalog() if abp_r.abp_id == "EVA-PUERTA-MINIMO"
        ).abp_verified

    def abp_test_validation(self, abp_services: abpAppServices) -> None:
        with pytest.raises(ValueError, match="positivo"):
            abpRuleVerification("EVA-PUERTA-MINIMO", 0, "RNE", "Art. 5")
        with pytest.raises(ValueError, match="artículo"):
            abpRuleVerification("EVA-PUERTA-MINIMO", 1, "RNE", " ")
        with pytest.raises(abpUserFacingError, match="necesita un valor"):
            abp_services.abp_norms.abp_verify_rule(
                abpRuleVerification("EVA-PUERTA-MINIMO", None, "RNE", "5")
            )
        with pytest.raises(abpUserFacingError, match="No existe"):
            abp_services.abp_norms.abp_verify_rule(abpRuleVerification("NO-EXISTE", 1, "RNE", "5"))
        assert abp_services.abp_norms.abp_verify_rule(
            abpRuleVerification("OCU-COM-BANOS", None, "RNE A.070", "Art. 8")
        ).abp_verified

    def abp_test_dialog(self, qtbot: QtBot, abp_services: abpAppServices) -> None:
        abp_dialog = abpRulesDialog(abp_services.abp_norms, abp_verifier="Ing. Ruiz")
        qtbot.addWidget(abp_dialog)
        abp_total = len(abp_dialog.abp_visible_rules)
        assert abp_total == len(abp_services.abp_norms.abp_catalog())
        abp_dialog.abp_select_rule("EVA-DISTANCIA-RECORRIDO")
        assert abp_dialog.abp_current_rule() is not None
        assert "45" in abp_dialog.abp_original_label.text()
        abp_dialog.abp_value_spin.setValue(50)
        abp_dialog.abp_article_edit.setText("Art. 14")
        assert not abp_dialog.abp_save_current()
        assert "confirmación" in abp_dialog.abp_message_label.text()
        abp_dialog.abp_confirm_check.setChecked(True)
        abp_dialog.abp_date_edit.setDate(QDate(2026, 11, 10))
        with qtbot.waitSignal(abp_dialog.abp_rules_changed):
            assert abp_dialog.abp_save_current()
        abp_rule = abp_dialog.abp_current_rule()
        assert abp_rule is not None
        assert (abp_rule.abp_value, abp_rule.abp_article, abp_rule.abp_verified_by) == (
            50.0,
            "Art. 14",
            "Ing. Ruiz",
        )
        abp_state = abp_dialog.abp_table.item(abp_dialog.abp_table.currentRow(), 3)
        assert abp_state is not None
        assert "10/11/2026" in abp_state.text()
        abp_dialog.abp_filter_combo.setCurrentIndex(abp_FILTER_DONE)
        assert [abp_r.abp_id for abp_r in abp_dialog.abp_visible_rules] == [
            "EVA-DISTANCIA-RECORRIDO"
        ]
        abp_dialog.abp_filter_combo.setCurrentIndex(abp_FILTER_PENDING)
        assert len(abp_dialog.abp_visible_rules) == abp_total - 1
        abp_dialog.abp_select_rule("EVA-DISTANCIA-RECORRIDO")
        abp_dialog.abp_reset_current()
        assert not abp_services.abp_norms.abp_original("EVA-DISTANCIA-RECORRIDO").abp_verified
        assert all(not abp_r.abp_verified for abp_r in abp_services.abp_norms.abp_catalog())


def abp_test_unified_room_type_selector(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QComboBox

    from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService
    from abp_rutasegura.abp_presentation.abp_rooms_page import abp_COL_USE, abpRoomsPage

    abp_norms = abpNormsService()
    abp_types = abp_norms.abp_room_types(abpUseType.abp_COMMERCE)
    assert abp_types[0][0] is abpUseType.abp_COMMERCE
    abp_labels = [abp_label for _, _, abp_label in abp_types]
    assert "Comercio › Servicios higiénicos (baños)" in abp_labels
    assert "Educación › Aula" in abp_labels
    abp_baths = abpRoom("Baños", abpUseType.abp_COMMERCE, abp_rect(0, 0, 2, 2))
    assert abp_norms.abp_effective_category(abp_baths) == "banos"
    assert (
        abp_norms.abp_effective_category(
            abpRoom("Sala", abpUseType.abp_COMMERCE, abp_rect(0, 0, 2, 2))
        )
        == "tienda"
    )

    abp_page = abpRoomsPage(abpPlanImportService(), abp_norms=abp_norms)
    qtbot.addWidget(abp_page)
    abp_plan = dataclasses.replace(
        abp_two_rooms(),
        abp_rooms=(abp_baths, abpRoom("Tienda", abpUseType.abp_COMMERCE, abp_rect(6, 0, 6, 6))),
    )
    abp_page.abp_set_content(abp_plan, None, abpScenario("Base", 1), [], abpUseType.abp_COMMERCE)
    abp_combo = abp_page.abp_table.cellWidget(0, abp_COL_USE)
    assert isinstance(abp_combo, QComboBox)
    assert abp_combo.currentText() == "Comercio › Servicios higiénicos (baños)"
    abp_combo.setCurrentIndex(abp_combo.findData("oficinas|oficina"))
    abp_room = abp_page.abp_plan.abp_rooms[0]
    assert (abp_room.abp_use, abp_room.abp_category) == (abpUseType.abp_OFFICE, "oficina")
