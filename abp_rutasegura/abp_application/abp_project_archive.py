from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import shutil
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_application.abp_projects import abpProjectService
from abp_rutasegura.abp_application.abp_serialization import (
    abp_plan_from_dict,
    abp_plan_to_dict,
    abp_scenario_from_dict,
    abp_scenario_to_dict,
)
from abp_rutasegura.abp_application.abp_simulation_service import abpSimulationService
from abp_rutasegura.abp_data.abp_database import abpDatabase
from abp_rutasegura.abp_data.abp_repositories import abpNotFoundError
from abp_rutasegura.abp_data.abp_vector_files import abp_vector_path
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_scenario import abpRealDrill

abp_FORMAT = "rutasegura-proyecto"
abp_VERSION = 1
abp_EXTENSION = ".rutasegura"
abp_MANIFEST = "proyecto.json"
abp_INVALID = "El archivo no es un proyecto de RutaSegura válido."
abp__DETAILS = (
    ("distrito", "abp_district"),
    ("provincia", "abp_province"),
    ("departamento", "abp_department"),
    ("responsable", "abp_responsible"),
    ("cargo_responsable", "abp_responsible_role"),
    ("telefono", "abp_phone"),
    ("correo", "abp_email"),
    ("horario", "abp_schedule"),
    ("notas", "abp_notes"),
)


class abpProjectArchiveService:
    def __init__(
        self,
        abp_db: abpDatabase,
        abp_projects: abpProjectService,
        abp_simulations: abpSimulationService,
    ) -> None:
        self.abp__db = abp_db
        self.abp__projects = abp_projects
        self.abp__simulations = abp_simulations

    def abp_export_bytes(self, abp_project_id: int) -> bytes:
        abp_project = self.abp__projects.abp_get_project(abp_project_id)
        abp_floors = self.abp__projects.abp_load_floors(abp_project_id)
        abp_scenarios = [
            abp_s
            for abp_s in self.abp__simulations.abp_list_scenarios(abp_project_id)
            if abp_s.abp_total_occupants or abp_s.abp_name != "Escenario base" or abp_s.abp_runs > 1
        ]
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_drills = [abp_d for _, abp_d in abp_uow.abp_drills.abp_list_all(abp_project_id)]
        abp_manifest = {
            "formato": abp_FORMAT,
            "version": abp_VERSION,
            "proyecto": {
                "nombre": abp_project.abp_name,
                "uso": abp_project.abp_use.value,
                "direccion": abp_project.abp_address,
                **{abp_key: getattr(abp_project, abp_attr) for abp_key, abp_attr in abp__DETAILS},
            },
            "pisos": [abp_plan_to_dict(abp_f) for abp_f in abp_floors],
            "escenarios": [abp_scenario_to_dict(abp_s) for abp_s in abp_scenarios],
            "simulacros": [
                {
                    "fecha": abp_d.abp_drill_date.isoformat(),
                    "participantes": abp_d.abp_participants,
                    "tiempo_total_s": abp_d.abp_total_time_s,
                    "tiempos_por_salida": [list(abp_t) for abp_t in abp_d.abp_time_per_exit_s],
                }
                for abp_d in abp_drills
            ],
        }
        abp_buffer = io.BytesIO()
        with zipfile.ZipFile(abp_buffer, "w", zipfile.ZIP_DEFLATED) as abp_archive:
            abp_archive.writestr(
                abp_MANIFEST, json.dumps(abp_manifest, ensure_ascii=False, indent=1)
            )
            for abp_plan in abp_floors:
                if abp_plan.abp_image_path and Path(abp_plan.abp_image_path).is_file():
                    abp_archive.write(
                        abp_plan.abp_image_path, f"planos/piso_{abp_plan.abp_level}.png"
                    )
                    abp_traces = abp_vector_path(Path(abp_plan.abp_image_path))
                    if abp_traces.is_file():
                        abp_archive.write(
                            abp_traces, f"planos/piso_{abp_plan.abp_level}.trazos.npz"
                        )
            if abp_project.abp_logo_path and Path(abp_project.abp_logo_path).is_file():
                abp_archive.write(
                    abp_project.abp_logo_path,
                    f"logo{Path(abp_project.abp_logo_path).suffix.lower()}",
                )
        return abp_buffer.getvalue()

    def abp_export_project(self, abp_project_id: int, abp_path: Path) -> Path:
        if abp_path.suffix.lower() != abp_EXTENSION:
            abp_path = abp_path.with_suffix(abp_EXTENSION)
        abp_data = self.abp_export_bytes(abp_project_id)
        try:
            abp_path.parent.mkdir(parents=True, exist_ok=True)
            abp_path.write_bytes(abp_data)
        except OSError as abp_exc:
            raise abpUserFacingError(f"No se pudo guardar el archivo: {abp_exc}") from abp_exc
        return abp_path

    def abp_import_bytes(self, abp_data: bytes, *, abp_name: str | None = None) -> int:
        try:
            with zipfile.ZipFile(io.BytesIO(abp_data)) as abp_archive:
                abp_manifest = json.loads(abp_archive.read(abp_MANIFEST).decode("utf-8"))
                if abp_manifest.get("formato") != abp_FORMAT:
                    raise abpUserFacingError(abp_INVALID)
                if int(abp_manifest.get("version", 0)) > abp_VERSION:
                    raise abpUserFacingError(
                        "El proyecto fue creado con una versión más nueva de RutaSegura. "
                        "Actualice el programa para abrirlo."
                    )
                abp_info = abp_manifest["proyecto"]
                abp_floors = [abp_plan_from_dict(abp_f) for abp_f in abp_manifest["pisos"]]
                abp_scenarios = [
                    abp_scenario_from_dict(abp_s) for abp_s in abp_manifest["escenarios"]
                ]
                abp_logo_name = next(
                    (abp_n for abp_n in abp_archive.namelist() if abp_n.startswith("logo.")), None
                )
                abp_logo = (
                    (abp_archive.read(abp_logo_name), Path(abp_logo_name).suffix)
                    if abp_logo_name
                    else None
                )
                abp_images = {
                    abp_plan.abp_level: abp_archive.read(f"planos/piso_{abp_plan.abp_level}.png")
                    for abp_plan in abp_floors
                    if f"planos/piso_{abp_plan.abp_level}.png" in abp_archive.namelist()
                }
                abp_traces_by_level = {
                    abp_plan.abp_level: abp_archive.read(
                        f"planos/piso_{abp_plan.abp_level}.trazos.npz"
                    )
                    for abp_plan in abp_floors
                    if f"planos/piso_{abp_plan.abp_level}.trazos.npz" in abp_archive.namelist()
                }
                abp_drills = [
                    abpRealDrill(
                        abp_drill_date=date.fromisoformat(abp_d["fecha"]),
                        abp_participants=int(abp_d["participantes"]),
                        abp_total_time_s=float(abp_d["tiempo_total_s"]),
                        abp_time_per_exit_s=tuple(
                            (str(abp_n), float(abp_t))
                            for abp_n, abp_t in abp_d["tiempos_por_salida"]
                        ),
                    )
                    for abp_d in abp_manifest.get("simulacros", [])
                ]
        except abpUserFacingError:
            raise
        except (zipfile.BadZipFile, KeyError, ValueError, TypeError) as abp_exc:
            raise abpUserFacingError(abp_INVALID) from abp_exc
        abp_use = abpUseType(abp_info["uso"])
        abp_extra: dict[str, Any] = {
            abp_attr: str(abp_info.get(abp_key, "")) for abp_key, abp_attr in abp__DETAILS
        }
        try:
            abp_details = abpProject(
                abp_name=abp_name or str(abp_info["nombre"]), abp_use=abp_use, **abp_extra
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(f"{abp_INVALID} {abp_exc}") from abp_exc
        abp_project_id = self.abp__projects.abp_create_project(
            abp_details.abp_name,
            abp_use,
            str(abp_info.get("direccion", "")),
            abp_details=abp_details,
        )
        try:
            for abp_plan in abp_floors:
                if abp_plan.abp_level in abp_images:
                    abp_target = self.abp__projects.abp_image_path(
                        abp_project_id, abp_plan.abp_level
                    )
                    abp_target.parent.mkdir(parents=True, exist_ok=True)
                    abp_target.write_bytes(abp_images[abp_plan.abp_level])
                    if abp_plan.abp_level in abp_traces_by_level:
                        abp_vector_path(abp_target).write_bytes(
                            abp_traces_by_level[abp_plan.abp_level]
                        )
                    abp_plan = dataclasses.replace(abp_plan, abp_image_path=str(abp_target))
                self.abp__projects.abp_save_floor(abp_project_id, abp_plan)
            if abp_logo is not None:
                self.abp__projects.abp_set_logo(abp_project_id, *abp_logo)
            for abp_scenario in abp_scenarios:
                self.abp__simulations.abp_save_scenario(abp_project_id, abp_scenario)
            with self.abp__db.abp_unit_of_work() as abp_uow:
                for abp_drill in abp_drills:
                    abp_uow.abp_drills.abp_add(abp_project_id, abp_drill)
        except (abpUserFacingError, OSError, ValueError) as abp_exc:
            self.abp_delete_project(abp_project_id)
            abp_message = (
                abp_exc.abp_message if isinstance(abp_exc, abpUserFacingError) else str(abp_exc)
            )
            raise abpUserFacingError(f"No se pudo importar el proyecto: {abp_message}") from abp_exc
        return abp_project_id

    def abp_import_project(self, abp_path: Path) -> int:
        try:
            abp_data = abp_path.read_bytes()
        except OSError as abp_exc:
            raise abpUserFacingError(f"No se pudo leer el archivo: {abp_exc}") from abp_exc
        return self.abp_import_bytes(abp_data)

    def abp_duplicate_project(self, abp_project_id: int, abp_name: str | None = None) -> int:
        abp_original = self.abp__projects.abp_get_project(abp_project_id)
        return self.abp_import_bytes(
            self.abp_export_bytes(abp_project_id),
            abp_name=abp_name or f"{abp_original.abp_name} (copia)",
        )

    def abp_delete_project(self, abp_project_id: int) -> None:
        with self.abp__db.abp_unit_of_work() as abp_uow, contextlib.suppress(abpNotFoundError):
            abp_uow.abp_projects.abp_delete(abp_project_id)
        for abp_folder in (
            self.abp__projects.abp_image_path(abp_project_id, 0).parent,
            self.abp__simulations.abp_project_runs_dir(abp_project_id),
        ):
            shutil.rmtree(abp_folder, ignore_errors=True)


def abp_default_export_name(abp_project: abpProject) -> str:
    abp_safe = (
        "".join(abp_c for abp_c in abp_project.abp_name if abp_c not in '\\/:*?"<>|').strip()
        or "proyecto"
    )
    return abp_safe + abp_EXTENSION
