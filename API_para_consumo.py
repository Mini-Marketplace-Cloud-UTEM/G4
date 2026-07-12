import asyncio
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# TAREA EN SEGUNDO PLANO (CRON JOB - TTL)
# ==========================================
async def tarea_ttl_carritos():
    """Ciclo infinito que corre en segundo plano cada 5 minutos para liberar stock."""
    while True:
        await asyncio.sleep(300)  # Espera 5 minutos (300 segundos)
        logger.info("INFO TTL: Ejecutando limpieza de carritos PENDING (15 min)...")
        try:
            await logica_negocio.limpiar_carritos_huerfanos_bd()
        except Exception as e:
            logger.error(f"ERROR TTL: Fallo en tarea de fondo - {str(e)}")

# ==========================================
# CICLO DE VIDA DE LA API (Startup & Shutdown)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Todo lo que esté aquí se ejecuta ANTES de que la API empiece a recibir tráfico
    print("Levantando servidor del Grupo 4 (Inventario y Checkout)...")
    print("Sincronizando catálogo desde el Grupo 3...")
    
    try:
        await sincronizar_catalogo_inicial()
        print("Sincronización de arranque completada.")
    except Exception as e:
        print(f"Error al intentar sincronizar al arranque: {e}")
    
    # 🚀 INICIAMOS LA TAREA DEL TTL EN SEGUNDO PLANO
    tarea_background = asyncio.create_task(tarea_ttl_carritos())
    
    yield # Aquí la API se queda encendida y funcionando normalmente
    
    # Lo que esté aquí abajo se ejecuta cuando Render apaga el servidor
    print("Servidor del Grupo 4 yendo a dormir...")
    tarea_background.cancel() # Apagamos la tarea de forma limpia

# ==========================================
# INICIALIZACIÓN DE FASTAPI
# ==========================================
app = FastAPI(
    title="Grupo 4 - Cart, Checkout and Inventory API QA/PROD",
    description="API real construida en FastAPI. Integración con G1, G2, G3, G7 y G8.",
    version="1.3.0",
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
    if not credentials:
        logger.info("Sesión: INVITADO (Se guardará como NULL en la BD)")
        return "00000000-0000-0000-0000-000000000000"
    
    token = credentials.credentials
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://grupo2-identidadusuario.onrender.com/auth/validate",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                datos_usuario = response.json()
                user_info = datos_usuario.get("user", datos_usuario)
                
                roles_usuario = user_info.get("roles", [])
                if "admin" in roles_usuario or "seller" in roles_usuario:
                    raise HTTPException(
                        status_code=403, 
                        detail={"error_code": "FORBIDDEN", "message": "ADMIN_Y_SELLER_NO_PUEDEN_TENER_CARRITO"}
                    )
                
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
            detail={"error_code": "INTERNAL_SERVER_ERROR", "message": "Error al procesar la creación del carrito.", "correlation_id": x_correlation_id}
        )

@app.get("/v1/cart/{cart_id}", response_model=CartResponse, tags=["Cart"])
async def get_cart(
    cart_id: str, 
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        logger.info(f"[{x_correlation_id}] Usuario {user_id} consultando el carrito {cart_id}")
        
        # MAGIA AQUÍ: Asignación automática tras Login
        if user_id and user_id != "00000000-0000-0000-0000-000000000000":
            await logica_negocio.asignar_usuario_a_carrito(cart_id, user_id)

        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        
        if resultado is None:
            raise HTTPException(status_code=404, detail={"error_code": "CART_NOT_FOUND", "message": "El carrito solicitado no existe."})
        return resultado
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": "Error al consultar el carrito."})

@app.post("/v1/cart/{cart_id}/items", response_model=CartResponse, tags=["Cart"])
async def add_item_to_cart(
    cart_id: str, 
    request: AddItemRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        if user_id and user_id != "00000000-0000-0000-0000-000000000000":
            await logica_negocio.asignar_usuario_a_carrito(cart_id, user_id)

        carro_existente = await logica_negocio.obtener_carrito_completo(cart_id)
        if not carro_existente:
            raise HTTPException(status_code=404, detail={"error_code": "CART_NOT_FOUND", "message": "Carrito no encontrado."})
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"https://grupo-3-catalogo.onrender.com/products/{request.product_id}",
                    headers={"X-Consumer": "cart-service", "X-Correlation-Id": x_correlation_id or ""}
                )
            except httpx.RequestError:
                raise HTTPException(status_code=503, detail={"error_code": "CATALOG_SERVICE_UNAVAILABLE", "message": "Servicio de catálogo no disponible."})
                
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail={"error_code": "PRODUCT_NOT_FOUND", "message": "Producto no existe en catálogo."})
        
        producto_json = response.json()
        producto_data = producto_json.get("data", producto_json) if isinstance(producto_json, dict) else producto_json

        if producto_data.get("status") != "ACTIVE":
            raise HTTPException(status_code=400, detail={"error_code": "INACTIVE_PRODUCT", "message": "Producto inactivo."})

        precio_unidad = int(producto_data.get("price", 0)) 
        nombre_producto = producto_data.get("name", "Producto Genérico")

        await logica_negocio.agregar_item_bd(
            cart_id=cart_id, product_id=request.product_id, name=nombre_producto,
            quantity=request.quantity, precio_unitario=precio_unidad
        )
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        return await logica_negocio.obtener_carrito_completo(cart_id)
        
    except HTTPException:
        raise 
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": "Error al procesar la solicitud."})

@app.put("/v1/cart/{cart_id}/items/{item_id}", response_model=CartResponse, tags=["Cart"])
async def update_item_quantity(
    cart_id: str, 
    item_id: str, 
    request: UpdateItemRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        await logica_negocio.actualizar_item_bd(cart_id, item_id, request.quantity)
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        if not resultado:
            raise HTTPException(status_code=404, detail={"error_code": "CART_NOT_FOUND", "message": "Carrito no encontrado."})
            
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

@app.delete("/v1/cart/{cart_id}/items/{item_id}", response_model=CartResponse, tags=["Cart"])
async def remove_item_from_cart(
    cart_id: str, 
    item_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") 
):
    try: 
        await logica_negocio.eliminar_item_bd(cart_id, item_id)
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        if not resultado:
            raise HTTPException(status_code=404, detail={"error_code": "CART_NOT_FOUND", "message": "Carrito no encontrado."})
        
        return resultado
    except HTTPException:
        raise 
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

@app.patch("/v1/cart/{cart_id}/activate", tags=["Cart"])
async def reactivate_cart(
    cart_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Devuelve un carrito PENDING a estado ACTIVE si el usuario cancela el pago."""
    try:
        logger.info(f"[{x_correlation_id}] Intentando reactivar carrito {cart_id}")
        await logica_negocio.reactivar_carrito_bd(cart_id)
        return {"message": "Carrito reactivado exitosamente", "status": "ACTIVE"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

# ==========================================
# 4. ENDPOINTS DE CHECKOUT 
# ==========================================
@app.get("/v1/checkout/{checkout_id}", tags=["Checkout"])
async def get_checkout_status(
    checkout_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        checkout = await logica_negocio.obtener_checkout_bd(checkout_id)
        if not checkout:
            raise HTTPException(status_code=404, detail={"error_code": "CHECKOUT_NOT_FOUND", "message": "Checkout no existe."})
        return checkout
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

@app.post("/v1/cart/{cart_id}/checkout", tags=["Checkout"])
async def checkout_cart(
    cart_id: str, 
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Paso 1: Marca el carrito como PENDING, indicando intención de pedido."""
    try:
        cart = await logica_negocio.obtener_carrito_completo(cart_id)
        if not cart:
            raise HTTPException(status_code=404, detail={"error_code": "CART_NOT_FOUND", "message": "Carrito no encontrado."})
            
        await logica_negocio.cerrar_pedido(cart_id)
        return {"message": "Intención de pedido registrada correctamente", "status": "PENDING"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

@app.patch("/v1/cart/{cart_id}/complete", tags=["Checkout"])
async def complete_checkout(
    cart_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Paso 2: Marca el carrito como COMPLETED definitivo tras confirmar el pago."""
    try:
        cart = await logica_negocio.obtener_carrito_completo(cart_id)
        if not cart:
            raise HTTPException(status_code=404, detail={"error_code": "CART_NOT_FOUND", "message": "Carrito no encontrado"})
            
        await logica_negocio.completar_pedido_bd(cart_id)
        return {"message": "Pago confirmado, carrito cerrado exitosamente", "status": "COMPLETED"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

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
        resultado = await logica_negocio.consultar_inventario_bd(product_id)
        if not resultado:
            raise HTTPException(status_code=404, detail={"error_code": "PRODUCT_NOT_FOUND", "message": "Producto no encontrado."})
        return resultado
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

@app.post("/v1/stock/reservations", tags=["Inventory"])
async def reserve_stock(
    request: ReservationRequest,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        return await logica_negocio.crear_reserva_bd(request.product_id, request.cart_id, request.user_id, request.quantity)
    except HTTPException:
        raise
    except Exception as e:
        mensaje_error = str(e)
        if "INSUFFICIENT_STOCK" in mensaje_error:
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
            await G4pubsub.publicar_evento(evento_shortage)
            raise HTTPException(status_code=409, detail={"error_code": "INSUFFICIENT_STOCK", "message": "No hay stock suficiente."})
            
        elif "PRODUCT_NOT_FOUND" in mensaje_error:
            raise HTTPException(status_code=404, detail={"error_code": "PRODUCT_NOT_FOUND", "message": "Producto no existe."})
            
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})

@app.delete("/v1/stock/reservations/{reservation_id}", tags=["Inventory"])
async def release_stock(
    reservation_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    try:
        resultado = await logica_negocio.liberar_reserva_bd(reservation_id)
        if resultado is False:
            raise HTTPException(status_code=404, detail={"error_code": "RESERVATION_NOT_FOUND", "message": "Reserva no existe."})
        return {"status": "RELEASED", "reservation_id": reservation_id, "message": "Stock liberado."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error_code": "INTERNAL_SERVER_ERROR", "message": str(e)})
    
### ==========================================
### 6. CONSUMIDOR DE EVENTOS (PUB/SUB)
### ==========================================
async def procesar_evento_pago_g8(evento_recibido: dict):
    """
    Consumidor llamado automáticamente cuando el Bus nos entregue un mensaje de G8.
    """
    tipo_evento = evento_recibido.get("eventType")
    correlation_id = evento_recibido.get("correlationId", str(uuid.uuid4()))
    fecha_actual = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    if tipo_evento == "PAYMENT_APPROVED":
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
                "message": "El pago fue aprobado."
            }
        }
        await G4pubsub.publicar_evento(evento_confirmed)
        
    elif tipo_evento == "PAYMENT_REJECTED":
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
