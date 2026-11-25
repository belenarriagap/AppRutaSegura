from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path

import abp_rutasegura
from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_norms_service import abpNormsService
from abp_rutasegura.abp_application.abp_projects import abpProjectService
from abp_rutasegura.abp_application.abp_sheet_service import abpSheetService
from abp_rutasegura.abp_application.abp_simulation_service import abpSimulationService
from abp_rutasegura.abp_data.abp_default_profiles import abp_load_default_profiles
from abp_rutasegura.abp_data.abp_evacuation_map import (
    abp_PAPER_SIZES,
    abp_write_evacuation_map,
    abpMapContent,
    abpMapFloor,
    abpMapOptions,
)
from abp_rutasegura.abp_data.abp_report_pdf import (
    abp_write_report,
    abpReportContent,
    abpScenarioRow,
)
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_results import abpEvacuationNetwork, abpRoomRoute
from abp_rutasegura.abp_engines.abp_simulation.abp_params import abpSimulationParams
from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS

abp_PAPER_NAMES: tuple[str, ...] = tuple(abp_PAPER_SIZES)
__all__ = ["abp_PAPER_NAMES", "abpMapOptions", "abpReportService", "abp_describe_parameters"]


def abp_describe_parameters(abp_params: abpSimulationParams) -> tuple[tuple[str, str], ...]:
    abp_p = abp_params
    return (
        ("Paso de tiempo", f"{abp_p.abp_dt_s:g} s"),
        ("Tamaño de celda de la grilla", "0.4 m"),
        ("Densidad máxima (provisional)", f"{abp_p.abp_jam_density:g} personas/m²"),
        ("Factor mínimo de velocidad (provisional)", f"{abp_p.abp_min_speed_factor:g}"),
        ("Variación individual de velocidad (provisional)", f"{abp_p.abp_speed_variation:.0%}"),
        ("Umbral de congestión (provisional)", f"{abp_p.abp_congestion_density:g} personas/m²"),
        (
            "Duración mínima de congestión (provisional)",
            f"{abp_p.abp_congestion_min_duration_s:g} s",
        ),
        ("Tiempo máximo simulado", f"{abp_p.abp_max_time_s:g} s"),
        ("Recorrido de escalera por piso (provisional)", f"{abp_p.abp_stair_travel_m:g} m"),
        (
            "Velocidad al bajar escaleras (provisional)",
            f"{abp_p.abp_stair_speed_factor:.0%} de la horizontal",
        ),
        (
            "Flujo específico de escalera (provisional)",
            f"{abp_p.abp_stair_specific_flow:g} personas/(s·m)",
        ),
    )


class abpReportService:
    def __init__(
        self,
        abp_projects: abpProjectService,
        abp_simulations: abpSimulationService,
        abp_norms: abpNormsService,
    ) -> None:
        self.abp__projects = abp_projects
        self.abp__simulations = abp_simulations
        self.abp__norms = abp_norms

    def abp_build_content(self, abp_project_id: int) -> abpReportContent:
        abp_project = self.abp__projects.abp_get_project(abp_project_id)
        abp_floors = [
            abp_f
            for abp_f in self.abp__projects.abp_load_floors(abp_project_id)
            if abp_f.abp_is_scaled
        ]
        if not abp_floors:
            raise abpUserFacingError("Primero cargue el plano y defina su escala (pasos 1 y 2).")
        abp_plan = abp_floors[0]
        abp_scenario = self.abp__simulations.abp_load_scenario(abp_project_id)
        abp_run = self.abp__simulations.abp_last_run(abp_project_id)
        abp_profiles = tuple(self.abp__simulations.abp_profiles())
        abp_defaults = {abp_d.abp_profile.abp_name: abp_d for abp_d in abp_load_default_profiles()}
        abp_provisional = tuple(
            abp_p.abp_name
            for abp_p in abp_profiles
            if abp_p.abp_name in abp_defaults
            and abp_defaults[abp_p.abp_name].abp_provisional
            and abp_defaults[abp_p.abp_name].abp_profile == abp_p
        )
        return abpReportContent(
            abp_project=abp_project,
            abp_plan=abp_plan,
            abp_plan_image=self.abp__projects.abp_load_floor_image(abp_plan),
            abp_floors=tuple(
                (abp_f, self.abp__projects.abp_load_floor_image(abp_f)) for abp_f in abp_floors
            ),
            abp_scenario=abp_scenario,
            abp_norms=self.abp__norms.abp_evaluate_building(abp_floors, abp_scenario),
            abp_result=None if abp_run is None else abp_run.abp_result,
            abp_congestion=() if abp_run is None else abp_run.abp_observations,
            abp_profiles=abp_profiles,
            abp_provisional_profiles=abp_provisional,
            abp_parameters=abp_describe_parameters(self.abp__simulations.abp_params),
            abp_legal_disclaimer=abp_TEXTS.abp_legal_disclaimer,
            abp_app_version=abp_rutasegura.__version__,
            abp_comparison=self.abp__comparison(abp_project_id),
            abp_statistics=None if abp_run is None else abp_run.abp_statistics,
            abp_floor_clearance=() if abp_run is None else abp_run.abp_floor_clearance,
        )

    def abp__comparison(self, abp_project_id: int) -> tuple[abpScenarioRow, ...]:
        abp_rows = []
        for abp_scenario in self.abp__simulations.abp_list_scenarios(abp_project_id):
            abp_run = self.abp__simulations.abp_last_run(abp_project_id, abp_scenario.abp_name)
            if abp_run is None:
                continue
            abp_result = abp_run.abp_result
            abp_rows.append(
                abpScenarioRow(
                    abp_name=abp_scenario.abp_name,
                    abp_occupants=abp_scenario.abp_total_occupants,
                    abp_blocked_exits=tuple(sorted(abp_scenario.abp_blocked_exits)),
                    abp_total_time_s=abp_result.abp_total_time_s,
                    abp_time_90_s=abp_result.abp_time_to_evacuate(0.9),
                    abp_evacuated=abp_result.abp_agents_evacuated,
                    abp_agents=abp_result.abp_agents_total,
                    abp_completed=abp_result.abp_completed,
                    abp_bottlenecks=len(abp_result.abp_bottlenecks),
                    abp_runs=abp_run.abp_statistics.abp_runs if abp_run.abp_statistics else 1,
                    abp_total_p95_s=abp_run.abp_statistics.abp_total_p95_s
                    if abp_run.abp_statistics
                    else None,
                )
            )
        return tuple(abp_rows)

    def abp_generate(self, abp_project_id: int, abp_path: Path) -> Path:
        if abp_path.suffix.lower() != ".pdf":
            abp_path = abp_path.with_suffix(".pdf")
        abp_content = self.abp_build_content(abp_project_id)
        try:
            abp_write_report(abp_path, abp_content)
        except OSError as abp_exc:
            raise abpUserFacingError(f"No se pudo guardar el informe: {abp_exc}") from abp_exc
        return abp_path

    def abp_map_content(self, abp_project_id: int, abp_options: abpMapOptions) -> abpMapContent:
        abp_project = self.abp__projects.abp_get_project(abp_project_id)
        abp_floors = [
            abp_f
            for abp_f in self.abp__projects.abp_load_floors(abp_project_id)
            if abp_f.abp_is_scaled
        ]
        if not abp_floors:
            raise abpUserFacingError("Primero cargue el plano y defina su escala (pasos 1 y 2).")
        if not any(
            abp_e.abp_confirmed for abp_f in abp_floors for abp_e in abp_f.abp_exits
        ) and not any(abp_f.abp_safe_zones for abp_f in abp_floors):
            raise abpUserFacingError(
                "El plano no tiene salidas confirmadas ni zonas seguras: no hay rutas que dibujar."
            )
        abp_scenario = dataclasses.replace(
            self.abp__simulations.abp_load_scenario(abp_project_id), abp_blocked_exits=frozenset()
        )
        abp_routes = self.abp__simulations.abp_routes(abp_floors, abp_scenario)
        abp_manual = [abp_r for abp_r in abp_routes if abp_r.abp_manual]
        return abpMapContent(
            abp_project=abp_project,
            abp_floors=tuple(
                abpMapFloor(
                    abp_f,
                    tuple(abp_r for abp_r in abp_routes if abp_r.abp_level == abp_f.abp_level),
                    self.abp__network(
                        abp_f, abp_manual, abp_upper_floor=abp_f is not abp_floors[0]
                    ),
                )
                for abp_f in abp_floors
            ),
            abp_options=abp_options,
            abp_app_version=abp_rutasegura.__version__,
        )

    def abp__network(
        self, abp_plan: abpFloorPlan, abp_manual: Sequence[abpRoomRoute], *, abp_upper_floor: bool
    ) -> abpEvacuationNetwork | None:
        if not abp_plan.abp_rooms:
            return None
        try:
            return abpSheetService.abp_network(
                abp_plan,
                {},
                abp_vector=self.abp__projects.abp_load_floor_vector(abp_plan),
                abp_upper_floor=abp_upper_floor,
                abp_manual=abp_manual,
            )
        except abpUserFacingError:
            return None

    def abp_generate_map(
        self, abp_project_id: int, abp_path: Path, abp_options: abpMapOptions
    ) -> Path:
        if abp_path.suffix.lower() != ".pdf":
            abp_path = abp_path.with_suffix(".pdf")
        abp_content = self.abp_map_content(abp_project_id, abp_options)
        try:
            abp_write_evacuation_map(abp_path, abp_content)
        except OSError as abp_exc:
            raise abpUserFacingError(f"No se pudo guardar el mapa: {abp_exc}") from abp_exc
        return abp_path
