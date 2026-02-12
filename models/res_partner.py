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
            file_content = base64.b64decode(self.x_csf_file)
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            
            if images:
                qr_codes = decode(images[0])
                if qr_codes:
                    qr_data = qr_codes[0].data.decode('utf-8')
                    _logger.info("URL extraída del QR: %s", qr_data)

                    # --- NUEVA LÓGICA PARA EL PARÁMETRO D3 ---
                    # Buscamos el RFC al final de la cadena D3 (después del guion bajo _)
                    # Ejemplo: ...D3=20030099070_EIAJ8910101J7
                    rfc_match = re.search(r'D3=.*?_([A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3})', qr_data)
                    
                    if rfc_match:
                        self.vat = rfc_match.group(1)
                        _logger.info("RFC asignado: %s", self.vat)
                    else:
                        # Intento alternativo si no trae guion bajo
                        rfc_alt = re.search(r'D3=([A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3})', qr_data)
                        if rfc_alt:
                            self.vat = rfc_alt.group(1)

                    # Nota: El QR del SAT normalmente no trae la CURP en esta URL simplificada.
                    # Si necesitas la CURP, tendremos que usar el OCR de texto además del QR.

                else:
                    _logger.warning("No se detectó QR en el archivo.")
                    
        except Exception as e:
            _logger.error("Error: %s", str(e))