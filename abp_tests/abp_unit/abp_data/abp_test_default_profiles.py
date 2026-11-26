from __future__ import annotations

import pytest

from abp_rutasegura.abp_data.abp_default_profiles import (
    abp_load_default_profiles,
    abp_parse_default_profiles,
)


def abp_test_packaged_catalog_has_the_three_spec_profiles() -> None:
    abp_defaults = abp_load_default_profiles()
    assert [abp_d.abp_profile.abp_name for abp_d in abp_defaults] == [
        "adulto",
        "niño",
        "movilidad reducida",
    ]


def abp_test_every_value_documents_its_source() -> None:
    for abp_default in abp_load_default_profiles():
        assert set(abp_default.abp_sources) >= {
            "vel_max_mps",
            "reaccion_media_s",
            "reaccion_desv_s",
            "radio_m",
        }
        assert all(abp_text.strip() for abp_text in abp_default.abp_sources.values())


def abp_test_values_are_marked_provisional_until_verified() -> None:
    assert all(abp_d.abp_provisional for abp_d in abp_load_default_profiles())


def abp_test_reduced_mobility_is_slowest() -> None:
    abp_speeds = {
        abp_d.abp_profile.abp_name: abp_d.abp_profile.abp_max_speed_mps
        for abp_d in abp_load_default_profiles()
    }
    assert abp_speeds["movilidad reducida"] < abp_speeds["niño"] <= abp_speeds["adulto"]


def abp_test_missing_source_is_rejected() -> None:
    abp_text = """
perfiles:
  - nombre: x
    vel_max_mps: 1
    reaccion_media_s: 1
    reaccion_desv_s: 1
    radio_m: 0.2
    fuentes:
      vel_max_mps: algo
"""
    with pytest.raises(ValueError, match="falta la fuente"):
        abp_parse_default_profiles(abp_text)


def abp_test_malformed_file_is_rejected() -> None:
    with pytest.raises(ValueError, match="perfiles"):
        abp_parse_default_profiles("otra_cosa: 1")
