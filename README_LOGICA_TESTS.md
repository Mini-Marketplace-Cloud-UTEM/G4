# Capa de Lógica de Negocio, Concurrencia y Testing

Este documento detalla la implementación de las reglas de negocio (`logica_negocio.py`) y el script de validación de flujo (`test_flujo.py`).

## Arquitectura de Persistencia e Integridad (`logica_negocio.py`)

Se resolvió la deuda técnica crítica de "almacenamiento en memoria" migrando la arquitectura hacia una persistencia real en **PostgreSQL (Supabase)**. La estrategia utilizada para garantizar la concurrencia e integridad combina:

* **Bloqueo y Cambio Condicional de Estado:** Se actualizan los estados mediante la instrucción `UPDATE ... WHERE status = 'ACTIVE'`. Esto impide que dos solicitudes procesen simultáneamente el mismo carrito.
* **Gestión Concurrente de Inventario:** Se utiliza una función almacenada en PostgreSQL/Supabase (`reserve_stock`) para comprobar y reservar stock dentro de una operación controlada por la base de datos[cite: 4]. Rechaza la reserva con un HTTP `409` cuando el stock es insuficiente.
* **Fórmula de Disponibilidad:** El sistema calcula el stock disponible restando las reservas activas al stock total (`stockDisponible = stockTotal - reservasActivas`).
* **Cálculo en Backend:** El cálculo de los subtotales y el total general se realiza exclusivamente en el backend para evitar vulnerabilidades.

## Máquina de Estados Transaccional

Para prevenir el procesamiento duplicado, se implementaron estados transaccionales estrictos:

### Estados del Carrito
* `ACTIVE`: Puede ser consultado y modificado.
* `PENDING`: Checkout en proceso; las modificaciones quedan bloqueadas.
* `COMPLETED`: Compra completada tras aprobación del pago.

### Estados de la Reserva de Stock
* `ACTIVE`: Stock temporalmente reservado.
* `RELEASED`: Stock liberado por cancelación, rechazo o expiración.
* `COMPLETED`: Reserva consumida por una compra confirmada.

## Script de Pruebas: `test_flujo.py`
El script automatizado valida el "Happy Path" del flujo transaccional directo sobre la lógica, incluyendo la creación del carrito, la inserción de ítems, y la transición de estado al realizar el checkout.
