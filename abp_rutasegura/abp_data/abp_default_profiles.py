from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import yaml

from abp_rutasegura.abp_domain.abp_people import abpPersonProfile

abp_PROFILES_RESOURCE = (
    "abp_rutasegura.abp_resources",
    "abp_profiles/abp_perfiles_por_defecto.yaml",
)
abp__VALUE_FIELDS = ("vel_max_mps", "reaccion_media_s", "reaccion_desv_s", "radio_m")


@dataclass(frozen=True, slots=True)
class abpDefaultProfile:
    abp_profile: abpPersonProfile
    abp_provisional: bool
    abp_sources: dict[str, str] = field(default_factory=dict)


def abp_parse_default_profiles(abp_text: str) -> list[abpDefaultProfile]:
    abp_data: Any = yaml.safe_load(abp_text)
    if not isinstance(abp_data, dict) or not isinstance(abp_data.get("perfiles"), list):
        raise ValueError("El archivo de perfiles debe tener una lista 'perfiles'.")
    abp_result: list[abpDefaultProfile] = []
    for abp_item in abp_data["perfiles"]:
        abp_sources = {
            str(abp_k): str(abp_v) for abp_k, abp_v in (abp_item.get("fuentes") or {}).items()
        }
        abp_missing = [abp_f for abp_f in abp__VALUE_FIELDS if abp_f not in abp_sources]
        if abp_missing:
            raise ValueError(
                f"Perfil «{abp_item.get('nombre')}»: falta la fuente de {abp_missing}."
            )
        abp_profile = abpPersonProfile(
            abp_name=str(abp_item["nombre"]),
            abp_max_speed_mps=float(abp_item["vel_max_mps"]),
            abp_reaction_mean_s=float(abp_item["reaccion_media_s"]),
            abp_reaction_std_s=float(abp_item["reaccion_desv_s"]),
            abp_radius_m=float(abp_item["radio_m"]),
        )
        abp_result.append(
            abpDefaultProfile(abp_profile, bool(abp_item.get("provisional", True)), abp_sources)
        )
    return abp_result


def abp_load_default_profiles() -> list[abpDefaultProfile]:
    abp_package, abp_name = abp_PROFILES_RESOURCE
    abp_text = resources.files(abp_package).joinpath(abp_name).read_text(encoding="utf-8")
    return abp_parse_default_profiles(abp_text)
