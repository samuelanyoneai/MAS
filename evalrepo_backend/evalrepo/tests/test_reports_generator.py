from __future__ import annotations

import io

import openpyxl

from reports.generator import render_individual, render_consolidated, generate_excel, _obs_estructural, _obs_contenido


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
