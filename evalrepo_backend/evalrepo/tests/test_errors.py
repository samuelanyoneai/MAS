from __future__ import annotations

from errors import FatalEvaluationError


# Prueba para que FatalEvaluationError se comporte como una excepcion normal
def test_fatal_evaluation_error_guarda_el_mensaje():
    try:
        raise FatalEvaluationError("algo salio mal")
    except FatalEvaluationError as e:
        assert str(e) == "algo salio mal"


# Prueba para que FatalEvaluationError sea instancia de Exception
def test_fatal_evaluation_error_es_exception():
    assert issubclass(FatalEvaluationError, Exception)
