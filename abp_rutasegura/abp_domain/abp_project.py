from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from abp_rutasegura.abp_domain.abp_enums import abpUseType


@dataclass(frozen=True, slots=True)
class abpProject:
    abp_name: str
    abp_use: abpUseType
    abp_address: str = ""
    abp_created_at: datetime | None = None
    abp_district: str = ""
    abp_province: str = ""
    abp_department: str = ""
    abp_responsible: str = ""
    abp_responsible_role: str = ""
    abp_phone: str = ""
    abp_email: str = ""
    abp_schedule: str = ""
    abp_notes: str = ""
    abp_logo_path: str | None = None

    def __post_init__(self) -> None:
        if not self.abp_name.strip():
            raise ValueError("El proyecto necesita un nombre.")
        if self.abp_email and ("@" not in self.abp_email or " " in self.abp_email.strip()):
            raise ValueError("El correo electrónico no es válido.")

    @property
    def abp_location(self) -> str:
        return ", ".join(
            abp_p for abp_p in (self.abp_district, self.abp_province, self.abp_department) if abp_p
        )

    @property
    def abp_full_address(self) -> str:
        return " · ".join(abp_p for abp_p in (self.abp_address, self.abp_location) if abp_p)
