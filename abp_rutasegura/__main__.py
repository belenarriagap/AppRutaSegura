from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import abp_rutasegura


def abp__parse(abp_argv: Sequence[str]) -> argparse.Namespace:
    abp_parser = argparse.ArgumentParser(prog="rutasegura", add_help=True)
    abp_parser.add_argument("--version", action="store_true")
    abp_parser.add_argument("--self-test", action="store_true")
    abp_parser.add_argument("--log", type=Path)
    abp_args, abp__qt_args = abp_parser.parse_known_args(abp_argv)
    return abp_args


def abp__logger(abp_path: Path | None) -> Callable[[str], None]:
    abp_lines: list[str] = []

    def abp_log(abp_text: str) -> None:
        abp_lines.append(abp_text)
        if sys.stdout is not None:
            print(abp_text, flush=True)
        if abp_path is not None:
            abp_path.write_text("\n".join(abp_lines) + "\n", encoding="utf-8")

    return abp_log


def abp_main(abp_argv: Sequence[str] | None = None) -> int:
    abp_args = abp__parse(sys.argv[1:] if abp_argv is None else abp_argv)
    if abp_args.version:
        abp__logger(abp_args.log)(f"RutaSegura {abp_rutasegura.__version__}")
        return 0
    if abp_args.self_test:
        from abp_rutasegura.abp_application.abp_self_test import abp_run_self_test

        return 0 if abp_run_self_test(abp__logger(abp_args.log)) else 1

    from PySide6.QtWidgets import QApplication

    from abp_rutasegura.abp_application.abp_services import abpAppServices
    from abp_rutasegura.abp_presentation.abp_main_window import abpMainWindow
    from abp_rutasegura.abp_presentation.abp_theme import abp_apply_theme
    from abp_rutasegura.abp_resources.abp_texts import abp_TEXTS

    abp_existing = QApplication.instance()
    abp_app = abp_existing if isinstance(abp_existing, QApplication) else QApplication(sys.argv)
    abp_app.setApplicationName(abp_TEXTS.abp_app_name)
    abp_apply_theme(abp_app)
    abp_services = abpAppServices.abp_open()
    try:
        abp_window = abpMainWindow(abp_services, abp_TEXTS)
        abp_window.show()
        return abp_app.exec()
    finally:
        abp_services.abp_close()


if __name__ == "__main__":
    sys.exit(abp_main())
