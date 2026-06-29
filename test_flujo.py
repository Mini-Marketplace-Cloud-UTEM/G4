import asyncio
import logica_negocio

async def test_flujo_completo():
    print("--- PASO 1: Creando carrito ---")
    cart_id = await logica_negocio.crear_carrito_bd()
    print(f"Carrito generado: {cart_id}")

    print("\n--- PASO 2: Agregando productos (Prueba de Decimales) ---")
    # Usamos los montos del ejemplo del .md de tu compañero para probar su lógica exacta
    await logica_negocio.agregar_item_bd(cart_id, "PROD-A", "Teclado Mecánico", 2, 799.98)
    await logica_negocio.agregar_item_bd(cart_id, "PROD-B", "Mouse Pad", 1, 100.00)
    print("Productos agregados a la base de datos.")

    print("\n--- PASO 3: Recalculando totales (Lógica del compañero) ---")
    # Esta es la nueva función que actualiza el total_amount en la tabla carts
    await logica_negocio.recalcular_total_carrito_bd(cart_id)
    print("Totales recalculados y guardados exitosamente.")

    print("\n--- PASO 4: Consultando carrito (Verificación) ---")
    carrito = await logica_negocio.obtener_carrito_completo(cart_id)
    
    # Imprimimos los subtotales para ver que se guardaron y leyeron bien
    print("Ítems en el carrito:")
    for item in carrito['items']:
        print(f" - {item['name']}: {item['quantity']} x ${item['unitPrice']} = Subtotal: ${item['subTotal']}")
    
    print(f"\nTotal general guardado en BD: ${carrito['total_price']}")

    # Validación lógica: (2 * 799.99) + (1 * 100.00) = 1599.98 + 100.00 = 1699
    total_esperado = 1699
    if carrito['total_price'] == total_esperado:
        print("✅ Lógica matemática correcta: El total coincide perfectamente con los decimales.")
    else:
        print(f"❌ Lógica incorrecta: Esperaba {total_esperado}, obtuve {carrito['total_price']}")
        
    print("\n--- PASO 5: Cerrando carrito (Intención de pedido) ---")
    await logica_negocio.cerrar_pedido(cart_id)
    
    # Verifiquemos si el estado cambió en la base de datos
    conn = await logica_negocio.get_db_connection()
    status_db = await conn.fetchval("SELECT status FROM carts WHERE cart_id = $1", cart_id)
    await conn.close()
    
    if status_db == 'PENDING':
        print("✅ ÉXITO FINAL: El estado del carrito es PENDING. Flujo completo validado.")
    else:
        print(f"❌ ERROR: El estado debería ser PENDING, pero es {status_db}")
        
asyncio.run(test_flujo_completo())

