# -*- coding: utf-8 -*-
import base64
import logging
import re
import requests
import urllib3
from odoo import fields, models, api

# Esto permite ignorar advertencias de SSL inseguro si fuera necesario
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from pyzbar.pyzbar import decode
    from pdf2image import convert_from_bytes
    from bs4 import BeautifulSoup
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
            # 1. Extraer URL del QR
            file_content = base64.b64decode(self.x_csf_file)
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            
            if images:
                qr_codes = decode(images[0])
                if qr_codes:
                    qr_data = qr_codes[0].data.decode('utf-8')
                    _logger.info("URL extraída del QR: %s", qr_data)

                    # 2. Configurar sesión para saltar el error "DH_KEY_TOO_SMALL"
                    # Bajamos el nivel de seguridad de CipherString a DEFAULT@SECLEVEL=1
                    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'
                    try:
                        response = requests.get(qr_data, timeout=15, verify=False)
                    except requests.exceptions.SSLError:
                        # Si falla por el nivel de seguridad, intentamos con una sesión configurada
                        session = requests.Session()
                        session.getattr = lambda *args: None 
                        response = session.get(qr_data, timeout=15, verify=False)

                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        tds = soup.find_all('td')
                        page_data = {}
                        
                        for i in range(len(tds)):
                            label = tds[i].get_text(strip=True)
                            if i + 1 < len(tds):
                                value = tds[i+1].get_text(strip=True)
                                if "RFC:" in label: page_data['rfc'] = value
                                if "CURP:" in label: page_data['curp'] = value
                                if "Nombre (s):" in label: page_data['nombre'] = value
                                if "Primer Apellido:" in label: page_data['p_apellido'] = value
                                if "Segundo Apellido:" in label: page_data['s_apellido'] = value
                                if "CP:" in label: page_data['cp'] = value
                                if "Nombre de la vialidad:" in label: page_data['calle'] = value
                                if "Número exterior:" in label: page_data['n_ext'] = value

                        # 3. Asignación a los campos
                        self.vat = page_data.get('rfc')
                        self.x_curp = page_data.get('curp')
                        self.name = ("%s %s %s" % (
                            page_data.get('nombre', ''),
                            page_data.get('p_apellido', ''),
                            page_data.get('s_apellido', '')
                        )).strip()
                        self.zip = page_data.get('cp')
                        self.street = ("%s %s" % (
                            page_data.get('calle', ''), 
                            page_data.get('n_ext', '')
                        )).strip()

                        _logger.info("Datos extraídos correctamente para: %s", self.name)
                else:
                    _logger.warning("No se detectó QR.")
        except Exception as e:
            _logger.error("Error procesando CSF: %s", str(e))