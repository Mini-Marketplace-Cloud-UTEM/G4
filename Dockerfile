# 1. Usamos una imagen oficial y ligera de Python
FROM python:3.10-slim

# 2. Le decimos a Docker en qué carpeta interna va a trabajar
WORKDIR /app

# 3. Copiamos el archivo de requerimientos y los instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos todo nuestro código (el main.py) al contenedor
COPY . .

# 5. Exponemos el puerto estándar
EXPOSE 8000

# 6. El comando maestro para arrancar FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
