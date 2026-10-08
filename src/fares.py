"""Reglas de negocio para calcular la tarifa de un viaje.

Este módulo no sabe nada de AWS ni de HTTP: recibe datos y devuelve un desglose.
Así se puede probar sin simular ningún servicio.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY = "COP"
ROUNDING_STEP = Decimal(100)  # El total se redondea a los 100 pesos más cercanos

MAX_DISTANCE_KM = 200
MAX_DURATION_MIN = 600
MIN_DEMAND_MULTIPLIER = Decimal("1.0")
MAX_DEMAND_MULTIPLIER = Decimal("3.0")

NIGHT_SURCHARGE_RATE = Decimal("0.20")
NIGHT_HOURS = frozenset({22, 23, 0, 1, 2, 3, 4})  # De 22:00 a 04:59


@dataclass(frozen=True)
class Tariff:
    """Precios de un tipo de vehículo, en pesos."""

    base_fare: int
    per_km: int
    per_minute: int
    minimum_fare: int


@dataclass(frozen=True)
class Promo:
    """Descuento porcentual con un tope máximo, en pesos."""

    percent: Decimal
    max_discount: int


TARIFFS = {
    "standard": Tariff(base_fare=3500, per_km=1200, per_minute=200, minimum_fare=6000),
    "xl": Tariff(base_fare=5000, per_km=1700, per_minute=300, minimum_fare=9000),
    "premium": Tariff(base_fare=7000, per_km=2400, per_minute=400, minimum_fare=12000),
}

PROMOS = {
    "BIENVENIDA": Promo(percent=Decimal("0.20"), max_discount=5000),
    "VIAJE10": Promo(percent=Decimal("0.10"), max_discount=3000),
}


class FareError(ValueError):
    """Los datos del viaje no son válidos."""


def _to_decimal(value, field):
    """Convierte un número (o un texto numérico) en Decimal."""
    if value is None:
        raise FareError(f"Falta el campo obligatorio '{field}'.")
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise FareError(f"El campo '{field}' debe ser un número.")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise FareError(f"El campo '{field}' debe ser un número.") from None
    if not number.is_finite():
        raise FareError(f"El campo '{field}' debe ser un número.")
    return number


def _to_hour(value):
    """Convierte la hora de recogida en un entero entre 0 y 23."""
    number = _to_decimal(value, "pickup_hour")
    if number != number.to_integral_value() or not 0 <= number <= 23:
        raise FareError("El campo 'pickup_hour' debe ser una hora entera entre 0 y 23.")
    return int(number)


def _pesos(amount):
    """Redondea un importe a pesos enteros."""
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _round_total(amount):
    """Redondea el total al múltiplo de ROUNDING_STEP más cercano."""
    steps = (Decimal(amount) / ROUNDING_STEP).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(steps * ROUNDING_STEP)


def calculate_fare(
    distance_km,
    duration_min,
    vehicle_type="standard",
    demand_multiplier=1,
    pickup_hour=None,
    promo_code=None,
):
    """Calcula la tarifa de un viaje y devuelve el desglose.

    El cálculo sigue este orden:
      1. Subtotal = tarifa base + distancia + tiempo.
      2. Recargo nocturno (20 % del subtotal) si la recogida es entre las 22:00 y las 04:59.
      3. Recargo por demanda = subtotal x (multiplicador - 1).
      4. Si la suma no alcanza la tarifa mínima del vehículo, se ajusta hasta la mínima.
      5. Descuento del código promocional, con su tope.
      6. El total se redondea a los 100 pesos más cercanos.
    """
    distance = _to_decimal(distance_km, "distance_km")
    if not 0 < distance <= MAX_DISTANCE_KM:
        raise FareError(f"'distance_km' debe ser mayor que 0 y no superar {MAX_DISTANCE_KM}.")

    duration = _to_decimal(duration_min, "duration_min")
    if not 0 < duration <= MAX_DURATION_MIN:
        raise FareError(f"'duration_min' debe ser mayor que 0 y no superar {MAX_DURATION_MIN}.")

    if not isinstance(vehicle_type, str) or vehicle_type.strip().lower() not in TARIFFS:
        valid = ", ".join(sorted(TARIFFS))
        raise FareError(f"'vehicle_type' no es válido. Valores permitidos: {valid}.")
    vehicle_type = vehicle_type.strip().lower()
    tariff = TARIFFS[vehicle_type]

    multiplier = _to_decimal(demand_multiplier, "demand_multiplier")
    if not MIN_DEMAND_MULTIPLIER <= multiplier <= MAX_DEMAND_MULTIPLIER:
        limits = f"{MIN_DEMAND_MULTIPLIER} y {MAX_DEMAND_MULTIPLIER}"
        raise FareError(f"'demand_multiplier' debe estar entre {limits}.")

    is_night = pickup_hour is not None and _to_hour(pickup_hour) in NIGHT_HOURS

    promo = None
    if promo_code is not None:
        if not isinstance(promo_code, str) or promo_code.strip().upper() not in PROMOS:
            raise FareError("El código promocional no es válido.")
        promo_code = promo_code.strip().upper()
        promo = PROMOS[promo_code]

    base_fare = tariff.base_fare
    distance_fare = _pesos(distance * tariff.per_km)
    time_fare = _pesos(duration * tariff.per_minute)
    subtotal = base_fare + distance_fare + time_fare

    night_surcharge = _pesos(subtotal * NIGHT_SURCHARGE_RATE) if is_night else 0
    demand_surcharge = _pesos(subtotal * (multiplier - 1))

    before_minimum = subtotal + night_surcharge + demand_surcharge
    minimum_fare_adjustment = max(0, tariff.minimum_fare - before_minimum)
    before_discount = before_minimum + minimum_fare_adjustment

    discount = 0
    if promo is not None:
        discount = min(_pesos(before_discount * promo.percent), promo.max_discount)

    return {
        "currency": CURRENCY,
        "vehicle_type": vehicle_type,
        "is_night": is_night,
        "promo_code": promo_code,
        "breakdown": {
            "base_fare": base_fare,
            "distance_fare": distance_fare,
            "time_fare": time_fare,
            "subtotal": subtotal,
            "night_surcharge": night_surcharge,
            "demand_surcharge": demand_surcharge,
            "minimum_fare_adjustment": minimum_fare_adjustment,
            "discount": discount,
        },
        "total": _round_total(before_discount - discount),
    }
