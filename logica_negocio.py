import asyncpg
import os
from typing import Optional

# ==========================================
# CONFIGURACIÓN DE BASE DE DATOS (SUPABASE)
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")

async def get_db_connection():
    conn = await asyncpg.connect(DATABASE_URL)
    # Esto le enseña a tu conexión a manejar los UUID de forma nativa
    await conn.set_type_codec(
        'uuid',
        encoder=str,
        decoder=str,
        schema='pg_catalog'
    )
    return conn

# ==========================================
# FUNCIONES TRANSACCIONALES
# ==========================================

async def crear_carrito_bd(user_id: Optional[str] = None) -> str:
    """
    Crea un nuevo carrito en la base de datos.
    Si el Grupo 2 nos entrega un user_id, lo asocia inmediatamente.
    """
    conn = await get_db_connection()
    try:
        # Insertamos el carrito con el user_id (puede ser NULL si es anónimo) y estado ACTIVE
        query = """
            INSERT INTO carts (user_id, status, total_amount, currency)
            VALUES ($1, 'ACTIVE', 0, 'CLP')
            RETURNING cart_id;
        """
        # asyncpg devuelve el UUID como un objeto, lo convertimos a string
        cart_id = await conn.fetchval(query, user_id)
        return str(cart_id)
    finally:
        await conn.close()

async def agregar_item_bd(cart_id: str, product_id: str, name: str, quantity: int, precio_unitario: int):
    """Inserta o actualiza un producto dentro de un carrito específico en la BD castenado a UUID."""
    conn = await get_db_connection()
    try:
        cart_id = str(cart_id)
        product_id = str(product_id)
        subtotal = quantity * precio_unitario
        
        # Agregamos ::uuid para que asyncpg no reclame por tipos
        check_query = "SELECT item_id, quantity FROM cart_items WHERE cart_id = $1::uuid AND product_id = $2"
        existing_item = await conn.fetchrow(check_query, cart_id, product_id)

        if existing_item:
            nueva_cantidad = existing_item['quantity'] + quantity
            nuevo_subtotal = nueva_cantidad * precio_unitario
            update_query = """
                UPDATE cart_items 
                SET quantity = $1, sub_total = $2 
                WHERE item_id = $3::uuid
            """
            await conn.execute(update_query, nueva_cantidad, nuevo_subtotal, existing_item['item_id'])
        else:
            insert_query = """
                INSERT INTO cart_items (cart_id, product_id, name, quantity, unit_price, sub_total)
                VALUES ($1::uuid, $2, $3, $4, $5, $6)
            """
            await conn.execute(insert_query, cart_id, product_id, name, quantity, precio_unitario, subtotal)
    finally:
        await conn.close()

async def obtener_carrito_completo(cart_id: str) -> Optional[dict]:
    """Extrae toda la información del carrito aplicando casteo de llaves."""
    conn = await get_db_connection()
    try:
        # Forzamos el tipo con ::uuid
        cart_query = "SELECT cart_id, user_id, status, total_amount FROM carts WHERE cart_id = $1::uuid"
        cart_row = await conn.fetchrow(cart_query, cart_id)
        
        if not cart_row:
            return None

        items_query = "SELECT item_id, product_id, name, quantity, unit_price, sub_total FROM cart_items WHERE cart_id = $1::uuid"
        items_rows = await conn.fetch(items_query, cart_id)

        items_list = []
        for row in items_rows:
            items_list.append({
                "item_id": str(row["item_id"]),
                "product_id": str(row["product_id"]),
                "name": row["name"],
                "quantity": row["quantity"],
                "price": row["unit_price"], 
                "subtotal": row["sub_total"]
            })

        carrito_dict = {
            "cart_id": str(cart_row["cart_id"]),
            "user_id": str(cart_row["user_id"]) if cart_row["user_id"] else None,
            "status": cart_row["status"],
            "items": items_list,
            "total_amount": cart_row["total_amount"]
        }
        return carrito_dict
    finally:
        await conn.close()

async def recalcular_total_carrito_bd(cart_id: str):
    """
    Suma todos los subtotales de los ítems y actualiza el total del carrito.
    La base de datos es la única fuente de verdad para la matemática.
    """
    conn = await get_db_connection()
    try:
        query = """
            UPDATE carts 
            SET total_amount = (
                SELECT COALESCE(SUM(sub_total), 0) 
                FROM cart_items 
                WHERE cart_id = $1
            )
            WHERE cart_id = $1;
        """
        await conn.execute(query, cart_id)
    finally:
        await conn.close()


async def cerrar_pedido(cart_id: str):
    """
    Cambia el estado del carrito de ACTIVE a PENDING (Checkout).
    """
    conn = await get_db_connection()
    try:
        query = "UPDATE carts SET status = 'PENDING' WHERE cart_id = $1"
        await conn.execute(query, cart_id)
    finally:
        await conn.close()

async def actualizar_item_bd(item_id: str, quantity: int):
    """Actualiza la cantidad de un ítem existente en el carrito."""
    conn = await get_db_connection()
    try:
        # Obtenemos el precio unitario actual para recalcular el subtotal
        row = await conn.fetchrow("SELECT unit_price FROM cart_items WHERE item_id = $1", item_id)
        if row:
            nuevo_subtotal = quantity * row['unit_price']
            await conn.execute(
                "UPDATE cart_items SET quantity = $1, sub_total = $2 WHERE item_id = $3", 
                quantity, nuevo_subtotal, item_id
            )
    finally:
        await conn.close()

async def eliminar_item_bd(item_id: str):
    """Elimina un ítem específico de la base de datos."""
    conn = await get_db_connection()
    try:
        await conn.execute("DELETE FROM cart_items WHERE item_id = $1", item_id)
    finally:
        await conn.close()
