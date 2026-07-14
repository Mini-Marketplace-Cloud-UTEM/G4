import os
import json
import logging
import aio_pika
import asyncio
import logica_negocio
import uuid
from google.cloud import pubsub_v1

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
EXCHANGE_NAME = "g4_events_exchange"

# ==========================================
# 1. PUBLICADOR: RABBITMQ (avisa a los demás)
# ==========================================

async def publicar_evento(evento_dict: dict):
    """
    Toma el diccionario del evento, lo convierte a JSON y lo dispara a tu propio RabbitMQ.
    """
    try:
        # 1. Nos conectamos a RabbitMQ
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
            
            # 5. Publicamos el mensaje
            await exchange.publish(mensaje, routing_key="")
            
            logger.info(f"Éxito: Evento {evento_dict['eventType']} publicado en tu RabbitMQ propio.")
            
    except Exception as e:
        logger.error(f"Error crítico al publicar en RabbitMQ: {e}")
        
# ==========================================
# 2. CONSUMIDOR: GOOGLE CLOUD PUB/SUB (Grupo 8)
# ==========================================

# Apunta al archivo JSON de Grupo 8 (tiene que estar en la raiz para que funcione)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "GCP_SERVICE_ACCOUNT.json"

#variables para poder conectarnos al pubsub del grupo8
PROJECT_ID = os.getenv("GCP_PAYMENT_PROJECT_ID", "project-76891426-ab92-49ba-b24")
SUBSCRIPTION_ID = os.getenv("GCP_PAYMENT_SUBSCRIPTION_ID", "g4-payment-events-sub")

async def procesar_evento_pago_g8(evento_recibido: dict):
    """Toma la decisión en la BD dependiendo de si el pago se aprobó o rechazó."""
    tipo_evento = evento_recibido.get("eventType")
    correlation_id = evento_recibido.get("correlationId", str(uuid.uuid4()))
    payload = evento_recibido.get("payload", {})
    
    # Nota: Asegúrate con G8 de que ellos te devuelvan el cartId en el payload,
    # o de lo contrario tendrás que buscar la reserva usando el orderId.
    cart_id = payload.get("cartId")
    reservation_id = payload.get("reservationId")
    try:
        if tipo_evento == "PAYMENT_APPROVED":
            logger.info(f"[{correlation_id}] Pago Aprobado. Completando pedido para carrito {cart_id}")
            await logica_negocio.completar_pedido_bd(cart_id)
            
        elif tipo_evento == "PAYMENT_REJECTED":
            logger.info(f"[{correlation_id}] Pago Rechazado. Liberando stock para reserva {reservation_id}")
            await logica_negocio.liberar_reserva_bd(reservation_id)
            
    except Exception as e:
        logger.error(f"Error crítico al impactar la BD tras evento de G8: {str(e)}")

def callback_pubsub(mensaje):
    """Atrapa el mensaje en bruto desde Google Cloud."""
    try:
        evento_dict = json.loads(mensaje.data.decode("utf-8"))
        # Usamos asyncio.run() para ejecutarlo de forma segura desde el hilo secundario de Google
        asyncio.run(procesar_evento_pago_g8(evento_dict))
        mensaje.ack() # Confirmamos a Google que lo recibimos bien
    except Exception as e:
        logger.error(f"Error procesando mensaje Pub/Sub de G8: {e}")
        mensaje.nack() # Si falla, le decimos a Google que nos lo reenvíe después

# Intentamos conectar a Google Cloud al arrancar este archivo
try:
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    subscriber.subscribe(subscription_path, callback=callback_pubsub)
    logger.info("Escuchando eventos de pagos del Grupo 8 exitosamente en GCP Pub/Sub.")
except Exception as e:
    logger.error(f"No se pudo conectar a GCP Pub/Sub: {e}")