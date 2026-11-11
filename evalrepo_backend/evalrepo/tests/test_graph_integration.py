from __future__ import annotations

from unittest.mock import patch

from errors import FatalEvaluationError
from graph import build_graph, initial_state
from tests.conftest import base_criteria, base_repo_data


# Prueba para que el grafo completo procese dos repositorios de punta a punta
def test_graph_procesa_dos_repos_completo():
    criteria = base_criteria()
    state = initial_state(
        repo_urls=["https://github.com/a/uno", "https://github.com/a/dos"],
        criteria=criteria,
        github_token="t",
    )
    graph = build_graph()

    with patch("agents.extraction._fetch_repo", return_value=base_repo_data()):
        with patch("agents.content._call_claude", return_value={
            "requirements_found": ["usa herencia"], "requirements_missing": [],
            "coherence_level": "Alta", "summary": "bien",
        }):
            final_state = graph.invoke(state)

    assert len(final_state["results"]) == 2
    assert final_state["current_index"] == 2
    assert final_state["consolidated_report"] is not None
    for r in final_state["results"]:
        assert r["report_html"] is not None
        assert r["error"] is None


# Prueba para que un error fatal en el primer repo corte el grafo sin seguir con el segundo
def test_graph_se_corta_ante_un_error_fatal():
    criteria = base_criteria()
    state = initial_state(
        repo_urls=["https://github.com/a/uno", "https://github.com/a/dos"],
        criteria=criteria,
        github_token="token-invalido",
    )
    graph = build_graph()

    import pytest
    with patch("agents.extraction._fetch_repo", side_effect=FatalEvaluationError("token invalido")):
        with pytest.raises(FatalEvaluationError):
            graph.invoke(state)


# Prueba para que un repo que falla en extraccion no impida procesar el resto
def test_graph_un_repo_con_error_no_detiene_a_los_demas():
    criteria = base_criteria()
    state = initial_state(
        repo_urls=["https://github.com/a/malo", "https://github.com/a/bueno"],
        criteria=criteria,
        github_token="t",
    )
    graph = build_graph()

    llamadas = {"n": 0}

    def fetch_repo_side_effect(url, token, crit):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            from github import GithubException
            raise GithubException(404, {"message": "Not Found"}, None)
        return base_repo_data()

    with patch("agents.extraction._fetch_repo", side_effect=fetch_repo_side_effect):
        with patch("agents.content._call_claude", return_value={
            "requirements_found": [], "requirements_missing": ["usa herencia"],
            "coherence_level": "Baja", "summary": "",
        }):
            final_state = graph.invoke(state)

    assert len(final_state["results"]) == 2
    assert final_state["results"][0]["error"] is not None
    assert final_state["results"][1]["error"] is None
