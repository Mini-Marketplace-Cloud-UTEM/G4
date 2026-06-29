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
