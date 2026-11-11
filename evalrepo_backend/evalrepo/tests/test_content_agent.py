from __future__ import annotations

from unittest.mock import patch

import anthropic
import httpx
import pytest

from agents import content
from errors import FatalEvaluationError
from tests.conftest import base_repo_data


def anthropic_error(cls, message="error"):
    """Arma una excepcion real del SDK de anthropic con un response httpx valido."""
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(401, request=req, json={"error": {"message": message}})
    return cls(message, response=resp, body=None)


# Prueba para un repo sin requisitos ni codigo, no deberia llamar a Claude
def test_content_sin_requisitos_ni_codigo():
    repo_data = base_repo_data(code_files={}, branch_content={})
    cfg = {"peso": 10, "requisitos_funcionales": []}
    with patch.object(content, "_call_claude") as mock_call:
        result = content._analyze(repo_data, cfg)
        mock_call.assert_not_called()
    assert result["score"] == 0.0


# Prueba para requisitos con peso explicito que suman el presupuesto completo
def test_content_peso_explicito_suma_presupuesto():
    repo_data = base_repo_data(code_files={"src/a.py": "class A: pass"})
    cfg = {
        "peso": 20,
        "requisitos_funcionales": [
            {"texto": "usa herencia", "peso_pct": 10},
            {"texto": "usa SOLID", "peso_pct": 10},
        ],
    }
    with patch.object(content, "_call_claude", return_value={
        "requirements_found": ["usa herencia"], "requirements_missing": ["usa SOLID"],
        "coherence_level": "Alta", "summary": "bien",
    }):
        result = content._analyze(repo_data, cfg)
    assert result["details"]["requisitos_pesos"] == {"usa herencia": 10, "usa SOLID": 10}
    # req_score = 10/20 = 0.5 ; coherencia Alta = 1.0 ; raw = 0.5*0.7+1.0*0.3 = 0.65 -> 13.0
    assert result["score"] == 13.0


# Prueba para requisitos sin peso que reparten lo que sobra del presupuesto
def test_content_peso_automatico_reparte_lo_que_sobra():
    repo_data = base_repo_data(code_files={"src/a.py": "x"})
    cfg = {
        "peso": 20,
        "requisitos_funcionales": [
            {"texto": "usa herencia", "peso_pct": 12},
            "usa SOLID",
            "usa condicionales",
        ],
    }
    with patch.object(content, "_call_claude", return_value={
        "requirements_found": [], "requirements_missing": [], "coherence_level": "Baja", "summary": "",
    }):
        result = content._analyze(repo_data, cfg)
    pesos = result["details"]["requisitos_pesos"]
    assert pesos["usa herencia"] == 12
    assert pesos["usa SOLID"] == 4.0
    assert pesos["usa condicionales"] == 4.0


# Prueba para que pesos que superan el presupuesto se reescalen proporcionalmente
def test_content_pesos_excedidos_se_reescalan():
    repo_data = base_repo_data(code_files={"src/a.py": "x"})
    cfg = {
        "peso": 10,
        "requisitos_funcionales": [
            {"texto": "req1", "peso_pct": 80},
            {"texto": "req2", "peso_pct": 80},
        ],
    }
    with patch.object(content, "_call_claude", return_value={
        "requirements_found": [], "requirements_missing": [], "coherence_level": "Baja", "summary": "",
    }):
        result = content._analyze(repo_data, cfg)
    pesos = result["details"]["requisitos_pesos"]
    assert pesos["req1"] == 5.0
    assert pesos["req2"] == 5.0


# Prueba para que la dimension deshabilitada devuelva un resultado vacio sin llamar a Claude
def test_content_agent_dimension_deshabilitada():
    state = {
        "current_repo_data": base_repo_data(),
        "criteria": {"contenido": {"habilitado": False, "peso": 10}},
    }
    with patch.object(content, "_call_claude") as mock_call:
        result = content.content_agent(state)
        mock_call.assert_not_called()
    assert result["content_result"]["score"] == 0.0


# Prueba para que el agente no haga nada si no hay repo_data
def test_content_agent_sin_repo_data():
    state = {"current_repo_data": None, "criteria": {"contenido": {}}}
    result = content.content_agent(state)
    assert result == {}


# Prueba para que una API key invalida de Claude corte toda la evaluacion
def test_content_agent_api_key_invalida_es_fatal():
    state = {
        "current_repo_data": base_repo_data(code_files={"a.py": "x"}),
        "criteria": {"contenido": {"habilitado": True, "peso": 10, "requisitos_funcionales": ["x"]}},
    }
    err = anthropic_error(anthropic.AuthenticationError, "invalid x-api-key")
    with patch.object(content, "_call_claude", side_effect=err):
        with pytest.raises(FatalEvaluationError, match="ANTHROPIC_API_KEY"):
            content.content_agent(state)


# Prueba para que la falta de permisos sobre el modelo corte toda la evaluacion
def test_content_agent_sin_permiso_de_modelo_es_fatal():
    state = {
        "current_repo_data": base_repo_data(code_files={"a.py": "x"}),
        "criteria": {"contenido": {"habilitado": True, "peso": 10, "requisitos_funcionales": ["x"]}},
    }
    err = anthropic_error(anthropic.PermissionDeniedError, "no access")
    with patch.object(content, "_call_claude", side_effect=err):
        with pytest.raises(FatalEvaluationError, match="permiso"):
            content.content_agent(state)


# Prueba para que un error generico de Claude no sea fatal, solo degrade ese repo
def test_content_agent_error_generico_no_es_fatal():
    state = {
        "current_repo_data": base_repo_data(code_files={"a.py": "x"}),
        "criteria": {"contenido": {"habilitado": True, "peso": 10, "requisitos_funcionales": ["x"]}},
    }
    with patch.object(content, "_call_claude", side_effect=TimeoutError("se colgo")):
        result = content.content_agent(state)
    assert result["content_result"]["score"] == 0.0
    assert "se colgo" in result["content_result"]["llm_summary"]


# Prueba para extraer JSON envuelto en un bloque de markdown
def test_parse_json_response_con_bloque_markdown():
    texto = '```json\n{"requirements_found": ["x"]}\n```'
    parsed = content._parse_json_response(texto)
    assert parsed == {"requirements_found": ["x"]}


# Prueba para que un JSON invalido devuelva un diccionario vacio sin lanzar
def test_parse_json_response_invalido_devuelve_vacio():
    parsed = content._parse_json_response("esto no es json")
    assert parsed == {}


# Prueba para que todos los requisitos por rama se resuelvan en una sola llamada
def test_analyze_branches_una_sola_llamada_para_varias_ramas():
    rama_items = {
        "prompts": [{"texto": "documenta prompts", "peso_pct": 5, "rama": "prompts"}],
        "docs": [{"texto": "tiene diagrama", "peso_pct": 5, "rama": "docs"}],
    }
    branch_content = {
        "prompts": {"README.md": "prompt usado: x"},
        "docs": {"README.md": "sin diagrama"},
    }
    with patch.object(content, "_call_claude", return_value={
        "branches": [
            {"branch": "prompts", "requirements_found": ["documenta prompts"], "requirements_missing": [], "summary": "ok"},
            {"branch": "docs", "requirements_found": [], "requirements_missing": ["tiene diagrama"], "summary": "falta"},
        ]
    }) as mock_call:
        resultados = content._analyze_branches(rama_items, branch_content)
        assert mock_call.call_count == 1
    por_rama = {r["branch"]: r for r in resultados}
    assert por_rama["prompts"]["requirements_found"] == ["documenta prompts"]
    assert por_rama["docs"]["requirements_missing"] == ["tiene diagrama"]


# Prueba para una rama sin los archivos solicitados, no deberia llamar a Claude
def test_analyze_branches_sin_archivos_no_llama_a_claude():
    rama_items = {"prompts": [{"texto": "documenta prompts", "peso_pct": 5, "rama": "prompts"}]}
    with patch.object(content, "_call_claude") as mock_call:
        resultados = content._analyze_branches(rama_items, {})
        mock_call.assert_not_called()
    assert resultados[0]["requirements_missing"] == ["documenta prompts"]


# Prueba para que _tag_items acepte tanto strings simples como diccionarios con peso
def test_tag_items_acepta_string_y_dict():
    items = content._tag_items(["simple", {"texto": "con peso", "peso_pct": 15}], rama=None)
    assert items[0] == {"texto": "simple", "peso_pct": None, "rama": None}
    assert items[1] == {"texto": "con peso", "peso_pct": 15, "rama": None}


# Prueba para que la coherencia alta otorgue mas puntaje que la coherencia baja
def test_content_coherencia_afecta_puntaje():
    repo_data = base_repo_data(code_files={"a.py": "x"})
    cfg = {"peso": 10, "requisitos_funcionales": [{"texto": "r1", "peso_pct": 0}]}
    with patch.object(content, "_call_claude", return_value={
        "requirements_found": [], "requirements_missing": ["r1"], "coherence_level": "Alta", "summary": "",
    }):
        alta = content._analyze(repo_data, cfg)
    with patch.object(content, "_call_claude", return_value={
        "requirements_found": [], "requirements_missing": ["r1"], "coherence_level": "Baja", "summary": "",
    }):
        baja = content._analyze(repo_data, cfg)
    assert alta["score"] > baja["score"]
