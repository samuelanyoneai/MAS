from __future__ import annotations

from unittest.mock import patch

from agents.versioning import versioning_agent, _analyze_versioning, _analyze_temporal
from tests.conftest import base_criteria, base_repo_data


def commit(date, message="Agrega validacion de entradas", author="juan"):
    return {"sha": "abc12345", "message": message, "author": author, "date": date}


# Prueba para que se cumpla el minimo de commits configurado
def test_versioning_commits_min_cumplido():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[commit(f"2026-06-{d:02d}T10:00:00+00:00") for d in range(1, 5)])
    result = _analyze_versioning(repo_data, criteria)
    assert result["total_commits"] == 4
    assert result["commits_ok"] is True


# Prueba para que no se cumpla el minimo de commits configurado
def test_versioning_commits_min_no_cumplido():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[commit("2026-06-01T10:00:00+00:00")])
    result = _analyze_versioning(repo_data, criteria)
    assert result["commits_ok"] is False


# Prueba para detectar mensajes genericos con los patrones por defecto
def test_versioning_detecta_mensajes_genericos():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        commit("2026-06-01T10:00:00+00:00", message="update"),
        commit("2026-06-02T10:00:00+00:00", message="fix"),
        commit("2026-06-03T10:00:00+00:00", message="Implementa validacion de formularios"),
    ])
    result = _analyze_versioning(repo_data, criteria)
    assert "update" in result["generic_messages"]
    assert "fix" in result["generic_messages"]
    assert result["quality_pct"] == round(1 / 3 * 100, 1)


# Prueba para que la calidad de mensajes se ignore si esta deshabilitada
def test_versioning_calidad_mensajes_deshabilitada_siempre_ok():
    criteria = base_criteria()
    criteria["versionado"]["calidad_mensajes"]["habilitado"] = False
    repo_data = base_repo_data(commits=[commit("2026-06-01T10:00:00+00:00", message="update")])
    result = _analyze_versioning(repo_data, criteria)
    assert result["quality_ok"] is True


# Prueba para que se cumpla el minimo de ramas
def test_versioning_ramas_suficientes():
    criteria = base_criteria()
    repo_data = base_repo_data(branches=["main", "feature/x"])
    result = _analyze_versioning(repo_data, criteria)
    assert result["branches_ok"] is True


# Prueba para que no se cumpla el minimo de ramas
def test_versioning_ramas_insuficientes():
    criteria = base_criteria()
    repo_data = base_repo_data(branches=["main"])
    result = _analyze_versioning(repo_data, criteria)
    assert result["branches_ok"] is False


# Prueba para que los colaboradores se cuenten y se ordenen por cantidad de commits
def test_versioning_contributors_ordenados_por_cantidad():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        commit("2026-06-01T10:00:00+00:00", author="ana"),
        commit("2026-06-02T10:00:00+00:00", author="juan"),
        commit("2026-06-03T10:00:00+00:00", author="juan"),
    ])
    result = _analyze_versioning(repo_data, criteria)
    assert result["contributors"][0] == {"author": "juan", "commits": 2}
    assert result["contributors"][1] == {"author": "ana", "commits": 1}


# Prueba para que un commit sin autor se cuente como Desconocido
def test_versioning_commit_sin_autor():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[{"sha": "x", "message": "x", "author": None, "date": "2026-06-01T10:00:00+00:00"}])
    result = _analyze_versioning(repo_data, criteria)
    assert result["contributors"][0]["author"] == "Desconocido"


# Prueba para que el historial de commits quede ordenado cronologicamente
def test_versioning_commit_log_ordenado():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        commit("2026-06-03T10:00:00+00:00"),
        commit("2026-06-01T10:00:00+00:00"),
        commit("2026-06-02T10:00:00+00:00"),
    ])
    result = _analyze_versioning(repo_data, criteria)
    fechas = [c["date"] for c in result["commit_log"]]
    assert fechas == sorted(fechas)


# Prueba para que la dimension deshabilitada devuelva un resultado vacio
def test_versioning_dimension_deshabilitada():
    criteria = base_criteria()
    criteria["versionado"]["habilitado"] = False
    repo_data = base_repo_data()
    result = _analyze_versioning(repo_data, criteria)
    assert result["score"] == 0.0
    assert result["max_score"] == 0.0


# Prueba para un repo sin ningun commit, no deberia romper nada
def test_versioning_sin_commits_no_rompe():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[])
    result = _analyze_versioning(repo_data, criteria)
    assert result["total_commits"] == 0
    assert result["quality_pct"] == 0.0


# Prueba para que la entrega a tiempo se detecte correctamente
def test_temporal_entrega_a_tiempo():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[commit("2026-07-01T10:00:00+00:00")])
    result = _analyze_temporal(repo_data, criteria)
    assert result["on_time"] is True


# Prueba para que la entrega tardia se detecte correctamente
def test_temporal_entrega_tardia():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[commit("2026-09-05T10:00:00+00:00")])
    result = _analyze_temporal(repo_data, criteria)
    assert result["on_time"] is False


# Prueba para que el desglose semanal traiga fechas reales, no "Semana N"
def test_temporal_weekly_breakdown_con_fechas_reales():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[commit("2026-06-22T09:00:00+00:00")])
    result = _analyze_temporal(repo_data, criteria)
    assert result["weekly_breakdown"][0]["start_date"] == "2026-06-22"
    assert result["weekly_breakdown"][0]["end_date"] == "2026-06-28"


# Prueba para que se dispare la alerta de concentracion al final
def test_temporal_concentracion_se_dispara():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        commit("2026-06-01T10:00:00+00:00"),
        commit("2026-08-30T10:00:00+00:00"),
        commit("2026-08-31T10:00:00+00:00"),
        commit("2026-09-01T10:00:00+00:00"),
    ])
    result = _analyze_temporal(repo_data, criteria)
    assert result["concentration_alert"] is True


# Prueba para que la alerta de concentracion se pueda deshabilitar
def test_temporal_concentracion_deshabilitada():
    criteria = base_criteria()
    criteria["temporal"]["alerta_concentracion"]["habilitado"] = False
    repo_data = base_repo_data(commits=[
        commit("2026-08-31T10:00:00+00:00"),
        commit("2026-09-01T10:00:00+00:00"),
    ])
    result = _analyze_temporal(repo_data, criteria)
    assert result["concentration_alert"] is False


# Prueba para el patron "Trabajo continuo"
def test_temporal_patron_trabajo_continuo():
    criteria = base_criteria(periodo={
        "inicio": "2026-06-01", "fin": "2026-06-22", "fecha_limite": "2026-06-22T23:59:00",
    })
    repo_data = base_repo_data(
        periodo_inicio="2026-06-01T00:00:00+00:00",
        commits=[commit(f"2026-06-0{d}T10:00:00+00:00") for d in range(1, 8, 2)],
    )
    result = _analyze_temporal(repo_data, criteria)
    assert result["pattern_label"] in ("Trabajo continuo", "Actividad irregular")


# Prueba para el patron "Concentracion al final"
def test_temporal_patron_concentracion_al_final():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        commit("2026-08-31T10:00:00+00:00"),
        commit("2026-09-01T10:00:00+00:00"),
    ])
    result = _analyze_temporal(repo_data, criteria)
    assert result["pattern_label"] == "Concentración al final"


# Prueba para que la dimension temporal deshabilitada devuelva resultado vacio
def test_temporal_dimension_deshabilitada():
    criteria = base_criteria()
    criteria["temporal"]["habilitado"] = False
    repo_data = base_repo_data()
    result = _analyze_temporal(repo_data, criteria)
    assert result["pattern_label"] == "Sin actividad"


# Prueba para que una fecha de commit invalida se ignore sin romper el analisis
def test_temporal_fecha_commit_invalida_se_ignora():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        {"sha": "x", "message": "x", "author": "juan", "date": "fecha-no-valida"},
        commit("2026-06-01T10:00:00+00:00"),
    ])
    result = _analyze_temporal(repo_data, criteria)
    assert result["active_weeks"] == 1


# Prueba para que una excepcion interna no tumbe el agente completo
def test_versioning_agent_degrada_en_vez_de_lanzar():
    state = {"current_repo_data": base_repo_data(), "criteria": base_criteria(), "errors": []}
    with patch("agents.versioning._analyze_versioning", side_effect=ValueError("dato raro")):
        result = versioning_agent(state)
    assert result["versioning_result"]["score"] == 0.0
    assert result["temporal_result"]["score"] == 0.0
    assert len(result["errors"]) == 1


# Prueba para que el agente no haga nada si no hay repo_data
def test_versioning_agent_sin_repo_data():
    state = {"current_repo_data": None, "criteria": base_criteria(), "errors": []}
    result = versioning_agent(state)
    assert result == {}
