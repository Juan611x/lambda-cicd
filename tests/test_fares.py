"""Pruebas de las reglas de negocio de la calculadora de tarifas."""

import pytest

from fares import PROMOS, TARIFFS, FareError, calculate_fare

# Viaje de referencia: 8,5 km y 22 minutos en vehículo estándar.
# 3500 (base) + 8,5 x 1200 (distancia) + 22 x 200 (tiempo) = 18100
REFERENCE = {"distance_km": 8.5, "duration_min": 22}
REFERENCE_SUBTOTAL = 18100


def test_viaje_estandar_sin_recargos():
    fare = calculate_fare(**REFERENCE)
    assert fare["breakdown"] == {
        "base_fare": 3500,
        "distance_fare": 10200,
        "time_fare": 4400,
        "subtotal": REFERENCE_SUBTOTAL,
        "night_surcharge": 0,
        "demand_surcharge": 0,
        "minimum_fare_adjustment": 0,
        "discount": 0,
    }
    assert fare["total"] == 18100
    assert fare["currency"] == "COP"
    assert fare["vehicle_type"] == "standard"


@pytest.mark.parametrize(
    ("vehicle_type", "expected_total"),
    [("standard", 18100), ("xl", 26100), ("premium", 36200)],
)
def test_cada_tipo_de_vehiculo_tiene_su_tarifa(vehicle_type, expected_total):
    # xl:      5000 + 8,5 x 1700 + 22 x 300 = 26050, redondeado a 26100
    # premium: 7000 + 8,5 x 2400 + 22 x 400 = 36200
    assert calculate_fare(**REFERENCE, vehicle_type=vehicle_type)["total"] == expected_total


def test_el_tipo_de_vehiculo_no_distingue_mayusculas():
    assert calculate_fare(**REFERENCE, vehicle_type=" XL ")["vehicle_type"] == "xl"


@pytest.mark.parametrize("hour", [22, 23, 0, 4])
def test_recargo_nocturno_del_20_por_ciento(hour):
    fare = calculate_fare(**REFERENCE, pickup_hour=hour)
    assert fare["is_night"] is True
    assert fare["breakdown"]["night_surcharge"] == 3620
    assert fare["total"] == 21700  # 18100 + 3620 = 21720, redondeado a 100


@pytest.mark.parametrize("hour", [5, 12, 21])
def test_sin_recargo_nocturno_de_dia(hour):
    fare = calculate_fare(**REFERENCE, pickup_hour=hour)
    assert fare["is_night"] is False
    assert fare["breakdown"]["night_surcharge"] == 0


def test_recargo_por_demanda():
    fare = calculate_fare(**REFERENCE, demand_multiplier=1.5)
    assert fare["breakdown"]["demand_surcharge"] == 9050
    assert fare["total"] == 27200  # 18100 + 9050 = 27150, redondeado a 100


def test_recargo_nocturno_y_demanda_se_suman():
    fare = calculate_fare(**REFERENCE, demand_multiplier=2, pickup_hour=23)
    assert fare["breakdown"]["night_surcharge"] == 3620
    assert fare["breakdown"]["demand_surcharge"] == 18100
    assert fare["total"] == 39800  # 18100 + 3620 + 18100 = 39820


def test_un_viaje_corto_se_ajusta_a_la_tarifa_minima():
    fare = calculate_fare(distance_km=1, duration_min=3)  # 3500 + 1200 + 600 = 5300
    assert fare["breakdown"]["minimum_fare_adjustment"] == 700
    assert fare["total"] == TARIFFS["standard"].minimum_fare


def test_descuento_porcentual():
    fare = calculate_fare(**REFERENCE, promo_code="VIAJE10")
    assert fare["breakdown"]["discount"] == 1810
    assert fare["total"] == 16300  # 18100 - 1810 = 16290, redondeado a 100


def test_el_descuento_no_supera_su_tope():
    fare = calculate_fare(distance_km=30, duration_min=60, promo_code="BIENVENIDA")
    # 3500 + 36000 + 12000 = 51500; el 20 % serían 10300, pero el tope es 5000
    assert fare["breakdown"]["discount"] == PROMOS["BIENVENIDA"].max_discount
    assert fare["total"] == 46500


def test_el_descuento_se_aplica_despues_de_la_tarifa_minima():
    fare = calculate_fare(distance_km=1, duration_min=3, promo_code="viaje10")
    assert fare["promo_code"] == "VIAJE10"
    assert fare["breakdown"]["discount"] == 600  # 10 % de la mínima (6000)
    assert fare["total"] == 5400


def test_acepta_numeros_escritos_como_texto():
    fare = calculate_fare(
        distance_km="8.5", duration_min="22", demand_multiplier="1.5", pickup_hour="23"
    )
    assert fare["breakdown"]["subtotal"] == REFERENCE_SUBTOTAL
    assert fare["is_night"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"distance_km": 0},
        {"distance_km": -3},
        {"distance_km": 201},
        {"distance_km": "abc"},
        {"distance_km": None},
        {"distance_km": True},
        {"distance_km": float("nan")},
        {"duration_min": 0},
        {"duration_min": 601},
        {"duration_min": None},
        {"vehicle_type": "moto"},
        {"vehicle_type": 7},
        {"demand_multiplier": 0.5},
        {"demand_multiplier": 3.1},
        {"pickup_hour": 24},
        {"pickup_hour": -1},
        {"pickup_hour": 10.5},
        {"promo_code": "NOEXISTE"},
        {"promo_code": 123},
    ],
)
def test_datos_invalidos_lanzan_un_error(overrides):
    with pytest.raises(FareError):
        calculate_fare(**{**REFERENCE, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"distance_km": 200},
        {"duration_min": 600},
        {"demand_multiplier": 1},
        {"demand_multiplier": 3},
        {"pickup_hour": 0},
        {"pickup_hour": 23},
    ],
)
def test_los_valores_en_el_limite_son_validos(overrides):
    assert calculate_fare(**{**REFERENCE, **overrides})["total"] > 0
