from __future__ import annotations
import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

load_dotenv()

# solo prendemos el trazado de LangSmith si hay API key configurada
if os.getenv("LANGCHAIN_API_KEY"):
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "evalrepo-utpl")

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("evalrepo.main")

from config.criteria_loader import load_criteria, _validate
from errors import FatalEvaluationError
from graph import build_graph, initial_state
from reports.generator import generate_excel, render_individual, render_consolidated
from state import EvaluationState


app = FastAPI(
    title="EvalRepo API",
    description="Sistema multi-agente para evaluación de repositorios GitHub estudiantiles — UTPL TIC 2025",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    from db.supabase_client import get_supabase_client
    return get_supabase_client()


def _row_to_result(row: dict[str, Any]) -> dict[str, Any]:
    """Convierte una fila de `repo_results` (nombres de columna) al dict que esperan
    las plantillas Jinja2 (nombres de campo de RepoResult)."""
    return {
        "url": row.get("url", ""),
        "owner": row.get("owner", ""),
        "repo_name": row.get("repo_name", ""),
        "student": row.get("student", ""),
        "structural": row.get("structural_result"),
        "versioning": row.get("versioning_result"),
        "temporal": row.get("temporal_result"),
        "content": row.get("content_result"),
        "global_score": row.get("global_score", 0),
        "alerts": row.get("alerts") or [],
        "pattern_label": row.get("pattern_label", ""),
        "error": row.get("error"),
        "score_overridden": row.get("score_overridden", False),
        "original_score": row.get("original_score"),
        "override_note": row.get("override_note"),
    }


class EvaluationRequest(BaseModel):
    repo_urls: list[str]
    github_token: str
    criteria_path: str | None = None
    # Override parcial que manda el Módulo de Configuración de Criterios del frontend.
    # Se fusiona sobre el YAML base (criteria_path o default.yaml); lo que no se envía
    # aquí conserva el valor del YAML, así el docente no tiene que repetir todo.
    criteria: dict[str, Any] | None = None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Fusiona `override` sobre `base`, sección por sección, sin perder claves que el override no toca."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class EvaluationStatus(BaseModel):
    evaluation_id: str
    status: str
    started_at: str
    finished_at: str | None
    total_repos: int
    processed_repos: int
    errors: list[str]


@app.get("/")
async def root():
    return {"service": "EvalRepo API", "version": "1.0.0", "docs": "/docs"}


@app.post("/evaluate", status_code=202)
async def start_evaluation(
    request: EvaluationRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Arranca la evaluación de la lista de repos en background y devuelve el id para hacerle seguimiento."""
    if not request.repo_urls:
        raise HTTPException(status_code=400, detail="Se requiere al menos una URL.")

    try:
        criteria_path = request.criteria_path or os.getenv("CRITERIA_PATH")
        criteria = load_criteria(criteria_path)
        if request.criteria:
            criteria = _deep_merge(criteria, request.criteria)
            _validate(criteria)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    evaluation_id = str(uuid.uuid4())

    try:
        db().table("evaluations").insert({
            "id": evaluation_id,
            "status": "pending",
            "total_repos": len(request.repo_urls),
            "processed_repos": 0,
            "errors": [],
            "criteria": criteria,
        }).execute()
    except RuntimeError as e:
        # get_supabase_client() lanza esto cuando faltan SUPABASE_URL/SUPABASE_SERVICE_KEY
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("[API] No se pudo conectar con Supabase: %s", e)
        raise HTTPException(
            status_code=503,
            detail=(
                "No se pudo conectar con la base de datos (Supabase). "
                "Verificá que SUPABASE_URL y SUPABASE_SERVICE_KEY en el archivo .env "
                "sean correctos y que el proyecto de Supabase esté activo."
            ),
        )

    background_tasks.add_task(
        _run_evaluation,
        evaluation_id=evaluation_id,
        repo_urls=request.repo_urls,
        criteria=criteria,
        github_token=request.github_token,
    )

    logger.info("[API] Evaluación %s creada — %d repos", evaluation_id, len(request.repo_urls))
    return {"evaluation_id": evaluation_id, "status": "pending"}


@app.get("/evaluate/{evaluation_id}", response_model=EvaluationStatus)
async def get_evaluation_status(evaluation_id: str) -> EvaluationStatus:
    """Para que el frontend vaya preguntando cómo va la evaluación mientras corre."""
    result = db().table("evaluations").select(
        "id,status,started_at,finished_at,total_repos,processed_repos,errors"
    ).eq("id", evaluation_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")

    ev = result.data[0]
    return EvaluationStatus(
        evaluation_id=evaluation_id,
        status=ev["status"],
        started_at=ev["started_at"],
        finished_at=ev.get("finished_at"),
        total_repos=ev["total_repos"],
        processed_repos=ev["processed_repos"],
        errors=ev.get("errors") or [],
    )


@app.get("/evaluate/{evaluation_id}/results")
async def get_evaluation_results(evaluation_id: str) -> list[dict]:
    """Los resultados de todos los repos ya evaluados, en JSON."""
    ev = db().table("evaluations").select("status").eq("id", evaluation_id).execute()
    if not ev.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    if ev.data[0]["status"] != "done":
        raise HTTPException(status_code=409, detail=f"La evaluación aún no está completa.")

    results = db().table("repo_results").select("*").eq(
        "evaluation_id", evaluation_id
    ).order("global_score", desc=True).execute()

    return results.data or []


class ScoreOverrideRequest(BaseModel):
    score: float
    note: str | None = None


class RequirementScoreInput(BaseModel):
    requirement: str
    weight_pct: float    # cuántos puntos del peso de Contenido vale este requisito
                          # (ej. si Contenido vale 20, dos requisitos pueden valer 10 c/u)
    achieved_pct: float  # qué % de ese requisito cumplió el estudiante (0-100)


class ContentOverrideRequest(BaseModel):
    requirements: list[RequirementScoreInput]
    note: str | None = None


def _fetch_eval_and_row(evaluation_id: str, student: str, repo: str) -> tuple[dict, dict]:
    """Trae los criterios de la evaluación y la fila del repo puntual, o lanza 404."""
    ev_res = db().table("evaluations").select("criteria").eq("id", evaluation_id).execute()
    if not ev_res.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    criteria = ev_res.data[0].get("criteria") or {}

    row_res = db().table("repo_results").select("*").eq(
        "evaluation_id", evaluation_id
    ).eq("student", student).eq("repo_name", repo).execute()
    if not row_res.data:
        raise HTTPException(status_code=404, detail=f"Resultado para {student}/{repo} no encontrado.")
    return criteria, row_res.data[0]


def _apply_override(
    evaluation_id: str, student: str, repo: str, row: dict[str, Any], criteria: dict[str, Any],
    new_global_score: float, note: str | None, content_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Guarda un ajuste manual de puntaje (global o solo de Contenido) y regenera los informes.

    Guarda el puntaje original (la primera vez que se ajusta) para que quede
    trazabilidad de qué calculó el sistema y qué decidió el docente.
    """
    original_score = row["original_score"] if row.get("score_overridden") else row["global_score"]

    updated_result = _row_to_result(row)
    if content_patch is not None:
        updated_result["content"] = content_patch
    updated_result["global_score"] = new_global_score
    updated_result["original_score"] = original_score
    updated_result["score_overridden"] = True
    updated_result["override_note"] = note

    report_html = render_individual(updated_result, criteria)

    update_fields: dict[str, Any] = {
        "global_score": new_global_score,
        "original_score": original_score,
        "score_overridden": True,
        "override_note": note,
        "report_html": report_html,
    }
    if content_patch is not None:
        update_fields["content_result"] = content_patch
    db().table("repo_results").update(update_fields).eq("id", row["id"]).execute()

    # el consolidado también tiene que reflejar el ajuste
    all_rows = db().table("repo_results").select("*").eq(
        "evaluation_id", evaluation_id
    ).execute().data or []
    consolidated_html = render_consolidated(
        [_row_to_result(r) for r in all_rows], criteria
    )
    db().table("evaluations").update({
        "consolidated_report": consolidated_html,
    }).eq("id", evaluation_id).execute()

    return {
        "student": student, "repo_name": repo,
        "global_score": new_global_score, "original_score": original_score,
        "score_overridden": True, "override_note": note,
        "content": content_patch,
    }


@app.patch("/evaluate/{evaluation_id}/results/{student}/{repo}/score")
async def override_score(
    evaluation_id: str, student: str, repo: str, body: ScoreOverrideRequest,
) -> dict[str, Any]:
    """Deja que el docente ajuste a mano el puntaje global de un repositorio ya evaluado."""
    if not (0 <= body.score <= 100):
        raise HTTPException(status_code=400, detail="El puntaje debe estar entre 0 y 100.")

    criteria, row = _fetch_eval_and_row(evaluation_id, student, repo)
    return _apply_override(evaluation_id, student, repo, row, criteria, body.score, body.note)


@app.patch("/evaluate/{evaluation_id}/results/{student}/{repo}/content-score")
async def override_content_score(
    evaluation_id: str, student: str, repo: str, body: ContentOverrideRequest,
) -> dict[str, Any]:
    """Deja que el docente asigne un puntaje (de los puntos que vale Contenido) y un
    % de cumplimiento a cada requisito (ej. si Contenido vale 20, "usa condicionales"
    puede valer 10 de esos 20, cumplido al 100%), en vez de cambiar el puntaje total
    a ciegas. Recalcula Contenido y el puntaje global."""
    if not body.requirements:
        raise HTTPException(status_code=400, detail="Debes incluir al menos un requisito.")

    criteria, row = _fetch_eval_and_row(evaluation_id, student, repo)
    content = row.get("content_result") or {}
    max_score = content.get("max_score") or criteria.get("contenido", {}).get("peso", 10)

    total_weight = sum(r.weight_pct for r in body.requirements)
    if total_weight > max_score + 0.01:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Los pesos de los requisitos suman {total_weight:.1f}, pero Contenido "
                f"vale {max_score} puntos — no pueden sumar más que eso."
            ),
        )
    for r in body.requirements:
        if not (0 <= r.weight_pct <= max_score) or not (0 <= r.achieved_pct <= 100):
            raise HTTPException(
                status_code=400,
                detail=f"'{r.requirement}': el peso debe estar entre 0 y {max_score}, y el % cumplido entre 0 y 100.",
            )

    content_score = round(
        sum(r.weight_pct * (r.achieved_pct / 100) for r in body.requirements), 2
    )
    content_score = min(content_score, max_score)

    requirement_scores = [
        {
            "requirement": r.requirement, "weight_pct": r.weight_pct, "achieved_pct": r.achieved_pct,
            "points": round(r.weight_pct * (r.achieved_pct / 100), 2),
        }
        for r in body.requirements
    ]
    new_content = dict(content)
    new_content["score"] = content_score
    new_content["max_score"] = max_score
    new_content["requirements_found"] = [r.requirement for r in body.requirements if r.achieved_pct >= 100]
    new_content["requirements_missing"] = [r.requirement for r in body.requirements if r.achieved_pct < 100]
    new_content["details"] = {
        **(content.get("details") or {}),
        "requirement_scores": requirement_scores,
        "manual": True,
    }

    structural_score = (row.get("structural_result") or {}).get("score", 0)
    versioning_score = (row.get("versioning_result") or {}).get("score", 0)
    temporal_score = (row.get("temporal_result") or {}).get("score", 0)
    new_global = min(100.0, round(structural_score + versioning_score + temporal_score + content_score, 2))

    return _apply_override(
        evaluation_id, student, repo, row, criteria, new_global, body.note, content_patch=new_content
    )


@app.get("/reports/{evaluation_id}/excel")
async def get_excel_report(evaluation_id: str) -> Response:
    """El reporte general en Excel: una fila por estudiante/repositorio."""
    ev = db().table("evaluations").select("status,criteria").eq("id", evaluation_id).execute()
    if not ev.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    if ev.data[0]["status"] != "done":
        raise HTTPException(status_code=409, detail="La evaluación aún no está completa.")

    rows = db().table("repo_results").select("*").eq(
        "evaluation_id", evaluation_id
    ).order("global_score", desc=True).execute().data or []

    xlsx_bytes = generate_excel([_row_to_result(r) for r in rows], ev.data[0].get("criteria"))

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="evalrepo_{evaluation_id}.xlsx"'},
    )


@app.get("/reports/{evaluation_id}", response_class=HTMLResponse)
async def get_consolidated_report(evaluation_id: str) -> str:
    """El informe consolidado en HTML, listo para mostrar o descargar."""
    result = db().table("evaluations").select(
        "status,consolidated_report"
    ).eq("id", evaluation_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    ev = result.data[0]
    if ev["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Estado: {ev['status']}")
    if not ev.get("consolidated_report"):
        raise HTTPException(status_code=404, detail="Informe consolidado no disponible.")
    return ev["consolidated_report"]


@app.get("/reports/{evaluation_id}/{student}/{repo}", response_class=HTMLResponse)
async def get_individual_report(evaluation_id: str, student: str, repo: str) -> str:
    """El informe HTML de un repositorio puntual."""
    result = db().table("repo_results").select("report_html").eq(
        "evaluation_id", evaluation_id
    ).eq("student", student).eq("repo_name", repo).execute()

    if not result.data or not result.data[0].get("report_html"):
        raise HTTPException(
            status_code=404,
            detail=f"Informe para {student}/{repo} no encontrado."
        )
    return result.data[0]["report_html"]


@app.post("/criteria/validate")
async def validate_criteria(body: dict[str, Any]) -> dict[str, Any]:
    """Chequea que un dict de criterios esté bien formado antes de usarlo."""
    try:
        _validate(body)
        return {"valid": True}
    except ValueError as e:
        return {"valid": False, "error": str(e)}


async def _run_evaluation(
    evaluation_id: str,
    repo_urls: list[str],
    criteria: dict[str, Any],
    github_token: str,
) -> None:
    """Corre el grafo y va guardando los resultados en Supabase a medida que salen."""

    db().table("evaluations").update({"status": "running"}).eq(
        "id", evaluation_id
    ).execute()

    try:
        graph = build_graph()
        state = initial_state(
            repo_urls=repo_urls,
            criteria=criteria,
            github_token=github_token,
        )

        loop = asyncio.get_event_loop()
        final_state: EvaluationState = await loop.run_in_executor(
            None, lambda: graph.invoke(state)
        )

        # va guardando cada repo procesado
        for r in final_state["results"]:
            db().table("repo_results").insert({
                "evaluation_id": evaluation_id,
                "url":        r.get("url", ""),
                "owner":      r.get("owner", ""),
                "repo_name":  r.get("repo_name", ""),
                "student":    r.get("student", ""),
                "global_score":       r.get("global_score", 0),
                "alerts":             r.get("alerts", []),
                "pattern_label":      r.get("pattern_label", ""),
                "structural_result":  r.get("structural"),
                "versioning_result":  r.get("versioning"),
                "temporal_result":    r.get("temporal"),
                "content_result":     r.get("content"),
                "report_html":        r.get("report_html"),
                "error":              r.get("error"),
            }).execute()

        # ya terminó, se marca como lista
        db().table("evaluations").update({
            "status":           "done",
            "finished_at":      datetime.now(tz=timezone.utc).isoformat(),
            "processed_repos":  len(final_state["results"]),
            "errors":           final_state.get("errors", []),
            "consolidated_report": final_state.get("consolidated_report"),
        }).eq("id", evaluation_id).execute()

        logger.info(
            "[API] Evaluación %s completada — %d repos",
            evaluation_id, len(final_state["results"])
        )

    except FatalEvaluationError as e:
        # un agente detectó algo que va a fallar igual en todos los repos restantes
        # (credenciales inválidas, límite de peticiones) y cortó todo de una vez,
        # en vez de repetir el mismo error un montón de veces — ya viene con un
        # mensaje claro, se guarda tal cual.
        logger.error("[API] Evaluación %s cortada: %s", evaluation_id, e)
        _mark_evaluation_error(evaluation_id, str(e))
    except Exception as e:
        logger.error("[API] Error en evaluación %s: %s", evaluation_id, e)
        _mark_evaluation_error(evaluation_id, f"Error inesperado al procesar la evaluación: {e}")


def _mark_evaluation_error(evaluation_id: str, message: str) -> None:
    """Marca la evaluación como fallida en Supabase. Si Supabase mismo es el que
    se cayó a mitad de la evaluación, esto puede fallar también — se registra en
    el log para no perder el rastro, pero no se vuelve a lanzar (ya estamos
    dentro de un background task, no hay nadie esperando la excepción)."""
    try:
        db().table("evaluations").update({
            "status":      "error",
            "finished_at": datetime.now(tz=timezone.utc).isoformat(),
            "errors":      [message],
        }).eq("id", evaluation_id).execute()
    except Exception as e:
        logger.error(
            "[API] No se pudo marcar la evaluación %s como fallida en Supabase: %s",
            evaluation_id, e,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
