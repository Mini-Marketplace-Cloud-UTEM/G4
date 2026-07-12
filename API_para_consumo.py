from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, AliasChoices, ConfigDict
from typing import List, Optional
import G4pubsub
from sincronizar_catalogo import sincronizar_catalogo_inicial 
import uuid
from uuid import UUID
import httpx
import logica_negocio
import logging
import json
from datetime import datetime, timezone
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# CICLO DE VIDA DE LA API (Startup)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Todo lo que esté aquí se ejecuta ANTES de que la API empiece a recibir tráfico
    print("Levantando servidor del Grupo 4 (Inventario y Checkout)...")
    print("Sincronizando catálogo desde el Grupo 3...")
    
    try:
        # Llamamos a tu función que descarga e inserta los productos
        await sincronizar_catalogo_inicial()
        print("Sincronización de arranque completada.")
    except Exception as e:
        print(f"Error al intentar sincronizar al arranque: {e}")
    
    yield # Aquí la API se queda encendida y funcionando normalmente
    
    # Lo que esté aquí abajo se ejecuta cuando Render apaga el servidor
    print("Servidor del Grupo 4 yendo a dormir...")

# ==========================================
# INICIALIZACIÓN DE FASTAPI
# ==========================================
app = FastAPI(
    title="Grupo 4 - Cart, Checkout and Inventory API QA",
    description="API real construida en FastAPI para el Entregable 1. Integración con G1, G2 y G3.",
    version="1.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. MODELOS DE DATOS 
# ==========================================
class AddItemRequest(BaseModel):
    product_id: UUID = Field(validation_alias=AliasChoices("productId", "product_id"))
    quantity: int = Field(gt=0, validation_alias=AliasChoices("quantity", "qty"))
    model_config = ConfigDict(populate_by_name=True)

class UpdateItemRequest(BaseModel):
    quantity: int = Field(gt=0, validation_alias=AliasChoices("quantity", "qty"))
    model_config = ConfigDict(populate_by_name=True)

class CheckoutRequest(BaseModel):
    cart_id: str = Field(validation_alias=AliasChoices("cartId", "cart_id"))
    model_config = ConfigDict(populate_by_name=True)

class ReservationRequest(BaseModel):
    product_id: str = Field(validation_alias=AliasChoices("productId", "product_id"))
    cart_id: str = Field(validation_alias=AliasChoices("cartId", "cart_id"))
    user_id: str = Field(validation_alias=AliasChoices("userId", "user_id"))
    quantity: int
    model_config = ConfigDict(populate_by_name=True)

class CartItemResponse(BaseModel):
    item_id: str = Field(serialization_alias="itemId")
    product_id: str = Field(serialization_alias="productId")
    name: str
    quantity: int
    price: int = Field(serialization_alias="unitPrice")
    subtotal: int
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

class CartResponse(BaseModel):
    cart_id: str = Field(serialization_alias="cartId")
    user_id: Optional[str] = Field(None, serialization_alias="userId")
    status: str
    items: List[CartItemResponse] = []
    total_amount: int = Field(0, serialization_alias="totalAmount")
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

class ShippingAddress(BaseModel):
    street: str
    city: str
    region: str
    country: str
    postal_code: str = Field(validation_alias=AliasChoices("postalCode", "postal_code"))

class CheckoutPayload(BaseModel):
    shippingAddress: ShippingAddress
    notes: Optional[str] = ""
### ==========================================
### 2. DEPENDENCIA DE AUTENTICACIÓN (GRUPO 2)
### ==========================================
security = HTTPBearer(auto_error=False)
async def verificar_usuario_grupo2(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Optional[str]:
    """
    Se comunica con el MS del Grupo 2. 
    Retorna el user_id (UUID) si es un cliente válido, o Nil UUID si es un invitado.
    FUSIONADO: Incluye soporte para invitados y control de roles de admin/seller.
    """
    # 1. ESCENARIO INVITADO
    if not credentials:
        logger.info("Sesión: INVITADO (Se guardará como NULL en la BD)")
        return "00000000-0000-0000-0000-000000000000"
    
    token = credentials.credentials
    
    # 2. ESCENARIO LOGUEADO
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://grupo2-identidadusuario.onrender.com/auth/validate",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                datos_usuario = response.json()
                user_info = datos_usuario.get("user", datos_usuario)
                
                # 3. CONTROL DE ROLES
                roles_usuario = user_info.get("roles", [])
                if "admin" in roles_usuario or "seller" in roles_usuario:
                    raise HTTPException(
                        status_code=403, 
                        detail={"error_code": "FORBIDDEN", "message": "ADMIN_Y_SELLER_NO_PUEDEN_TENER_CARRITO"}
                    )
                
                # Extraemos el ID real del usuario
                user_id = user_info.get("id")
                logger.info(f"Sesión: USUARIO AUTENTICADO | ID: {user_id}")
                return user_id
            else:
                raise HTTPException(status_code=401, detail={"error_code": "UNAUTHORIZED", "message": "Token inválido o expirado según Grupo 2"})
                
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail={"error_code": "BAD_GATEWAY", "message": "Error de comunicación con el servicio de autenticación"})


# ==========================================
# 3. ENDPOINTS DE CARRITO (CART)
# ==========================================
@app.post("/v1/cart", response_model=CartResponse, tags=["Cart"])
async def create_cart(
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        logger.info(f"[{x_correlation_id}] Solicitud para crear nuevo carrito (Usuario: {user_id})")
        nuevo_cart_id = await logica_negocio.crear_carrito_bd(user_id=user_id)
        logger.info(f"[{x_correlation_id}] Carrito {nuevo_cart_id} creado exitosamente")
        
        return {"cart_id": nuevo_cart_id, "user_id": user_id, "status": "ACTIVE", "items": [], "total_amount": 0}
        
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al crear carrito: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al procesar la creación del carrito.",
                "correlation_id": x_correlation_id
            }
        )

@app.get("/v1/cart/{cart_id}", response_model=CartResponse, tags=["Cart"])
async def get_cart(
    cart_id: str, 
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") 
):
    try:
        logger.info(f"[{x_correlation_id}] Usuario {user_id} consultando el carrito {cart_id}")
        
        # MAGIA AQUÍ: Si el usuario es real (no es invitado), nos adueñamos del carrito
        if user_id and user_id != "00000000-0000-0000-0000-000000000000":
            await logica_negocio.asignar_usuario_a_carrito(cart_id, user_id)

        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        
        if resultado is None:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CART_NOT_FOUND", 
                    "message": "El carrito solicitado no existe.", 
                    "correlation_id": x_correlation_id
                }
            )
        return resultado
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al consultar carrito {cart_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al consultar el carrito.",
                "correlation_id": x_correlation_id
            }
        )

@app.post("/v1/cart/{cart_id}/items", response_model=CartResponse, tags=["Cart"])
async def add_item_to_cart(
    cart_id: str, 
    request: AddItemRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        logger.info(f"[{x_correlation_id}] Usuario {user_id} intentando agregar producto {request.product_id} al carrito {cart_id}")

        # --- LA MAGIA ESTÁ AQUÍ ---
        # Si el usuario es real (inició sesión), le asignamos el carrito inmediatamente
        if user_id and user_id != "00000000-0000-0000-0000-000000000000":
            await logica_negocio.asignar_usuario_a_carrito(cart_id, user_id)
        # ---------------------------

        carro_existente = await logica_negocio.obtener_carrito_completo(cart_id)
        if not carro_existente:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado al agregar ítem.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CART_NOT_FOUND", 
                    "message": "Carrito no encontrado.", 
                    "correlation_id": x_correlation_id
                }
            )
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"https://grupo-3-catalogo.onrender.com/products/{request.product_id}",
                    headers={"X-Consumer": "cart-service", "X-Correlation-Id": x_correlation_id or ""}
                )
            except httpx.RequestError:
                logger.error(f"[{x_correlation_id}] Falla al comunicarse con Catálogo para el producto {request.product_id}")
                raise HTTPException(
                    status_code=503, 
                    detail={
                        "error_code": "CATALOG_SERVICE_UNAVAILABLE", 
                        "message": "El servicio de catálogo no está disponible.", 
                        "correlation_id": x_correlation_id
                    }
                )
        if response.status_code == 404:
            logger.warning(f"[{x_correlation_id}] Producto {request.product_id} no existe en catálogo.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "PRODUCT_NOT_FOUND", 
                    "message": "El producto no existe en el catálogo.", 
                    "correlation_id": x_correlation_id
                }
            )
        
        producto_json = response.json()

        if "data" in producto_json and isinstance(producto_json["data"], dict):
            producto_data = producto_json["data"]
        else:
            producto_data = producto_json

        if producto_data.get("status") != "ACTIVE":
            logger.warning(f"[{x_correlation_id}] Producto {request.product_id} inactivo.")
            raise HTTPException(
                status_code=400, 
                detail={
                    "error_code": "INACTIVE_PRODUCT", 
                    "message": "No se puede agregar un producto inactivo al carrito.", 
                    "correlation_id": x_correlation_id
                }
            )

        precio_unidad = int(producto_data.get("price", 0)) 
        nombre_producto = producto_data.get("name", "Producto Genérico")

        await logica_negocio.agregar_item_bd(
            cart_id=cart_id, product_id=request.product_id, name=nombre_producto,
            quantity=request.quantity, precio_unitario=precio_unidad
        )
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        logger.info(f"[{x_correlation_id}] Producto {request.product_id} agregado exitosamente al carrito {cart_id}")
        return await logica_negocio.obtener_carrito_completo(cart_id)
        
    except HTTPException:
        raise 
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al agregar ítem: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al procesar la solicitud del carrito.",
                "correlation_id": x_correlation_id
            }
        )

@app.put("/v1/cart/{cart_id}/items/{item_id}", response_model=CartResponse, tags=["Cart"])
async def update_item_quantity(
    cart_id: str, 
    item_id: str, 
    request: UpdateItemRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Modifica la cantidad de un producto específico en el carrito."""
    try:
        logger.info(f"[{x_correlation_id}] Usuario {user_id} actualizando cantidad a {request.quantity} para el ítem {item_id} en el carrito {cart_id}")
        
        # FUSIONADO: Añadido el cart_id para que tu candado PENDING funcione
        await logica_negocio.actualizar_item_bd(cart_id, item_id, request.quantity)
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        
        if not resultado:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado al intentar actualizar.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CART_NOT_FOUND", 
                    "message": "Carrito no encontrado.", 
                    "correlation_id": x_correlation_id
                }
            )
            
        logger.info(f"[{x_correlation_id}] Ítem {item_id} actualizado exitosamente")
        return resultado

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al actualizar cantidad del ítem {item_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al actualizar la cantidad del producto en el carrito.",
                "correlation_id": x_correlation_id
            }
        )

@app.delete("/v1/cart/{cart_id}/items/{item_id}", response_model=CartResponse, tags=["Cart"])
async def remove_item_from_cart(
    cart_id: str, 
    item_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") 
):
    """Elimina un producto específico del carrito.""" 
    try: 
        logger.info(f"[{x_correlation_id}] Usuario {user_id} intentando eliminar: {item_id} del carrito: {cart_id}")
        
        # FUSIONADO: Añadido el cart_id para que tu candado PENDING funcione
        await logica_negocio.eliminar_item_bd(cart_id, item_id)
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        if not resultado:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado tras eliminar ítem.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CART_NOT_FOUND", 
                    "message": "Carrito no encontrado.", 
                    "correlation_id": x_correlation_id
                }
            )
        
        logger.info(f"[{x_correlation_id}] Ítem {item_id} eliminado exitosamente")
        return resultado
        
    except HTTPException:
        raise 
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al eliminar ítem {item_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al eliminar el producto del carrito.",
                "correlation_id": x_correlation_id
            }
        )

@app.patch("/v1/cart/{cart_id}/activate", tags=["Cart"])
async def reactivate_cart(
    cart_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Devuelve un carrito PENDING a estado ACTIVE si el usuario cancela el pago."""
    try:
        logger.info(f"[{x_correlation_id}] Intentando reactivar carrito {cart_id}")
        
        # Usamos la función blindada con ::uuid
        await logica_negocio.reactivar_carrito_bd(cart_id)
        
        logger.info(f"[{x_correlation_id}] Carrito {cart_id} reactivado a ACTIVE")
        return {"message": "Carrito reactivado exitosamente", "status": "ACTIVE"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error al reactivar carrito {cart_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al reactivar el carrito.",
                "correlation_id": x_correlation_id
            }
        )

# ==========================================
# 4. ENDPOINTS DE CHECKOUT 
# ==========================================

@app.get("/v1/checkout/{checkout_id}", tags=["Checkout"])
async def get_checkout_status(
    checkout_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Consulta el estado de un checkout directamente en la BD."""
    try:
        logger.info(f"[{x_correlation_id}] Consultando estado del checkout {checkout_id}")
        
        checkout = await logica_negocio.obtener_checkout_bd(checkout_id)
        
        if not checkout:
            logger.warning(f"[{x_correlation_id}] Checkout {checkout_id} no encontrado.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CHECKOUT_NOT_FOUND",
                    "message": "El checkout solicitado no existe.",
                    "correlation_id": x_correlation_id
                }
            )
            
        logger.info(f"[{x_correlation_id}] Checkout {checkout_id} consultado exitosamente")
        return checkout
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al consultar checkout {checkout_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al consultar el estado del checkout.",
                "correlation_id": x_correlation_id
            }
        )


@app.post("/v1/cart/{cart_id}/checkout", tags=["Checkout"])
async def checkout_cart(
    cart_id: str, 
    request_body: CheckoutPayload, # Recibimos la dirección del Front
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    token: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Orquestador de Checkout Final:
    1. Bloquea el carrito (PENDING).
    2. Llama a G5 enviando ítems y dirección para obtener orderId.
    3. Llama a G8 con el orderId para iniciar el pago.
    """
    try:
        logger.info(f"[{x_correlation_id}] Orquestando checkout para carrito {cart_id}")
        
        # --- 1. BLOQUEAR CARRITO ---
        cart = await logica_negocio.obtener_carrito_completo(cart_id)
        if not cart or not cart["items"]:
            raise HTTPException(status_code=400, detail="Carrito no encontrado o vacío.")
# +++ NUEVO BLOQUE: 1.5 RESERVAR STOCK +++
        url_reserva = "https://g4-carrito-checkout-inventario-y.onrender.com/v1/stock/reservations"
        
        # Armamos el payload con los items que queremos reservar
        payload_reserva = {
            "reservation_id": cart_id, # Usamos el ID del carrito para rastrearlo fácil
            "items": [
                {"product_id": item["product_id"], "quantity": item["quantity"]} 
                for item in cart["items"]
            ]
        }
        
        async with httpx.AsyncClient() as client:
            respuesta_reserva = await client.post(url_reserva, json=payload_reserva)
            
            if respuesta_reserva.status_code == 409 or respuesta_reserva.status_code == 400:
                # El 409 (Conflict) suele usarse cuando no hay stock suficiente
                raise HTTPException(status_code=409, detail="No hay stock suficiente para uno o más productos del carrito.")
            elif respuesta_reserva.status_code not in (200, 201):
                raise HTTPException(status_code=502, detail="Error al comunicarse con el servicio de inventario.")
        # +++ FIN NUEVO BLOQUE +++

        # Solo si la reserva fue exitosa, pasamos el carrito a PENDING
        await logica_negocio.cerrar_pedido(cart_id)
        # --- 2. LLAMAR A G5 (PEDIDOS) ---
        url_g5 = "https://api-grupo5-pedidos.onrender.com/orders"
        
        headers_g5 = {
            "Idempotency-Key": str(uuid.uuid4()), # G5 lo exige
            "X-Correlation-Id": x_correlation_id or str(uuid.uuid4()),
            "Authorization": f"Bearer {token.credentials}" if token else ""
        }
        
        # Mapeamos los items exactamente a como los pide G5 (snake_case)
        items_g5 = [
            {
                "product_id": item["product_id"],
                "name": item["name"],
                "quantity": item["quantity"],
                "unit_price": item["price"],
                "subtotal": item["subtotal"]
            } for item in cart["items"]
        ]
        
        payload_g5 = {
            "userId": user_id,
            "items": items_g5,
            "shippingAddress": request_body.shippingAddress.model_dump(by_alias=True),
            "notes": request_body.notes
        }
        
        async with httpx.AsyncClient() as client:
            respuesta_g5 = await client.post(url_g5, json=payload_g5, headers=headers_g5, timeout=15.0)
            if respuesta_g5.status_code not in (200, 201):
                await logica_negocio.reactivar_carrito_bd(cart_id)
                logger.error(f"[{x_correlation_id}] Error G5: {respuesta_g5.text}")
                raise HTTPException(status_code=502, detail="Error al crear el pedido en G5")
                
            datos_g5 = respuesta_g5.json()
            order_id = datos_g5.get("orderId") 

        # --- 3. LLAMAR A G8 (PAGOS) ---
        url_g8 = "https://g8-pagos-y-notificaciones.onrender.com/v1/payments"
        
        headers_g8 = {
            "Idempotency-Key": str(uuid.uuid4()), # G8 también lo exige
            "Authorization": f"Bearer {token.credentials}" if token else "",
            "X-Correlation-Id": x_correlation_id or ""
        }
        
        payload_g8 = {
            "orderId": order_id, 
            "userId": user_id,
            "amount": cart["total_amount"],
            "currency": "CLP",
            "method": "MERCADOPAGO"
        }
        
        async with httpx.AsyncClient() as client:
            respuesta_g8 = await client.post(url_g8, json=payload_g8, headers=headers_g8, timeout=15.0)
            if respuesta_g8.status_code not in (200, 201):
                await logica_negocio.reactivar_carrito_bd(cart_id)
                logger.error(f"[{x_correlation_id}] Error G8: {respuesta_g8.text}")
                raise HTTPException(status_code=502, detail="Error al iniciar el pago en G8")
                
            datos_pago = respuesta_g8.json()
            
        # --- 4. RESPONDER AL FRONTEND ---
        logger.info(f"[{x_correlation_id}] Orquestación completa. Redirigiendo a pago.")
        return {
            "message": "Checkout iniciado correctamente",
            "status": "PENDING_PAYMENT",
            "orderId": order_id,
            "paymentUrl": datos_pago.get("checkoutUrl") 
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error crítico: {str(e)}")
        try:
            await logica_negocio.reactivar_carrito_bd(cart_id)
        except:
            pass
        raise HTTPException(status_code=500, detail="Error interno durante el orquestado de checkout")
#Esto le falta al QA. Debo agregarlo
@app.patch("/v1/cart/{cart_id}/complete", tags=["Checkout"])
async def complete_checkout(
    cart_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Marca el carrito como COMPLETED definitivo tras confirmar el pago."""
    try:
        logger.info(f"[{x_correlation_id}] Confirmando pago y cerrando carrito {cart_id} a COMPLETED")
        
        # 1. Verificamos que el carrito exista
        cart = await logica_negocio.obtener_carrito_completo(cart_id)
        if not cart:
            raise HTTPException(
                status_code=404, 
                detail={"error_code": "CART_NOT_FOUND", "message": "Carrito no encontrado"}
            )
            
        # 2. Pasamos el estado a COMPLETED en la BD
        await logica_negocio.completar_pedido_bd(cart_id)
        
        logger.info(f"[{x_correlation_id}] Carrito {cart_id} completado con éxito")
        return {"message": "Pago confirmado, carrito cerrado exitosamente", "status": "COMPLETED"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error al completar carrito {cart_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error interno al cerrar el pedido."
            }
        )
@app.patch("/v1/cart/{cart_id}/cancel_checkout", tags=["Checkout"])
async def cancel_checkout(
    cart_id: str, 
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """
    Cancela un proceso de checkout en curso:
    1. Libera las reservas de stock en el inventario.
    2. Devuelve el carrito al estado ACTIVE.
    """
    try:
        logger.info(f"[{x_correlation_id}] Cancelando checkout para carrito {cart_id}")
        
        cart = await logica_negocio.obtener_carrito_completo(cart_id)
        if not cart:
            raise HTTPException(status_code=404, detail="Carrito no encontrado.")

        # 1. Llamar al DELETE de Inventario para liberar el stock
        # Asumimos que la URL base de tu inventario es esta (¡Cámbiala si es otra!)
        url_inventario_base = "https://URL_DE_TU_INVENTARIO/v1/stock/reservations"
        
        # Opcional: Si en tu base de datos guardaste un reservation_id, lo usas. 
        # Si tu sistema usa el mismo cart_id como ID de reserva (muy común), mandamos el cart_id.
        reserva_id = cart_id 
        
        async with httpx.AsyncClient() as client:
            respuesta_inv = await client.delete(f"{url_inventario_base}/{reserva_id}")
            if respuesta_inv.status_code not in (200, 204):
                logger.warning(f"[{x_correlation_id}] No se pudo liberar stock o no había reserva activa: {respuesta_inv.text}")
                # No lanzamos error para no bloquear al usuario, pero lo logueamos

        # 2. Devolver el carrito a ACTIVE
        await logica_negocio.reactivar_carrito_bd(cart_id)
        
        logger.info(f"[{x_correlation_id}] Checkout cancelado. Carrito {cart_id} vuelve a ACTIVE.")
        return {
            "message": "Checkout cancelado. Los productos han sido devueltos a la tienda.",
            "status": "ACTIVE"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error al cancelar checkout: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno al intentar cancelar el checkout.")
### ==========================================
### 5. ENDPOINTS DE INVENTARIO (RESERVAS)
### ==========================================

@app.get("/v1/inventory/{product_id}", tags=["Inventory"])
async def check_inventory(
    product_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        logger.info(f"[{x_correlation_id}] Consultando inventario para producto {product_id}")
        resultado = await logica_negocio.consultar_inventario_bd(product_id)
        if not resultado:
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "PRODUCT_NOT_FOUND",
                    "message": "Producto no encontrado en inventario.",
                    "correlation_id": x_correlation_id
                }   
            )
        logger.info(f"[{x_correlation_id}] Inventario para producto {product_id} consultado exitosamente")
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error al consultar inventario para producto {product_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al consultar el inventario.",
                "correlation_id": x_correlation_id
            }
        )

@app.post("/v1/stock/reservations", tags=["Inventory"])
async def reserve_stock(
    request: ReservationRequest,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        logger.info(f"[{x_correlation_id}] Usuario {request.user_id} intentando reservar stock para producto {request.product_id} en carrito {request.cart_id}")
        
        # Llama a tu función real para insertar la reserva en Supabase
        resultado = await logica_negocio.crear_reserva_bd(
            request.product_id, request.cart_id, request.user_id, request.quantity
        )
        
        logger.info(f"[{x_correlation_id}] Reserva de stock para producto {request.product_id} creada exitosamente")
        return resultado
    
    except HTTPException:
        raise
    except Exception as e:
        mensaje_error = str(e)
        
        if "INSUFFICIENT_STOCK" in mensaje_error:
            logger.warning(f"[{x_correlation_id}] Falló la reserva: Stock insuficiente para el producto {request.product_id}")
            
            fecha_actual = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            evento_shortage = {
                "eventId": str(uuid.uuid4()),
                "eventType": "InventoryShortage",
                "version": "1.0",
                "occurredAt": fecha_actual,
                "producer": "g4-inventario",
                "correlationId": x_correlation_id or str(uuid.uuid4()), 
                "payload": {
                    "productId": request.product_id,
                    "currentStock": 0,
                    "requestedQuantity": request.quantity,
                    "occurredAt": fecha_actual
                }
            }
            print("Publicando evento para G7:", json.dumps(evento_shortage, indent=2))
            
            raise HTTPException(
                status_code=409, 
                detail={
                    "error_code": "INSUFFICIENT_STOCK",
                    "message": "No hay stock suficiente para crear la reserva.",
                    "correlation_id": x_correlation_id
                }
            )
            
        elif "PRODUCT_NOT_FOUND" in mensaje_error:
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "PRODUCT_NOT_FOUND",
                    "message": "El producto solicitado no existe.",
                    "correlation_id": x_correlation_id
                }
            )
            
        logger.error(f"[{x_correlation_id}] Error interno al crear reserva: {mensaje_error}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al crear la reserva de stock.",
                "correlation_id": x_correlation_id
            }
        )

@app.delete("/v1/stock/reservations/{reservation_id}", tags=["Inventory"])
async def release_stock(
    reservation_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        logger.info(f"[{x_correlation_id}] Intentando liberar stock para reserva {reservation_id}")
        resultado = await logica_negocio.liberar_reserva_bd(reservation_id)
        
        if resultado is False:
            logger.warning(f"[{x_correlation_id}] Reserva {reservation_id} no encontrada al intentar liberar.")
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "RESERVATION_NOT_FOUND",
                    "message": "La reserva especificada no existe o ya fue liberada.",
                    "correlation_id": x_correlation_id
                }
            )

        logger.info(f"[{x_correlation_id}] Stock liberado correctamente para la reserva {reservation_id}")
        return {"status": "RELEASED", "reservation_id": reservation_id, "message": "Stock liberado correctamente"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al liberar reserva {reservation_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al procesar la liberación de la reserva.",
                "correlation_id": x_correlation_id
            }
        )

### ==========================================
### 6. CONSUMIDOR DE EVENTOS (PUB/SUB)
### ==========================================
async def procesar_evento_pago_g8(evento_recibido: dict):
    """
    Esta función actuará como consumidor. Será llamada automáticamente 
    cuando el Bus de Eventos nos entregue un mensaje del Grupo 8.
    """
    tipo_evento = evento_recibido.get("eventType")
    correlation_id = evento_recibido.get("correlationId", str(uuid.uuid4()))
    fecha_actual = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    if tipo_evento == "PAYMENT_APPROVED":
        # 1. Aquí irá la lógica BD: await logica_negocio.confirmar_checkout(...)
        
        # --- ARMAMOS NUESTRO EVENTO: CheckoutConfirmed ---
        evento_confirmed = {
            "eventId": str(uuid.uuid4()),
            "eventType": "CheckoutConfirmed",
            "version": "1.0",
            "occurredAt": fecha_actual,
            "producer": "g4-checkout",
            "correlationId": correlation_id,
            "payload": {
                "orderId": evento_recibido.get("payload", {}).get("orderId"),
                "status": "CONFIRMED",
                "message": "El pago fue aprobado y el checkout se ha cerrado exitosamente."
            }
        }
        await G4pubsub.publicar_evento(evento_confirmed)
        
    elif tipo_evento == "PAYMENT_REJECTED":
        # 1. Aquí irá la lógica BD: await logica_negocio.fallar_checkout(...)
        # 2. Aquí irá la lógica BD: await logica_negocio.liberar_reserva_bd(...)
        
        # --- ARMAMOS NUESTRO EVENTO: CheckoutFailed ---
        evento_failed = {
            "eventId": str(uuid.uuid4()),
            "eventType": "CheckoutFailed",
            "version": "1.0",
            "occurredAt": fecha_actual,
            "producer": "g4-checkout",
            "correlationId": correlation_id,
            "payload": {
                "orderId": evento_recibido.get("payload", {}).get("orderId"),
                "status": "FAILED",
                "reason": "Pago rechazado por el banco (G8)",
                "action": "Inventory released"
            }
        }
        await G4pubsub.publicar_evento(evento_failed)

async def tarea_ttl_carritos():
    """Ciclo infinito que corre en segundo plano cada 5 minutos."""
    while True:
        await asyncio.sleep(300)  # Espera 5 minutos (300 segundos)
        print("INFO: Ejecutando limpieza de carritos PENDING...")
        await logica_negocio.limpiar_carritos_huerfanos_bd()

@app.on_event("startup")
async def iniciar_tareas_segundo_plano():
    """Se ejecuta automáticamente cuando arrancas el servidor en Render."""
    asyncio.create_task(tarea_ttl_carritos())
