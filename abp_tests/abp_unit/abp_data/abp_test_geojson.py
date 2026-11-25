from __future__ import annotations

import pytest

from abp_rutasegura.abp_data.abp_geojson import (
    abp_feature_dumps,
    abp_feature_loads,
    abp_point_from_geojson,
    abp_point_to_geojson,
    abp_polygon_from_geojson,
    abp_polygon_to_geojson,
    abp_segment_from_geojson,
    abp_segment_to_geojson,
)
from abp_rutasegura.abp_domain import abpPoint, abpPolygon, abpSegment


def abp_test_point_round_trip() -> None:
    abp_point = abpPoint(1.5, -2.25)
    assert abp_point_from_geojson(abp_point_to_geojson(abp_point)) == abp_point


def abp_test_segment_round_trip() -> None:
    abp_segment = abpSegment(abpPoint(0, 0), abpPoint(10.5, 3))
    assert abp_segment_from_geojson(abp_segment_to_geojson(abp_segment)) == abp_segment


def abp_test_polygon_ring_is_closed_and_round_trips() -> None:
    abp_polygon = abpPolygon((abpPoint(0, 0), abpPoint(4, 0), abpPoint(4, 3)))
    abp_geometry = abp_polygon_to_geojson(abp_polygon)
    abp_ring = abp_geometry["coordinates"][0]
    assert abp_ring[0] == abp_ring[-1]
    assert len(abp_ring) == 4
    assert abp_polygon_from_geojson(abp_geometry) == abp_polygon


def abp_test_feature_keeps_properties_and_unicode() -> None:
    abp_text = abp_feature_dumps(abp_point_to_geojson(abpPoint(0, 0)), {"nombre": "Salida Ñ"})
    assert "Salida Ñ" in abp_text
    abp_geometry, abp_props = abp_feature_loads(abp_text)
    assert abp_props == {"nombre": "Salida Ñ"}
    assert abp_geometry["type"] == "Point"


def abp_test_wrong_geometry_type_is_rejected() -> None:
    with pytest.raises(ValueError, match="LineString"):
        abp_segment_from_geojson(abp_point_to_geojson(abpPoint(0, 0)))
    with pytest.raises(ValueError, match="dos puntos"):
        abp_segment_from_geojson({"type": "LineString", "coordinates": [[0, 0], [1, 1], [2, 2]]})
    with pytest.raises(ValueError, match="Feature"):
        abp_feature_loads('{"type": "Point", "coordinates": [0, 0]}')
