"""
Este agente revisa dos cosas a la vez: el historial de commits y el patrón
temporal de actividad. 
"""

from __future__ import annotations
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from state import EvaluationState, VersioningResult, TemporalResult

logger = logging.getLogger(__name__)

# Patrones de mensajes genéricos (por defecto)
DEFAULT_GENERIC_PATTERNS = [
    r"^update$", r"^fix$", r"^test$", r"^changes$", r"^commit$",
    r"^wip$", r"^done$", r"^asdf", r"^\.", r"^[a-z]{1,3}$",
]


def versioning_agent(state: EvaluationState) -> dict[str, Any]:
    """Analiza commits, ramas y cómo se distribuyó la actividad en el tiempo."""
    repo_data = state.get("current_repo_data")
    if not repo_data:
        return {}

    criteria = state["criteria"]

    try:
        versioning_result = _analyze_versioning(repo_data, criteria)
        temporal_result = _analyze_temporal(repo_data, criteria)
    except Exception as e:
        # un dato inesperado de ESTE repo no debería tumbar toda la evaluación —
        # se marca 0 en estas dos dimensiones y se sigue con el resto
        msg = f"Error en análisis de versionado/temporal de {repo_data.get('url', '?')}: {e}"
        logger.error(msg)
        peso_v = criteria.get("versionado", {}).get("peso", 40)
        peso_t = criteria.get("temporal", {}).get("peso", 25)
        return {
            "versioning_result": _empty_versioning(float(peso_v)),
            "temporal_result": _empty_temporal(float(peso_t)),
            "errors": state["errors"] + [msg],
        }

    logger.info(
        "[Versionado] %s/%s → %.1f/%.1f pts | [Temporal] → %.1f/%.1f pts",
        repo_data["owner"], repo_data["repo_name"],
        versioning_result["score"], versioning_result["max_score"],
        temporal_result["score"], temporal_result["max_score"],
    )

    return {
        "versioning_result": versioning_result,
        "temporal_result": temporal_result,
    }


def _analyze_versioning(
    repo_data: dict[str, Any],
    criteria: dict[str, Any],
) -> VersioningResult:
    cfg = criteria.get("versionado", {})
    if not cfg.get("habilitado", True):
        return _empty_versioning(0.0)

    peso = cfg.get("peso", 40)
    commits: list[dict] = repo_data.get("commits", [])
    branches: list[str] = repo_data.get("branches", [])

    # cuántos commits en total
    commits_min = cfg.get("commits_min", 10)
    total_commits = len(commits)
    commits_ok = total_commits >= commits_min

    # qué tan descriptivos son los mensajes
    quality_cfg = cfg.get("calidad_mensajes", {})
    quality_enabled = quality_cfg.get("habilitado", True)
    quality_umbral = quality_cfg.get("umbral_porcentaje", 70)
    generic_patterns = [
        re.compile(p, re.IGNORECASE)
        for p in quality_cfg.get("patrones_genericos", DEFAULT_GENERIC_PATTERNS)
    ]

    generic_messages: list[str] = []
    if quality_enabled and commits:
        for c in commits:
            msg = c.get("message", "").strip()
            if any(p.search(msg) for p in generic_patterns):
                generic_messages.append(msg)

    descriptive = total_commits - len(generic_messages)
    quality_pct = round((descriptive / total_commits) * 100, 1) if total_commits > 0 else 0.0
    quality_ok = quality_pct >= quality_umbral if quality_enabled else True

    # ramas
    ramas_cfg = cfg.get("ramas", {})
    ramas_enabled = ramas_cfg.get("habilitado", True)
    min_ramas = ramas_cfg.get("min_ramas", 2)
    branch_count = len(branches)
    branches_ok = branch_count >= min_ramas if ramas_enabled else True

    # quién hizo cada commit y cuántos le corresponden a cada quién
    contributors_count: dict[str, int] = defaultdict(int)
    commit_log: list[dict[str, Any]] = []
    for c in commits:
        author = c.get("author") or "Desconocido"
        contributors_count[author] += 1
        commit_log.append({
            "date": c.get("date"),
            "author": author,
            "message": c.get("message", "").strip(),
        })
    contributors = [
        {"author": author, "commits": n}
        for author, n in sorted(contributors_count.items(), key=lambda kv: -kv[1])
    ]
    commit_log.sort(key=lambda c: c["date"] or "")

    # puntaje ponderado: commits pesan más, después calidad, después ramas
    max_score = float(peso)
    checks = [
        (commits_ok, 0.5),
        (quality_ok, 0.3),
        (branches_ok, 0.2),
    ]
    score = round(
        sum(w * max_score for ok, w in checks if ok), 2
    )

    return VersioningResult(
        total_commits=total_commits,
        commits_ok=commits_ok,
        branch_count=branch_count,
        branch_names=branches,
        branches_ok=branches_ok,
        quality_pct=quality_pct,
        quality_ok=quality_ok,
        generic_messages=generic_messages[:5],   # Máximo 5 ejemplos en el informe
        contributors=contributors,
        commit_log=commit_log,
        score=score,
        max_score=max_score,
        details={
            "commits_min": commits_min,
            "min_ramas": min_ramas,
            "quality_umbral": quality_umbral,
        },
    )


def _analyze_temporal(
    repo_data: dict[str, Any],
    criteria: dict[str, Any],
) -> TemporalResult:
    cfg = criteria.get("temporal", {})
    if not cfg.get("habilitado", True):
        return _empty_temporal(0.0)

    peso = cfg.get("peso", 25)
    commits: list[dict] = repo_data.get("commits", [])

    # sacamos las fechas de todos los commits
    commit_dates: list[datetime] = []
    for c in commits:
        raw = c.get("date")
        if raw:
            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                commit_dates.append(dt)
            except ValueError:
                pass
    commit_dates.sort()

    inicio = datetime.fromisoformat(repo_data["periodo_inicio"])
    fin_str = criteria["periodo"]["fecha_limite"]
    deadline = datetime.fromisoformat(fin_str)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)

    # si entregó a tiempo, según el último commit
    last_commit_date: str | None = None
    on_time = False
    if commit_dates:
        last_dt = commit_dates[-1]
        last_commit_date = last_dt.isoformat()
        on_time = last_dt <= deadline

    # cuántos commits hubo por semana, con la fecha real de cada semana (no solo "Semana N")
    weekly_counts: dict[str, int] = defaultdict(int)
    weekly_monday: dict[str, datetime] = {}
    for dt in commit_dates:
        week_key = dt.strftime("%Y-W%W")   # ej. "2025-W03"
        weekly_counts[week_key] += 1
        weekly_monday.setdefault(week_key, dt - timedelta(days=dt.weekday()))

    total_weeks = max(1, _weeks_between(inicio, deadline))
    active_weeks = len(weekly_counts)
    activity_ok_cfg = cfg.get("actividad_minima_semanal", True)
    # con actividad en la mitad de las semanas o más, lo damos por bueno
    activity_ok = (active_weeks / total_weeks) >= 0.5 if activity_ok_cfg else True

    # si se concentró todo al final (posible señal de que dejaron todo para último momento)
    conc_cfg = cfg.get("alerta_concentracion", {})
    dias_finales = conc_cfg.get("dias_finales", 3)
    conc_umbral = conc_cfg.get("porcentaje_umbral", 70)
    ventana_inicio = deadline - timedelta(days=dias_finales)

    final_commits = sum(1 for dt in commit_dates if dt >= ventana_inicio)
    concentration_pct = round(
        (final_commits / len(commit_dates)) * 100, 1
    ) if commit_dates else 0.0
    concentration_alert = (
        conc_cfg.get("habilitado", True)
        and concentration_pct >= conc_umbral
        and len(commit_dates) > 0
    )

    pattern_label = _compute_pattern(
        concentration_pct, concentration_alert, active_weeks, total_weeks
    )

    weekly_breakdown = [
        {
            "week_key": week_key,
            "start_date": weekly_monday[week_key].date().isoformat(),
            "end_date": (weekly_monday[week_key] + timedelta(days=6)).date().isoformat(),
            "count": count,
        }
        for week_key, count in sorted(weekly_counts.items())
    ]

    max_score = float(peso)
    checks = [
        (on_time, 0.35),
        (activity_ok, 0.40),
        (not concentration_alert, 0.25),
    ]
    score = round(
        sum(w * max_score for ok, w in checks if ok), 2
    )

    return TemporalResult(
        last_commit_date=last_commit_date,
        on_time=on_time,
        weekly_counts=dict(weekly_counts),
        weekly_breakdown=weekly_breakdown,
        active_weeks=active_weeks,
        total_weeks=total_weeks,
        activity_ok=activity_ok,
        concentration_pct=concentration_pct,
        concentration_alert=concentration_alert,
        pattern_label=pattern_label,
        score=score,
        max_score=max_score,
        details={
            "deadline": deadline.isoformat(),
            "dias_finales": dias_finales,
            "conc_umbral": conc_umbral,
        },
    )


def _compute_pattern(
    concentration_pct: float,
    concentration_alert: bool,
    active_weeks: int,
    total_weeks: int,
) -> str:
    if concentration_alert:
        return "Concentración al final"
    if total_weeks > 0 and (active_weeks / total_weeks) >= 0.7:
        return "Trabajo continuo"
    return "Actividad irregular"


def _weeks_between(start: datetime, end: datetime) -> int:
    delta = end - start
    return max(1, delta.days // 7)


def _empty_versioning(max_score: float) -> VersioningResult:
    return VersioningResult(
        total_commits=0, commits_ok=False, branch_count=0, branch_names=[],
        branches_ok=False, quality_pct=0.0, quality_ok=False,
        generic_messages=[], contributors=[], commit_log=[],
        score=0.0, max_score=max_score,
        details={"habilitado": False},
    )


def _empty_temporal(max_score: float) -> TemporalResult:
    return TemporalResult(
        last_commit_date=None, on_time=False, weekly_counts={}, weekly_breakdown=[],
        active_weeks=0, total_weeks=0, activity_ok=False,
        concentration_pct=0.0, concentration_alert=False,
        pattern_label="Sin actividad", score=0.0, max_score=max_score,
        details={"habilitado": False},
    )
