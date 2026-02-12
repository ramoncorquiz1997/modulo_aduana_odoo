# -*- coding: utf-8 -*-
import base64
import logging
import re
import requests
import ssl
from odoo import fields, models, api

try:
    from pyzbar.pyzbar import decode
    from pdf2image import convert_from_bytes
    from bs4 import BeautifulSoup
except ImportError:
    decode = None

_logger = logging.getLogger(__name__)

class DESAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        # Creamos un contexto SSL que ignore las restricciones modernas
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        # Desactivamos explícitamente el check_hostname para permitir verify=False
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(DESAdapter, self).init_poolmanager(*args, **kwargs)

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

                    session = requests.Session()
                    session.mount("https://", DESAdapter())
                    
                    # Ahora sí pasamos verify=False sin conflicto
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

                        _logger.info("Extracción exitosa: %s", self.name)
                else:
                    _logger.warning("No se detectó QR.")
        except Exception as e:
            _logger.error("Error procesando CSF: %s", str(e))