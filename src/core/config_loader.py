"""Load and deterministically validate domain request configuration."""

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml

from src.schemas.models import RequestConfiguration


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def normalize_request_config(raw_config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy source controls into the canonical typed request shape."""
    config = deepcopy(raw_config)
    research = dict(config.get("research") or {})
    source_controls = config.get("sources")
    if not isinstance(source_controls, dict):
        source_controls = {}
    else:
        source_controls = dict(source_controls)

    legacy_mappings = {
        "reference_urls": "seed_urls",
        "preferred_domains": "preferred_domains",
        "allowed_domains": "allowed_domains",
        "blocked_domains": "blocked_domains",
    }
    for legacy_name, canonical_name in legacy_mappings.items():
        if canonical_name not in source_controls and legacy_name in research:
            source_controls[canonical_name] = research.pop(legacy_name)
    if "source_policy" not in source_controls and "source_policy" in research:
        source_controls["source_policy"] = research.pop("source_policy")

    config["research"] = research
    config["sources"] = source_controls
    validated = RequestConfiguration.model_validate(config)
    return validated.model_dump(mode="json", by_alias=True)


def load_request_config(path: Path) -> Dict[str, Any]:
    """Load one request YAML through the typed application contract."""
    return normalize_request_config(_read_yaml(path))


def load_domain_config(domain: str) -> Dict[str, Any]:
    domain_directory = PROJECT_ROOT / "configs" / "domains" / domain
    if not domain_directory.is_dir():
        raise ValueError(f"Unknown domain: {domain}")

    domain_config = _read_yaml(domain_directory / "domain.yaml")
    request_config = load_request_config(domain_directory / "request.yaml")
    source_config = _read_yaml(domain_directory / "sources.yaml")
    validation_config = _read_yaml(domain_directory / "validation.yaml")
    return {
        **domain_config,
        **request_config,
        "mock_sources": source_config.get("sources", []),
        "quality": validation_config.get("quality", request_config.get("quality", {})),
    }
