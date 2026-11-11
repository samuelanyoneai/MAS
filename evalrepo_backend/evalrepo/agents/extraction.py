"""
Se usó PyGitHub en vez de llamar a la REST API a mano.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any

from github import Github, GithubException
from github.Repository import Repository

from errors import FatalEvaluationError
from state import EvaluationState

logger = logging.getLogger(__name__)


def extraction_agent(state: EvaluationState) -> dict[str, Any]:
    """
    Trae los datos del repo que toca según current_index y los mete en current_repo_data.
    """
    idx = state["current_index"]
    url = state["repo_urls"][idx]
    token = state["github_token"]
    criteria = state["criteria"]

    logger.info("[Extracción] Procesando (%d/%d): %s", idx + 1, len(state["repo_urls"]), url)

    try:
        repo_data = _fetch_repo(url, token, criteria)
        return {"current_repo_data": repo_data}
    except GithubException as e:
        detail = str(e.data or "")

        # credenciales inválidas: va a fallar igual en todos los repos que falten
        if e.status == 401:
            raise FatalEvaluationError(
                "El token de GitHub (GITHUB_TOKEN) no es válido o venció. "
                "Generá uno nuevo en github.com → Settings → Developer settings → "
                "Personal access tokens, y actualizá el archivo .env."
            ) from e

        # límite de peticiones agotado: seguir intentando solo gasta tiempo
        if e.status == 403 and "rate limit" in detail.lower():
            raise FatalEvaluationError(
                "Se agotó el límite de peticiones a la API de GitHub para este token. "
                "Esperá a que se reinicie (normalmente 1 hora) o usá un token con más cuota."
            ) from e

        # un solo repo sin acceso o inexistente — no afecta a los demás
        if e.status == 404:
            msg = f"Repositorio no encontrado o privado sin acceso: {url}"
        elif e.status == 403:
            msg = f"Acceso denegado por GitHub a {url}: {detail}"
        else:
            msg = f"Error de GitHub en {url} ({e.status}): {detail}"

        logger.error(msg)
        return {
            "current_repo_data": None,
            "errors": state["errors"] + [msg],
        }
    except FatalEvaluationError:
        raise
    except Exception as e:
        msg = f"Error inesperado extrayendo {url}: {e}"
        logger.error(msg)
        return {
            "current_repo_data": None,
            "errors": state["errors"] + [msg],
        }


def _fetch_repo(url: str, token: str, criteria: dict[str, Any]) -> dict[str, Any]:
    """Baja todo lo que necesitamos del repo con PyGitHub."""
    owner, repo_name = _parse_url(url)
    g = Github(token)
    repo: Repository = g.get_repo(f"{owner}/{repo_name}")

    # rango de fechas del período académico, sacado del YAML
    inicio_str = criteria["periodo"]["inicio"]
    fin_str = criteria["periodo"]["fin"]
    inicio = datetime.fromisoformat(inicio_str).replace(tzinfo=timezone.utc)
    fin = datetime.fromisoformat(fin_str).replace(tzinfo=timezone.utc)

    # commits dentro del período
    commits_raw = []
    try:
        for commit in repo.get_commits(since=inicio, until=fin):
            c = commit.commit
            commits_raw.append({
                "sha": commit.sha[:8],
                "message": c.message.split("\n")[0],
                "author": c.author.name if c.author else "unknown",
                "date": c.author.date.isoformat() if c.author and c.author.date else None,
        })
    except GithubException as e:
        logger.warning("No se pudieron obtener commits de %s/%s: %s", owner, repo_name, e)

    # árbol de archivos de la rama principal
    default_branch = repo.default_branch
    files_list: list[str] = []
    try:
        tree = repo.get_git_tree(default_branch, recursive=True)
        files_list = [item.path for item in tree.tree if item.type in ("blob", "tree")]
    except GithubException as e:
        logger.warning("No se pudo obtener el árbol de %s/%s: %s", owner, repo_name, e)

    # ramas
    branches: list[str] = []
    try:
        branches = [b.name for b in repo.get_branches()]
    except GithubException as e:
        logger.warning("No se pudieron obtener ramas de %s/%s: %s", owner, repo_name, e)

    # árbol de archivos de ramas puntuales que el docente haya pedido revisar
    # (ej. "el README tiene que estar en la rama 'docs', el código en 'main'")
    branch_files: dict[str, list[str]] = {default_branch: files_list}
    archivos_por_rama = criteria.get("estructural", {}).get("archivos_por_rama", {})
    requisitos_por_rama = criteria.get("contenido", {}).get("requisitos_por_rama", [])
    ramas_a_revisar = set(archivos_por_rama) | {g.get("rama") for g in requisitos_por_rama if g.get("rama")}
    for branch_name in ramas_a_revisar:
        if branch_name in branch_files:
            continue
        try:
            branch_tree = repo.get_git_tree(branch_name, recursive=True)
            branch_files[branch_name] = [
                item.path for item in branch_tree.tree if item.type in ("blob", "tree")
            ]
        except GithubException as e:
            logger.warning(
                "No se pudo obtener el árbol de la rama '%s' en %s/%s: %s",
                branch_name, owner, repo_name, e,
            )
            branch_files[branch_name] = []

    # contenido de archivos puntuales en ramas puntuales, para que el Agente de
    # Contenido pueda verificar requisitos tipo "el README de la rama 'prompts'
    # debe documentar los prompts usados"
    branch_content: dict[str, dict[str, str]] = {}
    content_cfg = criteria.get("contenido", {})
    max_chars_archivo = content_cfg.get("max_chars_archivo", 4000)
    for grupo in requisitos_por_rama:
        branch_name = grupo.get("rama")
        if not branch_name:
            continue
        nombres = grupo.get("archivos", ["README.md"])
        max_archivos_grupo = grupo.get("max_archivos", content_cfg.get("max_archivos", 10))
        branch_content[branch_name] = _fetch_named_files(
            repo, branch_name, nombres, branch_files.get(branch_name, []),
            max_files=max_archivos_grupo, max_chars=max_chars_archivo,
        )

    # README
    readme_content = ""
    try:
        readme = repo.get_readme()
        readme_content = readme.decoded_content.decode("utf-8", errors="replace")
    except GithubException:
        pass  # no tiene README, ni modo

    # código fuente, para que lo revise el agente de contenido
    code_files = _fetch_code_files(repo, default_branch, criteria, files_list)

    return {
        "url": url,
        "owner": owner,
        "repo_name": repo_name,
        "student": owner,
        "default_branch": default_branch,
        "commits": commits_raw,
        "files": files_list,
        "branches": branches,
        "branch_files": branch_files,
        "branch_content": branch_content,
        "readme_content": readme_content,
        "code_files": code_files,
        "periodo_inicio": inicio.isoformat(),
        "periodo_fin": fin.isoformat(),
    }


def _fetch_code_files(
    repo: Repository,
    branch: str,
    criteria: dict[str, Any],
    files_list: list[str],
) -> dict[str, str]:
    """Baja el código fuente que va a revisar Claude, respetando las extensiones y el límite de archivos del YAML."""
    content_cfg = criteria.get("contenido", {})
    extensions = tuple(content_cfg.get("extensiones_codigo", [".py", ".java", ".js"]))
    max_files = content_cfg.get("max_archivos", 10)
    max_chars = content_cfg.get("max_chars_archivo", 4000)

    selected = [
        f for f in files_list
        if any(f.endswith(ext) for ext in extensions)
           and not f.startswith(".")
           and "node_modules" not in f
           and "vendor" not in f
    ][:max_files]

    code_files: dict[str, str] = {}
    for path in selected:
        try:
            content = repo.get_contents(path, ref=branch)
            if hasattr(content, "decoded_content"):
                code_files[path] = content.decoded_content.decode("utf-8", errors="replace")[:max_chars]
        except Exception:
            pass

    return code_files


def _fetch_named_files(
    repo: Repository,
    branch: str,
    nombres: list[str],
    files_list: list[str],
    max_files: int = 10,
    max_chars: int = 4000,
) -> dict[str, str]:
    """Busca archivos por nombre (ej. 'README.md') en cualquier carpeta de una
    rama puntual y baja su contenido, para que el Agente de Contenido los analice.
    `max_files` y `max_chars` son configurables desde `contenido.max_chars_archivo`
    y `contenido.requisitos_por_rama[].max_archivos` en el YAML de criterios."""
    nombres_lower = {n.lower() for n in nombres}
    matched = [f for f in files_list if f.lower().rsplit("/", 1)[-1] in nombres_lower]

    contents: dict[str, str] = {}
    for path in matched[:max_files]:
        try:
            content = repo.get_contents(path, ref=branch)
            if hasattr(content, "decoded_content"):
                contents[path] = content.decoded_content.decode("utf-8", errors="replace")[:max_chars]
        except Exception:
            pass
    return contents


def _parse_url(url: str) -> tuple[str, str]:
    """Extrae owner y repo_name de una URL de GitHub."""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    # https://github.com/owner/repo → [-2], [-1]
    if len(parts) < 2:
        raise ValueError(f"URL de GitHub inválida: {url}")
    return parts[-2], parts[-1]
