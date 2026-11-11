"""
Revisa que estén los archivos y carpetas que pidió el docente, y que el
README pase el mínimo de caracteres configurado.
"""

from __future__ import annotations
import logging
from typing import Any

from state import EvaluationState, StructuralResult

logger = logging.getLogger(__name__)


def structural_agent(state: EvaluationState) -> dict[str, Any]:
    """Mira el repo actual y devuelve el resultado estructural para que lo junte el coordinador."""
    repo_data = state.get("current_repo_data")
    if not repo_data:
        return {}  # ya se dio cuenta el coordinador de que esto falló

    criteria_struct = state["criteria"].get("estructural", {})
    if not criteria_struct.get("habilitado", True):
        # el docente apagó esta dimensión, no debería restar puntos
        return {"structural_result": _empty_result(0.0)}

    peso = criteria_struct.get("peso", 25)
    try:
        result = _analyze(repo_data, criteria_struct)
    except Exception as e:
        # un dato inesperado de ESTE repo (ej. una ruta rara) no debería tumbar
        # toda la evaluación — se marca 0 en esta dimensión y se sigue
        msg = f"Error en análisis estructural de {repo_data.get('url', '?')}: {e}"
        logger.error(msg)
        return {
            "structural_result": _empty_result(float(peso)),
            "errors": state["errors"] + [msg],
        }

    logger.info(
        "[Estructural] %s/%s → %.1f/%.1f pts",
        repo_data["owner"], repo_data["repo_name"],
        result["score"], result["max_score"],
    )
    return {"structural_result": result}


def _analyze(repo_data: dict[str, Any], cfg: dict[str, Any]) -> StructuralResult:
    """Corre todas las verificaciones estructurales sobre un repo."""
    peso = cfg.get("peso", 25)
    archivos_requeridos: list[str] = cfg.get("archivos_requeridos", ["README.md"])
    readme_min_chars: int = cfg.get("readme_min_chars", 200)
    # {"rama": ["path1", "path2"]} — ej. el README debe estar en 'docs' y el código en 'main'
    archivos_por_rama: dict[str, list[str]] = cfg.get("archivos_por_rama", {})
    # [{"nombre": "config.py", "carpetas": ["src/", "app/"]}] — el archivo puede estar
    # en cualquiera de esas carpetas (o subcarpetas), no en una ruta exacta
    archivos_alternativos: list[dict[str, Any]] = cfg.get("archivos_alternativos", [])

    files_set = set(repo_data.get("files", []))
    # todo en minúscula para no pelearnos con mayúsculas al comparar
    files_lower = {f.lower() for f in files_set}

    found: list[str] = []
    missing: list[str] = []

    for required in archivos_requeridos:
        req_lower = required.lower().rstrip("/")
        # cuenta tanto si coincide exacto como si es prefijo de una ruta (carpetas)
        if _is_present(req_lower, files_lower):
            found.append(required)
        else:
            missing.append(required)

    # README
    readme_content: str = repo_data.get("readme_content", "")
    readme_exists = bool(readme_content)
    readme_char_count = len(readme_content)
    readme_ok = readme_char_count >= readme_min_chars

    # requisitos de archivo/carpeta en una rama puntual (no la rama principal)
    branch_files: dict[str, list[str]] = repo_data.get("branch_files", {})
    branch_checks: list[dict[str, Any]] = []
    for branch, paths in archivos_por_rama.items():
        branch_files_lower = {f.lower() for f in branch_files.get(branch, [])}
        for path in paths:
            found_here = _is_present(path.lower().rstrip("/"), branch_files_lower)
            branch_checks.append({"branch": branch, "path": path, "found": found_here})

    # requisitos de archivo en alguna de varias carpetas posibles
    alternative_checks: list[dict[str, Any]] = []
    for alt in archivos_alternativos:
        nombre = alt.get("nombre", "")
        carpetas = alt.get("carpetas", [])
        found_in = _find_in_any_folder(nombre, carpetas, files_set)
        alternative_checks.append({
            "nombre": nombre, "carpetas": carpetas,
            "found": found_in is not None, "found_in": found_in,
        })

    # el puntaje es proporcional a cuántos checks pasaron en total
    total_checks = len(archivos_requeridos) + 1 + len(branch_checks) + len(alternative_checks)
    passed_checks = (
        len(found) + (1 if readme_ok else 0)
        + sum(1 for c in branch_checks if c["found"])
        + sum(1 for c in alternative_checks if c["found"])
    )
    max_score = float(peso)
    score = round((passed_checks / total_checks) * max_score, 2) if total_checks > 0 else 0.0

    return StructuralResult(
        files_found=found,
        files_missing=missing,
        readme_exists=readme_exists,
        readme_char_count=readme_char_count,
        readme_ok=readme_ok,
        branch_checks=branch_checks,
        alternative_checks=alternative_checks,
        score=score,
        max_score=max_score,
        details={
            "archivos_requeridos": archivos_requeridos,
            "readme_min_chars": readme_min_chars,
            "total_files_in_repo": len(repo_data.get("files", [])),
        },
    )


def _is_present(required_lower: str, files_lower: set[str]) -> bool:
    """Chequea si un archivo o carpeta está en el repo, con o sin barra al final."""
    if required_lower in files_lower:
        return True
    if required_lower + "/" in files_lower:
        return True
    # para carpetas tipo 'src/', basta con que algún archivo empiece con ese prefijo
    prefix = required_lower.rstrip("/") + "/"
    return any(f.startswith(prefix) for f in files_lower)


def _find_in_any_folder(nombre: str, carpetas: list[str], files: set[str]) -> str | None:
    """Busca un archivo por nombre dentro de cualquiera de las carpetas dadas
    (incluye subcarpetas). Devuelve la ruta donde lo encontró, o None."""
    nombre_lower = nombre.lower()
    for carpeta in carpetas:
        prefix = carpeta.lower().rstrip("/") + "/"
        for f in files:
            f_lower = f.lower()
            if f_lower.startswith(prefix) and f_lower.rsplit("/", 1)[-1] == nombre_lower:
                return f
    return None


def _empty_result(max_score: float) -> StructuralResult:
    return StructuralResult(
        files_found=[], files_missing=[], readme_exists=False,
        readme_char_count=0, readme_ok=False,
        branch_checks=[], alternative_checks=[],
        score=0.0, max_score=max_score, details={"habilitado": False},
    )
