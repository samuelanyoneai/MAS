

from __future__ import annotations
from typing import Any, Optional
from typing_extensions import TypedDict



class BranchFileCheck(TypedDict):
    """Un requisito tipo 'este archivo/carpeta debe estar en esta rama puntual'."""
    branch: str
    path: str
    found: bool


class AlternativeFileCheck(TypedDict):
    """Un requisito tipo 'este archivo debe existir en alguna de estas carpetas'."""
    nombre: str
    carpetas: list[str]
    found: bool
    found_in: Optional[str]       # En qué carpeta se encontró (None si no se encontró)


class StructuralResult(TypedDict):
    """Resultado del Agente de Análisis Estructural."""
    files_found: list[str]         # Archivos/carpetas presentes en el repo
    files_missing: list[str]       # Archivos/carpetas requeridos pero ausentes
    readme_exists: bool
    readme_char_count: int
    readme_ok: bool                # True si supera el umbral mínimo configurado
    branch_checks: list[BranchFileCheck]           # Requisitos de archivo por rama específica
    alternative_checks: list[AlternativeFileCheck]  # Requisitos de archivo en alguna de varias carpetas
    score: float                   # Puntaje parcial
    max_score: float
    details: dict[str, Any]        # Metadatos adicionales para el informe


class Contributor(TypedDict):
    """Un colaborador del repo y cuántos commits le corresponden."""
    author: str
    commits: int


class CommitLogEntry(TypedDict):
    """Un commit puntual, con fecha exacta y autor, para el detalle del informe."""
    date: Optional[str]            # ISO-8601
    author: str
    message: str


class VersioningResult(TypedDict):
    """Resultado del Agente de Análisis de Versionado."""
    total_commits: int
    commits_ok: bool               # Cumple mínimo de commits
    branch_count: int
    branch_names: list[str]
    branches_ok: bool              # Cumple mínimo de ramas
    quality_pct: float             # % de mensajes descriptivos
    quality_ok: bool               # Supera umbral de calidad
    generic_messages: list[str]    # Ejemplos de mensajes genéricos detectados
    contributors: list[Contributor]    # Quién participó y cuántos commits hizo cada uno
    commit_log: list[CommitLogEntry]   # Detalle de cada commit: fecha exacta, autor y mensaje
    score: float
    max_score: float
    details: dict[str, Any]


class WeeklyBreakdownEntry(TypedDict):
    """Una semana del período con sus fechas reales, para no mostrar 'Semana 1' en el informe."""
    week_key: str          # "2026-W25" (uso interno)
    start_date: str        # YYYY-MM-DD (lunes de esa semana)
    end_date: str           # YYYY-MM-DD (domingo de esa semana)
    count: int


class TemporalResult(TypedDict):
    """Resultado del Agente de Análisis Temporal."""
    last_commit_date: Optional[str]   # ISO-8601
    on_time: bool                     # Antes de la fecha límite
    weekly_counts: dict[str, int]     # {"2025-W01": 3, ...}
    weekly_breakdown: list[WeeklyBreakdownEntry]  # Igual que weekly_counts, pero con fechas reales
    active_weeks: int
    total_weeks: int
    activity_ok: bool                 # Actividad mínima semanal cumplida
    concentration_pct: float          # % de commits en los últimos N días
    concentration_alert: bool
    pattern_label: str                # "Trabajo continuo" | "Actividad irregular" | "Concentración al final"
    score: float
    max_score: float
    details: dict[str, Any]


class BranchRequirementResult(TypedDict):
    """Resultado de analizar requisitos de contenido dentro de una rama puntual
    (ej. "el README de la rama 'prompts' debe documentar los prompts usados")."""
    branch: str
    archivos_analizados: list[str]
    requirements_found: list[str]
    requirements_missing: list[str]
    summary: str


class ContentResult(TypedDict):
    """Resultado del Agente de Análisis de Contenido (usa Claude)."""
    requirements_found: list[str]   # Requisitos funcionales detectados (código + ramas)
    requirements_missing: list[str] # Requisitos funcionales ausentes (código + ramas)
    coherence_level: str            # "Alta" | "Media" | "Baja"
    llm_summary: str                # Resumen generado por Claude
    branch_requirements: list[BranchRequirementResult]  # Detalle por rama analizada
    score: float
    max_score: float
    details: dict[str, Any]



class RepoResult(TypedDict):
    """Resultado consolidado de un repositorio evaluado."""
    url: str
    owner: str
    repo_name: str
    student: str                    # owner 
    structural: Optional[StructuralResult]
    versioning: Optional[VersioningResult]
    temporal: Optional[TemporalResult]
    content: Optional[ContentResult]
    global_score: float             # Suma ponderada de los cuatro puntajes
    alerts: list[str]               # Alertas generadas por el coordinador
    pattern_label: str
    report_html: Optional[str]      # HTML del informe individual (Jinja2)
    error: Optional[str]            # Si hubo error al procesar este repo

    # Ajuste manual del docente sobre el puntaje calculado (ver PATCH /evaluate/.../score)
    score_overridden: bool
    original_score: Optional[float]   # Puntaje calculado por el sistema, antes del ajuste
    override_note: Optional[str]      # Justificación que escribió el docente



class EvaluationState(TypedDict):
    """
    RECORDATORIO 09/09/2026 (JP): cualquier campo nuevo que se necesite pasar entre nodos tiene
    que declararse acá, si no LangGraph no lo va a preservar.
    """
    # Inputs del docente
    repo_urls: list[str]
    criteria: dict[str, Any]        # Criterios cargados desde el YAML
    github_token: str

    # Cursor de iteración
    current_index: int              # Índice del repositorio en proceso

    # Datos extraídos del repositorio actual (Agente de Extracción)
    current_repo_data: Optional[dict[str, Any]]

    # Resultados parciales por agente (se limpian en cada ciclo)
    structural_result: Optional[StructuralResult]
    versioning_result: Optional[VersioningResult]
    temporal_result: Optional[TemporalResult]
    content_result: Optional[ContentResult]

    # Acumulador de resultados
    results: list[RepoResult]

    # Informe consolidado final (HTML)
    consolidated_report: Optional[str]

    # Log de errores no fatales
    errors: list[str]
