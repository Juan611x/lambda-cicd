"""Función Lambda: calculadora de tarifas de viaje.

Esta capa solo traduce entre el evento de AWS y las reglas de negocio de `fares.py`.
Acepta tres formas de invocación:
  - Directa (consola, AWS CLI o pipeline):  {"distance_km": 8.5, "duration_min": 22}
  - HTTP con cuerpo JSON (Function URL o API Gateway)
  - HTTP con parámetros en la URL:          ?distance_km=8.5&duration_min=22
"""

import json
import logging
import os

from fares import FareError, calculate_fare

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

REQUIRED_FIELDS = ("distance_km", "duration_min")
OPTIONAL_FIELDS = ("vehicle_type", "demand_multiplier", "pickup_hour", "promo_code")


def extract_payload(event):
    """Devuelve los datos del viaje sin importar cómo se invocó la función."""
    if not isinstance(event, dict):
        raise FareError("El evento debe ser un objeto JSON.")

    body = event.get("body")
    if body:
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            raise FareError("El cuerpo de la petición no es un JSON válido.") from None
        if not isinstance(payload, dict):
            raise FareError("El cuerpo de la petición debe ser un objeto JSON.")
        return payload

    if event.get("queryStringParameters"):
        return event["queryStringParameters"]

    return event


def respond(status_code, body):
    """Da a la respuesta el formato que esperan Function URL y API Gateway."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event, context):
    """Punto de entrada de la función."""
    version = os.environ.get("APP_VERSION", "local")
    try:
        payload = extract_payload(event)
        arguments = {field: payload.get(field) for field in REQUIRED_FIELDS}
        arguments.update({f: payload[f] for f in OPTIONAL_FIELDS if payload.get(f) is not None})
        fare = calculate_fare(**arguments)
    except FareError as error:
        logger.warning("Petición rechazada: %s", error)
        return respond(400, {"error": str(error), "version": version})

    logger.info(
        "Tarifa calculada: vehicle_type=%s total=%s version=%s",
        fare["vehicle_type"],
        fare["total"],
        version,
    )
    return respond(200, {**fare, "version": version})
