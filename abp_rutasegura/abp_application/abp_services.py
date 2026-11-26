from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from abp_rutasegura.abp_application.abp_calibration_service import abpCalibrationService
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_plan_import import abpPlanImportService
from abp_rutasegura.abp_application.abp_project_archive import abpProjectArchiveService
from abp_rutasegura.abp_application.abp_projects import abpProjectService
from abp_rutasegura.abp_application.abp_report_service import abpReportService
from abp_rutasegura.abp_application.abp_sheet_service import abpSheetService
from abp_rutasegura.abp_application.abp_simulation_service import abpSimulationService
from abp_rutasegura.abp_data.abp_database import abp_default_database_path, abpDatabase


@dataclass(frozen=True)
class abpAppServices:
    abp_projects: abpProjectService
    abp_plans: abpPlanImportService
    abp_simulations: abpSimulationService
    abp_norms: abpNormsService
    abp_reports: abpReportService
    abp_calibration: abpCalibrationService
    abp_database: abpDatabase
    abp_archive: abpProjectArchiveService
    abp_sheets: abpSheetService

    @classmethod
    def abp_open(cls, abp_db_path: Path | None = None) -> abpAppServices:
        abp_path = abp_db_path or abp_default_database_path()
        abp_database = abpDatabase.abp_open(abp_path)
        abp_norms = abpNormsService(abp_db=abp_database)
        abp_projects = abpProjectService(abp_database, abp_path.parent / "planos")
        abp_simulations = abpSimulationService(
            abp_database, abp_path.parent / "trayectorias", abp_norms=abp_norms
        )
        return cls(
            abp_projects=abp_projects,
            abp_plans=abpPlanImportService(),
            abp_simulations=abp_simulations,
            abp_norms=abp_norms,
            abp_reports=abpReportService(abp_projects, abp_simulations, abp_norms),
            abp_calibration=abpCalibrationService(abp_database, abp_simulations),
            abp_database=abp_database,
            abp_archive=abpProjectArchiveService(abp_database, abp_projects, abp_simulations),
            abp_sheets=abpSheetService(abp_projects, abp_simulations, abp_norms),
        )

    def abp_close(self) -> None:
        self.abp_database.abp_close()
