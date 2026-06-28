# G4 - Cart, Checkout and Inventory API

Bienvenido a la API del Grupo 4. Esta es nuestra interfaz de backend construida en FastAPI, que gestiona el carrito de compras, el proceso de checkout y la reserva de stock.

##  Documentación interactiva (Swagger)
Puedes probar todos nuestros endpoints en tiempo real sin necesidad de herramientas externas aquí:
[https://g4-carrito-checkout-inventario-y.onrender.com/docs](https://g4-carrito-checkout-inventario-y.onrender.com/docs)

##  Cómo integrar nuestra API
Para que otros servicios (Frontend o Backend) puedan consumir nuestra API, deben respetar el siguiente contrato:

### Headers obligatorios
Todas las peticiones deben incluir los siguientes headers:
- `Authorization`: `Bearer token_de_prueba_123`
- `X-Correlation-Id`: `[UUID_unico_de_tu_peticion]`

### Ejemplos de consumo

#### 1. Frontend (JavaScript / Fetch)
Si estás llamando a nuestra API desde una aplicación web:

1.- JAVASCRIPT
```javascript
const response = await fetch("[https://g4-carrito-checkout-inventario-y.onrender.com/v1/cart](https://g4-carrito-checkout-inventario-y.onrender.com/v1/cart)", {
  method: "POST",
  headers: {
    "Authorization": "Bearer token_de_prueba_123",
    "X-Correlation-Id": "req-001"
  }
});
const data = await response.json();
```
2.- PYTHON
```Python
import httpx

async def llamar_api_grupo4():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "[https://g4-carrito-checkout-inventario-y.onrender.com/v1/cart](https://g4-carrito-checkout-inventario-y.onrender.com/v1/cart)",
            headers={
                "Authorization": "Bearer token_de_prueba_123",
                "X-Correlation-Id": "req-001"
            }
        )
    return response.json()
```
