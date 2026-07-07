from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, AliasChoices, ConfigDict
from typing import List, Optional
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
                "https://api-grupo2.onrender.com/api/v1/auth/validate",
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
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") # Agregado
):
    try:
        logger.info(f"[{x_correlation_id}] Usuario {user_id} consultando el carrito {cart_id}")
        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        
        if resultado is None:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado")
            # Error estructurado en lugar de texto simple
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

        carro_existente = await logica_negocio.obtener_carrito_completo(cart_id)
        if not carro_existente:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado al agregar ítem.")
            # Error estructurado
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
                    f"https://grupo-3-catalogo.onrender.com/v1/products/{request.product_id}",
                    headers={"X-Consumer": "cart-service", "X-Correlation-Id": x_correlation_id or ""}
                )
            except httpx.RequestError:
                logger.error(f"[{x_correlation_id}] Falla al comunicarse con Catálogo para el producto {request.product_id}")
                # Error estructurado
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
            # Error estructurado
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "PRODUCT_NOT_FOUND", 
                    "message": "El producto no existe en el catálogo.", 
                    "correlation_id": x_correlation_id
                }
            )
        
        producto_json = response.json()

        # CAPA ANTICORRUPCIÓN: Si el Grupo 3 envía el producto envuelto en "data", lo extraemos
        if "data" in producto_json and isinstance(producto_json["data"], dict):
            producto_data = producto_json["data"]
        else:
            producto_data = producto_json

        if producto_data.get("status") != "ACTIVE":
            logger.warning(f"[{x_correlation_id}] Producto {request.product_id} inactivo.")
            # Error estructurado
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
        raise # Dejamos pasar los errores que nosotros mismos provocamos arriba
    except Exception as e:
        # LOGTEAMOS EL ERROR CRÍTICO EN CONSOLA PARA RENDER
        logger.error(f"[{x_correlation_id}] Error interno al agregar ítem: {str(e)}")
        # DEVOLVEMOS EL ERROR ESTRUCTURADO AL CLIENTE
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
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") # 1. Agregamos el header
):
    """Modifica la cantidad de un producto específico en el carrito."""
    try:
        # 2. Log de inicio de la operación
        logger.info(f"[{x_correlation_id}] Usuario {user_id} actualizando cantidad a {request.quantity} para el ítem {item_id} en el carrito {cart_id}")
        
        # Ahora adaptado para llamar a la BD en vez de a fake_carts_db
        await logica_negocio.actualizar_item_bd(item_id, request.quantity)
        await logica_negocio.recalcular_total_carrito_bd(cart_id)
        
        resultado = await logica_negocio.obtener_carrito_completo(cart_id)
        
        # Validación extra de seguridad por si el carrito fue borrado entre medio
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
            
        # Log de éxito
        logger.info(f"[{x_correlation_id}] Ítem {item_id} actualizado exitosamente")
        return resultado

    # 3. Manejo de excepciones
    except HTTPException:
        raise # Dejamos pasar errores controlados (como el 404 de arriba)
    except Exception as e:
        # LOGTEAMOS EL ERROR CRÍTICO EN CONSOLA PARA RENDER
        logger.error(f"[{x_correlation_id}] Error interno al actualizar cantidad del ítem {item_id}: {str(e)}")
        # DEVOLVEMOS EL ERROR ESTRUCTURADO AL CLIENTE
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
        
        await logica_negocio.eliminar_item_bd(item_id)
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
        
        # Log de éxito real (después de la base de datos)
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


# ==========================================
# 4. ENDPOINTS DE CHECKOUT 
# ==========================================
@app.post("/v1/checkout", tags=["Checkout"])
async def initiate_checkout(
    request: CheckoutRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") # 1. Agregamos el header
):
    """Inicia el proceso de checkout."""
    try:
        logger.info(f"[{x_correlation_id}] Iniciando checkout para carrito {request.cart_id} (Idempotency: {idempotency_key})")
        
        cart = await logica_negocio.obtener_carrito_completo(request.cart_id)
        
        if not cart:
            logger.warning(f"[{x_correlation_id}] Carrito {request.cart_id} no encontrado.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CART_NOT_FOUND",
                    "message": "Carrito no encontrado.",
                    "correlation_id": x_correlation_id
                }
            )
            
        if len(cart["items"]) == 0:
            logger.warning(f"[{x_correlation_id}] Intento de checkout con carrito vacío ({request.cart_id}).")
            raise HTTPException(
                status_code=400, 
                detail={
                    "error_code": "EMPTY_CART",
                    "message": "No se puede iniciar el checkout de un carrito vacío.",
                    "correlation_id": x_correlation_id
                }
            )

        await logica_negocio.cerrar_pedido(request.cart_id)
        
        checkout_id = str(uuid.uuid4())
        
        respuesta_checkout = {
            "checkout_id": checkout_id,
            "status": "PROCESSING", 
            "cartId": request.cart_id,
            "currency": "CLP",
            "amount": cart["total_amount"]
        }
        
        # Log de éxito
        logger.info(f"[{x_correlation_id}] Checkout {checkout_id} iniciado exitosamente para carrito {request.cart_id}")
        return respuesta_checkout

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al iniciar checkout: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Ocurrió un error inesperado al iniciar el checkout.",
                "correlation_id": x_correlation_id
            }
        )

@app.get("/v1/checkout/{checkout_id}", tags=["Checkout"])
async def get_checkout_status(
    checkout_id: str,
    token: HTTPAuthorizationCredentials = Depends(security),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") # 1. Agregado
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
            
        # Log de éxito
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


@app.post("/v1/cart/{cart_id}/checkout", tags=["Cart"])
async def checkout_cart(
    cart_id: str, 
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id") # 1. Agregado
):
    """Marca el carrito como PENDING, indicando intención de pedido."""
    try:
        logger.info(f"[{x_correlation_id}] Usuario {user_id} registrando intención de pedido para carrito {cart_id}")
        
        # Validación extra de seguridad: verificar si el carrito existe antes de cerrarlo
        cart = await logica_negocio.obtener_carrito_completo(cart_id)
        if not cart:
            logger.warning(f"[{x_correlation_id}] Carrito {cart_id} no encontrado al intentar hacer checkout.")
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "CART_NOT_FOUND",
                    "message": "Carrito no encontrado.",
                    "correlation_id": x_correlation_id
                }
            )
            
        # Acción en la base de datos
        await logica_negocio.cerrar_pedido(cart_id)
        
        logger.info(f"[{x_correlation_id}] Intención de pedido (PENDING) registrada para carrito {cart_id}")
        return {"message": "Intención de pedido registrada correctamente", "status": "PENDING"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{x_correlation_id}] Error interno al procesar checkout del carrito {cart_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Error al registrar la intención de pedido.",
                "correlation_id": x_correlation_id
            }
        )
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
        
        # 1. CAPTURAMOS EL ERROR DE STOCK INSUFICIENTE
        if "INSUFFICIENT_STOCK" in mensaje_error:
            logger.warning(f"[{x_correlation_id}] Falló la reserva: Stock insuficiente para el producto {request.product_id}")
            
            # --- AQUÍ ARMAMOS Y PUBLICAMOS EL EVENTO PARA G7 ---
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
            # Simulación de publicación en Pub/Sub
            print("Publicando evento para G7:", json.dumps(evento_shortage, indent=2))
            # ---------------------------------------------------
            
            # Devolvemos el HTTP 409 Conflict exigido por el contrato
            raise HTTPException(
                status_code=409, 
                detail={
                    "error_code": "INSUFFICIENT_STOCK",
                    "message": "No hay stock suficiente para crear la reserva.",
                    "correlation_id": x_correlation_id
                }
            )
            
        # 2. CAPTURAMOS EL ERROR DE PRODUCTO INEXISTENTE
        elif "PRODUCT_NOT_FOUND" in mensaje_error:
            raise HTTPException(
                status_code=404, 
                detail={
                    "error_code": "PRODUCT_NOT_FOUND",
                    "message": "El producto solicitado no existe.",
                    "correlation_id": x_correlation_id
                }
            )
            
        # 3. CUALQUIER OTRO ERROR DESCONOCIDO DEVUELVE 500
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
