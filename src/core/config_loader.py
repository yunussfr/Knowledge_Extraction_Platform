"""Loads a domain request and source configuration without hard-coded domains."""

from pathlib import Path
from typing import Any, Dict

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def load_domain_config(domain: str) -> Dict[str, Any]:
    domain_directory = PROJECT_ROOT / "configs" / "domains" / domain
    if not domain_directory.is_dir():
        raise ValueError(f"Unknown domain: {domain}")

    domain_config = _read_yaml(domain_directory / "domain.yaml")
    request_config = _read_yaml(domain_directory / "request.yaml")
    source_config = _read_yaml(domain_directory / "sources.yaml")
    validation_config = _read_yaml(domain_directory / "validation.yaml")
    return {
        **domain_config,
        **request_config,
        "sources": source_config.get("sources", []),
        "quality": validation_config.get("quality", request_config.get("quality", {})),
    }
