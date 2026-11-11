from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from agents import extraction
from errors import FatalEvaluationError
from tests.conftest import base_criteria


# Prueba para parsear una URL normal de GitHub
def test_parse_url_normal():
    owner, repo = extraction._parse_url("https://github.com/juan/proyecto")
    assert (owner, repo) == ("juan", "proyecto")


# Prueba para parsear una URL terminada en .git
def test_parse_url_termina_en_git():
    owner, repo = extraction._parse_url("https://github.com/juan/proyecto.git")
    assert (owner, repo) == ("juan", "proyecto")


# Prueba para parsear una URL con barra final
def test_parse_url_con_barra_final():
    owner, repo = extraction._parse_url("https://github.com/juan/proyecto/")
    assert (owner, repo) == ("juan", "proyecto")


# Prueba para rechazar una URL que no tiene owner y repo
def test_parse_url_invalida():
    with pytest.raises(ValueError):
        extraction._parse_url("no-es-una-url")


def make_state(url="https://github.com/juan/proyecto"):
    return {
        "current_index": 0,
        "repo_urls": [url],
        "github_token": "un-token",
        "criteria": base_criteria(),
        "errors": [],
    }


# Prueba para que un token de GitHub invalido corte toda la evaluacion
def test_extraction_agent_token_invalido_es_fatal():
    state = make_state()
    err = GithubException(401, {"message": "Bad credentials"}, None)
    with patch.object(extraction, "_fetch_repo", side_effect=err):
        with pytest.raises(FatalEvaluationError, match="GITHUB_TOKEN"):
            extraction.extraction_agent(state)


# Prueba para que el limite de peticiones agotado corte toda la evaluacion
def test_extraction_agent_rate_limit_es_fatal():
    state = make_state()
    err = GithubException(403, {"message": "API rate limit exceeded for user"}, None)
    with patch.object(extraction, "_fetch_repo", side_effect=err):
        with pytest.raises(FatalEvaluationError, match="límite de peticiones"):
            extraction.extraction_agent(state)


# Prueba para que un repositorio no encontrado no corte la evaluacion completa
def test_extraction_agent_404_no_es_fatal():
    state = make_state()
    err = GithubException(404, {"message": "Not Found"}, None)
    with patch.object(extraction, "_fetch_repo", side_effect=err):
        result = extraction.extraction_agent(state)
    assert result["current_repo_data"] is None
    assert "no encontrado" in result["errors"][0]


# Prueba para un acceso denegado que no es por limite de peticiones
def test_extraction_agent_403_sin_rate_limit_no_es_fatal():
    state = make_state()
    err = GithubException(403, {"message": "Forbidden"}, None)
    with patch.object(extraction, "_fetch_repo", side_effect=err):
        result = extraction.extraction_agent(state)
    assert result["current_repo_data"] is None
    assert "Acceso denegado" in result["errors"][0]


# Prueba para un error de GitHub con un codigo distinto a los contemplados
def test_extraction_agent_error_generico_de_github():
    state = make_state()
    err = GithubException(500, {"message": "Internal Server Error"}, None)
    with patch.object(extraction, "_fetch_repo", side_effect=err):
        result = extraction.extraction_agent(state)
    assert "500" in result["errors"][0]


# Prueba para que un error totalmente inesperado no tumbe la evaluacion completa
def test_extraction_agent_error_inesperado_no_es_fatal():
    state = make_state()
    with patch.object(extraction, "_fetch_repo", side_effect=RuntimeError("algo raro")):
        result = extraction.extraction_agent(state)
    assert result["current_repo_data"] is None
    assert "inesperado" in result["errors"][0]


# Prueba para que la extraccion exitosa devuelva current_repo_data
def test_extraction_agent_exitoso():
    state = make_state()
    with patch.object(extraction, "_fetch_repo", return_value={"owner": "juan"}):
        result = extraction.extraction_agent(state)
    assert result == {"current_repo_data": {"owner": "juan"}}


# Prueba para que _fetch_named_files respete el limite de archivos
def test_fetch_named_files_respeta_max_files():
    repo = MagicMock()
    content_mock = MagicMock()
    content_mock.decoded_content = b"contenido"
    repo.get_contents.return_value = content_mock
    files_list = ["a/README.md", "b/README.md", "c/README.md"]
    result = extraction._fetch_named_files(repo, "main", ["README.md"], files_list, max_files=2)
    assert len(result) == 2


# Prueba para que _fetch_named_files respete el limite de caracteres por archivo
def test_fetch_named_files_respeta_max_chars():
    repo = MagicMock()
    content_mock = MagicMock()
    content_mock.decoded_content = b"0123456789"
    repo.get_contents.return_value = content_mock
    result = extraction._fetch_named_files(repo, "main", ["README.md"], ["README.md"], max_chars=5)
    assert result["README.md"] == "01234"


# Prueba para que _fetch_code_files filtre por extension configurada
def test_fetch_code_files_filtra_por_extension():
    repo = MagicMock()
    content_mock = MagicMock()
    content_mock.decoded_content = b"codigo"
    repo.get_contents.return_value = content_mock
    files_list = ["src/main.py", "src/estilos.css", "README.md"]
    criteria = {"contenido": {"extensiones_codigo": [".py"], "max_archivos": 10}}
    result = extraction._fetch_code_files(repo, "main", criteria, files_list)
    assert list(result.keys()) == ["src/main.py"]


# Prueba para que _fetch_code_files excluya carpetas de dependencias
def test_fetch_code_files_excluye_node_modules_y_vendor():
    repo = MagicMock()
    files_list = ["node_modules/x.py", "vendor/y.py", "src/main.py"]
    criteria = {"contenido": {"extensiones_codigo": [".py"], "max_archivos": 10}}
    with patch.object(repo, "get_contents") as mock_get:
        mock_get.return_value.decoded_content = b"x"
        extraction._fetch_code_files(repo, "main", criteria, files_list)
        rutas_pedidas = [call.args[0] for call in mock_get.call_args_list]
    assert rutas_pedidas == ["src/main.py"]
