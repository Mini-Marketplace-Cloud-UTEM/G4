# 1. Descarga la imagen oficial de Prism
FROM stoplight/prism:4

# 2. Copia el archivo de contrato al contenedor
COPY ["contrato-g4 .YAML", "/tmp/contrato.yaml"]

# 3. Informa el puerto interno que utiliza el contenedor 
EXPOSE 10000

# 4. Comando para ejecutar Prism en modo mock apuntando al archivo copiado
CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "/tmp/contrato.yaml"]

#para debuggear nombre archivo contrato-g4 por alguna razon mistica lo lee con un espacio de esta manera : contrato-g4 .YAML xDD
#FROM stoplight/prism:4

# 1. Cambiamos a un directorio de trabajo limpio
#WORKDIR /app

# 2. Copiamos TODO el repositorio de GitHub hacia adentro del contenedor
#COPY . .

# 3. Listamos recursivamente todo lo que se copió
#RUN ls -laR



