import asyncio
import httpx
import uuid
import asyncpg
from security_config import get_https_service_url, get_required_database_url, redact_identifier

# 1. Obtenemos la conexión a la BD
DATABASE_URL = get_required_database_url()
URL_G3_CATALOGO = get_https_service_url("URL_G3_CATALOGO", "https://grupo-3-catalogo.onrender.com/products")

async def get_db_connection():
    conn = await asyncpg.connect(DATABASE_URL, ssl=True)
    await conn.set_type_codec('uuid', encoder=str, decoder=str, schema='pg_catalog')
    return conn

async def insertar_producto_inventario(conn, product_id: str, name: str, stock_inicial: int):
    query = """
    INSERT INTO inventory (product_id, nombre, stock_total)
    VALUES ($1::uuid, $2, $3)
    ON CONFLICT (product_id) DO UPDATE 
    SET nombre = EXCLUDED.nombre,
        stock_total = EXCLUDED.stock_total;
    """
    await conn.execute(query, product_id, name, stock_inicial)

async def sincronizar_catalogo_inicial():
    print("Iniciando sincronización masiva desde Catálogo (Grupo 3)...")
    pagina_actual = 1
    total_paginas = 1
    
    headers = {
        "X-Consumer": "grupo-4-inventario",
        "X-Correlation-Id": str(uuid.uuid4()),
        "X-Request-Id": str(uuid.uuid4())
    }

    conn = await get_db_connection()
    
    try:
        async with httpx.AsyncClient() as client:
            while pagina_actual <= total_paginas:
                print(f"Obteniendo página {pagina_actual} de {total_paginas}...")
                
                response = await client.get(
                    f"{URL_G3_CATALOGO}?page={pagina_actual}&size=50",
                    headers=headers,
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    datos = response.json()
                    
                    # 1. Extraemos la lista usando la llave exacta 'data'
                    productos = datos.get("data", [])
                    
                    if "pagination" in datos:
                        total_paginas = datos["pagination"].get("totalPages", 1)
                    else:
                        total_paginas = 1

                    # 2. Iteramos buscando las llaves exactas del JSON
                    for prod in productos:
                        product_id = prod.get("id")
                        nombre = prod.get("name", "Producto Desconocido")
                        stock_inicial = prod.get("stockVisible", 0) 
                        
                        if product_id:
                            await insertar_producto_inventario(conn, product_id, nombre, stock_inicial)
                            print(f"Guardado: {nombre} | ID: {redact_identifier(product_id)} | Stock: {stock_inicial}")
                    
                    pagina_actual += 1
                else:
                    print(f"❌ Error HTTP {response.status_code}")
                    break
                    
    except Exception as e:
        print(f"Ocurrió un error grave en la Base de Datos: {str(e)}")
    finally:
        await conn.close()
        print("\nSincronización finalizada. ¡Revisa tu tabla inventory en Supabase!")

if __name__ == "__main__":
    asyncio.run(sincronizar_catalogo_inicial())
