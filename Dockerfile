# 1. Descarga la imagen oficial de Prism
FROM stoplight/prism:4

# 2. Creamos una carpeta de trabajo segura que Render no borre
WORKDIR /app

# 3. Copiamos el archivo comprobado hacia esta carpeta segura
COPY contrato-g4.yaml /app/contrato.yaml

# 4. Exponemos el puerto 10000
EXPOSE 10000

# 5. Arrancamos Prism apuntando a la nueva ruta inamovible
CMD ["mock", "-h", "0.0.0.0", "-p", "10000", "/app/contrato.yaml"]
