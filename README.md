# lambda-cicd

Función AWS Lambda en Python que calcula la tarifa de un viaje (al estilo de una aplicación
de transporte), con un pipeline de CI/CD en GitHub Actions que la valida y la despliega en
cada `push` a `main`.

## Qué hace

Recibe los datos de un viaje y devuelve el precio con su desglose, en pesos colombianos.

| Campo | Obligatorio | Descripción |
|---|---|---|
| `distance_km` | Sí | Distancia del viaje, mayor que 0 y hasta 200 |
| `duration_min` | Sí | Duración del viaje en minutos, mayor que 0 y hasta 600 |
| `vehicle_type` | No | `standard` (por defecto), `xl` o `premium` |
| `demand_multiplier` | No | Multiplicador por demanda, entre 1.0 (por defecto) y 3.0 |
| `pickup_hour` | No | Hora de recogida, de 0 a 23; activa el recargo nocturno |
| `promo_code` | No | `BIENVENIDA` (20 %, hasta $5.000) o `VIAJE10` (10 %, hasta $3.000) |

### Reglas de cálculo

1. **Subtotal** = tarifa base + distancia × precio por km + tiempo × precio por minuto.
2. **Recargo nocturno**: 20 % del subtotal si la recogida es entre las 22:00 y las 04:59.
3. **Recargo por demanda**: subtotal × (multiplicador − 1).
4. **Tarifa mínima**: si la suma no alcanza la mínima del vehículo, se ajusta hasta ella.
5. **Descuento**: porcentaje del código promocional, con su tope.
6. El **total** se redondea a los 100 pesos más cercanos.

| Vehículo | Base | Por km | Por minuto | Mínima |
|---|---|---|---|---|
| `standard` | $3.500 | $1.200 | $200 | $6.000 |
| `xl` | $5.000 | $1.700 | $300 | $9.000 |
| `premium` | $7.000 | $2.400 | $400 | $12.000 |

### Ejemplo

Entrada:

```json
{ "distance_km": 8.5, "duration_min": 22, "pickup_hour": 23, "promo_code": "VIAJE10" }
```

Respuesta (`200`):

```json
{
  "currency": "COP",
  "vehicle_type": "standard",
  "is_night": true,
  "promo_code": "VIAJE10",
  "breakdown": {
    "base_fare": 3500,
    "distance_fare": 10200,
    "time_fare": 4400,
    "subtotal": 18100,
    "night_surcharge": 3620,
    "demand_surcharge": 0,
    "minimum_fare_adjustment": 0,
    "discount": 2172
  },
  "total": 19500,
  "version": "local"
}
```

Si falta un campo obligatorio o algún dato no es válido, responde `400` con
`{"error": "...", "version": "..."}`.

La función acepta invocación directa (el JSON de arriba como evento) y peticiones HTTP, con
los datos en el cuerpo o como parámetros de la URL. El campo `version` sale de la variable
de entorno `APP_VERSION`; si no existe, vale `local`.

## Estructura

```
lambda-cicd/
├── .github/
│   ├── workflows/ci-cd.yml       # Pipeline: build, test y deploy
│   └── actions/setup-python-env/ # Acción reutilizable que prepara Python
├── src/
│   ├── lambda_function.py        # Handler: lee el evento y arma la respuesta
│   └── fares.py                  # Reglas de negocio: tarifas, recargos y descuentos
├── tests/
│   ├── test_lambda_function.py   # Pruebas del handler
│   └── test_fares.py             # Pruebas de las reglas de negocio
├── infra/                       # Políticas de IAM del rol que usa el pipeline
├── scripts/
│   └── package.py                # Genera build/lambda.zip de forma reproducible
├── requirements.txt              # Dependencias que se empaquetan con la función (ninguna por ahora)
├── requirements-dev.txt          # pytest y ruff, con versión fijada
├── pyproject.toml                # Configuración de pytest y ruff
└── .gitignore
```

## Pipeline de CI/CD

El workflow `.github/workflows/ci-cd.yml` se ejecuta en cada `push` a `main` y tiene tres
etapas. Cada una es un job independiente que solo arranca si la anterior terminó bien.

| Etapa | Qué hace |
|---|---|
| **Build** | Revisa el código con `ruff`, genera `lambda.zip` y lo publica como artefacto junto con su SHA-256 |
| **Test** | Descarga ese paquete, comprueba su SHA-256 y ejecuta las pruebas con `pytest` contra él |
| **Deploy** | Sube el mismo paquete a AWS Lambda, publica una versión y la invoca para comprobar que responde |

### Autenticación en AWS

El paso de despliegue admite dos formas de autenticarse; el workflow usa la que encuentre
configurada.

| Forma | Configuración | Cuándo usarla |
|---|---|---|
| **OIDC** | Variable `AWS_ROLE_ARN` | Cuenta propia: GitHub asume un rol con credenciales temporales y no se guarda ninguna clave |
| **Credenciales temporales** | Secretos `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` y `AWS_SESSION_TOKEN` | Cuenta de laboratorio que no permite crear roles de IAM |

Con credenciales temporales hay que renovar los tres secretos cuando caducan; si no, el
despliegue falla con `ExpiredToken`. Se obtienen con:

```bash
aws configure export-credentials
```

### Variables y secretos del repositorio

Se definen en *Settings > Secrets and variables > Actions*:

| Nombre | Tipo | Contenido |
|---|---|---|
| `AWS_REGION` | Variable | Región de la función, por ejemplo `eu-west-1` |
| `LAMBDA_FUNCTION_NAME` | Variable | Nombre de la función Lambda |
| `AWS_ROLE_ARN` | Variable | Solo con OIDC: ARN del rol que asume el pipeline |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Secretos | Solo sin OIDC: credenciales temporales |

### Preparación de OIDC (solo en una cuenta con permisos de IAM)

La carpeta `infra/` contiene las dos políticas del rol que asume el pipeline:

| Archivo | Para qué sirve |
|---|---|
| `infra/trust-policy.json` | Solo deja asumir el rol a GitHub Actions desde la rama `main` de este repositorio |
| `infra/deploy-policy.json` | Permite actualizar, publicar e invocar únicamente la función `fare-calculator` |

```bash
aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
aws iam create-role --role-name github-actions-lambda-cicd --assume-role-policy-document file://infra/trust-policy.json
aws iam put-role-policy --role-name github-actions-lambda-cicd --policy-name deploy-fare-calculator --policy-document file://infra/deploy-policy.json
```

## Ejecutar en local

Requiere Python 3.13.

```bash
python -m venv .venv
.venv\Scripts\activate            # En macOS o Linux: source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check .                      # Revisión de estilo y errores comunes
pytest -v                         # Pruebas unitarias
python scripts/package.py         # Genera build/lambda.zip
```

## Configuración en AWS Lambda

| Parámetro | Valor |
|---|---|
| Runtime | Python 3.13 |
| Handler | `lambda_function.lambda_handler` |
| Variables de entorno | `APP_VERSION` (opcional), `LOG_LEVEL` (opcional, por defecto `INFO`) |
