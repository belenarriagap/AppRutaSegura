from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from abp_rutasegura.abp_domain.abp_enums import abpAgentStatus

abpFloatArray = npt.NDArray[np.float64]
abpIntArray = npt.NDArray[np.int32]
abpStatusArray = npt.NDArray[np.int8]


@dataclass(eq=False, slots=True)
class abpAgentArrays:
    abp_position: abpFloatArray
    abp_velocity: abpFloatArray
    abp_max_speed: abpFloatArray
    abp_radius: abpFloatArray
    abp_reaction_time: abpFloatArray
    abp_profile_index: abpIntArray
    abp_status: abpStatusArray

    def __post_init__(self) -> None:
        abp_n = len(self)
        if self.abp_position.shape != (abp_n, 2) or self.abp_velocity.shape != (abp_n, 2):
            raise ValueError("position y velocity deben tener forma (n, 2).")
        for abp_name in (
            "abp_max_speed",
            "abp_radius",
            "abp_reaction_time",
            "abp_profile_index",
            "abp_status",
        ):
            if getattr(self, abp_name).shape != (abp_n,):
                raise ValueError(f"{abp_name} debe tener forma ({abp_n},).")

    def __len__(self) -> int:
        return int(self.abp_position.shape[0])

    @classmethod
    def abp_empty(cls, abp_n: int) -> abpAgentArrays:
        return cls(
            abp_position=np.zeros((abp_n, 2), dtype=np.float64),
            abp_velocity=np.zeros((abp_n, 2), dtype=np.float64),
            abp_max_speed=np.zeros(abp_n, dtype=np.float64),
            abp_radius=np.zeros(abp_n, dtype=np.float64),
            abp_reaction_time=np.zeros(abp_n, dtype=np.float64),
            abp_profile_index=np.zeros(abp_n, dtype=np.int32),
            abp_status=np.full(abp_n, abpAgentStatus.abp_WAITING, dtype=np.int8),
        )

    @property
    def abp_evacuated_count(self) -> int:
        return int(np.count_nonzero(self.abp_status == abpAgentStatus.abp_EVACUATED))
