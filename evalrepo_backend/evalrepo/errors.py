"""
Excepciones propias de EvalRepo.

La distinción importante es entre:
- Un error de UN repo puntual (ej. no existe, está vacío) → no debería tumbar
  el resto de la evaluación, solo ese repo queda marcado con error.
- Un error SISTÉMICO (ej. el token de GitHub o la API key de Claude están mal
  configurados) → va a fallar exactamente igual en TODOS los repos que falten,
  así que no tiene sentido seguir intentando uno por uno. `FatalEvaluationError`
  se usa para esos casos: al lanzarse desde un agente, LangGraph deja que se
  propague hacia afuera de `graph.invoke()`, y `_run_evaluation` en main.py la
  atrapa y corta la evaluación completa de inmediato, con un solo mensaje claro
  en vez de repetir el mismo error N veces.
"""

from __future__ import annotations


class FatalEvaluationError(Exception):
    """Error de configuración que va a repetirse igual en todos los repos
    restantes (credenciales inválidas, límite de peticiones agotado, etc.).
    Al lanzarse, corta toda la evaluación en vez de seguir repo por repo."""
    pass
