"""
criteria_loader.py
Carga el YAML de criterios que edita el docente y lo deja listo
para usar en el estado del grafo, validando que no falte nada.
"""

from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CRITERIA_PATH = Path(__file__).parent / "default.yaml"


def load_criteria(path: str | Path | None = None) -> dict[str, Any]:
    """Carga el YAML de criterios (o el default si no se pasa ruta) y lo valida."""
    resolved = Path(path) if path else DEFAULT_CRITERIA_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"Archivo de criterios no encontrado: {resolved}")

    with open(resolved, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _validate(raw)
    return raw


def _validate(criteria: dict[str, Any]) -> None:
    """Se fija que no falte ninguna sección y que los pesos cuadren."""
    required_sections = ["periodo", "estructural", "versionado", "temporal", "contenido"]
    for section in required_sections:
        if section not in criteria:
            raise ValueError(f"Sección obligatoria ausente en el YAML: '{section}'")

    # los pesos de las dimensiones habilitadas tienen que sumar 100
    dims = ["estructural", "versionado", "temporal", "contenido"]
    total = sum(
        criteria[d].get("peso", 0)
        for d in dims
        if criteria[d].get("habilitado", True)
    )
    if total != 100:
        raise ValueError(
            f"Los pesos de las dimensiones habilitadas deben sumar 100, "
            f"pero suman {total}. Revisa el archivo YAML."
        )

    # la fecha límite tiene que venir sí o sí, y en formato ISO
    fecha_str = criteria["periodo"].get("fecha_limite")
    if not fecha_str:
        raise ValueError("El campo 'periodo.fecha_limite' es obligatorio.")
    try:
        datetime.fromisoformat(fecha_str)
    except ValueError:
        raise ValueError(
            f"'periodo.fecha_limite' debe ser ISO-8601 (YYYY-MM-DDTHH:MM:SS): {fecha_str}"
        )


def get_deadline(criteria: dict[str, Any]) -> datetime:
    """Devuelve la fecha límite como datetime con zona horaria UTC."""
    fecha_str = criteria["periodo"]["fecha_limite"]
    dt = datetime.fromisoformat(fecha_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_peso(criteria: dict[str, Any], dimension: str) -> float:
    """Devuelve el peso porcentual de una dimensión (0–100)."""
    return float(criteria.get(dimension, {}).get("peso", 0))


def is_enabled(criteria: dict[str, Any], dimension: str) -> bool:
    """Devuelve True si la dimensión está habilitada."""
    return bool(criteria.get(dimension, {}).get("habilitado", True))
