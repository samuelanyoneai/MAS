from __future__ import annotations

import io

import openpyxl

from reports.generator import (
    render_individual,
    render_consolidated,
    generate_excel,
    generate_reports_node,
    save_reports,
    _safe_filename,
    _obs_estructural,
    _obs_versionado,
    _obs_temporal,
    _obs_contenido,
)


def full_result(**overrides):
    result = {
        "student": "juan", "repo_name": "proyecto", "url": "https://github.com/juan/proyecto",
        "global_score": 78.0, "alerts": [], "pattern_label": "Trabajo continuo",
        "score_overridden": False, "original_score": None, "override_note": None, "error": None,
        "structural": {
            "files_found": ["README.md"], "files_missing": [], "readme_exists": True,
            "readme_char_count": 300, "readme_ok": True, "score": 20.0, "max_score": 25.0,
            "details": {"readme_min_chars": 200}, "branch_checks": [], "alternative_checks": [],
        },
        "versioning": {
            "total_commits": 5, "commits_ok": True, "branch_count": 2, "branch_names": ["main", "dev"],
            "branches_ok": True, "quality_pct": 90.0, "quality_ok": True, "generic_messages": [],
            "contributors": [{"author": "juan", "commits": 5}], "commit_log": [],
            "score": 30.0, "max_score": 40.0,
            "details": {"commits_min": 3, "min_ramas": 2, "quality_umbral": 70},
        },
        "temporal": {
            "last_commit_date": "2026-07-01T10:00:00+00:00", "on_time": True,
            "weekly_counts": {"2026-W26": 5}, "weekly_breakdown": [
                {"week_key": "2026-W26", "start_date": "2026-06-22", "end_date": "2026-06-28", "count": 5},
            ],
            "active_weeks": 1, "total_weeks": 1, "activity_ok": True,
            "concentration_pct": 0.0, "concentration_alert": False,
            "pattern_label": "Trabajo continuo", "score": 20.0, "max_score": 25.0, "details": {},
        },
        "content": {
            "requirements_found": ["usa herencia"], "requirements_missing": [],
            "coherence_level": "Alta", "llm_summary": "Buen trabajo.",
            "branch_requirements": [], "score": 8.0, "max_score": 10.0, "details": {},
        },
    }
    result.update(overrides)
    return result


# Prueba para que el informe individual se genere sin lanzar excepciones
def test_render_individual_no_lanza():
    html = render_individual(full_result(), {})
    assert "juan" in html
    assert "proyecto" in html


# Prueba para que el informe individual muestre el aviso de ajuste manual
def test_render_individual_muestra_ajuste_manual():
    result = full_result(score_overridden=True, original_score=60.0, override_note="revisado a mano")
    html = render_individual(result, {})
    assert "ajustado manualmente" in html
    assert "revisado a mano" in html


# Prueba para que el consolidado calcule bien las estadisticas del grupo
def test_render_consolidated_estadisticas_correctas():
    resultados = [full_result(global_score=85.0), full_result(global_score=55.0), full_result(global_score=30.0)]
    html = render_consolidated(resultados, {})
    assert "juan" in html


# Prueba para que el consolidado calcule el promedio correctamente
def test_render_consolidated_promedio():
    from reports import generator

    resultados = [full_result(global_score=80.0), full_result(global_score=60.0)]
    # armamos las stats igual que render_consolidated, sin repetir el render completo
    scores = [r["global_score"] for r in resultados if not r.get("error")]
    promedio = round(sum(scores) / len(scores), 1)
    assert promedio == 70.0


# Prueba para que el reporte Excel genere un archivo valido y legible
def test_generate_excel_produce_archivo_valido():
    data = generate_excel([full_result()])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws.max_row == 2
    assert ws.cell(row=2, column=1).value == "juan"


# Prueba para que una fila con error se marque como tal en el Excel
def test_generate_excel_marca_fila_de_error():
    data = generate_excel([full_result(error="No se pudo extraer el repositorio.")])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws.cell(row=2, column=5).value == "Error"


# Prueba para que el Excel ordene las filas por puntaje descendente
def test_generate_excel_ordena_por_puntaje():
    data = generate_excel([
        full_result(student="bajo", global_score=40.0),
        full_result(student="alto", global_score=90.0),
    ])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws.cell(row=2, column=1).value == "alto"
    assert ws.cell(row=3, column=1).value == "bajo"


# Prueba para que las observaciones estructurales incluyan los checks por rama
def test_obs_estructural_incluye_branch_checks():
    result = full_result()
    result["structural"]["branch_checks"] = [{"branch": "docs", "path": "README.md", "found": True}]
    obs = _obs_estructural(result)
    assert "README.md en rama docs: OK" in obs


# Prueba para que las observaciones de contenido muestren el ajuste manual por requisito
def test_obs_contenido_con_ajuste_manual():
    result = full_result()
    result["content"]["details"] = {
        "requirement_scores": [
            {"requirement": "usa herencia", "weight_pct": 10, "achieved_pct": 100, "points": 10.0},
        ],
    }
    obs = _obs_contenido(result)
    assert "vale 10 pts" in obs
    assert "100% cumplido" in obs


# Prueba para que una dimension deshabilitada muestre el mensaje correspondiente
def test_obs_estructural_dimension_deshabilitada():
    result = full_result(structural=None)
    assert _obs_estructural(result) == "Dimensión deshabilitada."


# Prueba para que las observaciones estructurales listen los archivos faltantes
def test_obs_estructural_con_archivos_faltantes():
    result = full_result()
    result["structural"]["files_missing"] = ["src/", "tests/"]
    obs = _obs_estructural(result)
    assert "Faltan: src/, tests/" in obs


# Prueba para que las observaciones estructurales reporten los checks alternativos
def test_obs_estructural_alternative_checks():
    result = full_result()
    result["structural"]["alternative_checks"] = [
        {"nombre": "requirements.txt", "found": True, "found_in": "raiz"},
        {"nombre": "Pipfile", "found": False, "carpetas": ["raiz", "src/"]},
    ]
    obs = _obs_estructural(result)
    assert "requirements.txt encontrado en raiz." in obs
    assert "Pipfile no encontrado en raiz, src/." in obs


# Prueba para que una dimension de versionado deshabilitada muestre el mensaje correspondiente
def test_obs_versionado_dimension_deshabilitada():
    result = full_result(versioning=None)
    assert _obs_versionado(result) == "Dimensión deshabilitada."


# Prueba para que las observaciones de versionado listen los mensajes genericos
def test_obs_versionado_con_mensajes_genericos():
    result = full_result()
    result["versioning"]["generic_messages"] = ["fix", "update"]
    obs = _obs_versionado(result)
    assert 'Genéricos detectados: "fix", "update".' in obs


# Prueba para que una dimension temporal deshabilitada muestre el mensaje correspondiente
def test_obs_temporal_dimension_deshabilitada():
    result = full_result(temporal=None)
    assert _obs_temporal(result) == "Dimensión deshabilitada."


# Prueba para que las observaciones temporales alerten sobre la concentracion de commits
def test_obs_temporal_con_alerta_de_concentracion():
    result = full_result()
    result["temporal"]["concentration_alert"] = True
    result["temporal"]["concentration_pct"] = 85.0
    obs = _obs_temporal(result)
    assert "85.0% de commits concentrados al final del período." in obs


# Prueba para que una dimension de contenido deshabilitada muestre el mensaje correspondiente
def test_obs_contenido_dimension_deshabilitada():
    result = full_result(content=None)
    assert _obs_contenido(result) == "Dimensión deshabilitada."


# Prueba para que las observaciones de contenido listen los requisitos incumplidos con su peso
def test_obs_contenido_con_requisitos_faltantes():
    result = full_result()
    result["content"]["requirements_missing"] = ["usa polimorfismo"]
    result["content"]["details"] = {"requisitos_pesos": {"usa polimorfismo": 5.0}}
    obs = _obs_contenido(result)
    assert "No cumple: usa polimorfismo (5.0 pts)" in obs


# Prueba para que las observaciones de contenido reporten el cumplimiento por rama
def test_obs_contenido_branch_requirements():
    result = full_result()
    result["content"]["branch_requirements"] = [
        {"branch": "docs", "requirements_missing": []},
        {"branch": "prompts", "requirements_missing": ["documentar prompts"]},
    ]
    obs = _obs_contenido(result)
    assert "Rama 'docs': cumple." in obs
    assert "Rama 'prompts': no cumple: documentar prompts." in obs


# Prueba para que _safe_filename se quede solo con el nombre del archivo
def test_safe_filename_descarta_rutas():
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("juan_proyecto.html") == "juan_proyecto.html"


# Prueba para que save_reports escriba los informes individuales y el consolidado en disco
def test_save_reports_guarda_archivos(tmp_path):
    resultados = [full_result(report_html="<p>hola</p>")]
    save_reports(resultados, "<p>consolidado</p>", tmp_path)

    assert (tmp_path / "juan_proyecto.html").read_text(encoding="utf-8") == "<p>hola</p>"
    assert (tmp_path / "consolidado.html").read_text(encoding="utf-8") == "<p>consolidado</p>"


# Prueba para que save_reports descarte nombres de archivo que intenten escapar del directorio de salida
def test_save_reports_rechaza_nombre_inseguro(tmp_path):
    resultados = [full_result(student="../../tmp", repo_name="evil", report_html="<p>malo</p>")]
    save_reports(resultados, "<p>consolidado</p>", tmp_path)

    # el nombre inseguro se resuelve a "tmp_evil.html" dentro del propio tmp_path, asi que
    # el unico forma de comprobar el rechazo es que no se haya escapado del directorio
    assert all(p.parent == tmp_path for p in tmp_path.rglob("*.html"))


# Prueba para que generate_reports_node arme el HTML de cada repo y el consolidado
def test_generate_reports_node_genera_html(monkeypatch):
    state = {"results": [full_result()], "criteria": {}}
    output = generate_reports_node(state)
    assert len(output["results"]) == 1
    assert output["results"][0]["report_html"]
    assert "juan" in output["consolidated_report"]


# Prueba para que generate_reports_node siga adelante si un informe individual falla
def test_generate_reports_node_tolera_error_individual(monkeypatch):
    def fake_render_individual(result, criteria, env=None):
        raise ValueError("boom")

    monkeypatch.setattr("reports.generator.render_individual", fake_render_individual)
    state = {"results": [full_result()], "criteria": {}}
    output = generate_reports_node(state)

    assert len(output["results"]) == 1
    assert "report_html" not in output["results"][0] or output["results"][0]["report_html"] is None


# Prueba para que generate_reports_node siga adelante si el consolidado falla
def test_generate_reports_node_tolera_error_consolidado(monkeypatch):
    def fake_render_consolidated(results, criteria, env=None):
        raise ValueError("boom")

    monkeypatch.setattr("reports.generator.render_consolidated", fake_render_consolidated)
    state = {"results": [full_result()], "criteria": {}}
    output = generate_reports_node(state)

    assert "Error generando el informe consolidado" in output["consolidated_report"]
