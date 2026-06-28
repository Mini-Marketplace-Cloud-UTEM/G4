Cualquier problema con la integración, contactar al Grupo 4.

# G4 - Cart, Checkout and Inventory API

Bienvenido a la API del Grupo 4. 

##  Enlace de documentación (Swagger)
Puedes probar todos nuestros endpoints en tiempo real aquí:
[https://g4-carrito-checkout-inventario-y.onrender.com/docs](https://g4-carrito-checkout-inventario-y.onrender.com/docs)

##  Cómo consumir nuestra API
Para integrar tu servicio con el nuestro, ten en cuenta lo siguiente:

### Headers Obligatorios
Todas las peticiones deben incluir los siguientes headers para ser aceptadas:
- `Authorization`: `Bearer token_de_prueba_123`
- `X-Correlation-Id`: `[UUID_unico_de_tu_peticion]`

### Ejemplos de Integración
Si necesitas agregar un producto al carrito, realiza un POST a `/v1/cart/{cart_id}/items` con el siguiente cuerpo JSON:
```json
{
  "productId": "ID_DEL_PRODUCTO",
  "quantity": 1
}

