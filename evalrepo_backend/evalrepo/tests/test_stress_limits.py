"""
Pruebas de estres: no verifican "funciona o no funciona", sino hasta que
tamano de datos la app sigue respondiendo en un tiempo razonable y donde
empieza a degradarse. Cada prueba imprime los tiempos medidos (correr con
`pytest -s tests/test_stress_limits.py` para verlos) ademas de dejar un
assert de regresion para que una corrida normal de CI detecte si algo
empeoro sin querer.

No se llama a GitHub, Claude ni Supabase reales: el estres es sobre la
logica propia del backend (el unico costo real de red en produccion es la
cantidad de llamadas a esas APIs, que ya se documenta aparte).
"""

from __future__ import annotations

import io
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import openpyxl
import pytest

from agents import content
from agents.coordinator import _detect_massive_commits
from agents.structural import _analyze as analyze_structural
from agents.versioning import _analyze_versioning, _analyze_temporal
from errors import FatalEvaluationError
from graph import build_graph, initial_state
from reports.generator import generate_excel, render_individual
from tests.conftest import base_criteria, base_repo_data


def medir(fn, *args, **kwargs):
    t0 = time.perf_counter()
    resultado = fn(*args, **kwargs)
    return resultado, time.perf_counter() - t0


# Prueba para encontrar el punto donde la deteccion de commits masivos se
# vuelve cuadratica (O(n^2)) y empieza a notarse. Caso peor: ningun commit
# dispara la alerta, asi que el algoritmo recorre toda la lista sin cortar.
@pytest.mark.parametrize("n_commits", [500, 2000, 5000, 10000])
def test_limite_deteccion_commits_masivos(n_commits):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    commits = [{"date": (base + timedelta(hours=2 * i)).isoformat()} for i in range(n_commits)]
    _, segundos = medir(_detect_massive_commits, commits, 20, 1)
    print(f"\n[commits_masivos] {n_commits} commits -> {segundos:.4f}s")
    # umbral generoso a proposito: en una Mac tarda ~1.5s a 10000 commits, pero
    # en runners compartidos de CI (mas lentos y con CPU variable) se midio
    # hasta 7.7s para el mismo caso -- esto solo debe fallar ante una
    # regresion real (ej. si deja de ser O(n^2) y pasa a ser mas lento aun)
    assert segundos < 20.0


# Prueba para documentar el techo real: a partir de que cantidad de commits
# un solo repositorio tarda mas de 10 segundos solo en esta verificacion
def test_limite_deteccion_commits_masivos_techo_20000():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    commits = [{"date": (base + timedelta(hours=2 * i)).isoformat()} for i in range(20000)]
    _, segundos = medir(_detect_massive_commits, commits, 20, 1)
    print(f"\n[commits_masivos] 20000 commits -> {segundos:.4f}s (limite practico)")
    # no es un assert de "deberia pasar rapido" -- es la documentacion del techo:
    # a este tamano ya tarda varios segundos un solo repo, solo en este chequeo.
    # umbral generoso (ver comentario de arriba sobre runners de CI mas lentos)
    assert segundos < 60.0


# Prueba para ver si la alerta SI se dispara temprano (early exit), el tiempo
# deberia ser mucho menor que el peor caso con la misma cantidad de commits
def test_deteccion_commits_masivos_con_corte_temprano_es_mas_rapida():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # los primeros 25 commits estan todos pegados (deberian disparar la alerta
    # de inmediato), el resto bien espaciado
    commits = [{"date": (base + timedelta(minutes=i)).isoformat()} for i in range(25)]
    commits += [{"date": (base + timedelta(hours=2 * i)).isoformat()} for i in range(10000)]
    resultado, segundos = medir(_detect_massive_commits, commits, 20, 1)
    print(f"\n[commits_masivos] corte temprano con {len(commits)} commits -> {segundos:.4f}s")
    assert resultado is True
    assert segundos < 0.5


# Prueba para un repositorio con una cantidad extrema de archivos (50000) y
# muchos requisitos estructurales a la vez
def test_limite_structural_con_50000_archivos():
    archivos = [f"src/modulo_{i}/archivo_{i}.py" for i in range(50000)]
    repo_data = base_repo_data(files=archivos, readme_content="x" * 300)
    cfg = {
        "peso": 25,
        "archivos_requeridos": [f"src/modulo_{i}/" for i in range(0, 50000, 5000)],
        "readme_min_chars": 200,
        "archivos_alternativos": [
            {"nombre": f"archivo_{i}.py", "carpetas": ["src/"]} for i in range(0, 1000, 100)
        ],
    }
    resultado, segundos = medir(analyze_structural, repo_data, cfg)
    print(f"\n[structural] 50000 archivos, {len(cfg['archivos_requeridos'])} requeridos, "
          f"{len(cfg['archivos_alternativos'])} alternativos -> {segundos:.4f}s")
    assert resultado["score"] == resultado["max_score"]
    assert segundos < 5.0


# Prueba para un repositorio con una cantidad extrema de commits (30000) en
# el analisis de versionado y temporal completo, sin pasar por la deteccion
# cuadratica de commits masivos (que ya se mide aparte)
def test_limite_versioning_con_30000_commits():
    criteria = base_criteria()
    criteria["temporal"]["alerta_concentracion"]["habilitado"] = False
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    commits = [
        {
            "sha": f"{i:08x}"[:8], "message": f"Commit numero {i}", "author": f"autor{i % 50}",
            "date": (base + timedelta(hours=i)).isoformat(),
        }
        for i in range(30000)
    ]
    repo_data = base_repo_data(commits=commits, periodo_inicio=base.isoformat())

    _, segundos_v = medir(_analyze_versioning, repo_data, criteria)
    print(f"\n[versionado] 30000 commits -> {segundos_v:.4f}s")
    assert segundos_v < 5.0


# Prueba para el calculo de pesos de contenido con una cantidad extrema de
# requisitos (10000), para confirmar que el reparto sigue siendo lineal
def test_limite_content_con_10000_requisitos():
    items = [{"texto": f"requisito {i}", "peso_pct": None, "rama": None} for i in range(10000)]
    _, segundos = medir(content._fill_missing_weights, items, 100.0)
    print(f"\n[contenido] 10000 requisitos -> {segundos:.4f}s")
    suma = sum(i["peso_pct"] for i in items)
    assert abs(suma - 100.0) < 0.01
    assert segundos < 2.0


# Prueba para generar un Excel con muchas filas (una por cada repo evaluado
# en un ciclo grande, ej. varias secciones de la misma asignatura)
def test_limite_generate_excel_con_1000_filas():
    resultados = []
    for i in range(1000):
        resultados.append({
            "student": f"estudiante{i}", "repo_name": "proyecto", "url": "x",
            "global_score": i % 100, "pattern_label": "X", "alerts": [],
            "score_overridden": False, "override_note": None, "error": None,
            "structural": {"score": 20, "files_missing": [], "readme_ok": True, "readme_char_count": 300,
                           "branch_checks": [], "alternative_checks": []},
            "versioning": {"score": 30, "total_commits": 10, "details": {"commits_min": 3}, "quality_pct": 80,
                           "generic_messages": [], "branch_count": 2, "branch_names": ["main", "dev"], "contributors": []},
            "temporal": {"score": 20, "on_time": True, "last_commit_date": None, "active_weeks": 1,
                         "total_weeks": 2, "concentration_alert": False},
            "content": {"score": 8, "coherence_level": "Alta", "requirements_missing": [], "llm_summary": "",
                        "details": {}, "branch_requirements": []},
        })
    data, segundos = medir(generate_excel, resultados)
    print(f"\n[excel] 1000 filas -> {segundos:.4f}s, {len(data)} bytes")
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.active.max_row == 1001
    assert segundos < 10.0


# Prueba para renderizar el informe individual con un historial de commits
# enorme (5000 commits en el detalle del reporte HTML)
def test_limite_render_individual_con_5000_commits_en_historial():
    commit_log = [
        {"date": f"2026-06-01T10:{i % 60:02d}:00+00:00", "author": f"autor{i % 20}", "message": f"commit {i}"}
        for i in range(5000)
    ]
    result = {
        "student": "juan", "repo_name": "proyecto", "url": "x", "global_score": 80.0, "alerts": [],
        "pattern_label": "X", "score_overridden": False, "original_score": None, "override_note": None,
        "structural": {"files_found": [], "files_missing": [], "readme_exists": True, "readme_char_count": 300,
                       "readme_ok": True, "score": 20, "max_score": 25, "details": {"readme_min_chars": 200},
                       "branch_checks": [], "alternative_checks": []},
        "versioning": {"total_commits": 5000, "commits_ok": True, "branch_count": 1, "branch_names": ["main"],
                       "branches_ok": False, "quality_pct": 80, "quality_ok": True, "generic_messages": [],
                       "contributors": [{"author": f"autor{i}", "commits": 250} for i in range(20)],
                       "commit_log": commit_log, "score": 30, "max_score": 40,
                       "details": {"commits_min": 3, "min_ramas": 2, "quality_umbral": 70}},
        "temporal": {"last_commit_date": None, "on_time": True, "weekly_counts": {}, "weekly_breakdown": [],
                     "active_weeks": 1, "total_weeks": 2, "activity_ok": True, "concentration_pct": 0,
                     "concentration_alert": False, "pattern_label": "X", "score": 20, "max_score": 25, "details": {}},
        "content": {"requirements_found": [], "requirements_missing": [], "coherence_level": "Alta",
                    "llm_summary": "", "branch_requirements": [], "score": 8, "max_score": 10, "details": {}},
    }
    html, segundos = medir(render_individual, result, {})
    print(f"\n[render_individual] 5000 commits en historial -> {segundos:.4f}s, {len(html)} caracteres de HTML")
    assert "commit 4999" in html
    assert segundos < 5.0


# Prueba para correr el grafo completo con una cantidad grande de repositorios
# de una sola vez (el caso de uso real: un docente cargando todo un curso)
def test_limite_graph_con_50_repositorios():
    criteria = base_criteria()
    urls = [f"https://github.com/estudiante{i}/proyecto" for i in range(50)]
    state = initial_state(repo_urls=urls, criteria=criteria, github_token="t")
    graph = build_graph()

    with patch("agents.extraction._fetch_repo", return_value=base_repo_data()):
        with patch("agents.content._call_claude", return_value={
            "requirements_found": ["usa herencia"], "requirements_missing": [],
            "coherence_level": "Alta", "summary": "bien",
        }):
            final_state, segundos = medir(graph.invoke, state)

    print(f"\n[grafo] 50 repositorios -> {segundos:.4f}s ({segundos/50*1000:.1f}ms por repo, sin red real)")
    assert len(final_state["results"]) == 50
    assert segundos < 30.0


# Prueba para un mensaje de commit extremadamente largo (100000 caracteres),
# no deberia tardar de mas ni romper la deteccion de mensajes genericos
def test_limite_mensaje_de_commit_extremadamente_largo():
    criteria = base_criteria()
    mensaje_enorme = "a" * 100000
    repo_data = base_repo_data(commits=[
        {"sha": "x", "message": mensaje_enorme, "author": "juan", "date": "2026-06-01T10:00:00+00:00"},
    ])
    resultado, segundos = medir(_analyze_versioning, repo_data, criteria)
    print(f"\n[versionado] mensaje de {len(mensaje_enorme)} caracteres -> {segundos:.4f}s")
    assert segundos < 1.0


# Prueba para nombres con caracteres unicode y emojis en autor, rama y mensaje
def test_limite_caracteres_unicode_y_emojis_no_rompen_nada():
    criteria = base_criteria()
    repo_data = base_repo_data(
        commits=[{
            "sha": "x", "message": "Arregla el bug 🐛 en la función de validación ñandú",
            "author": "José Muñoz 😀", "date": "2026-06-01T10:00:00+00:00",
        }],
        branches=["main", "función-de-prueba-日本語"],
    )
    resultado = _analyze_versioning(repo_data, criteria)
    assert resultado["contributors"][0]["author"] == "José Muñoz 😀"


# Prueba para una fecha de commit en el limite extremo soportado por datetime.
# HALLAZGO: _analyze_temporal revienta con OverflowError si un commit cae tan
# cerca del año 9999 que "fin de semana + 6 dias" se sale del rango que
# datetime puede representar. No es un caso de la vida real (nadie tiene
# commits del año 9999), pero confirma que la funcion no esta blindada contra
# fechas corruptas/absurdas en el dato crudo de GitHub.
def test_limite_fecha_commit_año_maximo_revienta_en_la_funcion_interna():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        {"sha": "x", "message": "commit del futuro", "author": "juan", "date": "9999-12-31T23:59:59+00:00"},
    ])
    with pytest.raises(OverflowError):
        _analyze_temporal(repo_data, criteria)


# Prueba para confirmar que, aunque la funcion interna revienta, el agente que
# la llama SI absorbe el error (por el try/except agregado en versioning_agent)
# y el repo queda con 0 en vez de tumbar toda la evaluacion
def test_limite_fecha_commit_año_maximo_el_agente_lo_absorbe():
    from agents.versioning import versioning_agent

    criteria = base_criteria()
    repo_data = base_repo_data(commits=[
        {"sha": "x", "message": "commit del futuro", "author": "juan", "date": "9999-12-31T23:59:59+00:00"},
    ])
    state = {"current_repo_data": repo_data, "criteria": criteria, "errors": []}
    result = versioning_agent(state)
    assert result["temporal_result"]["score"] == 0.0
    assert len(result["errors"]) == 1


# Prueba para que un peso de Contenido en cero no produzca division por cero
def test_limite_peso_contenido_cero_no_rompe():
    repo_data = base_repo_data(code_files={"a.py": "x"})
    cfg = {"peso": 0, "requisitos_funcionales": ["usa herencia"]}
    with patch.object(content, "_call_claude", return_value={
        "requirements_found": ["usa herencia"], "requirements_missing": [], "coherence_level": "Alta", "summary": "",
    }):
        resultado = content._analyze(repo_data, cfg)
    assert resultado["score"] == 0.0


# Prueba para una lista de archivos requeridos vacia (el docente desactivo
# todos los checks estructurales salvo el README)
def test_limite_archivos_requeridos_vacio():
    repo_data = base_repo_data(readme_content="x" * 300)
    cfg = {"peso": 25, "archivos_requeridos": [], "readme_min_chars": 200}
    resultado = analyze_structural(repo_data, cfg)
    assert resultado["score"] == 25.0


# Prueba para un repositorio completamente vacio: sin commits, sin ramas,
# sin archivos, sin README -- el caso minimo real de una entrega en blanco.
# HALLAZGO: la dimension Temporal NO da 0 en este caso -- da 6.25/25. La razon
# es que "concentration_alert" se define como False cuando no hay commits (no
# hay nada que concentrar), y ese check vale 25% del puntaje temporal. Un repo
# completamente vacio termina con mas puntaje temporal que uno que si trabajo
# pero concentro todo al final. Es una inconsistencia logica del diseño actual,
# no un crash -- vale la pena documentarla para la tesis.
def test_limite_repositorio_completamente_vacio():
    criteria = base_criteria()
    repo_data = base_repo_data(commits=[], branches=[], files=[], readme_content="")
    v = _analyze_versioning(repo_data, criteria)
    t = _analyze_temporal(repo_data, criteria)
    s = analyze_structural(repo_data, criteria["estructural"])
    assert v["score"] == 0.0
    assert t["score"] == 6.25  # 25% del peso temporal, por "no concentracion" vacuamente verdadera
    assert s["score"] < s["max_score"]


# Prueba para que un error fatal a mitad de un lote grande corte todo de
# inmediato (no espera a procesar los 50 restantes con el mismo error)
def test_limite_error_fatal_corta_lote_grande_de_inmediato():
    criteria = base_criteria()
    urls = [f"https://github.com/estudiante{i}/proyecto" for i in range(50)]
    state = initial_state(repo_urls=urls, criteria=criteria, github_token="token-malo")
    graph = build_graph()

    llamadas = {"n": 0}

    def fetch_repo_side_effect(*a, **k):
        llamadas["n"] += 1
        raise FatalEvaluationError("token invalido")

    with patch("agents.extraction._fetch_repo", side_effect=fetch_repo_side_effect):
        with pytest.raises(FatalEvaluationError):
            graph.invoke(state)

    print(f"\n[corte temprano] se detuvo tras {llamadas['n']} intento(s) de 50 repos")
    assert llamadas["n"] == 1
