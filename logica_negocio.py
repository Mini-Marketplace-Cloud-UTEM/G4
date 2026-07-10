import asyncpg
import os
import json
from typing import Optional
from fastapi import HTTPException

# ==========================================
# CONFIGURACIÓN DE BASE DE DATOS (SUPABASE)
# ==========================================
# Usamos os.getenv para que tome la variable de entorno en Render, 
# pero le dejamos tu URL de fallback por si prueban en local.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.etgogvgvsqepdjiuulwh:AoUxcctg4URGf7gl@aws-1-us-west-2.pooler.supabase.com:5432/postgres")

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
# FUNCIONES TRANSACCIONALES DEL CARRITO
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
        # 1. EL CANDADO: Verificar el estado del carrito primero
        estado_carrito = await conn.fetchval("SELECT status FROM carts WHERE cart_id = $1::uuid", cart_id)
        
        if estado_carrito != 'ACTIVE':
            raise HTTPException(status_code=400, detail=f"No se puede modificar un carrito en estado {estado_carrito}")
        
        cart_id = str(cart_id)
        product_id = str(product_id)
        subtotal = quantity * precio_unitario
        
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

async def asignar_usuario_a_carrito(cart_id: str, user_id: str):
    """Asigna un carrito de invitado a un usuario real que acaba de iniciar sesión."""
    conn = await get_db_connection()
    try:
        # Solo lo actualiza si el carrito no tiene dueño o es de un invitado
        query = """
            UPDATE carts 
            SET user_id = $1 
            WHERE cart_id = $2::uuid 
            AND (user_id IS NULL OR user_id = '00000000-0000-0000-0000-000000000000')
        """
        await conn.execute(query, user_id, cart_id)
    finally:
        await conn.close()

async def reactivar_carrito_bd(cart_id: str):
    """Devuelve el estado de un carrito a ACTIVE (con validación estricta UUID)."""
    conn = await get_db_connection()
    try:
        estado_actual = await conn.fetchval("SELECT status FROM carts WHERE cart_id = $1::uuid", cart_id)
        
        if estado_actual == 'COMPLETED':
            raise HTTPException(status_code=400, detail="El carrito ya fue pagado.")
            
        if estado_actual == 'PENDING':
            await conn.execute("UPDATE carts SET status = 'ACTIVE' WHERE cart_id = $1::uuid", cart_id)
    finally:
        await conn.close()

async def actualizar_item_bd(cart_id: str, item_id: str, quantity: int):
    """Actualiza la cantidad de un ítem existente validando que pertenezca al carrito y esté ACTIVO."""
    conn = await get_db_connection()
    try:
        # 1. EL CANDADO: Verificar el estado del carrito primero
        estado_carrito = await conn.fetchval("SELECT status FROM carts WHERE cart_id = $1", cart_id)
        
        # Si no es ACTIVE (ej. está PENDING o COMPLETED), rebotamos la petición
        if estado_carrito != 'ACTIVE':
            raise HTTPException(status_code=400, detail=f"No se puede modificar un carrito en estado {estado_carrito}")

        # 2. La lógica de actualización que ya teníamos
        row = await conn.fetchrow(
            "SELECT unit_price FROM cart_items WHERE cart_id = $1 AND item_id = $2", 
            cart_id, item_id
        )
        
        if not row:
            raise HTTPException(status_code=404, detail="El ítem no existe en este carrito.")
            
        nuevo_subtotal = quantity * row['unit_price']
        await conn.execute(
            "UPDATE cart_items SET quantity = $1, sub_total = $2 WHERE item_id = $3", 
            quantity, nuevo_subtotal, item_id
        )
    finally:
        await conn.close()

async def eliminar_item_bd(cart_id: str, item_id: str):
    """Elimina un ítem específico validando el carrito y su estado ACTIVO."""
    conn = await get_db_connection()
    try:
        # 1. EL CANDADO: Verificar el estado del carrito primero
        estado_carrito = await conn.fetchval("SELECT status FROM carts WHERE cart_id = $1", cart_id)
        
        # Si no es ACTIVE, bloqueamos la eliminación
        if estado_carrito != 'ACTIVE':
            raise HTTPException(status_code=400, detail=f"No se puede modificar un carrito en estado {estado_carrito}")

        # 2. La lógica de eliminación segura
        resultado = await conn.execute(
            "DELETE FROM cart_items WHERE cart_id = $1 AND item_id = $2", 
            cart_id, item_id
        )
        
        if resultado == "DELETE 0":
            raise HTTPException(status_code=404, detail="Ítem no encontrado para eliminar.")
    finally:
        await conn.close()

# ==========================================
# FUNCIONES DE INVENTARIO Y RESERVAS (GRUPO 4)
# ==========================================

async def consultar_inventario_bd(product_id: str) -> Optional[dict]:
    """
    Consulta el stock real disponible.
    Calcula: Stock Total (inventory) - Reservas Activas (stock_reservations)
    """
    conn = await get_db_connection()
    try:
        # Buscamos el stock base en inventory y sumamos las reservas activas
        query = """
        SELECT 
            i.stock_total,
            COALESCE((
                SELECT SUM(quantity) 
                FROM stock_reservations 
                WHERE product_id = i.product_id 
                AND status = 'ACTIVE'
            ), 0) as reserved_quantity
        FROM inventory i
        WHERE i.product_id = $1::uuid;
        """
        row = await conn.fetchrow(query, product_id)
        
        if not row:
            return None
            
        stock_total = row['stock_total']
        reserved_quantity = row['reserved_quantity']
        available_stock = stock_total - reserved_quantity
        
        # Retornamos el diccionario tal cual lo exige el contrato del Grupo 4
        return {
            "productId": product_id,
            "stockTotal": stock_total,
            "reservedQuantity": reserved_quantity,
            "availableStock": available_stock
        }
    finally:
        await conn.close()

async def crear_reserva_bd(product_id: str, cart_id: str, user_id: str, quantity: int) -> dict:
    """
    Crea una reserva temporal llamando a la función almacenada 'reserve_stock' en Supabase.
    """
    conn = await get_db_connection()
    try:
        # Llamamos directamente a la función de Supabase
        query = "SELECT reserve_stock($1::uuid, $2::uuid, $3::uuid, $4);"
        
        # Obtenemos la respuesta de Supabase (que viene en formato JSON por tu RETURNS JSON)
        resultado_string = await conn.fetchval(query, product_id, cart_id, user_id, quantity)
        
        # Convertimos el string a un diccionario de Python y lo retornamos
        return json.loads(resultado_string)
        
    except asyncpg.exceptions.RaiseError as e:
        # Aquí capturamos los 'RAISE EXCEPTION' de la función SQL
        mensaje_error = str(e)
        if 'INSUFFICIENT_STOCK' in mensaje_error:
            raise Exception("INSUFFICIENT_STOCK")
        elif 'Producto no encontrado' in mensaje_error:
            raise Exception("PRODUCT_NOT_FOUND")
        raise Exception(f"Error en base de datos: {mensaje_error}")
        
    finally:
        await conn.close()

async def liberar_reserva_bd(reservation_id: str):
    """
    Libera anticipadamente una reserva activa (ej. si el pago es rechazado).
    """
    conn = await get_db_connection()
    try:
        query = """
        UPDATE stock_reservations
        SET status = 'RELEASED'
        WHERE reservation_id = $1::uuid AND status = 'ACTIVE';
        """
        await conn.execute(query, reservation_id)
    finally:
        await conn.close()
