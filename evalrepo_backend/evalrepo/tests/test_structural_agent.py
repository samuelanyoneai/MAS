from __future__ import annotations

from unittest.mock import patch

from agents.structural import structural_agent, _analyze, _is_present, _find_in_any_folder
from tests.conftest import base_criteria, base_repo_data


# Prueba para que el agente no haga nada si no hay repo_data
def test_structural_agent_sin_repo_data():
    state = {"current_repo_data": None, "criteria": base_criteria(), "errors": []}
    result = structural_agent(state)
    assert result == {}


# Prueba para que la dimension deshabilitada no reste puntos
def test_structural_agent_dimension_deshabilitada():
    criteria = base_criteria()
    criteria["estructural"]["habilitado"] = False
    state = {"current_repo_data": base_repo_data(), "criteria": criteria, "errors": []}
    result = structural_agent(state)
    assert result["structural_result"]["score"] == 0.0
    assert result["structural_result"]["max_score"] == 0.0


# Prueba para un repo que cumple todos los archivos requeridos y el readme
def test_analyze_todos_los_archivos_presentes():
    repo_data = base_repo_data(files=["README.md", "src/main.py"], readme_content="x" * 300)
    cfg = {"peso": 25, "archivos_requeridos": ["README.md", "src/"], "readme_min_chars": 200}
    result = _analyze(repo_data, cfg)
    assert result["files_missing"] == []
    assert result["readme_ok"] is True
    assert result["score"] == 25.0


# Prueba para un archivo requerido que falta
def test_analyze_archivo_faltante():
    repo_data = base_repo_data(files=["src/main.py"], readme_content="x" * 300)
    cfg = {"peso": 25, "archivos_requeridos": ["README.md", "src/"], "readme_min_chars": 200}
    result = _analyze(repo_data, cfg)
    assert "README.md" in result["files_missing"]
    assert result["score"] < 25.0


# Prueba para un readme por debajo del minimo de caracteres
def test_analyze_readme_insuficiente():
    repo_data = base_repo_data(files=["README.md"], readme_content="corto")
    cfg = {"peso": 25, "archivos_requeridos": ["README.md"], "readme_min_chars": 200}
    result = _analyze(repo_data, cfg)
    assert result["readme_ok"] is False
    assert result["readme_char_count"] == 5


# Prueba para que una carpeta con barra final se detecte por prefijo de ruta
def test_is_present_detecta_carpeta_por_prefijo():
    files_lower = {"src/main.py", "src/utils.py"}
    assert _is_present("src/", files_lower) is True


# Prueba para que un archivo ausente no se detecte como presente
def test_is_present_archivo_ausente():
    files_lower = {"src/main.py"}
    assert _is_present("tests/", files_lower) is False


# Prueba para que la comparacion ignore mayusculas y minusculas
def test_analyze_ignora_mayusculas():
    repo_data = base_repo_data(files=["ReadMe.MD"], readme_content="x" * 300)
    cfg = {"peso": 25, "archivos_requeridos": ["readme.md"], "readme_min_chars": 200}
    result = _analyze(repo_data, cfg)
    assert "readme.md" in result["files_found"]


# Prueba para un requisito de archivo presente en una rama especifica
def test_analyze_archivo_por_rama_encontrado():
    repo_data = base_repo_data(
        files=["src/main.py"],
        branch_files={"main": ["src/main.py"], "docs": ["README.md"]},
    )
    cfg = {
        "peso": 25, "archivos_requeridos": [], "readme_min_chars": 0,
        "archivos_por_rama": {"docs": ["README.md"]},
    }
    result = _analyze(repo_data, cfg)
    assert result["branch_checks"] == [{"branch": "docs", "path": "README.md", "found": True}]


# Prueba para un requisito de archivo ausente en una rama especifica
def test_analyze_archivo_por_rama_no_encontrado():
    repo_data = base_repo_data(branch_files={"main": [], "docs": []})
    cfg = {
        "peso": 25, "archivos_requeridos": [], "readme_min_chars": 0,
        "archivos_por_rama": {"docs": ["README.md"]},
    }
    result = _analyze(repo_data, cfg)
    assert result["branch_checks"][0]["found"] is False


# Prueba para encontrar un archivo dentro de alguna de varias carpetas posibles
def test_find_in_any_folder_encuentra_en_subcarpeta():
    files = {"src/utils/config.py", "app/helpers.py"}
    encontrado = _find_in_any_folder("config.py", ["src/", "app/"], files)
    assert encontrado == "src/utils/config.py"


# Prueba para no encontrar un archivo en ninguna de las carpetas dadas
def test_find_in_any_folder_no_encuentra():
    files = {"src/main.py"}
    encontrado = _find_in_any_folder("config.py", ["src/", "app/"], files)
    assert encontrado is None


# Prueba para que el puntaje combine archivos requeridos, rama y alternativos
def test_analyze_puntaje_combinado_con_todos_los_checks():
    repo_data = base_repo_data(
        files=["src/"],
        readme_content="x" * 300,
        branch_files={"main": [], "docs": ["README.md"]},
    )
    cfg = {
        "peso": 25,
        "archivos_requeridos": ["src/"],
        "readme_min_chars": 200,
        "archivos_por_rama": {"docs": ["README.md"], "main": ["tests/"]},
        "archivos_alternativos": [{"nombre": "config.py", "carpetas": ["src/", "app/"]}],
    }
    result = _analyze(repo_data, cfg)
    # total_checks = 1 (requerido) + 1 (readme) + 2 (rama) + 1 (alternativo) = 5
    # pasan: requerido(1) + readme(1) + docs(1) + main(0) + alternativo(0) = 3
    assert result["score"] == round(25 * 3 / 5, 2)


# Prueba para que una excepcion interna no tumbe el agente completo
def test_structural_agent_degrada_en_vez_de_lanzar():
    state = {"current_repo_data": base_repo_data(), "criteria": base_criteria(), "errors": []}
    with patch("agents.structural._analyze", side_effect=KeyError("dato raro")):
        result = structural_agent(state)
    assert result["structural_result"]["score"] == 0.0
    assert len(result["errors"]) == 1
