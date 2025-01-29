from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
import re
import json
from PIL import Image
import pytesseract
import fitz  # PyMuPDF para manejar PDFs


# Configurar Tesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


class LeerArchivoPdf(APIView):
    parser_classes = (MultiPartParser, FormParser)

    # Función para limpiar texto
    def limpiar_texto(self, texto):
        return texto.replace('\n', ' ').replace('  ', ' ').replace('(', '').replace(')', '').replace('_', '').strip()

    # Función para extraer datos con expresiones regulares
    def extraer_datos(self, texto):
        # Expresiones regulares
        solicitado_nombre_pattern = r"Solicitado por[:\s]*Nombre[:\s]*([\w\s'/]+)"
        solicitado_telefono_pattern = r"Teléfono[:\s]*([\d]+)"
        solicitado_correo_pattern = r"Correo[:\s]*([\w\.\-_]+@[A-Za-z0-9\.\-]+\.[A-Za-z]{2,})"

        entregar_nombre_pattern = r"Entregar a[:\s]*Nombre[:\s]*([\w\s'/]+)"
        entregar_telefono_pattern = r"Entregar a[:\s]*Teléfono[:\s]*([\d]+)"
        entregar_direccion_pattern = r"Dirección[:\s]*([\w\s]+)"
        entregar_notas_pattern = r"Notas[:\s]*([\w\s'/,]+)"

        # Buscar datos en el texto extraído
        solicitado_nombre = re.search(solicitado_nombre_pattern, texto)
        solicitado_telefono = re.search(solicitado_telefono_pattern, texto)
        solicitado_correo = re.search(solicitado_correo_pattern, texto)

        entregar_nombre = re.search(entregar_nombre_pattern, texto)
        entregar_telefono = re.search(entregar_telefono_pattern, texto)
        entregar_direccion = re.search(entregar_direccion_pattern, texto)
        entregar_notas = re.search(entregar_notas_pattern, texto)

        # Crear diccionario con los datos encontrados
        datos = {
            "Solicitado_por": {
                "Nombre": solicitado_nombre.group(1).strip() if solicitado_nombre else None,
                "Teléfono": solicitado_telefono.group(1) if solicitado_telefono else None,
                "Correo": solicitado_correo.group(1) if solicitado_correo else None
            },
            "Entregar_a": {
                "Nombre": entregar_nombre.group(1).strip() if entregar_nombre else None,
                "Teléfono": entregar_telefono.group(1) if entregar_telefono else None,
                "Dirección": entregar_direccion.group(1).strip() if entregar_direccion else None,
                "Notas": entregar_notas.group(1).strip() if entregar_notas else None
            }
        }
        return datos

    # Función para procesar un PDF
    def procesar_pdf(self, pdf_file):
        pdf_documento = fitz.open(stream=pdf_file.read(), filetype="pdf")
        resultados = []

        for num_pagina in range(len(pdf_documento)):
            pagina = pdf_documento[num_pagina]

            # Extraer imágenes de la página
            for img_index, img in enumerate(pagina.get_images(full=True)):
                xref = img[0]
                base_img = pdf_documento.extract_image(xref)
                image_bytes = base_img["image"]
                image_ext = base_img["ext"]
                image_path = f"temp_image_pagina_{num_pagina + 1}_img_{img_index + 1}.{image_ext}"

                # Guardar la imagen temporalmente
                with open(image_path, "wb") as img_file:
                    img_file.write(image_bytes)

                # Abrir la imagen y realizar OCR
                img = Image.open(image_path)
                texto_extraido = pytesseract.image_to_string(img, lang="spa")
                texto_limpio = self.limpiar_texto(texto_extraido)

                # Extraer los datos de la imagen
                datos = self.extraer_datos(texto_limpio)
                resultados.append({
                    "Pagina": num_pagina + 1,
                    "Imagen": img_index + 1,
                    "Datos": datos
                })

        return resultados

    # Método POST para procesar el archivo PDF
    def post(self, request, *args, **kwargs):
        pdf_file = request.FILES.get('archivo_pdf')

        if not pdf_file:
            return Response({"error": "No se ha proporcionado ningún archivo PDF"}, status=400)

        try:
            resultados = self.procesar_pdf(pdf_file)
            return Response(resultados, status=200)
        except Exception as e:
            return Response({"error": f"Error al procesar el archivo PDF: {str(e)}"}, status=500)

