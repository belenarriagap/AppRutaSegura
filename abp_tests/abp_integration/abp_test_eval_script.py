from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from abp_rutasegura.abp_engines.abp_vision.abp_images import abp_write_png
from abp_tests.abp_fixtures.abp_synthetic_plans import abp_generate_plan

abp_SCRIPT = Path(__file__).resolve().parents[2] / "abp_scripts" / "abp_eval_vision.py"


def abp__load_script() -> ModuleType:
    abp_spec = importlib.util.spec_from_file_location("eval_vision", abp_SCRIPT)
    assert abp_spec is not None
    assert abp_spec.loader is not None
    abp_module = importlib.util.module_from_spec(abp_spec)
    sys.modules[abp_spec.name] = abp_module
    abp_spec.loader.exec_module(abp_module)
    return abp_module


def abp_test_synthetic_evaluation_meets_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    abp_script = abp__load_script()
    assert abp_script.abp_main(["--synthetic", "2", "--overlays", str(tmp_path)]) == 0
    assert "CUMPLE" in capsys.readouterr().out
    assert len(list(tmp_path.glob("*.png"))) == 2


def abp_test_labeled_dataset_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    abp_plan = abp_generate_plan(5)
    abp_write_png(tmp_path / "local_a.png", abp_plan.abp_image)

    def abp_raw(abp_segments: tuple) -> list[list[float]]:
        return [
            [abp_s.abp_start.abp_x, abp_s.abp_start.abp_y, abp_s.abp_end.abp_x, abp_s.abp_end.abp_y]
            for abp_s in abp_segments
        ]

    abp_label = {
        "escala_m_por_px": abp_plan.abp_scale_m_per_px,
        "muros": abp_raw(abp_plan.abp_walls),
        "puertas": abp_raw(abp_plan.abp_doors),
        "salidas": abp_raw(abp_plan.abp_exits),
    }
    (tmp_path / "local_a.json").write_text(json.dumps(abp_label), encoding="utf-8")
    abp_script = abp__load_script()
    assert abp_script.abp_main(["--dataset", str(tmp_path)]) == 0
    assert "local_a" in capsys.readouterr().out
