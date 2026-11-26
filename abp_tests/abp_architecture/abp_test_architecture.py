from __future__ import annotations

from pathlib import Path

import pytest

import abp_rutasegura
from abp_tests.abp_architecture.abp_import_rules import abp_check_package, abp_check_source

abp_PACKAGE_DIR = Path(abp_rutasegura.__file__).parent


def abp_test_package_respects_architecture_rules() -> None:
    abp_violations, abp_checked = abp_check_package(abp_PACKAGE_DIR)
    assert abp_checked >= 15, "No se encontraron los módulos del paquete; ¿cambió la ruta?"
    assert not abp_violations, "Violaciones de arquitectura:\n" + "\n".join(
        map(str, abp_violations)
    )


@pytest.mark.parametrize(
    ("abp_module", "abp_source"),
    [
        (
            "abp_rutasegura.abp_presentation.abp_window",
            "from abp_rutasegura.abp_engines import abp_vision",
        ),
        (
            "abp_rutasegura.abp_presentation.abp_window",
            "import abp_rutasegura.abp_data.abp_repositories",
        ),
        ("abp_rutasegura.abp_presentation.abp_window", "from ..abp_data import abp_repositories"),
        ("abp_rutasegura.abp_presentation.abp_window", "from abp_rutasegura import abp_engines"),
        (
            "abp_rutasegura.abp_application.abp_service",
            "from abp_rutasegura.abp_presentation import window",
        ),
        (
            "abp_rutasegura.abp_engines.abp_vision.abp_walls",
            "from abp_rutasegura.abp_data import abp_models",
        ),
        (
            "abp_rutasegura.abp_engines.abp_vision.abp_walls",
            "from ...abp_application import orchestrator",
        ),
        ("abp_rutasegura.abp_data.abp_repo", "from abp_rutasegura.abp_engines import norms"),
        ("abp_rutasegura.abp_domain.abp_plan", "from abp_rutasegura.abp_engines import simulation"),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "from PySide6.QtCore import QObject",
        ),
        ("abp_rutasegura.abp_engines.abp_simulation.abp_model", "import sqlalchemy"),
        ("abp_rutasegura.abp_domain.abp_plan", "import cv2"),
        ("abp_rutasegura.abp_application.abp_service", "from PySide6 import QtCore"),
        ("abp_rutasegura.abp_presentation.abp_window", "from sqlalchemy.orm import Session"),
        ("abp_rutasegura.abp_data.abp_repo", "import socket"),
        ("abp_rutasegura.abp_data.abp_repo", "from urllib import request"),
        ("abp_rutasegura.abp_data.abp_repo", "import requests"),
        (
            "abp_rutasegura.abp_presentation.abp_window",
            "from PySide6.QtNetwork import QNetworkAccessManager",
        ),
        ("abp_rutasegura.abp_engines.abp_simulation.abp_model", "import random"),
        ("abp_rutasegura.abp_engines.abp_simulation.abp_model", "from random import uniform"),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "import numpy as np\nnp.random.seed(1)",
        ),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "import numpy as np\nx = np.random.rand(3)",
        ),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "import numpy\nnumpy.random.normal()",
        ),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "from numpy import random as npr\nnpr.seed(3)",
        ),
        ("abp_rutasegura.abp_engines.abp_simulation.abp_model", "from numpy.random import seed"),
    ],
)
def abp_test_checker_detects_violation(abp_module: str, abp_source: str) -> None:
    assert abp_check_source(abp_source, abp_module), (
        f"No se detectó la violación en {abp_module}: {abp_source!r}"
    )


@pytest.mark.parametrize(
    ("abp_module", "abp_source"),
    [
        (
            "abp_rutasegura.abp_presentation.abp_window",
            "from abp_rutasegura.abp_application import orchestrator",
        ),
        (
            "abp_rutasegura.abp_presentation.abp_window",
            "from abp_rutasegura.abp_domain import FloorPlan",
        ),
        (
            "abp_rutasegura.abp_presentation.abp_window",
            "from abp_rutasegura.abp_resources.abp_texts import TEXTS",
        ),
        ("abp_rutasegura.abp_presentation.abp_window", "from PySide6.QtWidgets import QMainWindow"),
        ("abp_rutasegura.abp_presentation.abp_window", "from . import widgets"),
        (
            "abp_rutasegura.abp_application.abp_service",
            "from abp_rutasegura.abp_engines import abp_vision\nimport abp_rutasegura.abp_data",
        ),
        ("abp_rutasegura.abp_engines.abp_vision.abp_walls", "import cv2\nimport numpy as np"),
        ("abp_rutasegura.abp_engines.abp_vision.abp_walls", "from ..abp_navigation import grid"),
        ("abp_rutasegura.abp_data.abp_repo", "from sqlalchemy.orm import Session"),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "import numpy as np\nrng = np.random.default_rng(7)",
        ),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "from numpy.random import Generator, default_rng",
        ),
        (
            "abp_rutasegura.abp_engines.abp_simulation.abp_model",
            "def f(rng):\n    return rng.random()",
        ),
        (
            "abp_rutasegura.__main__",
            "from abp_rutasegura.abp_data import repo\nfrom abp_rutasegura.abp_presentation import w",
        ),
    ],
)
def abp_test_checker_allows_valid_code(abp_module: str, abp_source: str) -> None:
    assert abp_check_source(abp_source, abp_module) == []
