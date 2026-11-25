from __future__ import annotations

import dataclasses
import tempfile
import traceback
from collections.abc import Callable
from pathlib import Path

import numpy as np

from abp_rutasegura.abp_application.abp_norms_service import abp_load_packaged_rules
from abp_rutasegura.abp_application.abp_services import abpAppServices
from abp_rutasegura.abp_application.abp_sheet_service import abpSheetOptions
from abp_rutasegura.abp_data.abp_default_profiles import abp_load_default_profiles
from abp_rutasegura.abp_domain.abp_enums import abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment
from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_domain.abp_plan import abpExit, abpFloorPlan, abpRoom, abpWall
from abp_rutasegura.abp_engines.abp_cad.abp_reader import abp_save_as_dwg, abp_write_sample_dxf

abp_PX_PER_M = 50.0


def abp__m(abp_x: float, abp_y: float) -> abpPoint:
    return abpPoint(abp_x * abp_PX_PER_M, abp_y * abp_PX_PER_M)


def abp_sample_plan() -> abpFloorPlan:
    abp_walls = [
        abpSegment(abp__m(0, 0), abp__m(8, 0)),
        abpSegment(abp__m(0, 6), abp__m(8, 6)),
        abpSegment(abp__m(0, 0), abp__m(0, 6)),
        abpSegment(abp__m(8, 0), abp__m(8, 2.4)),
        abpSegment(abp__m(8, 3.6), abp__m(8, 6)),
    ]
    abp_room = abpPolygon((abp__m(0, 0), abp__m(8, 0), abp__m(8, 6), abp__m(0, 6)))
    return abpFloorPlan(
        abp_scale_m_per_px=1 / abp_PX_PER_M,
        abp_walls=tuple(abpWall(abp_w) for abp_w in abp_walls),
        abp_exits=(abpExit(abpSegment(abp__m(8, 2.4), abp__m(8, 3.6)), "Salida 1"),),
        abp_rooms=(abpRoom("Aula 1", abpUseType.abp_EDUCATION, abp_room),),
    )


def abp_sample_image() -> np.ndarray:
    abp_image = np.full((360, 480, 3), 255, np.uint8)
    abp_image[20:30, 20:460] = 0
    abp_image[330:340, 20:460] = 0
    abp_image[20:340, 20:30] = 0
    abp_image[20:140, 450:460] = 0
    abp_image[200:340, 450:460] = 0
    return abp_image


def abp_run_self_test(abp_log: Callable[[str], None]) -> bool:
    abp_checks: list[tuple[str, Callable[[Path], str]]] = [
        ("Reglas normativas", lambda _: f"{len(abp_load_packaged_rules().abp_rules)} reglas"),
        ("Perfiles por defecto", lambda _: f"{len(abp_load_default_profiles())} perfiles"),
        ("Base de datos y migraciones", abp__check_database),
        ("Visión (OpenCV)", abp__check_vision),
        ("Simulación e informe PDF", abp__check_simulation_and_report),
        ("Lámina técnica y lectura de PDF", abp__check_sheet_and_pdf),
        ("Planos de AutoCAD", abp__check_cad),
    ]
    abp_ok = True
    with tempfile.TemporaryDirectory(prefix="rutasegura_autoprueba_") as abp_tmp:
        for abp_name, abp_check in abp_checks:
            try:
                abp_detail = abp_check(Path(abp_tmp))
            except Exception:
                abp_ok = False
                abp_log(f"FALLA  {abp_name}\n{traceback.format_exc()}")
            else:
                abp_log(f"OK     {abp_name}: {abp_detail}")
    abp_log("Autoprueba superada." if abp_ok else "La autoprueba encontró errores.")
    return abp_ok


def abp__check_database(abp_tmp: Path) -> str:
    abp_services = abpAppServices.abp_open(abp_tmp / "db" / "prueba.db")
    try:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Autoprueba", abpUseType.abp_EDUCATION
        )
        abp_services.abp_projects.abp_save_floor(
            abp_project_id, abp_sample_plan(), abp_sample_image()
        )
        abp_plan = abp_services.abp_projects.abp_load_floor(abp_project_id)
        if abp_plan is None or not abp_plan.abp_rooms:
            raise RuntimeError("El plano guardado no se pudo leer.")
        return f"{len(abp_services.abp_simulations.abp_profiles())} perfiles en la base"
    finally:
        abp_services.abp_close()


def abp__check_vision(abp_tmp: Path) -> str:
    abp_services = abpAppServices.abp_open(abp_tmp / "db_vision" / "prueba.db")
    try:
        abp_plan = abp_services.abp_plans.abp_detect(
            abp_sample_image(), abpFloorPlan(abp_scale_m_per_px=1 / abp_PX_PER_M)
        )
        return f"{len(abp_plan.abp_walls)} muros y {len(abp_plan.abp_exits)} salidas detectados"
    finally:
        abp_services.abp_close()


def abp__check_sheet_and_pdf(abp_tmp: Path) -> str:
    abp_services = abpAppServices.abp_open(abp_tmp / "db_lamina" / "prueba.db")
    try:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Autoprueba", abpUseType.abp_EDUCATION
        )
        abp_services.abp_projects.abp_save_floor(
            abp_project_id, abp_sample_plan(), abp_sample_image()
        )
        abp_sheet = abp_services.abp_sheets.abp_generate(
            abp_project_id, abp_tmp / "lamina.pdf", abpSheetOptions(abp_underlay="limpio")
        )
        abp_page = abp_services.abp_plans.abp_pdf_pages(abp_sheet)[0]
        abp_loaded = abp_services.abp_plans.abp_load_pdf_page(abp_sheet, 0)
        if abp_loaded.abp_vector is None or abp_page.abp_scale_denominator is None:
            raise RuntimeError("No se leyeron los trazos o la escala de la lámina.")
        return f"escala 1/{abp_page.abp_scale_denominator}, {len(abp_loaded.abp_vector.abp_segments)} trazos leídos"
    finally:
        abp_services.abp_close()


def abp__check_cad(abp_tmp: Path) -> str:
    abp_dxf = abp_tmp / "prueba.dxf"
    abp_write_sample_dxf(abp_dxf)
    abp_services = abpAppServices.abp_open(abp_tmp / "db_cad" / "prueba.db")
    try:
        abp_done = ["DXF"]
        abp_files = [abp_dxf]
        abp_dwg = abp_tmp / "prueba.dwg"
        if abp_save_as_dwg(abp_dxf, abp_dwg):
            abp_files.append(abp_dwg)
            abp_done.append("DWG")
        for abp_path in abp_files:
            abp_page = abp_services.abp_plans.abp_pdf_pages(
                abp_services.abp_plans.abp_cad_to_pdf(abp_path)
            )[0]
            if not abp_page.abp_is_vector or abp_page.abp_scale_denominator is None:
                raise RuntimeError(f"No se leyó {abp_path.name}.")
        return " y ".join(abp_done) + " leídos"
    finally:
        abp_services.abp_close()


def abp__check_simulation_and_report(abp_tmp: Path) -> str:
    abp_services = abpAppServices.abp_open(abp_tmp / "db_sim" / "prueba.db")
    try:
        abp_project_id = abp_services.abp_projects.abp_create_project(
            "Autoprueba", abpUseType.abp_EDUCATION
        )
        abp_plan = abp_services.abp_projects.abp_save_floor(
            abp_project_id, abp_sample_plan(), abp_sample_image()
        )
        abp_scenario = dataclasses.replace(
            abp_services.abp_simulations.abp_load_scenario(abp_project_id),
            abp_occupancies=(abpOccupancy("Aula 1", "adulto", 15),),
        )
        abp_run = abp_services.abp_simulations.abp_run(abp_project_id, abp_plan, abp_scenario)
        abp_report = abp_services.abp_reports.abp_generate(abp_project_id, abp_tmp / "informe.pdf")
        abp_size = abp_report.stat().st_size
        if not abp_run.abp_result.abp_completed:
            raise RuntimeError("La simulación de prueba no terminó.")
        if abp_size < 10_000:
            raise RuntimeError(f"El informe PDF es demasiado pequeño ({abp_size} bytes).")
        return f"evacuación en {abp_run.abp_result.abp_total_time_s:.0f} s, informe de {abp_size // 1024} KB"
    finally:
        abp_services.abp_close()
