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


CRITERIA_DIR = Path(__file__).parent.resolve()
DEFAULT_CRITERIA_PATH = CRITERIA_DIR / "default.yaml"


def load_criteria(path: str | Path | None = None, restrict_to_dir: bool = False) -> dict[str, Any]:
    """Carga el YAML de criterios (o el default si no se pasa ruta) y lo valida.

    `restrict_to_dir=True` limita `path` a CRITERIA_DIR: lo usa la API HTTP, donde
    `path` viene de `EvaluationRequest.criteria_path` (un campo del request, no confiable),
    para que no se pueda leer un archivo arbitrario del servidor con un "../../" o una
    ruta absoluta. El CLI (`demo.py`) no lo activa porque ahí la ruta la escribe quien
    ejecuta el script en su propia máquina, con acceso de todas formas a su filesystem.
    """
    if not path:
        resolved = DEFAULT_CRITERIA_PATH
    elif restrict_to_dir:
        candidate = (CRITERIA_DIR / path).resolve()
        try:
            candidate.relative_to(CRITERIA_DIR)
        except ValueError:
            raise ValueError(f"Ruta de criterios no permitida: {path}")
        resolved = candidate
    else:
        resolved = Path(path)

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
