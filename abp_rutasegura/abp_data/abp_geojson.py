from __future__ import annotations

import json
from typing import Any

from abp_rutasegura.abp_domain.abp_geometry import abpPoint, abpPolygon, abpSegment

abpJsonDict = dict[str, Any]


def abp_point_to_geojson(abp_point: abpPoint) -> abpJsonDict:
    return {"type": "Point", "coordinates": [abp_point.abp_x, abp_point.abp_y]}


def abp_segment_to_geojson(abp_segment: abpSegment) -> abpJsonDict:
    return {
        "type": "LineString",
        "coordinates": [
            [abp_segment.abp_start.abp_x, abp_segment.abp_start.abp_y],
            [abp_segment.abp_end.abp_x, abp_segment.abp_end.abp_y],
        ],
    }


def abp_polygon_to_geojson(abp_polygon: abpPolygon) -> abpJsonDict:
    abp_ring = [[abp_p.abp_x, abp_p.abp_y] for abp_p in abp_polygon.abp_vertices]
    abp_ring.append(abp_ring[0])
    return {"type": "Polygon", "coordinates": [abp_ring]}


def abp__expect(abp_geometry: abpJsonDict, abp_kind: str) -> Any:
    if abp_geometry.get("type") != abp_kind:
        raise ValueError(
            f"Se esperaba una geometría {abp_kind}, se recibió {abp_geometry.get('type')}."
        )
    return abp_geometry["coordinates"]


def abp_point_from_geojson(abp_geometry: abpJsonDict) -> abpPoint:
    abp_x, abp_y = abp__expect(abp_geometry, "Point")
    return abpPoint(float(abp_x), float(abp_y))


def abp_segment_from_geojson(abp_geometry: abpJsonDict) -> abpSegment:
    abp_coords = abp__expect(abp_geometry, "LineString")
    if len(abp_coords) != 2:
        raise ValueError("Un segmento debe tener exactamente dos puntos.")
    (abp_x1, abp_y1), (abp_x2, abp_y2) = abp_coords
    return abpSegment(
        abpPoint(float(abp_x1), float(abp_y1)), abpPoint(float(abp_x2), float(abp_y2))
    )


def abp_polygon_from_geojson(abp_geometry: abpJsonDict) -> abpPolygon:
    abp_ring = abp__expect(abp_geometry, "Polygon")[0]
    if len(abp_ring) > 1 and abp_ring[0] == abp_ring[-1]:
        abp_ring = abp_ring[:-1]
    return abpPolygon(tuple(abpPoint(float(abp_x), float(abp_y)) for abp_x, abp_y in abp_ring))


def abp_feature_dumps(abp_geometry: abpJsonDict, abp_properties: abpJsonDict | None = None) -> str:
    abp_feature = {"type": "Feature", "geometry": abp_geometry, "properties": abp_properties or {}}
    return json.dumps(abp_feature, ensure_ascii=False, separators=(",", ":"))


def abp_feature_loads(abp_text: str) -> tuple[abpJsonDict, abpJsonDict]:
    abp_feature = json.loads(abp_text)
    if abp_feature.get("type") != "Feature":
        raise ValueError("Se esperaba un GeoJSON Feature.")
    return abp_feature["geometry"], abp_feature.get("properties") or {}


def abp_geometry_dumps(abp_geometry: abpJsonDict) -> str:
    return json.dumps(abp_geometry, separators=(",", ":"))


def abp_geometry_loads(abp_text: str) -> abpJsonDict:
    abp_data: abpJsonDict = json.loads(abp_text)
    return abp_data
