# -*- coding: utf-8 -*-
import base64
import logging
import re
from odoo import fields, models, api

try:
    from pyzbar.pyzbar import decode
    from pdf2image import convert_from_bytes
except ImportError:
    decode = None

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = "res.partner"

    x_curp = fields.Char(string="CURP")
    x_identificacion_fiscal = fields.Char(string="Identificación fiscal (extranjero)")
    x_csf_filename = fields.Char(string="Nombre de archivo CSF")
    x_csf_file = fields.Binary(string="CSF (PDF)")

    @api.onchange('x_csf_file')
    def _onchange_x_csf_file(self):
        if not self.x_csf_file or not decode:
            return

        try:
            # 1. Convertir PDF a Imagen
            file_content = base64.b64decode(self.x_csf_file)
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            
            if images:
                # 2. Buscar y Decodificar el QR
                qr_codes = decode(images[0])
                
                if qr_codes:
                    # La URL del SAT suele ser algo como: https://msc.satsaid.gob.mx/consultas/....
                    qr_data = qr_codes[0].data.decode('utf-8')
                    _logger.info("URL extraída del QR: %s", qr_data)

                    # 3. Extraer RFC de la URL (El RFC siempre viene en el parámetro 'id=')
                    # Ejemplo: ...?id=EIAJ8910101J7&...
                    rfc_match = re.search(r'id=([A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3})', qr_data)
                    if rfc_match:
                        self.vat = rfc_match.group(1)
                        
                    # 4. Extraer CURP de la URL (si viene presente)
                    curp_match = re.search(r'curp=([A-Z]{4}[0-9]{6}[HM][A-Z]{5}[0-9]{2})', qr_data)
                    if curp_match:
                        self.x_curp = curp_match.group(1)

                else:
                    _logger.warning("No se encontró código QR en la primera página.")
                    
        except Exception as e:
            _logger.error("Error procesando QR: %s", str(e))