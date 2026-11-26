from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_application.abp_errors import abpUserFacingError
from abp_rutasegura.abp_data.abp_database import abpDatabase
from abp_rutasegura.abp_data.abp_repositories import abpNotFoundError
from abp_rutasegura.abp_data.abp_vector_files import (
    abp_load_vector,
    abp_save_vector,
    abp_vector_path,
)
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_plan import abpFloorPlan
from abp_rutasegura.abp_domain.abp_project import abpProject
from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan
from abp_rutasegura.abp_engines.abp_vision.abp_images import (
    abp_read_image,
    abp_write_png,
    abpPlanFileError,
)

abpImage = npt.NDArray[np.uint8]


class abpProjectService:
    def __init__(self, abp_db: abpDatabase, abp_images_dir: Path) -> None:
        self.abp__db = abp_db
        self.abp__images_dir = abp_images_dir

    def abp_create_project(
        self,
        abp_name: str,
        abp_use: abpUseType,
        abp_address: str = "",
        *,
        abp_details: abpProject | None = None,
    ) -> int:
        try:
            abp_base = abp_details or abpProject(abp_name=abp_name, abp_use=abp_use)
            abp_project = abp__clean(
                dataclasses.replace(
                    abp_base,
                    abp_name=abp_name,
                    abp_use=abp_use,
                    abp_address=abp_address,
                    abp_logo_path=None,
                )
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        with self.abp__db.abp_unit_of_work() as abp_uow:
            return abp_uow.abp_projects.abp_add(abp_project)

    def abp_update_project(self, abp_project_id: int, abp_project: abpProject) -> abpProject:
        try:
            abp_current = self.abp_get_project(abp_project_id)
            abp_cleaned = abp__clean(
                dataclasses.replace(abp_project, abp_logo_path=abp_current.abp_logo_path)
            )
        except ValueError as abp_exc:
            raise abpUserFacingError(str(abp_exc)) from abp_exc
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_projects.abp_update(abp_project_id, abp_cleaned)
        return abp_cleaned

    def abp_set_logo(
        self, abp_project_id: int, abp_data: bytes | None, abp_suffix: str = ".png"
    ) -> abpProject:
        abp_project = self.abp_get_project(abp_project_id)
        abp_folder = self.abp__images_dir / f"proyecto_{abp_project_id}"
        for abp_old in abp_folder.glob("logo.*"):
            abp_old.unlink(missing_ok=True)
        abp_logo: str | None = None
        if abp_data is not None:
            abp_suffix = (
                abp_suffix.lower() if abp_suffix.lower() in (".png", ".jpg", ".jpeg") else ".png"
            )
            abp_path = abp_folder / f"logo{abp_suffix}"
            try:
                abp_folder.mkdir(parents=True, exist_ok=True)
                abp_path.write_bytes(abp_data)
            except OSError as abp_exc:
                raise abpUserFacingError(f"No se pudo guardar el logo: {abp_exc}") from abp_exc
            abp_logo = str(abp_path)
        abp_updated = dataclasses.replace(abp_project, abp_logo_path=abp_logo)
        with self.abp__db.abp_unit_of_work() as abp_uow:
            abp_uow.abp_projects.abp_update(abp_project_id, abp_updated)
        return abp_updated

    def abp_list_projects(self) -> list[tuple[int, abpProject]]:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            return abp_uow.abp_projects.abp_list_all()

    def abp_get_project(self, abp_project_id: int) -> abpProject:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                return abp_uow.abp_projects.abp_get(abp_project_id)
            except abpNotFoundError as abp_exc:
                raise abpUserFacingError("El proyecto ya no existe.") from abp_exc

    def abp_image_path(self, abp_project_id: int, abp_level: int) -> Path:
        return self.abp__images_dir / f"proyecto_{abp_project_id}" / f"piso_{abp_level}.png"

    def abp_save_floor(
        self,
        abp_project_id: int,
        abp_plan: abpFloorPlan,
        abp_image: abpImage | None = None,
        abp_vector: abpVectorPlan | None = None,
    ) -> abpFloorPlan:
        if abp_image is not None:
            abp_path = self.abp_image_path(abp_project_id, abp_plan.abp_level)
            abp_write_png(abp_path, abp_image)
            if abp_vector is not None:
                abp_save_vector(abp_vector_path(abp_path), abp_vector)
            else:
                abp_vector_path(abp_path).unlink(missing_ok=True)
            abp_plan = dataclasses.replace(abp_plan, abp_image_path=str(abp_path))
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                abp_uow.abp_floors.abp_save(abp_project_id, abp_plan)
            except ValueError as abp_exc:
                raise abpUserFacingError(str(abp_exc)) from abp_exc
            except abpNotFoundError as abp_exc:
                raise abpUserFacingError("El proyecto ya no existe.") from abp_exc
        return abp_plan

    def abp_load_floor(self, abp_project_id: int, abp_level: int = 0) -> abpFloorPlan | None:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                return abp_uow.abp_floors.abp_get(abp_project_id, abp_level)
            except abpNotFoundError:
                return None

    def abp_load_floors(self, abp_project_id: int) -> list[abpFloorPlan]:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            return [
                abp_uow.abp_floors.abp_get(abp_project_id, abp_level)
                for abp_level in abp_uow.abp_floors.abp_levels(abp_project_id)
            ]

    def abp_delete_floor(self, abp_project_id: int, abp_level: int) -> None:
        with self.abp__db.abp_unit_of_work() as abp_uow:
            try:
                abp_uow.abp_floors.abp_delete(abp_project_id, abp_level)
            except abpNotFoundError:
                return

    @staticmethod
    def abp_load_floor_vector(abp_plan: abpFloorPlan) -> abpVectorPlan | None:
        return (
            abp_load_vector(abp_vector_path(Path(abp_plan.abp_image_path)))
            if abp_plan.abp_image_path
            else None
        )

    @staticmethod
    def abp_load_floor_image(abp_plan: abpFloorPlan) -> abpImage | None:
        if not abp_plan.abp_image_path:
            return None
        try:
            return abp_read_image(Path(abp_plan.abp_image_path))
        except abpPlanFileError:
            return None


def abp__clean(abp_project: abpProject) -> abpProject:
    abp_texts = {
        abp_f: getattr(abp_project, abp_f).strip()
        for abp_f in (
            "abp_name",
            "abp_address",
            "abp_district",
            "abp_province",
            "abp_department",
            "abp_responsible",
            "abp_responsible_role",
            "abp_phone",
            "abp_email",
            "abp_schedule",
            "abp_notes",
        )
    }
    return dataclasses.replace(abp_project, **abp_texts)
