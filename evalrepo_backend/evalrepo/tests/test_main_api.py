from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks, HTTPException

import main
from errors import FatalEvaluationError


def run(coro):
    return asyncio.run(coro)


# Prueba para que _deep_merge fusione secciones anidadas sin perder claves
def test_deep_merge_fusiona_anidado_sin_perder_claves():
    base = {"versionado": {"peso": 40, "commits_min": 10, "ramas": {"min_ramas": 2}}}
    override = {"versionado": {"commits_min": 5}}
    merged = main._deep_merge(base, override)
    assert merged["versionado"]["commits_min"] == 5
    assert merged["versionado"]["peso"] == 40
    assert merged["versionado"]["ramas"] == {"min_ramas": 2}


# Prueba para que _deep_merge reemplace listas completas en vez de mezclarlas
def test_deep_merge_reemplaza_listas_completas():
    base = {"estructural": {"archivos_requeridos": ["README.md", "src/"]}}
    override = {"estructural": {"archivos_requeridos": ["otra_cosa.md"]}}
    merged = main._deep_merge(base, override)
    assert merged["estructural"]["archivos_requeridos"] == ["otra_cosa.md"]


# Prueba para que start_evaluation rechace una lista vacia de repositorios
def test_start_evaluation_lista_vacia():
    req = main.EvaluationRequest(repo_urls=[], github_token="t")
    with pytest.raises(HTTPException) as exc_info:
        run(main.start_evaluation(req, BackgroundTasks()))
    assert exc_info.value.status_code == 400


# Prueba para que start_evaluation devuelva 503 si Supabase esta mal configurado
def test_start_evaluation_supabase_mal_configurado():
    def broken_db():
        raise RuntimeError("SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar configurados en .env")

    with patch.object(main, "db", broken_db):
        req = main.EvaluationRequest(repo_urls=["https://github.com/a/b"], github_token="t")
        with pytest.raises(HTTPException) as exc_info:
            run(main.start_evaluation(req, BackgroundTasks()))
    assert exc_info.value.status_code == 503
    assert "SUPABASE_URL" in exc_info.value.detail


# Prueba para que start_evaluation rechace criterios invalidos con pesos que no suman 100
def test_start_evaluation_criterios_invalidos():
    req = main.EvaluationRequest(
        repo_urls=["https://github.com/a/b"], github_token="t",
        criteria={"estructural": {"peso": 999}},
    )
    with pytest.raises(HTTPException) as exc_info:
        run(main.start_evaluation(req, BackgroundTasks()))
    assert exc_info.value.status_code == 400


# Prueba para que start_evaluation funcione con una lista valida y Supabase simulado
def test_start_evaluation_exitoso(fake_db):
    with patch.object(main, "db", lambda: fake_db):
        req = main.EvaluationRequest(repo_urls=["https://github.com/a/b"], github_token="t")
        result = run(main.start_evaluation(req, BackgroundTasks()))
    assert result["status"] == "pending"
    assert fake_db.store["evaluations"][0]["status"] == "pending"


# Prueba para que override_score rechace un puntaje fuera de rango
def test_override_score_rechaza_fuera_de_rango():
    body = main.ScoreOverrideRequest(score=150.0)
    with pytest.raises(HTTPException) as exc_info:
        run(main.override_score("ev1", "juan", "repo", body))
    assert exc_info.value.status_code == 400


def seed_evaluation_y_resultado(fake_db, **content_overrides):
    fake_db.store["evaluations"] = [{"id": "ev1", "criteria": {"contenido": {"peso": 20}}, "consolidated_report": None}]
    content = {
        "score": 0, "max_score": 20, "requirements_found": [], "requirements_missing": [],
        "coherence_level": "Baja", "llm_summary": "", "details": {}, "branch_requirements": [],
    }
    content.update(content_overrides)
    fake_db.store["repo_results"] = [{
        "id": "r1", "evaluation_id": "ev1", "url": "x", "owner": "juan", "repo_name": "repo",
        "student": "juan", "global_score": 50.0, "alerts": [], "pattern_label": "X",
        "structural_result": {
            "score": 25, "max_score": 25, "files_found": [], "files_missing": [], "readme_ok": True,
            "readme_char_count": 300, "details": {"readme_min_chars": 200}, "branch_checks": [], "alternative_checks": [],
        },
        "versioning_result": {
            "score": 15, "max_score": 40, "total_commits": 3, "commits_ok": True, "quality_ok": True,
            "quality_pct": 90, "branch_count": 1, "branches_ok": False, "generic_messages": [],
            "details": {"commits_min": 3, "min_ramas": 2, "quality_umbral": 70},
        },
        "temporal_result": {
            "score": 10, "max_score": 25, "weekly_counts": {}, "weekly_breakdown": [],
            "active_weeks": 1, "total_weeks": 2, "concentration_pct": 0, "on_time": True,
        },
        "content_result": content,
        "report_html": "<html>old</html>", "error": None,
        "score_overridden": False, "original_score": None, "override_note": None,
    }]


# Prueba para que override_score guarde el puntaje original solo la primera vez
def test_override_score_guarda_original_una_sola_vez(fake_db):
    seed_evaluation_y_resultado(fake_db)
    with patch.object(main, "db", lambda: fake_db):
        body = main.ScoreOverrideRequest(score=90.0, note="primer ajuste")
        run(main.override_score("ev1", "juan", "repo", body))
        row = fake_db.store["repo_results"][0]
        assert row["original_score"] == 50.0

        body2 = main.ScoreOverrideRequest(score=70.0, note="segundo ajuste")
        run(main.override_score("ev1", "juan", "repo", body2))
        row = fake_db.store["repo_results"][0]
        assert row["original_score"] == 50.0
        assert row["global_score"] == 70.0


# Prueba para que override_content_score rechace pesos que superen el maximo de Contenido
def test_override_content_score_rechaza_exceso_de_peso(fake_db):
    seed_evaluation_y_resultado(fake_db)
    with patch.object(main, "db", lambda: fake_db):
        body = main.ContentOverrideRequest(requirements=[
            main.RequirementScoreInput(requirement="a", weight_pct=15, achieved_pct=100),
            main.RequirementScoreInput(requirement="b", weight_pct=10, achieved_pct=100),
        ])
        with pytest.raises(HTTPException) as exc_info:
            run(main.override_content_score("ev1", "juan", "repo", body))
    assert exc_info.value.status_code == 400
    assert "20" in exc_info.value.detail


# Prueba para que override_content_score calcule correctamente el puntaje ponderado
def test_override_content_score_calcula_puntaje(fake_db):
    seed_evaluation_y_resultado(fake_db)
    with patch.object(main, "db", lambda: fake_db):
        body = main.ContentOverrideRequest(requirements=[
            main.RequirementScoreInput(requirement="usa herencia", weight_pct=10, achieved_pct=100),
            main.RequirementScoreInput(requirement="usa SOLID", weight_pct=10, achieved_pct=50),
        ])
        result = run(main.override_content_score("ev1", "juan", "repo", body))
    assert result["content"]["score"] == 15.0
    # global = estructural(25) + versionado(15) + temporal(10) + contenido(15) = 65
    assert result["global_score"] == 65.0


# Prueba para que override_content_score rechace un cuerpo sin requisitos
def test_override_content_score_sin_requisitos(fake_db):
    seed_evaluation_y_resultado(fake_db)
    with patch.object(main, "db", lambda: fake_db):
        body = main.ContentOverrideRequest(requirements=[])
        with pytest.raises(HTTPException) as exc_info:
            run(main.override_content_score("ev1", "juan", "repo", body))
    assert exc_info.value.status_code == 400


# Prueba para que override_score lance 404 si la evaluacion no existe
def test_override_score_evaluacion_inexistente(fake_db):
    with patch.object(main, "db", lambda: fake_db):
        body = main.ScoreOverrideRequest(score=80.0)
        with pytest.raises(HTTPException) as exc_info:
            run(main.override_score("no-existe", "juan", "repo", body))
    assert exc_info.value.status_code == 404


# Prueba para que _run_evaluation marque la evaluacion como error con mensaje claro ante un error fatal
def test_run_evaluation_error_fatal(fake_db):
    fake_db.store["evaluations"] = [{"id": "ev1", "status": "running"}]
    with patch.object(main, "db", lambda: fake_db):
        with patch("main.build_graph") as mock_build:
            mock_build.return_value.invoke.side_effect = FatalEvaluationError("token invalido")
            run(main._run_evaluation("ev1", ["https://github.com/a/b"], {}, "bad-token"))
    row = fake_db.store["evaluations"][0]
    assert row["status"] == "error"
    assert row["errors"] == ["token invalido"]


# Prueba para que _run_evaluation marque un error generico con un mensaje envuelto
def test_run_evaluation_error_generico(fake_db):
    fake_db.store["evaluations"] = [{"id": "ev1", "status": "running"}]
    with patch.object(main, "db", lambda: fake_db):
        with patch("main.build_graph") as mock_build:
            mock_build.return_value.invoke.side_effect = ValueError("algo raro")
            run(main._run_evaluation("ev1", ["https://github.com/a/b"], {}, "token"))
    row = fake_db.store["evaluations"][0]
    assert row["status"] == "error"
    assert "Error inesperado" in row["errors"][0]


# Prueba para que _run_evaluation termine en estado done cuando todo sale bien
def test_run_evaluation_exitoso(fake_db):
    fake_db.store["evaluations"] = [{"id": "ev1", "status": "running"}]
    final_state = {"results": [], "errors": [], "consolidated_report": "<html></html>"}
    with patch.object(main, "db", lambda: fake_db):
        with patch("main.build_graph") as mock_build:
            mock_build.return_value.invoke.return_value = final_state
            run(main._run_evaluation("ev1", ["https://github.com/a/b"], {}, "token"))
    row = fake_db.store["evaluations"][0]
    assert row["status"] == "done"


# Prueba para que _mark_evaluation_error no lance si Supabase tambien esta caido
def test_mark_evaluation_error_no_lanza_si_supabase_falla():
    def broken_db():
        raise RuntimeError("Supabase caido")

    with patch.object(main, "db", broken_db):
        main._mark_evaluation_error("ev1", "mensaje de error")  # no debe lanzar


# Prueba para que get_evaluation_status lance 404 cuando la evaluacion no existe
def test_get_evaluation_status_no_encontrada(fake_db):
    with patch.object(main, "db", lambda: fake_db):
        with pytest.raises(HTTPException) as exc_info:
            run(main.get_evaluation_status("no-existe"))
    assert exc_info.value.status_code == 404


# Prueba para que get_evaluation_results rechace una evaluacion que aun no termino
def test_get_evaluation_results_evaluacion_incompleta(fake_db):
    fake_db.store["evaluations"] = [{"id": "ev1", "status": "running"}]
    with patch.object(main, "db", lambda: fake_db):
        with pytest.raises(HTTPException) as exc_info:
            run(main.get_evaluation_results("ev1"))
    assert exc_info.value.status_code == 409


# Prueba para que validate_criteria detecte criterios correctos
def test_validate_criteria_endpoint_correctos():
    from tests.conftest import base_criteria

    result = run(main.validate_criteria(base_criteria()))
    assert result == {"valid": True}


# Prueba para que validate_criteria detecte criterios incorrectos sin lanzar excepcion
def test_validate_criteria_endpoint_incorrectos():
    result = run(main.validate_criteria({"estructural": {"peso": 999}}))
    assert result["valid"] is False
    assert "error" in result
