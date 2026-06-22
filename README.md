# G4 — Carrito, Checkout e Inventario Temporal

[cite_start]Servicio backend del **Grupo 4** para el ecosistema del Marketplace Distribuido (UTEM)[cite: 4]. [cite_start]Actúa como el núcleo transaccional del proceso de compra, coordinando la sesión del usuario antes de que se genere el pago y la orden final[cite: 17].

## ¿Qué hace este servicio?

[cite_start]Nuestro microservicio es responsable de administrar el proceso completo de compra previo al pago[cite: 7]. [cite_start]Sus responsabilidades clave se dividen en tres grandes módulos [cite: 253-276]:

1. [cite_start]**Gestión de Carrito:** Centraliza las acciones de agregar, modificar y eliminar productos de la sesión de compra[cite: 20, 21]. [cite_start]Aplica el principio de cero confianza al frontend: **todos los totales se calculan 100% en el backend** consultando los precios reales[cite: 22].
2. [cite_start]**Reserva de Inventario (Concurrencia):** Implementa un bloqueo pesimista en base de datos para evitar sobreventa[cite: 311, 339]. [cite_start]Toda reserva de stock expira exacta e irrevocablemente a los **15 minutos** de su creación [cite: 25, 122-123].
3. [cite_start]**Checkout e Idempotencia:** Coordina la intención de compra[cite: 23]. [cite_start]Exige el uso obligatorio de `Idempotency-Key` en las transacciones para evitar cobros dobles por clics accidentales o reintentos de red[cite: 27, 49, 136].

## Stack tecnológico

- **Backend:** Node.js
- [cite_start]**Base de datos Relacional:** PostgreSQL (Tablas `carts`, `cart_items`, `checkout_intents`, `stock_reservations`) [cite: 278-283]
- [cite_start]**Base de datos de Eventos:** Firestore [cite: 286]
- **Contenedor:** Docker

## Contrato de la API

[cite_start]El contrato completo (OpenAPI 3.0) define los 10 endpoints REST y los esquemas de error[cite: 360, 363]. 

[cite_start]**⚠️ Headers Obligatorios para todos los endpoints [cite: 132-134]:**
- `Authorization: Bearer <token>` (Validación estricta de propiedad del carrito).
- [cite_start]`Idempotency-Key: <uuid>` (Obligatorio SOLO para operaciones de Checkout [cite: 135-136]).

Para visualizar el contrato de forma interactiva con ejemplos:

```bash
npx @stoplight/prism-cli mock docs/G4_Contratos_REST.yaml
