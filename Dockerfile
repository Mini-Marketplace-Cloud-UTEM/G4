# 1. Descarga la imagen oficial de Prism
FROM stoplight/prism:4

# 2. Copia el archivo de contrato al contenedor
COPY ["contrato-g4.yaml", "/tmp/contrato.yaml"]

# 3. Informa el puerto interno que utiliza el contenedor 
EXPOSE 10000

# 4. Comando para ejecutar Prism en modo mock apuntando al archivo copiado
CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "/tmp/contrato.yaml"]



