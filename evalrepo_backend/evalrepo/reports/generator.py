"""
Genera los informes en HTML con Jinja2
"""

from __future__ import annotations
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from state import EvaluationState, RepoResult

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_jinja_env() -> Environment:
    """Arma el entorno de Jinja2 apuntando a la carpeta de templates."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def generate_reports_node(state: EvaluationState) -> dict[str, Any]:
    """Último paso del grafo: genera el HTML de cada repo y el consolidado del grupo."""
    env = _get_jinja_env()
    results_with_html: list[RepoResult] = []

    for result in state["results"]:
        try:
            html = render_individual(result, state["criteria"], env)
            updated = dict(result)
            updated["report_html"] = html
            results_with_html.append(RepoResult(**updated))
        except Exception as e:
            logger.error(
                "[Generador] Error generando informe para %s/%s: %s",
                result.get("owner"), result.get("repo_name"), e,
            )
            results_with_html.append(result)

    try:
        consolidated_html = render_consolidated(results_with_html, state["criteria"], env)
    except Exception as e:
        logger.error("[Generador] Error generando informe consolidado: %s", e)
        consolidated_html = f"<p>Error generando el informe consolidado: {e}</p>"

    logger.info(
        "[Generador] %d informes individuales + consolidado generados.",
        len(results_with_html),
    )

    return {
        "results": results_with_html,
        "consolidated_report": consolidated_html,
    }


def render_individual(
    result: RepoResult,
    criteria: dict[str, Any],
    env: Environment | None = None,
) -> str:
    """Arma el HTML del informe de un solo repositorio."""
    if env is None:
        env = _get_jinja_env()
    template = env.get_template("individual.html.j2")
    return template.render(
        result=result,
        criteria=criteria,
        generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def render_consolidated(
    results: list[RepoResult],
    criteria: dict[str, Any],
    env: Environment | None = None,
) -> str:
    """Arma el HTML del informe consolidado con todo el grupo."""
    if env is None:
        env = _get_jinja_env()
    template = env.get_template("consolidated.html.j2")

    # números de resumen para el encabezado
    scores = [r["global_score"] for r in results if not r.get("error")]
    stats = {
        "total": len(results),
        "evaluados": len(scores),
        "aprobados": sum(1 for s in scores if s >= 70),
        "en_riesgo": sum(1 for s in scores if 50 <= s < 70),
        "reprobados": sum(1 for s in scores if s < 50),
        "promedio": round(sum(scores) / len(scores), 1) if scores else 0,
        "max": max(scores) if scores else 0,
        "min": min(scores) if scores else 0,
    }

    return template.render(
        results=results,
        criteria=criteria,
        stats=stats,
        generated_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def save_reports(
    results: list[RepoResult],
    consolidated_html: str,
    output_dir: Path,
) -> None:
    """Guarda los HTML generados en disco, para el modo demo por línea de comandos."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        if result.get("report_html"):
            filename = f"{result['student']}_{result['repo_name']}.html"
            (output_dir / filename).write_text(result["report_html"], encoding="utf-8")
            logger.info("[Generador] Guardado: %s", filename)

    consolidated_path = output_dir / "consolidado.html"
    consolidated_path.write_text(consolidated_html, encoding="utf-8")
    logger.info("[Generador] Consolidado guardado: %s", consolidated_path)


# ─── Reporte Excel general ──────────────────────────────────────────────────
# Una fila por estudiante/repositorio, con lo que cumplió y observaciones
# puntuales por dimensión (no solo un check ✓/✗, pero sin llegar al detalle
# completo del informe HTML individual).

_HEADER_FILL = PatternFill(start_color="1B3A5C", end_color="1B3A5C", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_WRAP = Alignment(wrap_text=True, vertical="top")
_FAIL_FILL = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")
_RISK_FILL = PatternFill(start_color="FFFBEB", end_color="FFFBEB", fill_type="solid")


def _obs_estructural(r: dict[str, Any]) -> str:
    s = r.get("structural")
    if not s:
        return "Dimensión deshabilitada."
    parts = []
    if s.get("files_missing"):
        parts.append("Faltan: " + ", ".join(s["files_missing"]))
    else:
        parts.append("Todos los archivos requeridos presentes.")
    estado_readme = "OK" if s.get("readme_ok") else "insuficiente"
    parts.append(f"README: {s.get('readme_char_count', 0)} caracteres ({estado_readme}).")
    for c in s.get("branch_checks", []):
        estado = "OK" if c["found"] else "FALTA"
        parts.append(f"{c['path']} en rama {c['branch']}: {estado}.")
    for c in s.get("alternative_checks", []):
        if c["found"]:
            parts.append(f"{c['nombre']} encontrado en {c['found_in']}.")
        else:
            parts.append(f"{c['nombre']} no encontrado en {', '.join(c['carpetas'])}.")
    return " ".join(parts)


def _obs_versionado(r: dict[str, Any]) -> str:
    v = r.get("versioning")
    if not v:
        return "Dimensión deshabilitada."
    min_commits = v.get("details", {}).get("commits_min", "?")
    parts = [f"{v.get('total_commits', 0)} commits (mínimo {min_commits})."]
    parts.append(f"{v.get('quality_pct', 0)}% de mensajes descriptivos.")
    if v.get("generic_messages"):
        ejemplos = ", ".join(f'"{m}"' for m in v["generic_messages"][:3])
        parts.append(f"Genéricos detectados: {ejemplos}.")
    parts.append(f"{v.get('branch_count', 0)} rama(s): " + ", ".join(v.get("branch_names", [])) + ".")
    if v.get("contributors"):
        contrib = ", ".join(f"{c['author']} ({c['commits']})" for c in v["contributors"])
        parts.append(f"Colaboradores: {contrib}.")
    return " ".join(parts)


def _obs_temporal(r: dict[str, Any]) -> str:
    t = r.get("temporal")
    if not t:
        return "Dimensión deshabilitada."
    parts = []
    if t.get("last_commit_date"):
        fecha = t["last_commit_date"][:16].replace("T", " ")
        parts.append(f"Último commit: {fecha} ({'a tiempo' if t.get('on_time') else 'tarde'}).")
    parts.append(f"Actividad en {t.get('active_weeks', 0)} de {t.get('total_weeks', 0)} semanas.")
    if t.get("concentration_alert"):
        parts.append(f"{t.get('concentration_pct', 0)}% de commits concentrados al final del período.")
    return " ".join(parts)


def _obs_contenido(r: dict[str, Any]) -> str:
    c = r.get("content")
    if not c:
        return "Dimensión deshabilitada."
    parts = [f"Coherencia: {c.get('coherence_level', 'N/A')}."]
    requirement_scores = (c.get("details") or {}).get("requirement_scores")
    if requirement_scores:
        parts.append("Puntaje por requisito: " + "; ".join(
            f"{rs['requirement']} (vale {rs['weight_pct']} pts, {rs['achieved_pct']}% cumplido = {rs['points']} pts obtenidos)"
            for rs in requirement_scores
        ))
    elif c.get("requirements_missing"):
        pesos = (c.get("details") or {}).get("requisitos_pesos") or {}
        parts.append("No cumple: " + "; ".join(
            f"{req} ({pesos[req]:.1f} pts)" if req in pesos else req
            for req in c["requirements_missing"]
        ))
    for br in c.get("branch_requirements", []):
        estado = "cumple" if not br["requirements_missing"] else f"no cumple: {'; '.join(br['requirements_missing'])}"
        parts.append(f"Rama '{br['branch']}': {estado}.")
    if c.get("llm_summary"):
        parts.append(c["llm_summary"])
    return " ".join(parts)


def generate_excel(results: list[dict[str, Any]], criteria: dict[str, Any] | None = None) -> bytes:
    """Arma el reporte Excel general: una fila por estudiante/repositorio."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Consolidado"

    headers = [
        "Estudiante", "Repositorio", "URL", "Puntaje global", "Patrón de trabajo",
        "Entrega", "Alertas",
        "Estructural (pts)", "Observaciones estructurales",
        "Versionado (pts)", "Observaciones de versionado",
        "Temporal (pts)", "Observaciones temporales",
        "Contenido (pts)", "Observaciones de contenido",
        "Ajustado manualmente", "Justificación del ajuste",
    ]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    sorted_results = sorted(results, key=lambda r: r.get("global_score", 0), reverse=True)

    for r in sorted_results:
        if r.get("error"):
            ws.append([
                r.get("student", ""), r.get("repo_name", ""), r.get("url", ""),
                0, "Error", "—", "", "", f"No se pudo evaluar: {r['error']}",
                "", "", "", "", "", "", "", "",
            ])
            continue

        temporal = r.get("temporal") or {}
        row = [
            r.get("student", ""),
            r.get("repo_name", ""),
            r.get("url", ""),
            round(r.get("global_score", 0), 1),
            r.get("pattern_label", ""),
            "A tiempo" if temporal.get("on_time") else "Tarde",
            "; ".join(r.get("alerts", [])),
            round((r.get("structural") or {}).get("score", 0), 1),
            _obs_estructural(r),
            round((r.get("versioning") or {}).get("score", 0), 1),
            _obs_versionado(r),
            round(temporal.get("score", 0), 1),
            _obs_temporal(r),
            round((r.get("content") or {}).get("score", 0), 1),
            _obs_contenido(r),
            "Sí" if r.get("score_overridden") else "No",
            r.get("override_note") or "",
        ]
        ws.append(row)

        row_idx = ws.max_row
        score = r.get("global_score", 0)
        fill = _FAIL_FILL if score < 50 else (_RISK_FILL if score < 70 else None)
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.alignment = _WRAP
            if fill:
                cell.fill = fill

    widths = [16, 20, 28, 12, 16, 10, 20, 10, 38, 10, 46, 10, 34, 10, 38, 10, 28]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
