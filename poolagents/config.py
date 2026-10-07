"""Load threshold configs (bundled defaults, or a user-supplied JSON file)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


def _load_bundled(name: str) -> dict[str, Any]:
    text = resources.files("poolagents").joinpath("config", name).read_text(encoding="utf-8")
    return json.loads(text)


def load_rug_config(path: str | Path | None = None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return _load_bundled("rugcheck_v6.json")


def load_scalp_config(path: str | Path | None = None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return _load_bundled("scalp_playbook.json")
