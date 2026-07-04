from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, AliasChoices, ConfigDict
from typing import List, Optional
import uuid
import httpx
import logica_negocio

app = FastAPI(
    title="Grupo 4 - Cart, Checkout and Inventory API",
    description="API real construida en FastAPI para el Entregable 1. Integración con G1, G2 y G3.",
    version="1.2.0"
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
    product_id: str = Field(validation_alias=AliasChoices("productId", "product_id"))
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


# --- BASES DE DATOS SIMULADAS  ---
fake_checkouts_db = {}
fake_inventory_reservations = {}

# ==========================================
# 2. DEPENDENCIA DE AUTENTICACIÓN (GRUPO 2)
# ==========================================
security = HTTPBearer(auto_error=False)

async def verificar_usuario_grupo2(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials:
        return None
    token = credentials.credentials 
    # El formato estricto de UUID que exige la base de datos y el Grupo 2
    user_id_simulado = "5efb5b26-14ac-44a0-899f-a439924a69ef" #para este caso está este id ya que el grupo 2 aun no envía tokens o identificadores reales o al azar para poder consumirlos.
    return user_id_simulado


# ==========================================
# 3. ENDPOINTS DE CARRITO (CART)
# ==========================================
@app.post("/v1/cart", response_model=CartResponse, tags=["Cart"])
async def create_cart(
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    nuevo_cart_id = await logica_negocio.crear_carrito_bd(user_id=user_id)
    return {"cart_id": nuevo_cart_id, "user_id": user_id, "status": "ACTIVE", "items": [], "total_amount": 0}

@app.get("/v1/cart/{cart_id}", response_model=CartResponse, tags=["Cart"])
async def get_cart(cart_id: str, user_id: Optional[str] = Depends(verificar_usuario_grupo2)):
    resultado = await logica_negocio.obtener_carrito_completo(cart_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    return resultado

@app.post("/v1/cart/{cart_id}/items", response_model=CartResponse, tags=["Cart"])
async def add_item_to_cart(
    cart_id: str, 
    request: AddItemRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    print(f"Usuario {user_id} agregando ítem. Trace ID: {x_correlation_id}")
    carro_existente = await logica_negocio.obtener_carrito_completo(cart_id)
    if not carro_existente:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://grupo-3-catalogo.onrender.com/products/{request.product_id}",
                headers={"X-Consumer": "cart-service"}
            )
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="SERVICIO_CATALOGO_NO_DISPONIBLE")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="PRODUCTO_NO_ENCONTRADO_EN_CATALOGO")
        
    producto_json = response.json()
    
    # CAPA ANTICORRUPCIÓN: Si el Grupo 3 envía el producto envuelto en "data", lo extraemos
    if "data" in producto_json and isinstance(producto_json["data"], dict):
        producto_data = producto_json["data"]
    else:
        producto_data = producto_json

    if producto_data.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="PRODUCTO_INACTIVO")

    precio_unidad = int(producto_data.get("price", 0)) 
    nombre_producto = producto_data.get("name", "Producto Genérico")

    await logica_negocio.agregar_item_bd(
        cart_id=cart_id, product_id=request.product_id, name=nombre_producto,
        quantity=request.quantity, precio_unitario=precio_unidad
    )
    
    await logica_negocio.recalcular_total_carrito_bd(cart_id)
    return await logica_negocio.obtener_carrito_completo(cart_id)

@app.put("/v1/cart/{cart_id}/items/{item_id}", response_model=CartResponse, tags=["Cart"])
async def update_item_quantity(
    cart_id: str, 
    item_id: str, 
    request: UpdateItemRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2)
):
    """Modifica la cantidad de un producto específico en el carrito."""
    # Ahora adaptado para llamar a la BD en vez de a fake_carts_db
    await logica_negocio.actualizar_item_bd(item_id, request.quantity)
    await logica_negocio.recalcular_total_carrito_bd(cart_id)
    return await logica_negocio.obtener_carrito_completo(cart_id)

@app.delete("/v1/cart/{cart_id}/items/{item_id}", response_model=CartResponse, tags=["Cart"])
async def remove_item_from_cart(
    cart_id: str, 
    item_id: str,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2)
):
    """Elimina un producto específico del carrito."""
    # Ahora adaptado para llamar a la BD en vez de a fake_carts_db
    await logica_negocio.eliminar_item_bd(item_id)
    await logica_negocio.recalcular_total_carrito_bd(cart_id)
    return await logica_negocio.obtener_carrito_completo(cart_id)


# ==========================================
# 4. ENDPOINTS DE CHECKOUT 
# ==========================================
@app.post("/v1/checkout", tags=["Checkout"])
async def initiate_checkout(
    request: CheckoutRequest,
    user_id: Optional[str] = Depends(verificar_usuario_grupo2),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Inicia el proceso de checkout."""
    cart = await logica_negocio.obtener_carrito_completo(request.cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    if len(cart["items"]) == 0:
        raise HTTPException(status_code=400, detail="CARRITO_VACIO")

    checkout_id = str(uuid.uuid4())
    fake_checkouts_db[checkout_id] = {
        "checkout_id": checkout_id,
        "status": "PROCESSING",
        "cartId": request.cart_id,
        "currency": "CLP",
        "amount": cart["total_amount"]
    }
    return fake_checkouts_db[checkout_id]

@app.get("/v1/checkout/{checkout_id}", tags=["Checkout"])
async def get_checkout_status(checkout_id: str):
    """Consulta el estado de un checkout."""
    checkout = fake_checkouts_db.get(checkout_id)
    if not checkout:
        raise HTTPException(status_code=404, detail="CHECKOUT_NO_ENCONTRADO")
    return checkout

@app.post("/v1/cart/{cart_id}/checkout", tags=["Cart"])
async def checkout_cart(cart_id: str, user_id: Optional[str] = Depends(verificar_usuario_grupo2)):
    """Marca el carrito como PENDING, indicando intención de pedido."""
    await logica_negocio.cerrar_pedido(cart_id)
    return {"message": "Intención de pedido registrada correctamente", "status": "PENDING"}


# ==========================================
# 5. ENDPOINTS DE INVENTARIO (RESERVAS)
# ==========================================
@app.get("/v1/inventory/{product_id}", tags=["Inventory"])
async def check_inventory(product_id: str):
    reservado = fake_inventory_reservations.get(product_id, 0)
    stock_total_simulado = 100 
    return {
        "productId": product_id,
        "stockVisible": stock_total_simulado - reservado,
        "reservas_activas": reservado
    }

@app.post("/v1/stock/reservations", tags=["Inventory"])
async def reserve_stock(request: ReservationRequest):
    reservation_id = str(uuid.uuid4())
    current_reserved = fake_inventory_reservations.get(request.productId, 0)
    fake_inventory_reservations[request.productId] = current_reserved + request.quantity
    return {
        "reservation_id": reservation_id,
        "status": "RESERVED",
        "productId": request.productId,
        "quantity": request.quantity
    }

@app.delete("/v1/stock/reservations/{reservation_id}", tags=["Inventory"])
async def release_stock(reservation_id: str):
    return {
        "status": "RELEASED",
        "reservation_id": reservation_id,
        "message": "Stock liberado correctamente"
    }
