import json
import logging
from security_config import encrypt_json_field, get_required_rabbitmq_url

logger = logging.getLogger(__name__)

RABBITMQ_URL = get_required_rabbitmq_url()
EXCHANGE_NAME = "g4_events_exchange"


def preparar_evento_seguro(evento_dict: dict) -> dict:
    """
    Cifra el payload de negocio antes de publicarlo en RabbitMQ.
    Los metadatos quedan visibles para ruteo, trazabilidad y auditoria.
    """
    evento_seguro = dict(evento_dict)
    payload = evento_seguro.pop("payload", None)
    if payload is not None:
        evento_seguro["payloadEncrypted"] = True
        evento_seguro["payloadEncryption"] = "fernet"
        evento_seguro["encryptedPayload"] = encrypt_json_field(payload)
    return evento_seguro

async def publicar_evento(evento_dict: dict):
    """
    Cifra el payload, convierte el evento a JSON y lo publica en RabbitMQ.
    """
    import aio_pika

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
            
            # 4. Codificamos el evento a formato JSON estándar sin payload sensible en claro
            evento_seguro = preparar_evento_seguro(evento_dict)
            mensaje_bytes = json.dumps(evento_seguro).encode("utf-8")
            mensaje = aio_pika.Message(
                body=mensaje_bytes,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )
            
            # 5. ¡Publicamos el mensaje!
            await exchange.publish(mensaje, routing_key="")
            
            logger.info(f"Éxito: Evento {evento_dict['eventType']} publicado en RabbitMQ con payload cifrado.")
            
    except Exception as e:
        logger.error(f"Error crítico al publicar en RabbitMQ: {e}")
