import asyncpg
import json
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

async def consultar_inventario_bd(product_id: str):
    """Consulta el stock físico y las reservas activas en Supabase."""
    conn = await get_db_connection()
    try:
        # 1. Obtenemos el stock físico total
        stock_row = await conn.fetchrow(
            "SELECT stock_total FROM inventory WHERE product_id = $1::uuid", 
            product_id
        )
        if not stock_row:
            return None

        stock_total = stock_row['stock_total']

        # 2. Obtenemos las reservas activas (estado ACTIVE y no expiradas)
        res_row = await conn.fetchrow("""
            SELECT COALESCE(SUM(quantity), 0) as reserved_qty
            FROM stock_reservations
            WHERE product_id = $1::uuid
              AND status = 'ACTIVE'
              AND expires_at > NOW()
        """, product_id)

        reserved_qty = res_row['reserved_qty'] if res_row else 0
        available_stock = stock_total - reserved_qty

        return {
            "productId": product_id,
            "stockTotal": stock_total,
            "reservedQuantity": reserved_qty,
            "availableStock": available_stock
        }
    finally:
        await conn.close()


async def reservar_stock_bd(product_id: str, cart_id: str, user_id: str, quantity: int):
    """Llama a la función SQL de concurrencia en Supabase."""
    conn = await get_db_connection()
    try:
        # Llamamos al Procedimiento Almacenado que maneja el SELECT FOR UPDATE
        resultado_json = await conn.fetchval("""
            SELECT reserve_stock($1::uuid, $2::uuid, $3::uuid, $4::integer)
        """, product_id, cart_id, user_id, quantity)

        # asyncpg nos devuelve el JSON como un string de texto, lo convertimos a diccionario
        return json.loads(resultado_json)
        
    except asyncpg.exceptions.RaiseError as e:
        # Capturamos los errores que arroja la función SQL
        error_msg = str(e)
        if 'INSUFFICIENT_STOCK' in error_msg:
            raise Exception("INSUFFICIENT_STOCK")
        elif 'Producto no encontrado' in error_msg:
            raise Exception("PRODUCT_NOT_FOUND")
        else:
            raise Exception(error_msg)
    finally:
        await conn.close()


async def liberar_reserva_bd(reservation_id: str):
    """Cambia el estado de una reserva a RELEASED."""
    conn = await get_db_connection()
    try:
        resultado = await conn.execute("""
            UPDATE stock_reservations
            SET status = 'RELEASED'
            WHERE reservation_id = $1::uuid
        """, reservation_id)
        # conn.execute devuelve "UPDATE 1" si encontró la fila, "UPDATE 0" si no
        return resultado == "UPDATE 1"
    finally:
        await conn.close()
