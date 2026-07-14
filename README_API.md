# G4 - Cart, Checkout and Inventory API

Bienvenido a la API del Grupo 4. Nuestro microservicio transaccional es el responsable de administrar el carrito de compra, coordinar el checkout, mantener reservas temporales de inventario y controlar accesos concurrentes al stock.

## Integrantes del Equipo

| Integrante | Rol |
|---|---|
| Javier Agusto | LIDEL SUPLEMO |
| Ricardo Castillo | Desarrollo e integración |
| Ignacio Muñoz | Desarrollo e integración |
| Jaime Orellana | Desarrollo e integración |
| Carlos Quinteros | Desarrollo e integración |

## Tecnologías Principales
* Python 3.10, FastAPI, Uvicorn, Pydantic, HTTPX.
* PostgreSQL / Supabase (asyncpg).
* RabbitMQ (mediante `aio-pika`) y Google Cloud Pub/Sub.
* Docker.

## Cómo integrar nuestra API
Para que otros servicios (Frontend o Backend) puedan consumir nuestra API, deben respetar el siguiente contrato de cabeceras de integración:

### Headers obligatorios y de trazabilidad
* `Authorization`: Identifica al usuario a través del Grupo 2 mediante un token Bearer. Algunos flujos admiten usuario invitado.
* `X-Correlation-Id`: Correlaciona llamadas entre microservicios y registros.
* `X-Request-Id`: Identifica una solicitud puntual enviada a otro servicio.
* `X-Consumer`: Declara el microservicio consumidor.

### Documentación interactiva (Swagger)
Puedes probar todos nuestros endpoints en tiempo real (creación de carrito, checkout, inventario) aquí:
[https://g4-carrito-checkout-inventario-y.onrender.com/docs](https://g4-carrito-checkout-inventario-y.onrender.com/docs)
