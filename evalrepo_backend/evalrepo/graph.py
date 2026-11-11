"""
Acá se arma el grafo de LangGraph que mueve todo el flujo de EvalRepo.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from state import EvaluationState
from agents.extraction import extraction_agent
from agents.structural import structural_agent
from agents.versioning import versioning_agent
from agents.content import content_agent
from agents.coordinator import coordinator_agent, should_continue
from reports.generator import generate_reports_node


def build_graph() -> "CompiledGraph":
    """Arma y compila el grafo. Devuelve algo listo para invocar con un EvaluationState."""
    graph = StateGraph(EvaluationState)

    # nodos
    graph.add_node("extraction", extraction_agent)
    graph.add_node("structural", structural_agent)
    graph.add_node("versioning", versioning_agent)
    graph.add_node("content", content_agent)
    graph.add_node("coordinator", coordinator_agent)
    graph.add_node("generate_reports", generate_reports_node)

    graph.set_entry_point("extraction")

    # un repo pasa por estos cuatro agentes en orden
    graph.add_edge("extraction", "structural")
    graph.add_edge("structural", "versioning")
    graph.add_edge("versioning", "content")
    graph.add_edge("content", "coordinator")

    # el coordinador decide si queda algo por procesar
    graph.add_conditional_edges(
        "coordinator",
        should_continue,
        {
            "next_repo": "extraction",     # todavía hay repos en la lista
            "end": "generate_reports",     # ya terminamos, a generar el informe
        },
    )

    graph.add_edge("generate_reports", END)

    return graph.compile()


def initial_state(
    repo_urls: list[str],
    criteria: dict,
    github_token: str,
) -> EvaluationState:
    """Arma el estado con el que arranca una evaluación nueva (cursor en 0, todo vacío)."""
    return EvaluationState(
        repo_urls=repo_urls,
        criteria=criteria,
        github_token=github_token,
        current_index=0,
        current_repo_data=None,
        structural_result=None,
        versioning_result=None,
        temporal_result=None,
        content_result=None,
        results=[],
        consolidated_report=None,
        errors=[],
    )
