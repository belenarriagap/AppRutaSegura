from __future__ import annotations

import dataclasses
import math
from collections.abc import Collection
from dataclasses import dataclass, field, replace

import numpy as np
import numpy.typing as npt

abpFloatArray = npt.NDArray[np.float64]
abpIntArray = npt.NDArray[np.int64]
abpBoolArray = npt.NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class abpVectorText:
    abp_text: str
    abp_x: float
    abp_y: float
    abp_width: float
    abp_size: float
    abp_angle_deg: float
    abp_font: str = ""


@dataclass(frozen=True, slots=True)
class abpPlacedBlock:
    abp_name: str
    abp_x: float
    abp_y: float
    abp_width: float
    abp_height: float
    abp_angle_deg: float


@dataclass(frozen=True, eq=False, slots=True)
class abpVectorPlan:
    abp_width: float
    abp_height: float
    abp_dpi: float
    abp_layers: tuple[str, ...]
    abp_segments: abpFloatArray
    abp_segment_layer: abpIntArray
    abp_filled: abpBoolArray
    abp_arcs: abpFloatArray
    abp_arc_layer: abpIntArray
    abp_texts: tuple[abpVectorText, ...] = ()
    abp_segment_width: abpFloatArray = field(default_factory=lambda: np.zeros(0))
    abp_scale_denominator: float | None = None
    abp_exact_scale: bool = False

    def __post_init__(self) -> None:
        abp_n, abp_m = len(self.abp_segments), len(self.abp_arcs)
        if len(self.abp_segment_width) == 0 and abp_n:
            object.__setattr__(self, "abp_segment_width", np.zeros(abp_n))
        if len(self.abp_segment_width) != abp_n:
            raise ValueError("Trazos con dimensiones inconsistentes.")
        if self.abp_segments.shape != (abp_n, 4) or self.abp_arcs.shape != (abp_m, 5):
            raise ValueError("Trazos con dimensiones inconsistentes.")
        if (
            not len(self.abp_segment_layer) == len(self.abp_filled) == abp_n
            or len(self.abp_arc_layer) != abp_m
        ):
            raise ValueError("Trazos con dimensiones inconsistentes.")

    @property
    def abp_scale_m_per_px(self) -> float | None:
        if self.abp_scale_denominator is None:
            return None
        return 0.0254 / self.abp_dpi * self.abp_scale_denominator

    def abp_rotated(self, abp_turns: int) -> abpVectorPlan:
        abp_out = self
        for _ in range(abp_turns % 4):
            abp_h = abp_out.abp_height
            abp_s, abp_a = abp_out.abp_segments, abp_out.abp_arcs
            abp_out = replace(
                abp_out,
                abp_width=abp_h,
                abp_height=abp_out.abp_width,
                abp_segments=np.c_[
                    abp_h - abp_s[:, 1], abp_s[:, 0], abp_h - abp_s[:, 3], abp_s[:, 2]
                ].reshape(-1, 4),
                abp_arcs=np.c_[
                    abp_h - abp_a[:, 1],
                    abp_a[:, 0],
                    abp_a[:, 2],
                    abp_a[:, 3] + math.pi / 2,
                    abp_a[:, 4],
                ].reshape(-1, 5),
                abp_texts=tuple(
                    replace(
                        abp_t,
                        abp_x=abp_h - abp_t.abp_y,
                        abp_y=abp_t.abp_x,
                        abp_angle_deg=(abp_t.abp_angle_deg + 90.0 + 180.0) % 360.0 - 180.0,
                    )
                    for abp_t in abp_out.abp_texts
                ),
            )
        return abp_out

    def abp_without_layers(self, abp_names: Collection[str]) -> abpVectorPlan:
        abp_hidden = [
            abp_i for abp_i, abp_name in enumerate(self.abp_layers) if abp_name in abp_names
        ]
        abp_keep = ~np.isin(self.abp_segment_layer, abp_hidden)
        abp_arcs = ~np.isin(self.abp_arc_layer, abp_hidden)
        return dataclasses.replace(
            self,
            abp_segments=self.abp_segments[abp_keep],
            abp_segment_layer=self.abp_segment_layer[abp_keep],
            abp_filled=self.abp_filled[abp_keep],
            abp_segment_width=self.abp_segment_width[abp_keep],
            abp_arcs=self.abp_arcs[abp_arcs],
            abp_arc_layer=self.abp_arc_layer[abp_arcs],
        )

    def abp_cropped(
        self, abp_x0: float, abp_y0: float, abp_x1: float, abp_y1: float
    ) -> abpVectorPlan:
        abp_s = self.abp_segments
        abp_inside = (
            (np.minimum(abp_s[:, 0], abp_s[:, 2]) <= abp_x1)
            & (np.maximum(abp_s[:, 0], abp_s[:, 2]) >= abp_x0)
            & (np.minimum(abp_s[:, 1], abp_s[:, 3]) <= abp_y1)
            & (np.maximum(abp_s[:, 1], abp_s[:, 3]) >= abp_y0)
        )
        abp_a = self.abp_arcs
        abp_arcs_in = (
            (abp_a[:, 0] >= abp_x0)
            & (abp_a[:, 0] <= abp_x1)
            & (abp_a[:, 1] >= abp_y0)
            & (abp_a[:, 1] <= abp_y1)
        )
        abp_arcs_in |= abp_a[:, 2] > min(abp_x1 - abp_x0, abp_y1 - abp_y0) / 2
        return dataclasses.replace(
            self,
            abp_width=abp_x1 - abp_x0,
            abp_height=abp_y1 - abp_y0,
            abp_segments=abp_s[abp_inside] - np.array([abp_x0, abp_y0, abp_x0, abp_y0]),
            abp_segment_layer=self.abp_segment_layer[abp_inside],
            abp_filled=self.abp_filled[abp_inside],
            abp_segment_width=self.abp_segment_width[abp_inside],
            abp_arcs=abp_a[abp_arcs_in] - np.array([abp_x0, abp_y0, 0.0, 0.0, 0.0]),
            abp_arc_layer=self.abp_arc_layer[abp_arcs_in],
            abp_texts=tuple(
                dataclasses.replace(abp_t, abp_x=abp_t.abp_x - abp_x0, abp_y=abp_t.abp_y - abp_y0)
                for abp_t in self.abp_texts
                if abp_x0 <= abp_t.abp_x <= abp_x1 and abp_y0 <= abp_t.abp_y <= abp_y1
            ),
        )


@dataclass(frozen=True, slots=True)
class abpPdfPage:
    abp_number: int
    abp_width_mm: float
    abp_height_mm: float
    abp_is_vector: bool
    abp_title: str = ""
    abp_level: int | None = None
    abp_scale_denominator: float | None = None
    abp_layers: tuple[str, ...] = ()
    abp_kind: str = ""
