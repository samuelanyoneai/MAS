"""
Este es el único agente que usa LLM
"""

from __future__ import annotations
import logging
from typing import Any

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from errors import FatalEvaluationError
from state import EvaluationState, ContentResult

logger = logging.getLogger(__name__)

MODEL_ID = "claude-sonnet-4-6"   # modelo

SYSTEM_PROMPT = """\
Eres un evaluador académico de código fuente estudiantil.
Tu tarea es verificar si el código provisto cumple una lista de requisitos
funcionales definidos por el docente.

Responde ÚNICAMENTE en el siguiente formato JSON, sin texto adicional:
{
  "requirements_found": ["requisito 1 exacto", "requisito 2 exacto"],
  "requirements_missing": ["requisito 3 exacto"],
  "coherence_level": "Alta | Media | Baja",
  "summary": "Resumen breve (máximo 3 oraciones) de los hallazgos principales."
}

Criterios para coherence_level:
- Alta: el código refleja claramente lo solicitado con buena estructura.
- Media: el código intenta cumplir los requisitos pero con limitaciones notables.
- Baja: el código está incompleto, mal estructurado o no refleja los requisitos.

No penalices errores de estilo ni de performance; enfócate en la funcionalidad.
"""

# Para ramas puntuales el contenido suele ser documentación (README, notas, prompts
# usados), no necesariamente código — el criterio de "coherencia" no aplica igual.
# Se piden TODAS las ramas en una sola llamada (una por sección "=== RAMA 'x' ===")
# para no multiplicar el costo y el tiempo cuando hay varios grupos configurados.
BRANCH_SYSTEM_PROMPT = """\
Eres un evaluador académico revisando el contenido de archivos de documentación
(README u otros) que el docente pidió verificar en ramas específicas del
repositorio del estudiante. El mensaje trae una o más ramas, cada una marcada
con "=== RAMA 'nombre' ===", con sus propios requisitos y contenido.

Responde ÚNICAMENTE en el siguiente formato JSON, sin texto adicional, con un
objeto por cada rama que te hayan pedido:
{
  "branches": [
    {
      "branch": "nombre exacto de la rama",
      "requirements_found": ["requisito 1 exacto", "requisito 2 exacto"],
      "requirements_missing": ["requisito 3 exacto"],
      "summary": "Resumen breve (máximo 3 oraciones) de los hallazgos en esa rama."
    }
  ]
}

Verifica cada requisito contra el contenido real de los archivos de SU rama. Si
el archivo no menciona o no documenta lo pedido, es un requisito ausente.
"""


def content_agent(state: EvaluationState) -> dict[str, Any]:
    """Le manda el código (y, si corresponde, archivos de ramas puntuales) a Claude
    y devuelve el resultado del análisis de contenido."""
    repo_data = state.get("current_repo_data")
    if not repo_data:
        return {}

    cfg = state["criteria"].get("contenido", {})
    if not cfg.get("habilitado", True):
        peso = cfg.get("peso", 10)
        return {"content_result": _empty_result(float(peso))}

    try:
        result = _analyze(repo_data, cfg)
    except anthropic.AuthenticationError as e:
        # la API key de Claude está mal — va a fallar exactamente igual en todos
        # los repos que falten, no tiene sentido seguir gastando llamadas a GitHub
        raise FatalEvaluationError(
            "La API key de Anthropic (ANTHROPIC_API_KEY) no es válida. "
            "Verificala en console.anthropic.com → API Keys y actualizá el archivo .env."
        ) from e
    except anthropic.PermissionDeniedError as e:
        raise FatalEvaluationError(
            "La API key de Anthropic no tiene permiso para usar el modelo "
            f"'{MODEL_ID}'. Revisá los permisos de la key en console.anthropic.com."
        ) from e
    except Exception as e:
        # cualquier otro problema (límite de peticiones, timeout, JSON raro de
        # Claude, etc.) solo afecta el puntaje de Contenido de ESTE repo
        logger.error("[Contenido] Error llamando a Claude: %s", e)
        peso = cfg.get("peso", 10)
        result = ContentResult(
            requirements_found=[],
            requirements_missing=[i["texto"] for i in _tag_items(cfg.get("requisitos_funcionales", []), rama=None)],
            coherence_level="Baja",
            llm_summary=f"No se pudo analizar el contenido: {e}",
            branch_requirements=[],
            score=0.0,
            max_score=float(peso),
            details={"error": str(e)},
        )

    logger.info(
        "[Contenido] %s/%s → %.1f/%.1f pts | coherencia: %s",
        repo_data["owner"], repo_data["repo_name"],
        result["score"], result["max_score"],
        result["coherence_level"],
    )
    return {"content_result": result}


def _tag_items(raw: list[Any], rama: str | None) -> list[dict[str, Any]]:
    """Acepta tanto requisitos como texto simple ("usa herencia") como objetos con
    peso propio ({"texto": "usa herencia", "peso_pct": 30}), y los marca con la
    rama a la que pertenecen (None = código principal)."""
    items: list[dict[str, Any]] = []
    for r in raw:
        if isinstance(r, dict):
            items.append({"texto": r.get("texto", ""), "peso_pct": r.get("peso_pct"), "rama": rama})
        else:
            items.append({"texto": r, "peso_pct": None, "rama": rama})
    return items


def _fill_missing_weights(items: list[dict[str, Any]], presupuesto: float) -> None:
    """Todos los requisitos — los del código principal y los de cada rama puntual —
    comparten el mismo presupuesto: el peso que el docente le dio a la dimensión
    de Contenido (ej. si Contenido vale 20%, los requisitos deben sumar 20 entre
    todos, no 100). En una sola pasada conjunta: si se normalizara cada grupo por
    separado, cada uno terminaría valiendo el presupuesto completo y habría que
    repartirlo de nuevo. A los que no traen peso propio se les reparte en partes
    iguales lo que quede disponible del presupuesto."""
    asignado = sum(i["peso_pct"] for i in items if i["peso_pct"] is not None)
    sin_peso = [i for i in items if i["peso_pct"] is None]
    if sin_peso:
        restante = max(0.0, presupuesto - asignado)
        parejo = restante / len(sin_peso)
        for i in sin_peso:
            i["peso_pct"] = parejo
    # si aun así el docente asignó manualmente más (o menos) del presupuesto entre
    # todos, reescalamos para que el puntaje no se dispare ni se quede corto
    total = sum(i["peso_pct"] for i in items)
    if total > 0 and presupuesto > 0 and abs(total - presupuesto) > 0.01:
        for i in items:
            i["peso_pct"] = i["peso_pct"] * presupuesto / total


def _analyze(repo_data: dict[str, Any], cfg: dict[str, Any]) -> ContentResult:
    """Llamada(s) a Claude con langchain-anthropic para revisar si se cumplen los requisitos."""
    peso = cfg.get("peso", 10)

    main_items = _tag_items(cfg.get("requisitos_funcionales", []), rama=None)
    rama_groups_cfg = cfg.get("requisitos_por_rama", [])
    rama_items_por_grupo: dict[str, list[dict[str, Any]]] = {}
    grupo_items_flat: list[dict[str, Any]] = []
    for grupo in rama_groups_cfg:
        rama = grupo.get("rama")
        if not rama:
            continue
        items = _tag_items(grupo.get("requisitos", []), rama=rama)
        rama_items_por_grupo[rama] = items
        grupo_items_flat += items

    all_items = main_items + grupo_items_flat
    _fill_missing_weights(all_items, peso)

    code_files: dict[str, str] = repo_data.get("code_files", {})
    found_texts: set[str] = set()
    coherence = "N/A"
    summary = ""
    files_analyzed: list[str] = []

    main_texts = [i["texto"] for i in all_items if i["rama"] is None]
    if main_texts:
        if code_files:
            parsed = _call_claude(
                SYSTEM_PROMPT,
                f"""Analiza el siguiente código fuente estudiantil y verifica si cumple estos requisitos:

REQUISITOS A VERIFICAR:
{_requirements_text(main_texts)}

CÓDIGO FUENTE DEL REPOSITORIO:
{_build_code_context(code_files)}

Verifica cada requisito y responde en el formato JSON indicado.""",
            )
            found_texts |= set(parsed.get("requirements_found", []))
            coherence = parsed.get("coherence_level", "Baja")
            summary = parsed.get("summary", "")
            files_analyzed = list(code_files.keys())
        else:
            summary = "No se encontraron archivos de código fuente para analizar."
            coherence = "Baja"

    # Requisitos de contenido por rama (ej. README con los prompts usados). Se
    # analizan todas las ramas en UNA sola llamada a Claude (en vez de una por
    # rama) para no multiplicar costo ni tiempo cuando hay varios grupos.
    branch_content: dict[str, dict[str, str]] = repo_data.get("branch_content", {})
    branch_results = _analyze_branches(rama_items_por_grupo, branch_content)
    for br in branch_results:
        found_texts |= set(br["requirements_found"])

    found = [i["texto"] for i in all_items if i["texto"] in found_texts]
    missing = [i["texto"] for i in all_items if i["texto"] not in found_texts]

    # el puntaje mezcla cuántos requisitos (ponderados, en puntos del propio peso
    # de Contenido) cumplió con qué tan coherente vio Claude el código principal
    puntos_cumplidos = sum(i["peso_pct"] for i in all_items if i["texto"] in found_texts)
    req_score = min(1.0, puntos_cumplidos / peso) if peso > 0 else 0.0
    coherence_bonus = {"Alta": 1.0, "Media": 0.6, "Baja": 0.2}.get(coherence, 0.2)
    raw_pct = (req_score * 0.7) + (coherence_bonus * 0.3)
    score = round(raw_pct * float(peso), 2) if all_items else 0.0

    return ContentResult(
        requirements_found=found,
        requirements_missing=missing,
        coherence_level=coherence,
        llm_summary=summary,
        branch_requirements=branch_results,
        score=score,
        max_score=float(peso),
        details={
            "files_analyzed": files_analyzed,
            "requisitos_pesos": {i["texto"]: round(i["peso_pct"], 2) for i in all_items},
        },
    )


def _analyze_branches(
    rama_items_por_grupo: dict[str, list[dict[str, Any]]],
    branch_content: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    """Analiza todos los grupos de requisitos por rama en una sola llamada a Claude
    (una sección por rama dentro del mismo prompt), en vez de una llamada por rama."""
    sin_archivos: list[dict[str, Any]] = []
    con_archivos: dict[str, tuple[list[str], dict[str, str]]] = {}
    for rama, items in rama_items_por_grupo.items():
        texts = [i["texto"] for i in items]
        archivos = branch_content.get(rama, {})
        if not archivos:
            sin_archivos.append({
                "branch": rama, "archivos_analizados": [],
                "requirements_found": [], "requirements_missing": texts,
                "summary": f"No se encontraron los archivos solicitados en la rama '{rama}'.",
            })
        else:
            con_archivos[rama] = (texts, archivos)

    if not con_archivos:
        return sin_archivos

    bloques = [
        f"""=== RAMA '{rama}' ===
REQUISITOS A VERIFICAR EN ESTA RAMA:
{_requirements_text(texts)}

CONTENIDO DE LA RAMA '{rama}':
{_build_code_context(archivos)}"""
        for rama, (texts, archivos) in con_archivos.items()
    ]
    user_prompt = (
        "Analiza el contenido de cada una de las siguientes ramas del repositorio "
        "y verifica si cumple los requisitos de esa rama puntual:\n\n"
        + "\n\n".join(bloques)
        + "\n\nResponde con un resultado por cada rama, en el formato JSON indicado."
    )

    parsed = _call_claude(BRANCH_SYSTEM_PROMPT, user_prompt, max_tokens=2048)
    por_rama = {b.get("branch"): b for b in parsed.get("branches", [])}

    resultados = list(sin_archivos)
    for rama, (texts, archivos) in con_archivos.items():
        b = por_rama.get(rama, {})
        resultados.append({
            "branch": rama,
            "archivos_analizados": list(archivos.keys()),
            "requirements_found": b.get("requirements_found", []),
            "requirements_missing": b.get("requirements_missing", texts),
            "summary": b.get("summary", ""),
        })
    return resultados


def _call_claude(system_prompt: str, user_prompt: str, max_tokens: int = 1536) -> dict[str, Any]:
    """Llamada a Claude con langchain-anthropic; devuelve el JSON ya parseado."""
    llm = ChatAnthropic(model=MODEL_ID, max_tokens=max_tokens, temperature=0)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    response = llm.invoke(messages)
    return _parse_json_response(response.content)


def _requirements_text(requisitos: list[str]) -> str:
    return "\n".join(f"- {r}" for r in requisitos)


def _build_code_context(code_files: dict[str, str]) -> str:
    """Junta todo el código en un solo bloque de texto para mandárselo a Claude."""
    parts: list[str] = []
    for path, content in code_files.items():
        parts.append(f"--- {path} ---\n{content}")
    return "\n\n".join(parts)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Saca el JSON de la respuesta de Claude, aunque venga envuelto en un bloque de markdown."""
    import json
    text = text.strip()
    # a veces Claude lo manda entre ```json ... ```, hay que sacarlo
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _empty_result(max_score: float) -> ContentResult:
    return ContentResult(
        requirements_found=[], requirements_missing=[],
        coherence_level="N/A",
        llm_summary="Dimensión de contenido deshabilitada.",
        branch_requirements=[],
        score=0.0, max_score=max_score, details={"habilitado": False},
    )
