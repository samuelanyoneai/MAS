"""
Pruebas del script de linea de comandos demo.py. No llama a GitHub, a Claude ni
construye el grafo real: todo lo externo se reemplaza con dobles.
"""

from __future__ import annotations

import sys

import pytest

import demo
from tests.conftest import base_criteria


class FakeGraph:
    def __init__(self, final_state):
        self._final_state = final_state

    def invoke(self, state):
        return self._final_state


# Prueba para que main() use "default.yaml" como ruta de criterios cuando no se pasa --criteria
def test_main_usa_default_yaml_cuando_no_se_pasa_criteria(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "y")
    monkeypatch.setattr(
        sys, "argv",
        ["demo.py", "--urls", "https://github.com/juan/proyecto"],
    )

    criterios = base_criteria()
    monkeypatch.setattr("config.criteria_loader.load_criteria", lambda path: criterios)

    final_state = {"results": [], "errors": [], "consolidated_report": ""}
    monkeypatch.setattr("graph.build_graph", lambda: FakeGraph(final_state))
    monkeypatch.setattr("graph.initial_state", lambda **kwargs: {})

    saved = {}
    def fake_save_reports(results, consolidated_html, output_dir):
        saved["output_dir"] = output_dir
    monkeypatch.setattr("reports.generator.save_reports", fake_save_reports)

    demo.main()

    out = capsys.readouterr().out
    assert "default.yaml" in out
    assert saved["output_dir"].name == "reportes"


# Prueba para que main() respete la ruta de criterios pasada por --criteria
def test_main_respeta_criteria_explicito(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "y")
    monkeypatch.setattr(
        sys, "argv",
        ["demo.py", "--urls", "https://github.com/juan/proyecto", "--criteria", "otro.yaml"],
    )

    criterios = base_criteria()
    monkeypatch.setattr("config.criteria_loader.load_criteria", lambda path: criterios)

    final_state = {"results": [], "errors": [], "consolidated_report": ""}
    monkeypatch.setattr("graph.build_graph", lambda: FakeGraph(final_state))
    monkeypatch.setattr("graph.initial_state", lambda **kwargs: {})
    monkeypatch.setattr("reports.generator.save_reports", lambda **kwargs: None)

    demo.main()

    out = capsys.readouterr().out
    assert "otro.yaml" in out


# Prueba para que main() aborte si faltan variables de entorno requeridas
def test_main_sale_si_faltan_variables_de_entorno(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["demo.py", "--urls", "https://github.com/juan/proyecto"])

    with pytest.raises(SystemExit):
        demo.main()


# Prueba para que _resolve_urls lea un archivo .txt con una URL por linea
def test_resolve_urls_desde_archivo(tmp_path):
    archivo = tmp_path / "repos.txt"
    archivo.write_text("https://github.com/a/b\n# comentario\n\nhttps://github.com/c/d\n")
    assert demo._resolve_urls([str(archivo)]) == [
        "https://github.com/a/b",
        "https://github.com/c/d",
    ]


# Prueba para que _resolve_urls deje pasar URLs sueltas tal cual
def test_resolve_urls_urls_sueltas():
    assert demo._resolve_urls(["https://github.com/a/b", "  "]) == ["https://github.com/a/b"]
