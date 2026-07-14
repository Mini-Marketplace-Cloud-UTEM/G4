import os
import json
import logging
import aio_pika

logger = logging.getLogger(__name__)

# Aquí pones la URL que copiaste de CloudAMQP
# (Recuerda luego pasarla a las variables de entorno de Render)
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
EXCHANGE_NAME = "g4_events_exchange"

async def publicar_evento(evento_dict: dict):
    """
    Toma el diccionario del evento, lo convierte a JSON y lo dispara a tu propio RabbitMQ.
    """
    try:
        # 1. Nos conectamos a tu servidor RabbitMQ
        conexion = await aio_pika.connect_robust(RABBITMQ_URL)
        
        async with conexion:
            # 2. Abrimos un canal de comunicación
            canal = await conexion.channel()
            
            # 3. Declaramos un "Exchange" (el buzón donde dejaremos los mensajes de G4)
            exchange = await canal.declare_exchange(
                EXCHANGE_NAME, 
                aio_pika.ExchangeType.FANOUT, # FANOUT envía copias a todos los grupos que escuchen
                durable=True
            )

            # Forzamos la creación de la cola y la vinculamos (Bind) mediante código
            cola = await canal.declare_queue("cola_de_prueba", durable=True)
            await cola.bind(exchange)
            # ------------------------------------
            
            # 4. Codificamos el evento a formato JSON estándar
            mensaje_bytes = json.dumps(evento_dict).encode("utf-8")
            mensaje = aio_pika.Message(
                body=mensaje_bytes,
                content_type="application/json"
            )
            
            # 5. ¡Publicamos el mensaje!
            await exchange.publish(mensaje, routing_key="")
            
            logger.info(f"Éxito: Evento {evento_dict['eventType']} publicado en tu RabbitMQ propio.")
            
    except Exception as e:
        logger.error(f"Error crítico al publicar en RabbitMQ: {e}")
