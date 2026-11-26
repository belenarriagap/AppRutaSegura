from __future__ import annotations

from pathlib import Path

import abp_rutasegura
from abp_rutasegura.abp_engines.abp_norms.abp_rules import abp_parse_rules, abpRuleSet

abp_NORMS_DIR = Path(abp_rutasegura.__file__).parent / "abp_resources" / "abp_norms"


def abp_packaged_rules() -> abpRuleSet:
    return abp_parse_rules(
        (abp_p.name, abp_p.read_text(encoding="utf-8"))
        for abp_p in sorted(abp_NORMS_DIR.glob("*.yaml"))
    )
