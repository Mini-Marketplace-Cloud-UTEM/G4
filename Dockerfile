# 1. Descarga la imagen oficial de Prism
#FROM stoplight/prism:4

# 2. Copia el archivo de contrato al contenedor
#COPY ["contrato-g4.yaml", "/tmp/contrato.yaml"]

# 3. Informa el puerto interno que utiliza el contenedor 
#EXPOSE 10000

# 4. Comando para ejecutar Prism en modo mock apuntando al archivo copiado
#CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "/tmp/contrato.yaml"]

# 1. Descarga la imagen oficial
FROM stoplight/prism:4

# 2. Copiamos TODO tu repositorio a una carpeta aislada llamada /auditoria
COPY . /auditoria/

# 3. Listamos todo recursivamente. 
# El flag '-b' revelará cualquier espacio invisible o carácter raro escapándolo (ej: \ )
RUN ls -laRb /auditoria/

# 4. Exponemos el puerto que le gusta a Render
EXPOSE 10000

# 5. Ponemos un comando inofensivo para que el contenedor no colapse buscando Node.js
CMD ["echo", "Auditoria de archivos completada. Revisa los logs de construccion."]

