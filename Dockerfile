# 1. Descarga la imagen oficial de Prism
FROM stoplight/prism:4

# 2. Copiamos el archivo directamente a la raíz para que Render no lo borre
COPY contrato-g4.yaml /contrato.yaml

# 3. Exponemos el puerto 10000
EXPOSE 10000

# 4. Arrancamos Prism apuntando a la raíz
CMD ["mock", "-h", "0.0.0.0", "-p", "10000", "/contrato.yaml"]
