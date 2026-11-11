from __future__ import annotations

from agents.coordinator import coordinator_agent, should_continue, _generate_alerts, _detect_massive_commits
from tests.conftest import base_criteria, base_repo_data


def make_state(**overrides):
    state = {
        "current_repo_data": base_repo_data(),
        "current_index": 0,
        "repo_urls": ["https://github.com/juan/proyecto"],
        "criteria": base_criteria(),
        "structural_result": {"score": 20.0, "max_score": 25.0},
        "versioning_result": {"score": 30.0, "max_score": 40.0},
        "temporal_result": {"score": 20.0, "max_score": 25.0, "pattern_label": "Trabajo continuo"},
        "content_result": {"score": 8.0, "max_score": 10.0},
        "results": [],
    }
    state.update(overrides)
    return state


# Prueba para que un repo sin datos extraidos quede marcado como error
def test_coordinator_repo_sin_datos_queda_como_error():
    state = make_state(current_repo_data=None)
    result = coordinator_agent(state)
    assert result["results"][0]["error"] == "No se pudo extraer el repositorio."
    assert result["results"][0]["pattern_label"] == "Error"
    assert result["current_index"] == 1


# Prueba para que el puntaje global sea la suma de los cuatro puntajes parciales
def test_coordinator_suma_los_cuatro_puntajes():
    state = make_state()
    result = coordinator_agent(state)
    assert result["results"][0]["global_score"] == 78.0


# Prueba para que el puntaje global nunca supere 100
def test_coordinator_puntaje_global_no_supera_100():
    state = make_state(
        structural_result={"score": 50.0, "max_score": 25.0},
        versioning_result={"score": 50.0, "max_score": 40.0},
    )
    result = coordinator_agent(state)
    assert result["results"][0]["global_score"] == 100.0


# Prueba para que el indice avance despues de procesar un repo
def test_coordinator_avanza_el_indice():
    state = make_state(current_index=2)
    result = coordinator_agent(state)
    assert result["current_index"] == 3


# Prueba para que el patron de trabajo se tome del resultado temporal
def test_coordinator_propaga_pattern_label():
    state = make_state()
    result = coordinator_agent(state)
    assert result["results"][0]["pattern_label"] == "Trabajo continuo"


# Prueba para que should_continue siga mientras queden repos
def test_should_continue_quedan_repos():
    state = {"current_index": 1, "repo_urls": ["a", "b", "c"]}
    assert should_continue(state) == "next_repo"


# Prueba para que should_continue termine cuando ya no quedan repos
def test_should_continue_no_quedan_repos():
    state = {"current_index": 3, "repo_urls": ["a", "b", "c"]}
    assert should_continue(state) == "end"


# Prueba para la alerta de concentracion de commits al final
def test_generate_alerts_concentracion_final():
    temporal = {"concentration_alert": True, "concentration_pct": 85.0}
    versioning = {}
    criteria = base_criteria()
    alerts = _generate_alerts(temporal, versioning, base_repo_data(), criteria)
    assert any("85%" in a for a in alerts)


# Prueba para la alerta de entrega despues de la fecha limite
def test_generate_alerts_entrega_tardia():
    temporal = {"last_commit_date": "2026-09-05T10:00:00+00:00", "on_time": False}
    alerts = _generate_alerts(temporal, {}, base_repo_data(), base_criteria())
    assert any("después de la fecha límite" in a for a in alerts)


# Prueba para la alerta de semanas consecutivas sin actividad
def test_generate_alerts_inactividad_prolongada():
    temporal = {
        "weekly_counts": {},
        "total_weeks": 5,
    }
    repo_data = base_repo_data(periodo_inicio="2026-06-01T00:00:00+00:00")
    criteria = base_criteria()
    criteria["temporal"]["alerta_inactividad"] = {"habilitado": True, "semanas_consecutivas": 2}
    alerts = _generate_alerts(temporal, {}, repo_data, criteria)
    assert any("semanas consecutivas sin actividad" in a for a in alerts)


# Prueba para detectar commits masivos en una ventana corta de tiempo
def test_detect_massive_commits_detecta_rafaga():
    commits = [
        {"date": f"2026-06-01T10:0{i}:00+00:00"} for i in range(5)
    ]
    assert _detect_massive_commits(commits, threshold=5, window_hours=1) is True


# Prueba para que no se detecten commits masivos cuando estan bien distribuidos
def test_detect_massive_commits_no_detecta_cuando_distribuidos():
    commits = [
        {"date": "2026-06-01T10:00:00+00:00"},
        {"date": "2026-06-15T10:00:00+00:00"},
        {"date": "2026-07-01T10:00:00+00:00"},
    ]
    assert _detect_massive_commits(commits, threshold=3, window_hours=1) is False


# Prueba para que no se generen alertas cuando todo esta en orden
def test_generate_alerts_sin_alertas_cuando_todo_bien():
    temporal = {
        "concentration_alert": False,
        "last_commit_date": "2026-06-01T10:00:00+00:00",
        "on_time": True,
        "weekly_counts": {"2026-W22": 3},
        "total_weeks": 1,
    }
    repo_data = base_repo_data(periodo_inicio="2026-06-01T00:00:00+00:00", commits=[
        {"date": "2026-06-01T10:00:00+00:00"},
    ])
    alerts = _generate_alerts(temporal, {}, repo_data, base_criteria())
    assert alerts == []
