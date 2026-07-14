# Grupo 4 - Cart, Checkout and Inventory API (Capa de Consumo)

**Proyecto de Arquitectura de Software - UTEM**

Este documento detalla la capa de exposición de la API para el dominio de Carrito de Compras y Checkout, implementada en el archivo `API_para_consumo.py`.

## Descripción General

La API de consumo está construida con **FastAPI** y actúa como la puerta de enlace para las operaciones del cliente. Su principal responsabilidad es recibir las peticiones HTTP, validar los contratos de entrada mediante **Pydantic** y orquestar la comunicación con servicios externos antes de delegar la persistencia a la lógica de negocio.

## Características Principales y Resolución de Deuda Técnica

* **Validación Estricta (Pydantic):** Se implementó validación de tipos y restricciones lógicas (ej. `quantity: int = Field(gt=0)`) para prevenir la entrada de datos corruptos o valores negativos, rebotando peticiones maliciosas (Error 422) antes de procesarlas.
* **Alineación con Contrato OpenAPI:** La API fue refactorizada para cumplir estrictamente con el contrato establecido (`contrato-g4.yaml`). Las respuestas JSON ahora utilizan la convención *camelCase* exigida por el frontend (`cartId`, `totalAmount`, `itemId`), resolviendo una deuda técnica crítica de integración.
* **Integración con Grupo 3 (Catálogo):** Se implementó un cliente asíncrono con `httpx` para consultar la disponibilidad y precio base de los productos directamente desde el microservicio de Catálogo, garantizando que no se agreguen productos inactivos o inexistentes (Status 404/400).
* **Manejo de Moneda Local:** El sistema está optimizado para trabajar con Pesos Chilenos (CLP). Se descartó el uso de punto flotante/decimales en favor de transacciones enteras (`int`) para evitar errores de precisión financiera.

## Endpoints Principales

* `POST /v1/cart/{cart_id}/items`: Valida el producto contra el Catálogo, verifica cantidades y delega la inserción y cálculo de totales a la capa de persistencia.
* `POST /v1/cart/{cart_id}/checkout`: Cambia el estado del carrito registrando la "Intención de pedido" e inicializa el flujo de pago.

---

## Flujo Resumido del Checkout Orquestado

La orquestación principal del endpoint de checkout sigue esta secuencia estricta:

1. El cliente envía el carrito y la dirección de despacho.
2. El servicio valida la identidad y restricciones de rol con el Grupo 2.
3. Se obtiene el carrito y se valida que tenga productos.
4. El estado cambia atómicamente de `ACTIVE` a `PENDING`.
5. Se crean reservas de stock para los productos.
6. Se consultan atributos físicos en el catálogo del Grupo 3.
7. Se solicita una cotización al Grupo 6.
8. Se calcula el total de productos más despacho.
9. Se publica o continúa el proceso de pago mediante integración asíncrona.
10. Ante un error, se reactiva el carrito y se liberan las reservas aplicables.

## Mapa de Integraciones de Microservicios

Nuestra API consume y provee información a los siguientes componentes:

* **Grupo 1 (Frontend):** Consume carrito, checkout e inventario.
* **Grupo 2 (Identidad):** Valida tokens y entrega la identidad/roles del usuario.
* **Grupo 3 (Catálogo):** Entrega productos, precios, estado, tamaño, origen y stock visible.
* **Grupo 6 (Despacho):** Calcula alternativas y costos de envío.
* **Grupo 8 (Pagos):** Publica eventos de pago aprobados o rechazados mediante GCP Pub/Sub.
* **RabbitMQ & GCP Pub/Sub:** Distribuye eventos producidos por el Grupo 4 y consume los eventos del Grupo 8.

## Políticas de Seguridad de la API

Para mantener la integridad del microservicio, se aplican las siguientes reglas de seguridad:
* Los roles `admin` y `seller` validados por el Grupo 2 no pueden utilizar el carrito de compras.
* Los secretos y credenciales (tokens, URLs externas, cadenas de base de datos) se reciben exclusivamente por variables de entorno y no deben versionarse.
* Los identificadores sensibles se redactan en los registros mediante `redact_identifier`.
* Se exige el uso de HTTPS y AMQPS (para RabbitMQ) en entornos productivos, gestionable a través del middleware TLS incluido en el código.
