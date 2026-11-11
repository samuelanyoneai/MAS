from __future__ import annotations

import pytest

from config.criteria_loader import load_criteria, _validate, get_deadline, get_peso, is_enabled
from tests.conftest import base_criteria


# Prueba para cargar el archivo de criterios real del proyecto sin errores
def test_load_criteria_default_yaml_es_valido():
    criteria = load_criteria()
    assert "periodo" in criteria
    assert "contenido" in criteria


# Prueba para cargar un archivo de criterios que no existe
def test_load_criteria_ruta_inexistente():
    with pytest.raises(FileNotFoundError):
        load_criteria("config/no_existe.yaml")


# Prueba para validar un criterio completo y correcto
def test_validate_criterios_correctos_no_lanza():
    _validate(base_criteria())


# Prueba para detectar que falta la seccion periodo
def test_validate_falta_seccion_periodo():
    criteria = base_criteria()
    del criteria["periodo"]
    with pytest.raises(ValueError, match="periodo"):
        _validate(criteria)


# Prueba para detectar que falta la seccion contenido
def test_validate_falta_seccion_contenido():
    criteria = base_criteria()
    del criteria["contenido"]
    with pytest.raises(ValueError, match="contenido"):
        _validate(criteria)


# Prueba para rechazar pesos que no suman 100
def test_validate_pesos_no_suman_100():
    criteria = base_criteria()
    criteria["estructural"]["peso"] = 50
    with pytest.raises(ValueError, match="deben sumar 100"):
        _validate(criteria)


# Prueba para que una dimension deshabilitada no cuente en la suma de pesos
def test_validate_dimension_deshabilitada_no_cuenta_en_suma():
    criteria = base_criteria()
    criteria["contenido"]["habilitado"] = False
    criteria["contenido"]["peso"] = 999  # no deberia importar, esta apagada
    criteria["estructural"]["peso"] = 35  # 35 + 40 + 25 = 100 sin contar contenido
    _validate(criteria)


# Prueba para rechazar la ausencia de fecha limite
def test_validate_sin_fecha_limite():
    criteria = base_criteria()
    del criteria["periodo"]["fecha_limite"]
    with pytest.raises(ValueError, match="fecha_limite"):
        _validate(criteria)


# Prueba para rechazar una fecha limite mal formada
def test_validate_fecha_limite_formato_invalido():
    criteria = base_criteria()
    criteria["periodo"]["fecha_limite"] = "31/12/2026"
    with pytest.raises(ValueError, match="ISO-8601"):
        _validate(criteria)


# Prueba para que get_deadline agregue UTC cuando la fecha no trae zona horaria
def test_get_deadline_agrega_utc_si_falta():
    criteria = base_criteria()
    deadline = get_deadline(criteria)
    assert deadline.tzinfo is not None


# Prueba para que get_peso devuelva el valor configurado
def test_get_peso_devuelve_valor_configurado():
    criteria = base_criteria()
    assert get_peso(criteria, "versionado") == 40.0


# Prueba para que get_peso devuelva 0 en una dimension inexistente
def test_get_peso_dimension_inexistente_devuelve_cero():
    criteria = base_criteria()
    assert get_peso(criteria, "no_existe") == 0.0


# Prueba para que is_enabled sea True por defecto si no se especifica
def test_is_enabled_por_defecto_true():
    criteria = {"estructural": {}}
    assert is_enabled(criteria, "estructural") is True


# Prueba para que is_enabled respete habilitado=False
def test_is_enabled_false_explicito():
    criteria = base_criteria()
    criteria["contenido"]["habilitado"] = False
    assert is_enabled(criteria, "contenido") is False
