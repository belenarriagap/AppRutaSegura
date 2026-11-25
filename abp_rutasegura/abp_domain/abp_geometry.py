from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class abpPoint:
    abp_x: float
    abp_y: float

    def abp_distance_to(self, abp_other: abpPoint) -> float:
        return math.hypot(self.abp_x - abp_other.abp_x, self.abp_y - abp_other.abp_y)


@dataclass(frozen=True, slots=True)
class abpSegment:
    abp_start: abpPoint
    abp_end: abpPoint

    @property
    def abp_length(self) -> float:
        return self.abp_start.abp_distance_to(self.abp_end)

    @property
    def abp_midpoint(self) -> abpPoint:
        return abpPoint(
            (self.abp_start.abp_x + self.abp_end.abp_x) / 2,
            (self.abp_start.abp_y + self.abp_end.abp_y) / 2,
        )


@dataclass(frozen=True, slots=True)
class abpPolygon:
    abp_vertices: tuple[abpPoint, ...]

    def __post_init__(self) -> None:
        if len(self.abp_vertices) < 3:
            raise ValueError("Un polígono necesita al menos 3 vértices.")

    @property
    def abp_area(self) -> float:
        abp_pts = self.abp_vertices
        abp_twice = sum(
            abp_pts[abp_i].abp_x * abp_pts[(abp_i + 1) % len(abp_pts)].abp_y
            - abp_pts[(abp_i + 1) % len(abp_pts)].abp_x * abp_pts[abp_i].abp_y
            for abp_i in range(len(abp_pts))
        )
        return abs(abp_twice) / 2

    @property
    def abp_centroid(self) -> abpPoint:
        abp_n = len(self.abp_vertices)
        return abpPoint(
            sum(abp_p.abp_x for abp_p in self.abp_vertices) / abp_n,
            sum(abp_p.abp_y for abp_p in self.abp_vertices) / abp_n,
        )
