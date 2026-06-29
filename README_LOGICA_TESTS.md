# Capa de Lógica de Negocio y Testing de Integración

Este documento detalla la implementación de las reglas de negocio (`logica_negocio.py`) y el script de validación de flujo (`test_flujo.py`).

## Arquitectura de Persistencia (`logica_negocio.py`)

Se resolvió la deuda técnica crítica de "almacenamiento en memoria" migrando la arquitectura hacia una persistencia real y robusta. 

* **Base de Datos en la Nube:** Integración con **PostgreSQL (Supabase)** utilizando el driver asíncrono `asyncpg`.
* **Cálculo de Totales en Backend:** Para evitar discrepancias de precios, el cálculo del `totalAmount` se realiza exclusivamente en el servidor mediante consultas SQL dinámicas (`SELECT sub_total`). La base de datos actúa como la única fuente de verdad.
* **Máquina de Estados de Pedidos:** Se implementó un flujo transaccional mediante la actualización de la columna `status` en la tabla `carts`, permitiendo transicionar de forma segura desde un estado `ACTIVE` (borrador) hacia `PENDING` (intención de checkout).

## Script de Pruebas: `test_flujo.py`

Para garantizar la estabilidad del código y facilitar la validación por parte de otros desarrolladores, se incluye un script de pruebas de integración automatizado que no requiere levantar el servidor web ni utilizar herramientas externas como Postman.

### Flujo Validado (Happy Path)

El script simula un flujo transaccional completo:
1. **Creación:** Instancia un nuevo carrito (`ACTIVE`) y genera su `UUID` en la base de datos.
2. **Inserción de Ítems:** Simula la agregación de múltiples productos con sus respectivas cantidades y precios unitarios.
3. **Cálculo y Persistencia:** Ejecuta la función de recálculo y valida que la base de datos guarde correctamente los subtotales y la suma final exacta en números enteros (CLP).
4. **Validación Matemática:** Compara el `totalAmount` extraído de la base de datos contra el resultado esperado en el código.
5. **Transición de Estado (Checkout):** Ejecuta el cierre del pedido y verifica mediante una consulta directa a PostgreSQL que el estado haya mutado exitosamente a `PENDING`.

### Ejecución de Pruebas

Para validar la lógica localmente, ejecutar en la terminal:
```bash
python test_flujo.py
