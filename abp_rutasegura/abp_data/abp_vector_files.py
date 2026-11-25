from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np

from abp_rutasegura.abp_domain.abp_vector import abpVectorPlan, abpVectorText

abp_VERSION = 1


def abp_vector_path(abp_image_path: Path) -> Path:
    return abp_image_path.with_suffix(".trazos.npz")


def abp_save_vector(abp_path: Path, abp_vector: abpVectorPlan) -> None:
    abp_meta = {
        "version": abp_VERSION,
        "width": abp_vector.abp_width,
        "height": abp_vector.abp_height,
        "dpi": abp_vector.abp_dpi,
        "layers": list(abp_vector.abp_layers),
        "scale": abp_vector.abp_scale_denominator,
        "exact": abp_vector.abp_exact_scale,
        "texts": [
            [
                abp_t.abp_text,
                abp_t.abp_x,
                abp_t.abp_y,
                abp_t.abp_width,
                abp_t.abp_size,
                abp_t.abp_angle_deg,
                abp_t.abp_font,
            ]
            for abp_t in abp_vector.abp_texts
        ],
    }
    abp_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        abp_path,
        meta=np.array(json.dumps(abp_meta, ensure_ascii=False)),
        segments=abp_vector.abp_segments,
        segment_layer=abp_vector.abp_segment_layer,
        filled=abp_vector.abp_filled,
        segment_width=abp_vector.abp_segment_width,
        arcs=abp_vector.abp_arcs,
        arc_layer=abp_vector.abp_arc_layer,
    )


def abp_load_vector(abp_path: Path) -> abpVectorPlan | None:
    if not abp_path.is_file():
        return None
    try:
        with np.load(abp_path, allow_pickle=False) as abp_data:
            abp_meta = json.loads(str(abp_data["meta"]))
            if abp_meta["version"] != abp_VERSION:
                return None
            return abpVectorPlan(
                abp_width=float(abp_meta["width"]),
                abp_height=float(abp_meta["height"]),
                abp_dpi=float(abp_meta["dpi"]),
                abp_layers=tuple(abp_meta["layers"]),
                abp_segments=abp_data["segments"],
                abp_segment_layer=abp_data["segment_layer"],
                abp_filled=abp_data["filled"],
                abp_segment_width=(
                    abp_data["segment_width"] if "segment_width" in abp_data.files else np.zeros(0)
                ),
                abp_arcs=abp_data["arcs"],
                abp_arc_layer=abp_data["arc_layer"],
                abp_texts=tuple(
                    abpVectorText(
                        str(abp_t[0]),
                        abp_t[1],
                        abp_t[2],
                        abp_t[3],
                        abp_t[4],
                        abp_t[5],
                        str(abp_t[6]),
                    )
                    for abp_t in abp_meta["texts"]
                ),
                abp_scale_denominator=abp_meta["scale"],
                abp_exact_scale=bool(abp_meta.get("exact", False)),
            )
    except (OSError, ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile):
        return None
