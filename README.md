# Grupo 4- Carrito, Checkout, Inventario y Concurrencia
(Se tienen otros readme en el repositorio para disposición y ver en que punto está el grupo en el momento)
Integrantes:

Javier Agusto (Lidel suplemo) - Ricardo Castillo - Ignacio Muñoz - Jaime Orellana - Carlos Quinteros

Servicio backend del **Grupo 4** para el ecosistema del Marketplace Distribuido (UTEM). Actúa como el núcleo transaccional del proceso de compra, tomando lo que el cliente quiera comprar, y tomando el inicio de sesión de un usuario, y los datos de envío de la persona

# ¿Qúe hace este servicio?

Nuestro microservicio administra el núcleo transaccional del proceso de compra del usuario. Sus responsabilidades principales incluyen:

-**Gestión de Compra**:Permite al usuario autenticado gestionar su sesión mediante la adición o eliminación de productos, mientras el servicio se encarga de calcular 100% en el backend los subtotales y totales reales.

-**Inventario Temporal y Concurrencia**: Actualiza de forma temporal el stock del producto mediante un **bloqueo pesimista** en la base de datos. Esto deja el stock reservado de forma segura y evita la sobreventa (concurrencia) cuando múltiples usuarios intentan comprar el mismo ítem al mismo tiempo. Si la transacción no se concreta, el servicio devuelve la reserva al conteo general.

-**Seguridad y Propiedad**:Garantiza mediante validaciones estrictas que la compra y el carrito pertenezcan única y exclusivamente al usuario que la está realizando.

-**Idempotencia**:Exige el uso obligatorio de una llave única (`Idempotency-Key`) en el checkout. Con esto, el servicio se asegura de no tener duplicidad de transacciones, protegiendo al sistema ante recargas de página, reintentos de red o "dobles clics" accidentales del cliente.

-----------------------------------------------------------------------------------------------------------------------------------
## Contrato de la API (REST y Eventos)

Nuestra API se divide en 10 endpoints REST síncronos y un catálogo de eventos asíncronos (Pub/Sub). 

**Headers Obligatorios:**
- Authorization: Bearer <token>`: Obligatorio en todos los endpoints para asegurar que el usuario solo modifique su propio carrito 
- Idempotency-Key: <uuid>`: Obligatorio en el módulo de Checkout para evitar doble cobro.

### 1. Endpoints REST

#### Módulo 1: Gestión de Carrito (Cart) 
| Método | Endpoint | Descripción |
| :--- | :---: | :--- |
| **POST** | `/v1/cart` | Crea un nuevo carrito vacío para el usuario autenticado. |
| **GET** | `/v1/cart/{cartId}` | Retorna el carrito con sus ítems y el monto total calculado. |
| **POST** | `/v1/cart/{cartId}/items` | Agrega un nuevo producto (`productId`, `quantity`) al carrito. |
| **PUT** | `/v1/cart/{cartId}/items/{itemId}` | Actualiza la cantidad de un ítem existente. |
| **DELETE**| `/v1/cart/{cartId}/items/{itemId}` | Elimina un ítem específico del carrito. |

#### Módulo 2: Checkout 
| Método | Endpoint | Descripción |
| :--- | :---: | :--- |
| **POST** | `/v1/checkout` | Inicia el proceso de compra basado en un `cartId`. Requiere `Idempotency-Key`. |
| **GET** | `/v1/checkout/{checkoutId}` | Consulta el estado actual de una intención de compra. |

#### Módulo 3: Inventario Temporal (Concurrencia)
| Método | Endpoint | Descripción |
| :--- | :---: | :--- |
| **GET** | `/v1/inventory/{productId}` | Consulta el stock real disponible (Stock Total G7 - Reservas Activas G4). |
| **POST** | `/v1/stock/reservations` | Crea un bloqueo/reserva temporal (15 minutos) de unidades. |
| **DELETE**| `/v1/stock/reservations/{reservationId}` | Libera manualmente una reserva antes de su expiración. |

-----------------------------------------------------------------------------------------------------------------------------------

### 2. Contrato de Eventos (Pub/Sub)

Para mantener la arquitectura desacoplada, nuestro servicio se comunica asíncronamente con el resto del ecosistema mediante eventos JSON estándar 

#### Eventos que NOSOTROS Publicamos
| Evento | Cuándo se emite |
| :--- | :---: |
| `CheckoutStarted` | Al iniciar exitosamente un checkout. |
| `StockReserved` | Cuando se logra asegurar el bloqueo de inventario. |
| `CheckoutConfirmed` | Cuando el proceso termina exitosamente. |
| `CheckoutFailed` | Si el proceso falla por errores externos o validaciones. |
| `StockReservationExpired` | Automáticamente a los 15 minutos si no se concreta el pago. |

#### Eventos que NOSOTROS Consumimos 
| Evento | Productor | Nuestra Acción Interna |
| :--- | :---: | :--- |
| `PaymentApproved` | **G8 (Pagos)** | Marcamos Checkout como `CONFIRMED` y Reservas como `COMPLETED`. |
| `PaymentRejected` | **G8 (Pagos)** | Marcamos Checkout como `FAILED` y liberamos el stock (`RELEASED`). |
| `OrderCreated` | **G5 (Pedidos)** | Asociamos el `orderId` final al registro de nuestro checkout. |
| `ProductPriceChanged` | **G3 (Catálogo)**| Recalculamos los totales de carritos activos antes de que confirmen. |

-----------------------------------------------------------------------------------------------------------------------------------
#INTEGRACIONES

Como el grupo se encarga ded la parte del núcleo transaccional de compra, las integraciones son con casi todos los demás grupos del entorno:

Grupo,Relación:

Grupo 1 — Frontend,Consume nuestros endpoints /v1/cart y /v1/checkout

Grupo 2 — Identidad,Validamos sesiones vía POST /auth/validate

Grupo 3 — Catálogo,Consultamos precios vía GET /v1/products/{id} y escuchamos ProductPriceChanged

Grupo 5 — Pedidos,Orquestamos la creación de la orden tras el checkout

Grupo 7 — Inventario Físico,Consultamos stock base vía GET /v1/products/{id}/stock

Grupo 8 — Pago Simulado,Escuchamos sus eventos PaymentApproved y PaymentRejected para confirmar o liberar stock

-----------------------------------------------------------------------------------------------------------------------------------
# Entorno de Pruebas (Mock API para el Grupo 1)

Para no bloquear el desarrollo del Frontend, hemos desplegado un servidor Mock en Render usando Prism. Este servidor valida los contratos OpenAPI y devuelve respuestas simuladas para que puedan probar sus interfaces.

**Base URL:** `https://api-mock-grupo4.onrender.com`

*Nota: Todas las peticiones deben incluir el header `Authorization: Bearer <token>` para pasar la validación de seguridad.*

| Acción | Método | Endpoint | ¿Requiere Body? (JSON) |
| :--- | :---: | :--- | :--- |
| **Obtener carrito** | `GET` | `/v1/cart/{cartId}` | No |
| **Agregar producto** | `POST` | `/v1/cart/{cartId}/items` | Sí (`productId`, `quantity`) |
| **Eliminar producto** | `DELETE` | `/v1/cart/{cartId}/items/{itemId}` | No |
| **Vaciar carrito** | `DELETE` | `/v1/cart/{cartId}` | No |
| **Iniciar Checkout** | `POST` | `/v1/checkout` | Sí (Datos de facturación) |
| **Consultar Checkout**| `GET` | `/v1/checkout/{checkoutId}` | No |

> **Importante:** Como este servidor está en la capa gratuita de Render, si no se ha usado en 15 minutos entrará en modo reposo. La primera petición puede tardar hasta 50 segundos en responder mientras "despierta". Las siguientes serán instantáneas.

### Datos de Prueba para el Mock

Para probar las peticiones en este entorno simulado, utilicen los siguientes datos de ejemplo que ya están cargados en el servidor:

* **Token de Autorización válido:** `Bearer mi-token-falso-123`
* **ID de Carrito de prueba (`cartId`):** `26f79265-51a4-9eb1-e729-81228c5ff597`

**Ejemplo de URL completa para hacer un GET (Obtener carrito):**
`https://api-mock-grupo4.onrender.com/v1/cart/26f79265-51a4-9eb1-e729-81228c5ff597`
-----------------------------------------------------------------------------------------------------------------------------------
#ESTADO DEL PROYECTO
En desarrollo — Fase E3.


