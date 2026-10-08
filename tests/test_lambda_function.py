"""Pruebas del handler: cómo se lee el evento y qué forma tiene la respuesta."""

import json

import pytest

from lambda_function import lambda_handler

TRIP = {"distance_km": 8.5, "duration_min": 22}


def invoke(event):
    """Invoca el handler y devuelve (código de estado, cuerpo ya convertido a dict)."""
    response = lambda_handler(event, None)
    return response["statusCode"], json.loads(response["body"])


def test_invocacion_directa():
    status, body = invoke(TRIP)
    assert status == 200
    assert body["total"] == 18100
    assert body["breakdown"]["subtotal"] == 18100


def test_peticion_http_con_cuerpo_json():
    status, body = invoke({"body": json.dumps({**TRIP, "vehicle_type": "xl"})})
    assert status == 200
    assert body["vehicle_type"] == "xl"
    assert body["total"] == 26100


def test_peticion_http_con_parametros_en_la_url():
    event = {
        "queryStringParameters": {"distance_km": "8.5", "duration_min": "22", "pickup_hour": "23"}
    }
    status, body = invoke(event)
    assert status == 200
    assert body["is_night"] is True
    assert body["total"] == 21700


def test_todas_las_opciones_juntas():
    event = {
        **TRIP,
        "vehicle_type": "premium",
        "demand_multiplier": 1.5,
        "pickup_hour": 2,
        "promo_code": "VIAJE10",
    }
    status, body = invoke(event)
    assert status == 200
    # 36200 + 7240 (noche) + 18100 (demanda) = 61540; descuento 10 % con tope de 3000
    assert body["breakdown"]["discount"] == 3000
    assert body["total"] == 58500


def test_los_campos_opcionales_en_null_se_ignoran():
    status, body = invoke({**TRIP, "promo_code": None, "pickup_hour": None})
    assert status == 200
    assert body["total"] == 18100


def test_falta_un_campo_obligatorio():
    status, body = invoke({"distance_km": 8.5})
    assert status == 400
    assert "duration_min" in body["error"]


def test_dato_invalido_devuelve_400():
    status, body = invoke({**TRIP, "vehicle_type": "moto"})
    assert status == 400
    assert "vehicle_type" in body["error"]


def test_cuerpo_que_no_es_json_devuelve_400():
    status, body = invoke({"body": "esto no es json"})
    assert status == 400
    assert "JSON" in body["error"]


def test_cuerpo_json_que_no_es_un_objeto_devuelve_400():
    status, _ = invoke({"body": "[1, 2, 3]"})
    assert status == 400


@pytest.mark.parametrize("event", [None, "texto", 42, []])
def test_un_evento_que_no_es_un_objeto_devuelve_400(event):
    status, body = invoke(event)
    assert status == 400
    assert "error" in body


def test_la_respuesta_declara_json_como_tipo_de_contenido():
    response = lambda_handler(TRIP, None)
    assert response["headers"]["Content-Type"].startswith("application/json")


def test_la_version_sale_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc1234")
    _, body = invoke(TRIP)
    assert body["version"] == "abc1234"


def test_la_version_tambien_se_incluye_en_los_errores(monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    _, body = invoke({})
    assert body["version"] == "local"
