from __future__ import annotations

from pathlib import Path

import pytest

import abp_rutasegura
from abp_rutasegura.__main__ import abp_main
from abp_rutasegura.abp_application import abp_self_test


def abp_test_version(tmp_path: Path) -> None:
    abp_log = tmp_path / "version.txt"
    assert abp_main(["--version", "--log", str(abp_log)]) == 0
    assert abp_log.read_text(encoding="utf-8").strip() == f"RutaSegura {abp_rutasegura.__version__}"


def abp_test_self_test_passes(tmp_path: Path) -> None:
    abp_log = tmp_path / "autoprueba.txt"
    assert abp_main(["--self-test", "--log", str(abp_log)]) == 0
    abp_text = abp_log.read_text(encoding="utf-8")
    assert abp_text.count("OK     ") == 7
    assert "Autoprueba superada." in abp_text


def abp_test_self_test_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def abp_broken() -> object:
        raise RuntimeError("faltan las reglas")

    monkeypatch.setattr(abp_self_test, "abp_load_packaged_rules", abp_broken)
    abp_lines: list[str] = []
    assert not abp_self_test.abp_run_self_test(abp_lines.append)
    assert any(abp_line.startswith("FALLA  Reglas normativas") for abp_line in abp_lines)
    assert abp_lines[-1] == "La autoprueba encontró errores."
