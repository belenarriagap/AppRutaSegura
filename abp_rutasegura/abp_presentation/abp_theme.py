from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

abp_BACKGROUND = "#ececec"
abp_SURFACE = "#ffffff"
abp_BORDER = "#a0a0a0"
abp_TEXT = "#000000"
abp_MUTED = "#555555"
abp_PRIMARY = "#333333"
abp_PRIMARY_SOFT = "#d6d6d6"
abp_SIDEBAR = "#dadada"
abp_SIDEBAR_MUTED = "#555555"
abp_SIDEBAR_DISABLED = "#9a9a9a"
abp_DISABLED = "#9a9a9a"
abp_SUCCESS = "#333333"
abp_WARNING = "#333333"
abp_ERROR = "#000000"
abp_INFO = "#333333"

abp_KIND_BORDERS: dict[str, str] = {
    "success": "#8a8a8a",
    "warning": "#555555",
    "error": "#000000",
    "info": "#8a8a8a",
}

abp_BASE_POINT_SIZE = 9


def abp__kind_rules() -> str:
    return "".join(
        f'QFrame#banner[kind="{abp_kind}"] {{ border: 1px solid {abp_color}; }}\n'
        for abp_kind, abp_color in abp_KIND_BORDERS.items()
    )


abp_STYLESHEET = f"""
QMainWindow, QDialog {{ background: {abp_BACKGROUND}; }}

QLabel#pageTitle {{ font-size: {abp_BASE_POINT_SIZE + 3}pt; font-weight: bold; }}
QLabel#pageHelp, QLabel#muted, QLabel#navStep, QLabel#cardTitle, QLabel#cardNote {{
    color: {abp_MUTED};
}}
QLabel#sectionTitle {{ font-weight: bold; }}

QPushButton {{ padding: 3px 10px; min-height: 18px; }}
QPushButton[primary="true"] {{ font-weight: bold; }}
QPushButton#bannerClose {{ padding: 0 4px; min-height: 0; }}

QGroupBox {{ font-weight: bold; }}
QGroupBox QCheckBox {{ font-weight: normal; }}
QHeaderView::section {{
    background: {abp_BACKGROUND}; border: none; border-right: 1px solid #c8c8c8;
    border-bottom: 1px solid {abp_BORDER}; padding: 3px 4px;
}}
QToolBar {{ border: none; border-bottom: 1px solid #c8c8c8; spacing: 1px; }}
QToolBar QToolButton:checked {{ background: #cfcfcf; border: 1px solid #7a7a7a; }}
QGraphicsView {{ border: 1px solid {abp_BORDER}; }}

QWidget#sidebar {{ background: {abp_SIDEBAR}; border-right: 1px solid {abp_BORDER}; }}
QLabel#sidebarTitle {{ font-size: {abp_BASE_POINT_SIZE + 3}pt; font-weight: bold; }}
QLabel#sidebarSubtitle {{ color: {abp_MUTED}; }}
QListWidget#wizardSteps {{ background: transparent; border: none; outline: none; }}
QListWidget#wizardSteps::item {{ padding: 5px 4px; }}
QListWidget#wizardSteps::item:selected {{ background: #bdbdbd; color: {abp_TEXT}; }}
QListWidget#wizardSteps::item:disabled {{ color: {abp_DISABLED}; }}

QWidget#floorBar {{ border-bottom: 1px solid #c8c8c8; }}
QWidget#navBar {{ border-top: 1px solid #c8c8c8; }}

QFrame#banner {{ background: #f5f5f5; }}
QFrame#banner QLabel {{ background: transparent; border: none; }}
QLabel#bannerIcon {{ font-weight: bold; }}
QFrame#banner[kind="error"] QLabel {{ font-weight: bold; }}

QFrame#card {{ background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; }}
QFrame#card QLabel {{ border: none; background: transparent; }}
QLabel#cardValue {{ font-size: {abp_BASE_POINT_SIZE + 6}pt; font-weight: bold; }}
QFrame#card[kind="error"] {{ border: 2px solid #000000; }}

QFrame#welcomeCard {{ background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; }}
QFrame#welcomeCard QLabel {{ background: transparent; }}
QLabel#welcomeTitle {{ font-size: {abp_BASE_POINT_SIZE + 4}pt; font-weight: bold; }}
QFrame#legend QLabel {{ font-weight: normal; }}
{abp__kind_rules()}
"""


def abp__palette() -> QPalette:
    abp_palette = QPalette()
    abp_roles = {
        QPalette.ColorRole.Window: abp_BACKGROUND,
        QPalette.ColorRole.WindowText: abp_TEXT,
        QPalette.ColorRole.Base: abp_SURFACE,
        QPalette.ColorRole.AlternateBase: "#f4f4f4",
        QPalette.ColorRole.Text: abp_TEXT,
        QPalette.ColorRole.Button: "#e1e1e1",
        QPalette.ColorRole.ButtonText: abp_TEXT,
        QPalette.ColorRole.Highlight: abp_PRIMARY,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#ffffe8",
        QPalette.ColorRole.ToolTipText: abp_TEXT,
        QPalette.ColorRole.PlaceholderText: "#808080",
        QPalette.ColorRole.Link: abp_TEXT,
        QPalette.ColorRole.Light: "#ffffff",
        QPalette.ColorRole.Midlight: "#d0d0d0",
        QPalette.ColorRole.Mid: "#a0a0a0",
        QPalette.ColorRole.Dark: "#808080",
        QPalette.ColorRole.Shadow: "#505050",
    }
    for abp_role, abp_color in abp_roles.items():
        abp_palette.setColor(abp_role, QColor(abp_color))
    for abp_role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        abp_palette.setColor(QPalette.ColorGroup.Disabled, abp_role, QColor(abp_DISABLED))
    return abp_palette


def abp_apply_theme(abp_app: QApplication) -> None:
    abp_app.setStyle("Fusion")
    abp_app.setPalette(abp__palette())
    abp_font = QFont(abp_app.font())
    abp_font.setPointSize(abp_BASE_POINT_SIZE)
    abp_app.setFont(abp_font)
    abp_app.setStyleSheet(abp_STYLESHEET)


def abp_set_primary(abp_button: QPushButton, abp_primary: bool = True) -> QPushButton:
    abp_button.setProperty("primary", abp_primary)
    abp_repolish(abp_button)
    return abp_button


def abp_repolish(abp_widget: QWidget) -> None:
    abp_style = abp_widget.style()
    abp_style.unpolish(abp_widget)
    abp_style.polish(abp_widget)
    abp_widget.update()
