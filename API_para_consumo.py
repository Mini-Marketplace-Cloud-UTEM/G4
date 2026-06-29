from fastapi import FastAPI, HTTPException, Header, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import httpx
import logica_negocio

# Inicializamos la aplicación FastAPI
app = FastAPI(
    title="Grupo 4 - Cart, Checkout and Inventory API",
    description="API real construida en FastAPI para el Entregable 1 (Actualizada con nueva colección Postman).",
    version="1.1.0"
)

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS DE DATOS (Pydantic adaptado al nuevo Postman JSON) ---
class AddItemRequest(BaseModel):
    product_id: str
    name: str
    quantity: int = Field(gt=0, description="La cantidad debe ser mayor a cero")
    precio_unitario: float

class AddItemRequest(BaseModel):
    productId: str
    quantity: int

class UpdateItemRequest(BaseModel):
    quantity: int

class CartItem(BaseModel):
    item_id: str
    productId: str
    name: str
    quantity: int
    unitPrice: float

class Cart(BaseModel):
    cart_id: str
    items: List[CartItem] = []
    total_price: float = 0.0

class CheckoutRequest(BaseModel):
    cartId: str
    currency: str

class ReservationRequest(BaseModel):
    productId: str
    cartId: str
    userId: str
    quantity: int

# --- BASES DE DATOS SIMULADAS ---
fake_carts_db = {}
fake_checkouts_db = {}
fake_inventory_reservations = {}

# Función de ayuda para recalcular totales
def recalcular_total_carrito(cart: Cart):
    cart.total_price = sum(item.quantity * item.unitPrice for item in cart.items)

# ==========================================
# ENDPOINTS DE CARRITO (CART)
# ==========================================

@app.post("/v1/cart", response_model=Cart, tags=["Cart"])
async def create_cart(
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Crea un nuevo carrito de compras vacío en la base de datos."""
    # Crea el registro en Supabase y retorna el UUID generado
    nuevo_cart_id = await logica_negocio.crear_carrito_bd()
    
    # Retorna la estructura inicial vacía respetando el response_model
    return {"cart_id": nuevo_cart_id, "items": [], "total_price": 0.0}
# Asegúrate de tener este GET en main.py

@app.get("/v1/cart/{cart_id}", response_model=Cart, tags=["Cart"])
async def get_cart(cart_id: str):
    """Consulta el estado actual del carrito desde la base de datos."""
    resultado = await logica_negocio.obtener_carrito_completo(cart_id)
    
    if resultado is None:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    
    return resultado

"""""
@app.get("/v1/cart/{cart_id}", response_model=Cart, tags=["Cart"])
async def get_cart(
    cart_id: str,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    Consulta los detalles de un carrito específico.
    cart = fake_carts_db.get(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    return cart
"""
@app.post("/v1/cart/{cart_id}/items", response_model=Cart, tags=["Cart"])
async def add_item_to_cart(
    cart_id: str, 
    request: AddItemRequest,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Agrega un producto al carrito, valida con Grupo 3 y persiste en Supabase."""
    
    # 1. Verificar primero si el carro existe en la base de datos
    carro_existente = await logica_negocio.obtener_carrito_completo(cart_id)
    if not carro_existente:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    
    # 2. INTEGRACIÓN CON GRUPO 3 (CATÁLOGO)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"https://grupo3-catalogo.onrender.com/products/{request.productId}",
                headers={"X-Consumer": "cart-service"}
            )
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="SERVICIO_CATALOGO_NO_DISPONIBLE")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="PRODUCTO_NO_ENCONTRADO_EN_CATALOGO")
        
    producto_data = response.json()
    if producto_data.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="PRODUCTO_INACTIVO")

    # CAMBIO AQUÍ: Usamos float en vez de int para respetar la lógica de Decimales de tu compañero
    precio_unidad = int(producto_data.get("price", 0.0)) 
    nombre_producto = producto_data.get("name", "Producto Genérico")

    # 3. Guardar el ítem validado en Supabase (Usando la matemática de tu compañero)
    await logica_negocio.agregar_item_bd(
        cart_id=cart_id,
        product_id=request.productId,
        name=nombre_producto,
        quantity=request.quantity,
        precio_unitario=precio_unidad
    )
    
    # 4. Procesar el cálculo de totales (Lógica de tu compañero adaptada a BD)
    await logica_negocio.recalcular_total_carrito_bd(cart_id)
    
    # 5. Recuperar el estado actualizado directo de la base de datos para responder
    carro_actualizado = await logica_negocio.obtener_carrito_completo(cart_id)
    return carro_actualizado

@app.put("/v1/cart/{cart_id}/items/{item_id}", response_model=Cart, tags=["Cart"])
async def update_item_quantity(
    cart_id: str, 
    item_id: str, 
    request: UpdateItemRequest,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Modifica la cantidad de un producto específico en el carrito."""
    cart = fake_carts_db.get(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    
    item_found = False
    for item in cart.items:
        if item.item_id == item_id:
            item.quantity = request.quantity
            item_found = True
            break
            
    if not item_found:
        raise HTTPException(status_code=404, detail="ITEM_NO_ENCONTRADO_EN_CARRITO")
        
    recalcular_total_carrito(cart)
    return cart

@app.delete("/v1/cart/{cart_id}/items/{item_id}", response_model=Cart, tags=["Cart"])
async def remove_item_from_cart(
    cart_id: str, 
    item_id: str,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Elimina un producto específico del carrito."""
    cart = fake_carts_db.get(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    
    # Filtramos para conservar todos los items excepto el que queremos borrar
    cart.items = [item for item in cart.items if item.item_id != item_id]
    recalcular_total_carrito(cart)
    
    return cart

# ==========================================
# ENDPOINTS DE CHECKOUT
# ==========================================

@app.post("/v1/checkout", tags=["Checkout"])
async def initiate_checkout(
    request: CheckoutRequest,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    prefer: Optional[str] = Header(None)
):
    """Inicia el proceso de checkout."""
    cart = fake_carts_db.get(request.cartId)
    if not cart:
        raise HTTPException(status_code=404, detail="CARRITO_NO_ENCONTRADO")
    
    if len(cart.items) == 0:
        raise HTTPException(status_code=400, detail="CARRITO_VACIO")

    checkout_id = str(uuid.uuid4())
    fake_checkouts_db[checkout_id] = {
        "checkout_id": checkout_id,
        "status": "PROCESSING",
        "cartId": request.cartId,
        "currency": request.currency,
        "amount": cart.total_price
    }

    return fake_checkouts_db[checkout_id]

@app.get("/v1/checkout/{checkout_id}", tags=["Checkout"])
async def get_checkout_status(
    checkout_id: str,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Consulta el estado de un checkout."""
    checkout = fake_checkouts_db.get(checkout_id)
    if not checkout:
        raise HTTPException(status_code=404, detail="CHECKOUT_NO_ENCONTRADO")
    return checkout

@app.post("/v1/cart/{cart_id}/checkout", tags=["Cart"])
async def checkout_cart(cart_id: str):
    """Marca el carrito como PENDING, indicando intención de pedido."""
    await logica_negocio.cerrar_pedido(cart_id)
    return {"message": "Intención de pedido registrada correctamente", "status": "PENDING"}
# ==========================================
# ENDPOINTS DE INVENTARIO (RESERVAS)
# ==========================================

@app.get("/v1/inventory/{product_id}", tags=["Inventory"])
async def check_inventory(
    product_id: str,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Consulta el stock disponible de un producto."""
    # Retorna data simulada, restando lo que tengamos en reservas temporales
    reservado = fake_inventory_reservations.get(product_id, 0)
    stock_total_simulado = 100 
    
    return {
        "productId": product_id,
        "stockVisible": stock_total_simulado - reservado,
        "reservas_activas": reservado
    }

@app.post("/v1/stock/reservations", tags=["Inventory"])
async def reserve_stock(
    request: ReservationRequest,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Crea una reserva temporal de stock."""
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
async def release_stock(
    reservation_id: str,
    authorization: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None, alias="X-Correlation-Id")
):
    """Libera una reserva temporal de stock (ej. si el pago falla)."""
    # Como es un mock y no guardamos el detalle por ID de reserva en memoria, 
    # simplemente devolvemos un OK. En la vida real aquí buscaríamos la reserva y restaríamos la cantidad.
    return {
        "status": "RELEASED",
        "reservation_id": reservation_id,
        "message": "Stock liberado correctamente"
    }

class AddItemRequest(BaseModel):
    productId: str
    quantity: int
