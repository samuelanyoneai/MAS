"""
Junta lo que hicieron los otros cuatro agentes: calcula
el puntaje global del repo, genera las alertas, arma el RepoResult y decide si queda
algo más por procesar o si ya se puede pasar a generar los informes.
"""

from __future__ import annotations
import logging
from typing import Any, Literal

from state import (
    EvaluationState,
    RepoResult,
    StructuralResult,
    VersioningResult,
    TemporalResult,
    ContentResult,
)

logger = logging.getLogger(__name__)


def coordinator_agent(state: EvaluationState) -> dict[str, Any]:
    """Junta lo que dejaron los otros agentes en el estado y arma el RepoResult del repo actual."""
    repo_data = state.get("current_repo_data")
    idx = state["current_index"]

    if not repo_data:
        # no se pudo bajar el repo, lo anotamos como error y seguimos con el siguiente
        url = state["repo_urls"][idx]
        error_result = _error_result(url, "No se pudo extraer el repositorio.")
        return {
            "results": state["results"] + [error_result],
            "current_index": idx + 1,
            "current_repo_data": None,
            "structural_result": None,
            "versioning_result": None,
            "temporal_result": None,
            "content_result": None,
        }

    structural: StructuralResult = state.get("structural_result") or _empty_structural()
    versioning: VersioningResult = state.get("versioning_result") or _empty_versioning()
    temporal: TemporalResult = state.get("temporal_result") or _empty_temporal()
    content: ContentResult = state.get("content_result") or _empty_content()

    # sumamos los cuatro puntajes parciales (ya vienen ponderados por su peso)
    global_score = round(
        structural["score"] + versioning["score"]
        + temporal["score"] + content["score"],
        2,
    )
    global_score = min(100.0, global_score)

    alerts: list[str] = _generate_alerts(temporal, versioning, repo_data, state["criteria"])

    pattern_label = temporal.get("pattern_label", "Sin datos")

    repo_result = RepoResult(
        url=repo_data["url"],
        owner=repo_data["owner"],
        repo_name=repo_data["repo_name"],
        student=repo_data["owner"],
        structural=structural,
        versioning=versioning,
        temporal=temporal,
        content=content,
        global_score=global_score,
        alerts=alerts,
        pattern_label=pattern_label,
        report_html=None,   # El Generador de Informes lo completa
        error=None,
        score_overridden=False,
        original_score=None,
        override_note=None,
    )

    logger.info(
        "[Coordinador] %s/%s — Puntaje global: %.1f | Patrón: %s | Alertas: %d",
        repo_data["owner"], repo_data["repo_name"],
        global_score, pattern_label, len(alerts),
    )

    return {
        "results": state["results"] + [repo_result],
        "current_index": idx + 1,
        "current_repo_data": None,
        "structural_result": None,
        "versioning_result": None,
        "temporal_result": None,
        "content_result": None,
    }


def should_continue(state: EvaluationState) -> Literal["next_repo", "end"]:
    """Le dice al grafo si sigue con otro repo o si ya terminamos."""
    if state["current_index"] < len(state["repo_urls"]):
        return "next_repo"
    return "end"


def _generate_alerts(
    temporal: TemporalResult,
    versioning: VersioningResult,
    repo_data: dict[str, Any],
    criteria: dict[str, Any],
) -> list[str]:
    """Revisa si hay algo raro que valga la pena avisarle al docente."""
    alerts: list[str] = []
    cfg_temporal = criteria.get("temporal", {})

    # commits concentrados al final
    if temporal.get("concentration_alert"):
        pct = temporal["concentration_pct"]
        dias = criteria.get("temporal", {}).get("alerta_concentracion", {}).get("dias_finales", 3)
        alerts.append(
            f"{pct:.0f}% de commits realizados en los últimos {dias} días antes de la entrega."
        )

    # entrega tardía
    if temporal.get("last_commit_date") and not temporal.get("on_time"):
        alerts.append("Repositorio entregado después de la fecha límite.")

    # semanas sin actividad
    inact_cfg = cfg_temporal.get("alerta_inactividad", {})
    if inact_cfg.get("habilitado", True):
        semanas_umbral = inact_cfg.get("semanas_consecutivas", 2)
        max_consec = _max_consecutive_inactive_weeks(
            temporal.get("weekly_counts", {}),
            temporal.get("total_weeks", 0),
            repo_data.get("periodo_inicio", ""),
        )
        if max_consec >= semanas_umbral:
            alerts.append(
                f"{max_consec} semanas consecutivas sin actividad de commits."
            )

    # muchos commits juntos en poco tiempo, puede ser una entrega copiada de golpe
    masivo_cfg = cfg_temporal.get("alerta_commits_masivos", {})
    if masivo_cfg.get("habilitado", True):
        commits_umbral = masivo_cfg.get("commits_en_ventana", 20)
        ventana_h = masivo_cfg.get("ventana_horas", 1)
        if _detect_massive_commits(repo_data.get("commits", []), commits_umbral, ventana_h):
            alerts.append(
                f"Detectados {commits_umbral}+ commits en una ventana de {ventana_h}h "
                "(posible actividad automatizada)."
            )

    return alerts


def _max_consecutive_inactive_weeks(
    weekly_counts: dict[str, int],
    total_weeks: int,
    periodo_inicio: str,
) -> int:
    """La racha más larga de semanas seguidas sin ningún commit."""
    if not periodo_inicio or total_weeks == 0:
        return 0
    from datetime import datetime, timedelta
    try:
        inicio = datetime.fromisoformat(periodo_inicio)
    except ValueError:
        return 0

    max_consec = 0
    current_consec = 0
    for w in range(total_weeks):
        week_dt = inicio + timedelta(weeks=w)
        week_key = week_dt.strftime("%Y-W%W")
        if weekly_counts.get(week_key, 0) == 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0
    return max_consec


def _detect_massive_commits(
    commits: list[dict],
    threshold: int,
    window_hours: int,
) -> bool:
    """True si hay `threshold` commits o más apretados en una ventana de `window_hours` horas."""
    from datetime import datetime, timedelta, timezone
    dates: list[datetime] = []
    for c in commits:
        raw = c.get("date")
        if raw:
            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dates.append(dt)
            except ValueError:
                pass
    dates.sort()
    window = timedelta(hours=window_hours)
    for i in range(len(dates)):
        count = sum(1 for j in range(i, len(dates)) if dates[j] - dates[i] <= window)
        if count >= threshold:
            return True
    return False


def _empty_structural() -> StructuralResult:
    from state import StructuralResult
    return StructuralResult(
        files_found=[], files_missing=[], readme_exists=False,
        readme_char_count=0, readme_ok=False,
        branch_checks=[], alternative_checks=[],
        score=0.0, max_score=0.0, details={},
    )


def _empty_versioning() -> VersioningResult:
    from state import VersioningResult
    return VersioningResult(
        total_commits=0, commits_ok=False, branch_count=0, branch_names=[],
        branches_ok=False, quality_pct=0.0, quality_ok=False,
        generic_messages=[], contributors=[], commit_log=[],
        score=0.0, max_score=0.0, details={},
    )


def _empty_temporal() -> TemporalResult:
    from state import TemporalResult
    return TemporalResult(
        last_commit_date=None, on_time=False, weekly_counts={}, weekly_breakdown=[],
        active_weeks=0, total_weeks=0, activity_ok=False,
        concentration_pct=0.0, concentration_alert=False,
        pattern_label="Sin datos", score=0.0, max_score=0.0, details={},
    )


def _empty_content() -> ContentResult:
    from state import ContentResult
    return ContentResult(
        requirements_found=[], requirements_missing=[],
        coherence_level="N/A", llm_summary="",
        branch_requirements=[],
        score=0.0, max_score=0.0, details={},
    )


def _error_result(url: str, msg: str) -> RepoResult:
    parts = url.rstrip("/").split("/")
    owner = parts[-2] if len(parts) >= 2 else "unknown"
    repo_name = parts[-1] if parts else "unknown"
    return RepoResult(
        url=url, owner=owner, repo_name=repo_name, student=owner,
        structural=None, versioning=None, temporal=None, content=None,
        global_score=0.0, alerts=[], pattern_label="Error",
        report_html=None, error=msg,
        score_overridden=False, original_score=None, override_note=None,
    )
