"""
Fixtures y utilidades compartidas por toda la suite de pruebas.

No se llama a GitHub, a Claude ni a Supabase reales en ningun lado: todo lo
externo se simula con los dobles definidos aca (FakeSupabase) o con
unittest.mock en cada archivo de prueba puntual.
"""

from __future__ import annotations

import pytest


def base_criteria(**overrides):
    """Un dict de criterios minimo y valido (pesos suman 100), para no repetir
    la misma estructura en cada prueba. `overrides` reemplaza secciones completas."""
    criteria = {
        "periodo": {
            "inicio": "2026-06-01",
            "fin": "2026-09-01",
            "fecha_limite": "2026-09-01T23:59:00",
        },
        "estructural": {
            "habilitado": True, "peso": 25,
            "archivos_requeridos": ["README.md", "src/"],
            "readme_min_chars": 50,
        },
        "versionado": {
            "habilitado": True, "peso": 40,
            "commits_min": 3,
            "calidad_mensajes": {"habilitado": True, "umbral_porcentaje": 70},
            "ramas": {"habilitado": True, "min_ramas": 2},
        },
        "temporal": {
            "habilitado": True, "peso": 25,
            "actividad_minima_semanal": True,
            "alerta_concentracion": {"habilitado": True, "dias_finales": 3, "porcentaje_umbral": 70},
        },
        "contenido": {
            "habilitado": True, "peso": 10,
            "requisitos_funcionales": ["usa herencia"],
        },
    }
    criteria.update(overrides)
    return criteria


def base_repo_data(**overrides):
    """Un dict de repo_data minimo, como lo entregaria extraction_agent."""
    data = {
        "url": "https://github.com/estudiante/proyecto",
        "owner": "estudiante",
        "repo_name": "proyecto",
        "student": "estudiante",
        "default_branch": "main",
        "commits": [],
        "files": ["README.md", "src/main.py"],
        "branches": ["main"],
        "branch_files": {"main": ["README.md", "src/main.py"]},
        "branch_content": {},
        "readme_content": "x" * 100,
        "code_files": {},
        "periodo_inicio": "2026-06-01T00:00:00+00:00",
        "periodo_fin": "2026-09-01T00:00:00+00:00",
    }
    data.update(overrides)
    return data


class FakeQueryResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """Imita la interfaz encadenable de supabase-py (.table().select().eq()...execute())."""

    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self.filters = {}
        self._update_data = None
        self._order = None

    def select(self, cols):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def order(self, key, desc=False):
        self._order = (key, desc)
        return self

    def update(self, data):
        self._update_data = data
        return self

    def insert(self, data):
        self.store.setdefault(self.table_name, []).append(dict(data))
        return self

    def execute(self):
        rows = self.store.get(self.table_name, [])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self._update_data is not None:
            for r in matched:
                r.update(self._update_data)
            return FakeQueryResult(matched)
        if self._order:
            key, desc = self._order
            matched = sorted(matched, key=lambda r: r.get(key, 0), reverse=desc)
        return FakeQueryResult(matched)


class FakeSupabase:
    """Base de datos en memoria que reemplaza a Supabase en las pruebas."""

    def __init__(self):
        self.store: dict[str, list[dict]] = {}

    def table(self, name):
        return FakeQuery(self.store, name)


@pytest.fixture
def fake_db():
    return FakeSupabase()
