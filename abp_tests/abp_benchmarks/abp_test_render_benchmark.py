from __future__ import annotations

import time

import numpy as np
import pytest
from PySide6.QtGui import QImage, QPainter
from pytestqt.qtbot import QtBot

from abp_rutasegura.abp_domain.abp_people import abpOccupancy
from abp_rutasegura.abp_presentation.abp_simulation_viewer import abpSimulationViewer
from abp_tests.abp_fixtures.abp_simple_plans import abp_SCALE, abp_single_room
from abp_tests.abp_unit.abp_engines.abp_simulation.abp_helpers import abp_make_simulation

abp_FRAMES = 30
abp_MIN_FPS = 10.0


@pytest.mark.benchmark
def abp_test_viewer_render_speed(qtbot: QtBot) -> None:
    abp_plan = abp_single_room(
        abp_width=30.0, abp_height=20.0, abp_exit_width=1.8, abp_second_exit=True
    )
    abp_sim = abp_make_simulation(abp_plan, [abpOccupancy("Aula 1", "adulto", 500)], abp_seed=3)
    abp_sim.abp_agents.abp_reaction_time[:] = 0.0
    for _ in range(20):
        abp_sim.abp_step()
    abp_out = abp_sim.abp_output()
    abp_viewer = abpSimulationViewer()
    qtbot.addWidget(abp_viewer)
    abp_viewer.resize(1000, 700)
    abp_viewer.abp_set_plan(abp_plan, np.full((1100, 1600, 3), 255, np.uint8))
    abp_viewer.abp_set_run(abp_out.abp_trajectories, abp_out.abp_result, abp_SCALE)
    abp_target = QImage(1000, 700, QImage.Format.Format_ARGB32)
    abp_start = time.perf_counter()
    for abp_k in range(abp_FRAMES):
        abp_viewer.abp_set_time(abp_out.abp_trajectories.abp_times_s[-1] * abp_k / abp_FRAMES)
        abp_painter = QPainter(abp_target)
        abp_viewer.abp_scene.render(abp_painter)
        abp_painter.end()
    abp_fps = abp_FRAMES / (time.perf_counter() - abp_start)
    print(f"\nrender con 500 agentes: {abp_fps:.1f} cuadros/s")
    assert abp_fps >= abp_MIN_FPS
