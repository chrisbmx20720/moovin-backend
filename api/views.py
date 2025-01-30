from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
import re
import json
from PIL import Image
import pytesseract
import fitz  # PyMuPDF para manejar PDFs


# Configuracion Tesseract
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

   
    def post(self, request, *args, **kwargs):
        pdf_file = request.FILES.get('archivo_pdf')

       

        try:
            
            if not pdf_file:
             return Response({"error": "No se ha proporcionado ningún archivo PDF"}, status=400)
            print("✅ Archivo PDF recibido")

            # Procesar el PDF y extraer el texto
            resultados = self.procesar_pdf(pdf_file)
            print(f"✅ Resultados extraídos: {resultados}")

            
            # Convertimos cada diccionario a JSON para convertirlo en una cadena
            texto_extraido = '\n'.join([json.dumps(res['Datos'], ensure_ascii=False) for res in resultados])

            # Cargar las credenciales de Google
            creds = cargar_credenciales()
            print("✅ Credenciales cargadas correctamente") 

            # Crear el documento en Google Docs
            document_id = crear_documento_google(creds, texto_extraido)
            if document_id:
                print(f'Documento creado con ID: {document_id}')

            # Subir el archivo a Google Drive
            file_id = subir_archivo_drive(creds, texto_extraido)
            if file_id:
                print(f'Archivo subido con ID: {file_id}')

            # Responder al frontend con los datos procesados
            return Response(resultados, status=200)

        except Exception as e:
            return Response({"error": f"Error al procesar el archivo PDF: {str(e)}"}, status=500) 
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pickle
from googleapiclient.http import MediaInMemoryUpload  # Importar MediaInMemoryUpload
from google.auth.transport.requests import Request  # Importar Request para actualizar las credenciales

# Definir los alcances para Google Docs y Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/documents']

# Función para cargar las credenciales de Google
def cargar_credenciales():
    """Maneja la autenticación con Google y devuelve un objeto de autorización"""
    creds = None
    # El archivo token.pickle almacena las credenciales del usuario
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # Si no hay credenciales (o son inválidas), pide autorización al usuario.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "../Backend/api/google_credentials/credentials.json", SCOPES)
            creds = flow.run_local_server(port=5173 )
        
        # Guardar las credenciales para la próxima vez
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

# Función para crear un documento en Google Docs
def crear_documento_google(creds, texto):
    try:
        service = build('docs', 'v1', credentials=creds)
        document = service.documents().create().execute()
        document_id = document['documentId']
        
        # Insertar el texto extraído del PDF en el documento de Google Docs
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': 1
                    },
                    'text': texto
                }
            }
        ]
        service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()
        return document_id
    except HttpError as err:
        print(f"Error al crear el documento: {err}")
        return None

# Función para subir un archivo a Google Drive
def subir_archivo_drive(creds, texto, nombre_archivo="documento_extraido.txt"):
    try:
        service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': nombre_archivo, 'mimeType': 'text/plain'}
        media = MediaInMemoryUpload(texto.encode(), mimetype='text/plain')

        file = service.files().create(
            media_body=media,
            body=file_metadata,
            fields='id'
        ).execute()
        
        return file.get('id')
    except HttpError as err:
        print(f"Error al subir archivo: {err}")
        return None
