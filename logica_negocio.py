import asyncpg
import uuid

# --- CONFIGURACIÓN CENTRALIZADA ---
DATABASE_URL = "postgresql://postgres.stbnjjpelelbsdeudqad:2CCCzfeXw2bfZYj8@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

async def get_db_connection():
    return await asyncpg.connect(DATABASE_URL)

async def crear_carrito_bd():
    conn = await get_db_connection()
    try:
        nuevo_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO carts (cart_id, status, total_amount, currency) VALUES ($1, $2, $3, $4)",
            nuevo_id, 'ACTIVE', 0, 'CLP'
        )
        return nuevo_id
    finally:
        await conn.close()

async def agregar_item_bd(cart_id: str, product_id: str, name: str, quantity: int, precio_unitario: int):
    """Agrega un ítem calculando el subtotal con números enteros."""
    conn = await get_db_connection()
    try:
        item_id = str(uuid.uuid4())
        
        # Matemática simple y directa con enteros
        sub_total = quantity * precio_unitario
        
        await conn.execute(
            """
            INSERT INTO cart_items (item_id, cart_id, product_id, name, quantity, unit_price, sub_total) 
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            item_id, cart_id, product_id, name, quantity, precio_unitario, sub_total
        )
    finally:
        await conn.close()

async def recalcular_total_carrito_bd(cart_id: str):
    """Obtiene los subtotales, los suma como enteros y actualiza el carro."""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch("SELECT sub_total FROM cart_items WHERE cart_id = $1", cart_id)
        
        # Suma directa de enteros
        total = sum(int(row['sub_total']) for row in rows)
        
        await conn.execute(
            "UPDATE carts SET total_amount = $1 WHERE cart_id = $2",
            total, cart_id
        )
    finally:
        await conn.close()

async def obtener_carrito_completo(cart_id: str):
    conn = await get_db_connection()
    try:
        cart_row = await conn.fetchrow("SELECT cart_id, total_amount FROM carts WHERE cart_id = $1", cart_id)
        if not cart_row:
            return None
        
        item_rows = await conn.fetch(
            "SELECT item_id, product_id, name, quantity, unit_price, sub_total FROM cart_items WHERE cart_id = $1", 
            cart_id
        )
        
        items_list = [{
            "itemId": row["item_id"],
            "productId": row["product_id"],
            "name": row["name"],
            "quantity": row["quantity"],
            "unitPrice": int(row["unit_price"]),
            "subTotal": int(row["sub_total"]) 
        } for row in item_rows]
            
        return {
            "cartId": cart_id,
            "items": items_list,
            "totalAmount": int(cart_row["total_amount"]) 
        }
    finally:
        await conn.close()

async def cerrar_pedido(cart_id: str):
    conn = await get_db_connection()
    try:
        await conn.execute(
            "UPDATE carts SET status = $1 WHERE cart_id = $2",
            "PENDING", cart_id
        )
        print(f"Carrito {cart_id} marcado como PENDING (Intención de compra).")
    finally:
        await conn.close()