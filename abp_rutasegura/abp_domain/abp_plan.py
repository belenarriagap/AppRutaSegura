from __future__ import annotations

from dataclasses import dataclass, field

from abp_rutasegura.abp_domain.abp_enums import abpSignKind, abpStairUse, abpUseType
from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment


def abp__check_confidence(abp_value: float) -> None:
    if not 0.0 <= abp_value <= 1.0:
        raise ValueError(f"La confianza debe estar entre 0 y 1 (se recibió {abp_value}).")


@dataclass(frozen=True, slots=True)
class abpWall:
    abp_segment: abpSegment
    abp_confidence: float = 1.0

    def __post_init__(self) -> None:
        abp__check_confidence(self.abp_confidence)


@dataclass(frozen=True, slots=True)
class abpDoor:
    abp_segment: abpSegment
    abp_confidence: float = 1.0

    def __post_init__(self) -> None:
        abp__check_confidence(self.abp_confidence)


@dataclass(frozen=True, slots=True)
class abpExit:
    abp_segment: abpSegment
    abp_name: str = ""
    abp_confirmed: bool = True


@dataclass(frozen=True, slots=True)
class abpStair:
    abp_area: abpPolygon
    abp_connects_to_level: int | None = None
    abp_confirmed: bool = True
    abp_name: str = ""
    abp_use: abpStairUse = abpStairUse.abp_AUTO
    abp_entry: abpPoint | None = None
    abp_leads_to: str = ""


@dataclass(frozen=True, slots=True)
class abpObstacle:
    abp_area: abpPolygon
    abp_confirmed: bool = True
    abp_name: str = ""


@dataclass(frozen=True, slots=True)
class abpSafeZone:
    abp_area: abpPolygon
    abp_name: str = ""


@dataclass(frozen=True, slots=True)
class abpSign:
    abp_kind: abpSignKind
    abp_position: abpPoint
    abp_rotation_deg: float = 0.0
    abp_text: str = ""


@dataclass(frozen=True, slots=True)
class abpRoom:
    abp_name: str
    abp_use: abpUseType
    abp_area: abpPolygon
    abp_category: str = ""
    abp_exit_name: str = ""


@dataclass(frozen=True, slots=True)
class abpFloorPlan:
    abp_level: int = 0
    abp_image_path: str | None = None
    abp_scale_m_per_px: float | None = None
    abp_walls: tuple[abpWall, ...] = field(default_factory=tuple)
    abp_doors: tuple[abpDoor, ...] = field(default_factory=tuple)
    abp_exits: tuple[abpExit, ...] = field(default_factory=tuple)
    abp_stairs: tuple[abpStair, ...] = field(default_factory=tuple)
    abp_obstacles: tuple[abpObstacle, ...] = field(default_factory=tuple)
    abp_safe_zones: tuple[abpSafeZone, ...] = field(default_factory=tuple)
    abp_rooms: tuple[abpRoom, ...] = field(default_factory=tuple)
    abp_signs: tuple[abpSign, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.abp_scale_m_per_px is not None and self.abp_scale_m_per_px <= 0:
            raise ValueError("La escala debe ser positiva.")

    @property
    def abp_has_pending_proposals(self) -> bool:
        abp_groups = (self.abp_exits, self.abp_stairs, self.abp_obstacles)
        return any(not abp_x.abp_confirmed for abp_group in abp_groups for abp_x in abp_group)

    @property
    def abp_is_scaled(self) -> bool:
        return self.abp_scale_m_per_px is not None

    def abp_to_meters(self, abp_length_px: float) -> float:
        if self.abp_scale_m_per_px is None:
            raise ValueError("Primero define la escala del plano.")
        return abp_length_px * self.abp_scale_m_per_px

    def abp_area_m2(self, abp_polygon: abpPolygon) -> float:
        if self.abp_scale_m_per_px is None:
            raise ValueError("Primero define la escala del plano.")
        return abp_polygon.abp_area * self.abp_scale_m_per_px**2
