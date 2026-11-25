from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

abp_PACKAGE = "abp_rutasegura"

abp_ALLOWED_LAYERS: dict[str, frozenset[str]] = {
    "abp_domain": frozenset({"abp_domain"}),
    "abp_resources": frozenset({"abp_resources"}),
    "abp_engines": frozenset({"abp_domain", "abp_engines", "abp_resources"}),
    "abp_data": frozenset({"abp_domain", "abp_data", "abp_resources"}),
    "abp_application": frozenset(
        {"abp_domain", "abp_engines", "abp_data", "abp_application", "abp_resources"}
    ),
    "abp_presentation": frozenset(
        {"abp_domain", "abp_application", "abp_presentation", "abp_resources"}
    ),
}
abp_UNRESTRICTED_LAYERS = frozenset({"__main__", "__init__"})

abp__QT = frozenset({"PySide6", "shiboken6"})
abp__DB = frozenset({"sqlalchemy", "alembic"})

abp_FORBIDDEN_EXTERNAL: dict[str, frozenset[str]] = {
    "abp_domain": abp__QT | abp__DB | {"cv2", "fitz", "pymupdf", "reportlab", "matplotlib", "yaml"},
    "abp_resources": abp__QT | abp__DB,
    "abp_engines": abp__QT | abp__DB | {"reportlab"},
    "abp_data": abp__QT,
    "abp_application": abp__QT,
    "abp_presentation": abp__DB | {"cv2"},
}

abp_NETWORK_MODULES = frozenset(
    {
        "socket",
        "ssl",
        "urllib.request",
        "urllib3",
        "http.client",
        "http.server",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "websocket",
        "websockets",
        "PySide6.QtNetwork",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    }
)

abp_NUMPY_RANDOM_ALLOWED = frozenset(
    {
        "default_rng",
        "Generator",
        "SeedSequence",
        "BitGenerator",
        "PCG64",
        "PCG64DXSM",
        "Philox",
        "SFC64",
        "MT19937",
    }
)


@dataclass(frozen=True)
class abpViolation:
    abp_location: str
    abp_line: int
    abp_message: str

    def __str__(self) -> str:
        return f"{self.abp_location}:{self.abp_line}: {self.abp_message}"


def abp__matches(abp_name: str, abp_prefixes: frozenset[str]) -> str | None:
    for abp_prefix in abp_prefixes:
        if abp_name == abp_prefix or abp_name.startswith(abp_prefix + "."):
            return abp_prefix
    return None


def abp__imports(
    abp_tree: ast.AST, abp_module: str, abp_is_package: bool
) -> Iterator[tuple[str, int]]:
    for abp_node in ast.walk(abp_tree):
        if isinstance(abp_node, ast.Import):
            for abp_alias in abp_node.names:
                yield abp_alias.name, abp_node.lineno
        elif isinstance(abp_node, ast.ImportFrom):
            if abp_node.level:
                abp_parts = abp_module.split(".") if abp_is_package else abp_module.split(".")[:-1]
                abp_base = abp_parts[: len(abp_parts) - (abp_node.level - 1)]
                if abp_node.module:
                    abp_base = [*abp_base, abp_node.module]
                abp_name = ".".join(abp_base)
            else:
                abp_name = abp_node.module or ""
            yield abp_name, abp_node.lineno
            for abp_alias in abp_node.names:
                if abp_alias.name != "*":
                    yield f"{abp_name}.{abp_alias.name}", abp_node.lineno


def abp__numpy_aliases(abp_tree: ast.AST) -> dict[str, str]:
    abp_aliases: dict[str, str] = {}
    for abp_node in ast.walk(abp_tree):
        if isinstance(abp_node, ast.Import):
            for abp_alias in abp_node.names:
                if abp_alias.name == "numpy" or abp_alias.name.startswith("numpy."):
                    abp_aliases[abp_alias.asname or abp_alias.name.split(".")[0]] = (
                        abp_alias.name if abp_alias.asname else abp_alias.name.split(".")[0]
                    )
        elif (
            isinstance(abp_node, ast.ImportFrom)
            and abp_node.module
            and abp_node.level == 0
            and (abp_node.module == "numpy" or abp_node.module.startswith("numpy."))
        ):
            for abp_alias in abp_node.names:
                abp_aliases[abp_alias.asname or abp_alias.name] = (
                    f"{abp_node.module}.{abp_alias.name}"
                )
    return abp_aliases


def abp__dotted(abp_node: ast.expr) -> list[str] | None:
    abp_parts: list[str] = []
    while isinstance(abp_node, ast.Attribute):
        abp_parts.append(abp_node.attr)
        abp_node = abp_node.value
    if isinstance(abp_node, ast.Name):
        abp_parts.append(abp_node.id)
        return abp_parts[::-1]
    return None


def abp__layer_of(abp_module: str) -> str:
    abp_parts = abp_module.split(".")
    return abp_parts[1] if len(abp_parts) > 1 else "__init__"


def abp_check_source(
    abp_source: str, abp_module: str, *, abp_is_package: bool = False
) -> list[abpViolation]:
    abp_tree = ast.parse(abp_source)
    abp_layer = abp__layer_of(abp_module)
    abp_found: list[abpViolation] = []

    def abp_report(abp_line: int, abp_message: str) -> None:
        abp_found.append(abpViolation(abp_module, abp_line, abp_message))

    for abp_name, abp_line in abp__imports(abp_tree, abp_module, abp_is_package):
        abp_top = abp_name.split(".")[0]
        if abp_top == abp_PACKAGE and abp_layer not in abp_UNRESTRICTED_LAYERS:
            abp_target = abp__layer_of(abp_name)
            abp_allowed = abp_ALLOWED_LAYERS.get(abp_layer, frozenset())
            if abp_target != "__init__" and abp_target not in abp_allowed:
                abp_report(
                    abp_line, f"la capa '{abp_layer}' no puede importar '{abp_target}' ({abp_name})"
                )
        elif abp_top != abp_PACKAGE:
            abp_banned = abp__matches(abp_name, abp_FORBIDDEN_EXTERNAL.get(abp_layer, frozenset()))
            if abp_banned:
                abp_report(abp_line, f"la capa '{abp_layer}' no puede importar '{abp_banned}'")
        abp_net = abp__matches(abp_name, abp_NETWORK_MODULES)
        if abp_net:
            abp_report(abp_line, f"acceso a red prohibido ('{abp_net}')")
        if abp_name == "random" or abp_name.startswith("random."):
            abp_report(
                abp_line, "usa numpy.random.Generator con la semilla del escenario, no 'random'"
            )
        if abp_name.startswith("numpy.random."):
            abp_leaf = abp_name.split(".")[2]
            if abp_leaf not in abp_NUMPY_RANDOM_ALLOWED:
                abp_report(abp_line, f"API aleatoria global de NumPy prohibida ({abp_name})")

    abp_aliases = abp__numpy_aliases(abp_tree)
    for abp_node in ast.walk(abp_tree):
        if isinstance(abp_node, ast.Attribute):
            abp_parts = abp__dotted(abp_node)
            if not abp_parts or abp_parts[0] not in abp_aliases:
                continue
            abp_full = ".".join([abp_aliases[abp_parts[0]], *abp_parts[1:]]).split(".")
            abp_is_global_random = (
                abp_full[:2] == ["numpy", "random"]
                and len(abp_full) > 2
                and abp_full[2] not in abp_NUMPY_RANDOM_ALLOWED
            )
            if abp_is_global_random:
                abp_report(
                    abp_node.lineno,
                    f"API aleatoria global de NumPy prohibida ({'.'.join(abp_full)})",
                )
    return abp_found


def abp_check_package(abp_package_dir: Path) -> tuple[list[abpViolation], int]:
    abp_violations: list[abpViolation] = []
    abp_files = sorted(abp_package_dir.rglob("*.py"))
    for abp_path in abp_files:
        abp_rel = abp_path.relative_to(abp_package_dir.parent).with_suffix("")
        abp_is_package = abp_rel.name == "__init__"
        abp_parts = abp_rel.parts[:-1] if abp_is_package else abp_rel.parts
        abp_module = ".".join(abp_parts)
        abp_violations.extend(
            abp_check_source(
                abp_path.read_text(encoding="utf-8"), abp_module, abp_is_package=abp_is_package
            )
        )
    return abp_violations, len(abp_files)
