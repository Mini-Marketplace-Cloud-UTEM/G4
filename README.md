# Grupo 4 — Carrito de Compra, Checkout, Inventario y Concurrencia

Microservicio transaccional del **Mini Marketplace Cloud UTEM**, responsable de administrar el carrito de compra, coordinar el checkout, mantener reservas temporales de inventario y controlar accesos concurrentes al stock.

## Integrantes

| Integrante | Rol |
|---|---|
| Javier Agusto | LIDEL SUPLEMO |
| Ricardo Castillo | Desarrollo e integración |
| Ignacio Muñoz | Desarrollo e integración |
| Jaime Orellana | Desarrollo e integración |
| Carlos Quinteros | Desarrollo e integración |

## Estado del entregable

**Versión final integrada del Grupo 4.**

El servicio contiene la implementación consolidada de:

- Gestión de carritos para usuarios autenticados e invitados.
- Incorporación, modificación y eliminación de productos.
- Cálculo de subtotales y total general en el backend.
- Validación de identidad y restricciones de rol mediante el Grupo 2.
- Consulta de productos, precios y disponibilidad mediante el Grupo 3.
- Checkout orquestado con reserva de stock y cotización de despacho.
- Integración con despacho del Grupo 6.
- Publicación y consumo de eventos de integración.
- Reservas de inventario protegidas frente a concurrencia.
- Liberación y expiración de reservas.
- Prevención de procesamiento duplicado mediante estados transaccionales.

## Responsabilidad del microservicio

El Grupo 4 constituye el núcleo transaccional entre la selección de productos y la confirmación de una compra. Su responsabilidad termina cuando el carrito ha sido procesado y la información necesaria ha sido enviada a los servicios externos correspondientes.

### Carrito de compra

- Crea carritos asociados a usuarios o sesiones invitadas.
- Obtiene el contenido y estado de un carrito.
- Agrega productos utilizando el precio vigente del catálogo.
- Actualiza cantidades únicamente mientras el carrito esté `ACTIVE`.
- Elimina productos y recalcula el total.
- Permite asociar un carrito invitado a un usuario autenticado.

### Checkout

- Bloquea el carrito al pasar de `ACTIVE` a `PENDING`.
- Impide que dos solicitudes procesen simultáneamente el mismo carrito.
- Reserva el inventario requerido.
- Obtiene datos físicos del producto desde catálogo.
- Solicita una cotización de despacho al Grupo 6.
- Calcula el total final del proceso.
- Permite cancelar el checkout y reactivar el carrito.
- Completa o revierte el flujo según el resultado del pago recibido por eventos.

### Inventario y concurrencia

- Sincroniza el inventario inicial desde el catálogo del Grupo 3.
- Calcula el stock disponible como:

```text
stockDisponible = stockTotal - reservasActivas
```

- Crea reservas mediante una operación almacenada en PostgreSQL/Supabase.
- Rechaza la reserva con HTTP `409` cuando el stock es insuficiente.
- Libera reservas canceladas o rechazadas.
- Ejecuta limpieza periódica de carritos `PENDING` abandonados.

## Arquitectura

```text
                          ┌───────────────────────┐
                          │ Grupo 1 - Frontend    │
                          └───────────┬───────────┘
                                      │ REST/JSON
                                      ▼
┌──────────────────┐       ┌─────────────────────────────┐       ┌──────────────────┐
│ Grupo 2          │◀─────▶│ Grupo 4                     │◀─────▶│ Grupo 3          │
│ Identidad        │       │ Cart / Checkout / Inventory │       │ Catálogo         │
└──────────────────┘       └──────────────┬──────────────┘       └──────────────────┘
                                         │
                         ┌───────────────┼────────────────┐
                         │               │                │
                         ▼               ▼                ▼
                ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
                │ PostgreSQL /   │ │ Grupo 6      │ │ RabbitMQ /       │
                │ Supabase       │ │ Despacho     │ │ GCP Pub/Sub      │
                └────────────────┘ └──────────────┘ └──────────────────┘
```


## Tecnologías

- Python 3.10
- FastAPI
- Uvicorn
- Pydantic
- HTTPX
- PostgreSQL / Supabase
- asyncpg
- RabbitMQ mediante `aio-pika`
- Google Cloud Pub/Sub
- Docker

## Estructura del repositorio

```text
.
├── API_para_consumo.py          # Aplicación FastAPI y orquestación REST
├── logica_negocio.py            # Persistencia y reglas transaccionales
├── sincronizar_catalogo.py      # Sincronización inicial con Grupo 3
├── G4pubsub.py                   # Publicación y consumo de eventos
├── security_config.py           # Validación de secretos y utilidades de seguridad
├── contrato-g4.yaml             # Contrato OpenAPI de referencia
├── test_flujo.py                # Prueba funcional directa sobre la lógica
├── Dockerfile                   # Imagen de despliegue
├── requirements.txt             # Dependencias Python
├── .env.example                 # Variables de entorno requeridas
└── docs/
    ├── API.md                    # Referencia de endpoints
    ├── ARQUITECTURA.md           # Diseño técnico y flujo transaccional
    ├── INTEGRACIONES.md          # Contratos con otros grupos
    ├── DESPLIEGUE.md             # Ejecución local, Docker y producción
    └── PRUEBAS.md                # Estrategia de validación
```

## Requisitos previos

- Python 3.10 o superior.
- PostgreSQL accesible mediante una URL de conexión.
- Función almacenada `reserve_stock` y tablas del dominio creadas en la base de datos.
- Credenciales de RabbitMQ cuando se publican eventos.
- Credenciales y suscripción de Google Cloud Pub/Sub cuando se consumen eventos de pago.
- Acceso de red a los servicios de identidad, catálogo y despacho.

## Configuración

Copie el archivo de ejemplo:

```bash
cp .env.example .env
```

Variables principales:

| Variable | Obligatoria | Descripción |
|---|---:|---|
| `DATABASE_URL` | Sí | Cadena de conexión PostgreSQL/Supabase. |
| `RABBITMQ_URL` | Sí para eventos | Conexión RabbitMQ; en producción debe utilizar `amqps://`. |
| `ENVIRONMENT` | No | `local`, `development`, `test` o `production`. |
| `URL_G3_CATALOGO` | No | URL HTTPS del catálogo del Grupo 3. |
| `GCP_PAYMENT_PROJECT_ID` | Sí para pagos | Proyecto de Google Cloud que contiene la suscripción. |
| `GCP_PAYMENT_SUBSCRIPTION_ID` | Sí para pagos | Suscripción a eventos del Grupo 8. |
| `FIELD_ENCRYPTION_KEY` | Según uso | Clave Fernet para cifrado de campos sensibles. |

La cuenta de servicio de Google Cloud debe estar disponible como:

```text
GCP_SERVICE_ACCOUNT.json
```

Este archivo contiene secretos y **no debe versionarse**.

## Instalación y ejecución local

> El archivo `requirements.txt` del repositorio debe encontrarse codificado en un formato compatible con `pip`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn API_para_consumo:app --reload --host 0.0.0.0 --port 8000
```

En Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
uvicorn API_para_consumo:app --reload --host 0.0.0.0 --port 8000
```

Documentación interactiva:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Ejecución con Docker

```bash
docker build -t g4-cart-checkout-inventory .
docker run --rm -p 8000:8000 --env-file .env g4-cart-checkout-inventory
```

Consulte [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md) para el procedimiento completo.

## Endpoints implementados

### Carrito

| Método | Ruta | Propósito |
|---|---|---|
| `POST` | `/v1/cart` | Crear un carrito. |
| `GET` | `/v1/cart/{cart_id}` | Obtener un carrito. |
| `POST` | `/v1/cart/{cart_id}/items` | Agregar un producto. |
| `PUT` | `/v1/cart/{cart_id}/items/{item_id}` | Actualizar cantidad. |
| `DELETE` | `/v1/cart/{cart_id}/items/{item_id}` | Eliminar un producto. |
| `PATCH` | `/v1/cart/{cart_id}/activate` | Reactivar un carrito. |

### Checkout

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/v1/checkout/{checkout_id}` | Consultar un checkout. |
| `POST` | `/v1/cart/{cart_id}/checkout` | Iniciar el checkout del carrito. |
| `PATCH` | `/v1/cart/{cart_id}/cancel_checkout` | Cancelar checkout y reactivar carrito. |

### Inventario

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/v1/inventory/{product_id}` | Consultar stock total, reservado y disponible. |
| `POST` | `/v1/stock/reservations` | Crear una reserva temporal. |
| `DELETE` | `/v1/stock/reservations/{reservation_id}` | Liberar una reserva. |

La especificación de solicitudes, respuestas y códigos de error se encuentra en [docs/API.md](docs/API.md).

## Headers de integración

| Header | Uso |
|---|---|
| `Authorization: Bearer <token>` | Identifica al usuario a través del Grupo 2. Algunos flujos admiten invitado. |
| `X-Correlation-Id` | Correlaciona llamadas entre microservicios y registros. |
| `X-Request-Id` | Identifica una solicitud puntual enviada a otro servicio. |
| `X-Consumer` | Declara el microservicio consumidor. |

## Estados principales

### Carrito

| Estado | Significado |
|---|---|
| `ACTIVE` | Puede ser consultado y modificado. |
| `PENDING` | Checkout en proceso; las modificaciones quedan bloqueadas. |
| `COMPLETED` | Compra completada tras aprobación del pago. |

### Reserva

| Estado | Significado |
|---|---|
| `ACTIVE` | Stock temporalmente reservado. |
| `RELEASED` | Stock liberado por cancelación, rechazo o expiración. |
| `COMPLETED` | Reserva consumida por una compra confirmada, según la operación de base de datos. |

## Flujo resumido del checkout

1. El cliente envía el carrito y la dirección de despacho.
2. El servicio valida la identidad con el Grupo 2.
3. Se obtiene el carrito y se valida que tenga productos.
4. El estado cambia atómicamente de `ACTIVE` a `PENDING`.
5. Se crean reservas de stock para los productos.
6. Se consultan atributos físicos en el catálogo del Grupo 3.
7. Se solicita una cotización al Grupo 6.
8. Se calcula el total de productos más despacho.
9. Se publica o continúa el proceso de pago mediante integración asíncrona.
10. Ante error, se reactiva el carrito y se liberan las reservas aplicables.

## Concurrencia e integridad

La estrategia utilizada combina:

- Cambio condicional de estado: `UPDATE ... WHERE status = 'ACTIVE'`.
- Función almacenada para comprobar y reservar stock dentro de una operación controlada por la base de datos.
- Cálculo de disponibilidad descontando reservas activas.
- Bloqueo de actualizaciones y eliminaciones cuando el carrito no está activo.
- Limpieza periódica de carritos pendientes abandonados.
- Correlación de solicitudes para facilitar trazabilidad.

Esto evita sobreventa y reduce el riesgo de doble procesamiento ante clics repetidos o solicitudes concurrentes.

## Integraciones

| Grupo / servicio | Interacción |
|---|---|
| Grupo 1 — Frontend | Consume carrito, checkout e inventario. |
| Grupo 2 — Identidad | Valida tokens y entrega la identidad/roles del usuario. |
| Grupo 3 — Catálogo | Entrega productos, precios, estado, tamaño, origen y stock visible. |
| Grupo 6 — Despacho | Calcula alternativas y costos de envío. |
| Grupo 8 — Pagos | Publica eventos de pago aprobados o rechazados mediante GCP Pub/Sub. |
| RabbitMQ | Distribuye eventos producidos por el Grupo 4. |
| Supabase/PostgreSQL | Persiste carritos, ítems, inventario y reservas. |

Detalles en [docs/INTEGRACIONES.md](docs/INTEGRACIONES.md).

## Pruebas

La validación debe incluir, como mínimo:

- Creación y consulta de carrito.
- Agregado, modificación y eliminación de productos.
- Rechazo de productos inexistentes o inactivos.
- Rechazo de modificación de carritos `PENDING` o `COMPLETED`.
- Reserva exitosa e insuficiencia de stock.
- Dos checkouts concurrentes sobre el mismo carrito.
- Cancelación y reactivación.
- Aprobación y rechazo de pago.
- Caída temporal de servicios externos.

Consulte [docs/PRUEBAS.md](docs/PRUEBAS.md).

## Seguridad

- Los secretos se reciben por variables de entorno.
- Los identificadores se redactan en registros mediante `redact_identifier`.
- Las URLs externas configurables se validan como HTTPS.
- RabbitMQ debe utilizar AMQPS en producción.
- Los roles `admin` y `seller` no pueden utilizar carrito.
- No se deben versionar tokens, claves, cadenas de base de datos ni cuentas de servicio.
- La configuración CORS abierta debe restringirse a los orígenes autorizados antes de un despliegue productivo.
- El middleware de exigencia TLS se encuentra disponible en el código, pero debe habilitarse para producción.

Consulte también [DECISIONES_SEGURIDAD_G4.md](DECISIONES_SEGURIDAD_G4.md).

## Observaciones del entregable

- `API_para_consumo.py` representa la fuente de verdad de las rutas actualmente implementadas.
- `contrato-g4.yaml` debe mantenerse sincronizado con la implementación antes de publicarse como contrato definitivo.
- Las direcciones de algunos servicios externos están declaradas directamente en el código; se recomienda migrarlas completamente a variables de entorno.
- El consumidor de GCP intenta inicializarse al importar `G4pubsub.py`; los entornos sin credenciales registrarán el error, pero la API puede continuar dependiendo de la configuración instalada.

## Licencia

El proyecto conserva la licencia incluida en [LICENSE](LICENSE).



