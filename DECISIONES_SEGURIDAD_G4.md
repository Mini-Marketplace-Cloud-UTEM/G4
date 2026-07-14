# Decisiones de Seguridad - G4

Este documento registra las decisiones implementadas para proteger la API de carrito, checkout e inventario del Grupo 4.

## 1. TLS obligatorio

Decisión: todo tráfico de entrada a la API debe llegar por HTTPS.

Implementación:
- `API_para_consumo.py` incorpora middleware que rechaza solicitudes no HTTPS con `TLS_REQUIRED`.
- En ambientes locales (`ENVIRONMENT=local`, `development` o `test`) se permite HTTP solo para `localhost`/`127.0.0.1`.
- Las llamadas entre grupos usan URLs validadas con esquema `https://`.
- RabbitMQ exige `amqps://`.
- Supabase/PostgreSQL se conecta con `ssl=True`.

Variables configurables:
- `URL_G2_AUTH_VALIDATE`
- `URL_G3_CATALOGO`
- `URL_G4_STOCK_RESERVATIONS`
- `URL_G5_ORDERS`
- `URL_G6_DESPACHO`
- `URL_G8_PAYMENTS`

Todas deben usar `https://`.

## 2. Secretos solo por entorno/secret manager

Decisión: G4 no debe tener credenciales hardcodeadas en el repositorio.

Implementación:
- `DATABASE_URL` es obligatoria y se lee desde variables de entorno.
- `RABBITMQ_URL` es obligatoria y se lee desde variables de entorno.
- Tokens `Authorization: Bearer` se usan solo en memoria para validar usuario o reenviar a servicios autorizados.
- Los errores externos se sanitizan antes de enviarse a logs.

Variables obligatorias:
- `DATABASE_URL`
- `RABBITMQ_URL`

## 3. Supabase cifrado en reposo

Decisión: la base de datos debe tener cifrado en reposo habilitado desde Supabase/proveedor cloud.

Implementación en código:
- G4 fuerza conexión SSL hacia PostgreSQL con `asyncpg.connect(..., ssl=True)`.
- No existe fallback local hardcodeado para `DATABASE_URL`.

Responsabilidad operativa:
- Verificar en Supabase que el proyecto tenga cifrado en reposo habilitado.
- Restringir acceso a la base por credenciales de menor privilegio.
- Rotar `DATABASE_URL` si fue expuesta previamente.

## 4. Cifrado campo a campo

Decisión: `shippingAddress`, `notes` y payloads de eventos RabbitMQ se cifran cuando G4 los almacena o publica fuera del flujo HTTP directo.

Implementación:
- `security_config.py` provee `encrypt_field`, `decrypt_field` y `encrypt_json_field` con Fernet.
- La llave se entrega con `FIELD_ENCRYPTION_KEY`.
- G4 actualmente no persiste `shippingAddress` ni `notes`; los envía a G5 por HTTPS dentro del flujo de checkout.
- No se cifra el payload enviado a G5 porque rompería el contrato funcional entre servicios. El cifrado campo a campo aplica a almacenamiento local en G4.
- `G4pubsub.py` cifra automáticamente el campo `payload` antes de publicar eventos en RabbitMQ.
- Los eventos publicados mantienen metadatos visibles (`eventId`, `eventType`, `version`, `occurredAt`, `producer`, `correlationId`) y reemplazan `payload` por:
  - `payloadEncrypted: true`
  - `payloadEncryption: "fernet"`
  - `encryptedPayload: "<ciphertext>"`

Variable requerida si G4 persiste esos campos o publica eventos RabbitMQ:
- `FIELD_ENCRYPTION_KEY`

Generación recomendada:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 5. Minimización de logs

Decisión: logs operativos no deben exponer tokens, direcciones, notas ni identificadores completos.

Implementación:
- Se redactan identificadores sensibles como `user_id`, `cart_id`, `item_id`, `product_id`, `checkout_id` y `reservation_id`.
- Se sanitizan respuestas de servicios externos antes de loguearlas.
- No se imprime el valor de `Authorization` ni de secretos de entorno.

## Estado final

Controles implementados en código:
- HTTPS obligatorio para API.
- HTTPS obligatorio para integraciones entre grupos.
- AMQPS obligatorio para RabbitMQ.
- SSL obligatorio para Supabase/PostgreSQL.
- Secretos obligatorios desde entorno.
- Helpers de cifrado campo a campo para datos sensibles en reposo.
- Cifrado automatico del `payload` de eventos RabbitMQ.
- Redacción básica de logs.

Controles que deben configurarse fuera del código:
- Cifrado en reposo del proyecto Supabase.
- Secret manager/variables protegidas en Render o plataforma equivalente.
- Rotación de secretos si ya fueron compartidos.
