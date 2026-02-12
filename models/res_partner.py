# -*- coding: utf-8 -*-
import base64
import re
import logging
from odoo import fields, models, api

# Intentar importar las librerías de OCR
try:
    import pytesseract
    from pdf2image import convert_from_bytes
except ImportError:
    pytesseract = None

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = "res.partner"

    x_curp = fields.Char(string="CURP")
    x_identificacion_fiscal = fields.Char(string="Identificación fiscal (extranjero)")

    # Documentos
    x_csf_filename = fields.Char(string="Nombre de archivo CSF")
    x_csf_file = fields.Binary(string="CSF (PDF)")

    @api.onchange('x_csf_file')
    def _onchange_x_csf_file(self):
        if not self.x_csf_file or not pytesseract:
            return

        try:
            file_content = base64.b64decode(self.x_csf_file)
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            
            if images:
                text = pytesseract.image_to_string(images[0], lang='spa')
                
                clean_text = " ".join(text.split())
                _logger.info("OCR Result: %s", clean_text)

                
                rfc_match = re.search(r'RFC:?\s*([A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3})', clean_text)
                if rfc_match:
                    self.vat = rfc_match.group(1)

                curp_match = re.search(r'CURP:?\s*([A-Z]{4}[0-9]{6}[HM][A-Z]{5}[0-9]{2})', clean_text)
                if curp_match:
                    self.x_curp = curp_match.group(1)

                
        except Exception as e:
            _logger.error("Error en OCR CSF: %s", str(e))
            return {'warning': {'title': "Error de lectura", 'message': "No se pudo procesar el OCR: %s" % str(e)}}