#!/usr/bin/env python
"""
demo.py
Script para correr EvalRepo desde la línea de comandos, sin necesidad
de levantar el servidor ni Supabase. Corre el grafo directo y deja los
informes en HTML en una carpeta de salida. Pensado para mostrar el
funcionamiento del sistema sin depender de la infraestructura completa.

Uso:
  # Con lista de URLs directa
  python demo.py --urls https://github.com/user/repo1 https://github.com/user/repo2

  # Con archivo de texto (una URL por línea)
  python demo.py --urls repos.txt

  # Especificando directorio de salida y criterios
  python demo.py --urls repos.txt --output ./reportes-parcial1 --criteria config/default.yaml
"""

from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="EvalRepo — Evaluación automática de repositorios GitHub estudiantiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--urls", nargs="+", required=True,
        help="URLs de repositorios GitHub o ruta a un archivo .txt con una URL por línea",
    )
    parser.add_argument(
        "--criteria", default=None,
        help="Ruta al archivo YAML de criterios (default: config/default.yaml)",
    )
    parser.add_argument(
        "--output", default="./reportes",
        help="Directorio donde se guardarán los informes HTML (default: ./reportes)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar logs detallados de cada agente",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    _check_env()

    repo_urls = _resolve_urls(args.urls)
    if not repo_urls:
        _exit("No se encontraron URLs válidas.")

    from config.criteria_loader import load_criteria
    try:
        criteria = load_criteria(args.criteria)
    except (FileNotFoundError, ValueError) as e:
        _exit(f"Error en criterios: {e}")

    _banner(repo_urls, args.criteria or "config/default.yaml", args.output)

    from graph import build_graph, initial_state
    graph = build_graph()
    state = initial_state(
        repo_urls=repo_urls,
        criteria=criteria,
        github_token=os.environ["GITHUB_TOKEN"],
    )

    print("Iniciando evaluación...\n")
    final_state = graph.invoke(state)

    from reports.generator import save_reports
    output_dir = Path(args.output)
    save_reports(
        results=final_state["results"],
        consolidated_html=final_state.get("consolidated_report", ""),
        output_dir=output_dir,
    )

    _print_summary(final_state, output_dir)


def _check_env() -> None:
    missing = []
    for var in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        _exit(
            f"Variables de entorno no configuradas: {', '.join(missing)}\n"
            "Copia .env.example como .env y rellena los valores."
        )


def _resolve_urls(urls_arg: list[str]) -> list[str]:
    """Sirve tanto para URLs sueltas como para un .txt con una URL por línea."""
    if len(urls_arg) == 1 and Path(urls_arg[0]).is_file():
        return [
            u.strip()
            for u in Path(urls_arg[0]).read_text(encoding="utf-8").splitlines()
            if u.strip() and not u.strip().startswith("#")
        ]
    return [u.strip() for u in urls_arg if u.strip()]


def _banner(repo_urls: list[str], criteria_path: str, output: str) -> None:
    line = "─" * 58
    print(f"\n┌{line}┐")
    print(f"│  EvalRepo — Sistema Multi-Agente de Evaluación{' ' * 10}│")
    print(f"│  Universidad Técnica Particular de Loja · TIC 2025{' ' * 6}│")
    print(f"├{line}┤")
    print(f"│  Repositorios : {len(repo_urls):<40}│")
    print(f"│  Criterios    : {criteria_path:<40}│")
    print(f"│  Salida       : {output:<40}│")
    print(f"└{line}┘\n")


def _print_summary(state: dict, output_dir: Path) -> None:
    results = state.get("results", [])
    errors  = state.get("errors", [])

    line = "─" * 58
    print(f"\n┌{line}┐")
    print(f"│  Evaluación completada — {len(results)} repositorios{' ' * 20}│")
    print(f"├{line}┤")
    print(f"│  {'Repositorio':<32} {'Puntaje':>7}  {'Patrón':<17}│")
    print(f"│  {'─'*32} {'─'*7}  {'─'*17}│")

    for r in sorted(results, key=lambda x: x.get("global_score", 0), reverse=True):
        name    = f"{r.get('student','?')}/{r.get('repo_name','?')}"[:32]
        score   = r.get("global_score", 0)
        pattern = r.get("pattern_label", "—")[:17]
        status  = "OK " if score >= 70 else "ALT" if score >= 50 else "BAJ"
        print(f"│  {name:<32} {score:>6.1f}  {status} {pattern:<15}│")

    if errors:
        print(f"├{line}┤")
        print(f"│  Errores ({len(errors)}):{' ' * (47 - len(str(len(errors))))}│")
        for e in errors[:3]:
            truncated = e[:54]
            print(f"│    • {truncated:<52}│")

    print(f"├{line}┤")
    print(f"│  Informes guardados en: {str(output_dir):<33}│")
    print(f"└{line}┘\n")


def _exit(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
