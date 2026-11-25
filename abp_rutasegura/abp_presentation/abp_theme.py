from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

abp_BACKGROUND = "#f3f6f8"
abp_SURFACE = "#ffffff"
abp_BORDER = "#d5dee4"
abp_TEXT = "#16232b"
abp_MUTED = "#5a6b75"
abp_PRIMARY = "#0e7490"
abp_PRIMARY_HOVER = "#0b5f76"
abp_PRIMARY_SOFT = "#e0f2f7"
abp_PRIMARY_PRESSED = "#c7e6ef"
abp_PRIMARY_DISABLED = "#8fc0cf"
abp_SIDEBAR = "#0d3346"
abp_SIDEBAR_HOVER = "#164a63"
abp_SIDEBAR_MUTED = "#8fb2c2"
abp_SIDEBAR_DISABLED = "#5d8396"
abp_SIDEBAR_TEXT = "#d7e8ef"
abp_SUCCESS = "#2e7d32"
abp_SUCCESS_SOFT = "#e7f4e8"
abp_WARNING = "#a85d00"
abp_WARNING_SOFT = "#fff3df"
abp_ERROR = "#c62828"
abp_ERROR_SOFT = "#fdeceb"
abp_INFO = abp_PRIMARY
abp_INFO_SOFT = abp_PRIMARY_SOFT

abp_KIND_COLORS: dict[str, tuple[str, str]] = {
    "success": (abp_SUCCESS, abp_SUCCESS_SOFT),
    "warning": (abp_WARNING, abp_WARNING_SOFT),
    "error": (abp_ERROR, abp_ERROR_SOFT),
    "info": (abp_INFO, abp_INFO_SOFT),
}

abp_BASE_POINT_SIZE = 10


def abp__kind_rules() -> str:
    abp_rules = []
    for abp_kind, (abp_strong, abp_soft) in abp_KIND_COLORS.items():
        abp_rules.append(
            f'QFrame#banner[kind="{abp_kind}"] {{ background: {abp_soft}; border: 1px solid {abp_strong};'
            f" border-left: 5px solid {abp_strong}; border-radius: 6px; }}\n"
            f'QFrame#banner[kind="{abp_kind}"] QLabel#bannerIcon {{ color: {abp_strong}; }}\n'
            f'QFrame#card[kind="{abp_kind}"] {{ border-top: 4px solid {abp_strong}; }}\n'
            f'QFrame#card[kind="{abp_kind}"] QLabel#cardValue {{ color: {abp_strong}; }}\n'
        )
    return "".join(abp_rules)


abp_STYLESHEET = f"""
QWidget {{ color: {abp_TEXT}; }}
QMainWindow, QDialog {{ background: {abp_BACKGROUND}; }}
QToolTip {{ background: {abp_TEXT}; color: white; border: none; padding: 6px; }}

QLabel#pageTitle {{ font-size: {abp_BASE_POINT_SIZE + 7}pt; font-weight: 600; color: {abp_TEXT}; }}
QLabel#pageHelp {{ color: {abp_MUTED}; }}
QLabel#muted {{ color: {abp_MUTED}; }}
QLabel#sectionTitle {{ font-size: {abp_BASE_POINT_SIZE + 2}pt; font-weight: 600; }}

QPushButton {{
    background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 6px;
    padding: 6px 14px; min-height: 22px;
}}
QPushButton:hover {{ background: {abp_PRIMARY_SOFT}; border-color: {abp_PRIMARY}; }}
QPushButton:pressed {{ background: {abp_PRIMARY_PRESSED}; }}
QPushButton:checked {{ background: {abp_PRIMARY_SOFT}; border-color: {abp_PRIMARY}; color: {abp_PRIMARY}; }}
QPushButton:disabled {{ color: #a3acb8; background: #eef1f5; border-color: #e1e5ea; }}
QPushButton[primary="true"] {{
    background: {abp_PRIMARY}; color: white; border: 1px solid {abp_PRIMARY}; font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: {abp_PRIMARY_HOVER}; }}
QPushButton[primary="true"]:disabled {{
    background: {abp_PRIMARY_DISABLED}; border-color: {abp_PRIMARY_DISABLED};
}}
QPushButton[flat="true"] {{ background: transparent; border: none; padding: 2px 6px; }}
QPushButton#bannerClose {{ background: transparent; border: none; padding: 0 6px;
    font-size: {abp_BASE_POINT_SIZE + 3}pt; color: {abp_MUTED}; }}
QPushButton#bannerClose:hover {{ color: {abp_TEXT}; }}

QLineEdit {{
    background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 5px; padding: 4px 6px;
    min-height: 22px;
}}
QLineEdit:focus {{ border-color: {abp_PRIMARY}; }}
QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit {{ min-height: 24px; }}
QGroupBox {{
    background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 8px;
    margin-top: 14px; padding: 10px 8px 8px 8px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QGroupBox QCheckBox {{ font-weight: normal; }}

QTableWidget, QTableView, QListWidget, QTreeWidget {{
    background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 6px;
    alternate-background-color: #f8fafc; gridline-color: #e8ecf1;
    selection-background-color: {abp_PRIMARY_SOFT}; selection-color: {abp_TEXT};
}}
QHeaderView::section {{
    background: #eef2f7; border: none; border-bottom: 1px solid {abp_BORDER};
    padding: 6px; font-weight: 600;
}}
QProgressBar {{
    background: #e6ebf1; border: none; border-radius: 6px; text-align: center; min-height: 14px;
}}
QProgressBar::chunk {{ background: {abp_PRIMARY}; border-radius: 6px; }}
QToolBar {{
    background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 8px; padding: 3px;
    spacing: 2px;
}}
QToolBar QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 4px 5px; }}
QToolBar QToolButton:hover {{ background: {abp_PRIMARY_SOFT}; }}
QToolBar QToolButton:checked {{
    background: {abp_PRIMARY_SOFT}; border-color: {abp_PRIMARY}; color: {abp_PRIMARY}; font-weight: 600;
}}
QToolBar QToolButton:disabled {{ color: #a3acb8; }}
QGraphicsView {{ border: 1px solid {abp_BORDER}; border-radius: 6px; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: {abp_SURFACE}; border-top: 1px solid {abp_BORDER}; color: {abp_MUTED}; }}
QMenuBar {{ background: {abp_SURFACE}; border-bottom: 1px solid {abp_BORDER}; }}
QMenu {{ background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {abp_PRIMARY_SOFT}; color: {abp_TEXT}; }}
QMenu::item:disabled {{ color: #a3acb8; }}

QWidget#sidebar {{ background: {abp_SIDEBAR}; }}
QLabel#sidebarTitle {{ color: white; font-size: {abp_BASE_POINT_SIZE + 5}pt; font-weight: 700; }}
QLabel#sidebarSubtitle {{ color: {abp_SIDEBAR_MUTED}; }}
QListWidget#wizardSteps {{
    background: transparent; border: none; color: {abp_SIDEBAR_TEXT}; outline: none;
}}
QListWidget#wizardSteps::item {{ padding: 9px 8px; border-radius: 6px; margin: 1px 0; }}
QListWidget#wizardSteps::item:hover {{ background: {abp_SIDEBAR_HOVER}; }}
QListWidget#wizardSteps::item:selected {{ background: {abp_PRIMARY}; color: white; }}
QListWidget#wizardSteps::item:disabled {{ color: {abp_SIDEBAR_DISABLED}; }}

QWidget#floorBar, QWidget#navBar {{ background: {abp_SURFACE}; border: 1px solid {abp_BORDER};
    border-radius: 8px; }}
QLabel#navStep {{ color: {abp_MUTED}; }}

QFrame#banner QLabel {{ background: transparent; border: none; }}
QLabel#bannerIcon {{ font-size: {abp_BASE_POINT_SIZE + 4}pt; font-weight: 700; }}

QFrame#card {{ background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 8px; }}
QFrame#card QLabel {{ border: none; background: transparent; }}
QLabel#cardTitle {{ color: {abp_MUTED}; }}
QLabel#cardValue {{ font-size: {abp_BASE_POINT_SIZE + 10}pt; font-weight: 700; }}
QLabel#cardNote {{ color: {abp_MUTED}; }}

QFrame#welcomeCard {{ background: {abp_SURFACE}; border: 1px solid {abp_BORDER}; border-radius: 12px; }}
QFrame#welcomeCard QLabel {{ background: transparent; }}
QLabel#welcomeTitle {{ font-size: {abp_BASE_POINT_SIZE + 12}pt; font-weight: 700; }}
QFrame#legend QLabel {{ font-weight: normal; }}
{abp__kind_rules()}
"""


def abp__palette() -> QPalette:
    abp_palette = QPalette()
    abp_roles = {
        QPalette.ColorRole.Window: abp_BACKGROUND,
        QPalette.ColorRole.WindowText: abp_TEXT,
        QPalette.ColorRole.Base: abp_SURFACE,
        QPalette.ColorRole.AlternateBase: "#f8fafc",
        QPalette.ColorRole.Text: abp_TEXT,
        QPalette.ColorRole.Button: abp_SURFACE,
        QPalette.ColorRole.ButtonText: abp_TEXT,
        QPalette.ColorRole.Highlight: abp_PRIMARY,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: abp_TEXT,
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: abp_MUTED,
        QPalette.ColorRole.Link: abp_PRIMARY,
    }
    for abp_role, abp_color in abp_roles.items():
        abp_palette.setColor(abp_role, QColor(abp_color))
    abp_palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#a3acb8"))
    abp_palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#a3acb8")
    )
    abp_palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#a3acb8")
    )
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
