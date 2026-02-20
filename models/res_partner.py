# -*- coding: utf-8 -*-
import base64
import logging
import requests
import ssl
import urllib3
from odoo import api, fields, models

# Desactivar advertencias de SSL en el log
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from pyzbar.pyzbar import decode
    from pdf2image import convert_from_bytes
    from bs4 import BeautifulSoup
except ImportError:
    decode = None

_logger = logging.getLogger(__name__)


class DESAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.set_ciphers("DEFAULT@SECLEVEL=1")
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = context
        return super(DESAdapter, self).init_poolmanager(*args, **kwargs)


class ResPartner(models.Model):
    _inherit = "res.partner"

    x_contact_role = fields.Selection(
        [
            ("cliente", "Cliente"),
            ("agente_aduanal", "Agente Aduanal"),
            ("transportista", "Transportista"),
            ("proveedor", "Proveedor"),
            ("otro", "Otro"),
        ],
        string="Rol aduanal",
        default="cliente",
    )
    x_curp = fields.Char(string="CURP")
    x_identificacion_fiscal = fields.Char(string="Identificacion fiscal (extranjero)")
    x_patente_aduanal = fields.Char(string="Patente aduanal")
    x_num_autorizacion_aduanal = fields.Char(string="Num. autorizacion aduanal")
    x_csf_filename = fields.Char(string="Nombre de archivo CSF")
    x_csf_file = fields.Binary(string="CSF (PDF)")

    def _extract_csf_values(self, encoded_pdf):
        if not encoded_pdf or not decode:
            return {}
        try:
            file_content = base64.b64decode(encoded_pdf)
            images = convert_from_bytes(file_content, first_page=1, last_page=1)
            if not images:
                return {}

            qr_codes = decode(images[0])
            if not qr_codes:
                _logger.warning("CSF sin QR detectable.")
                return {}

            qr_data = qr_codes[0].data.decode("utf-8")
            session = requests.Session()
            session.mount("https://", DESAdapter())
            response = session.get(qr_data, timeout=15, verify=False)
            if response.status_code != 200:
                _logger.warning("CSF QR URL respondio %s", response.status_code)
                return {}

            soup = BeautifulSoup(response.text, "html.parser")
            tds = soup.find_all("td")
            page_data = {}
            for i in range(len(tds)):
                label = tds[i].get_text().replace(":", "").strip()
                if i + 1 < len(tds):
                    value = tds[i + 1].get_text(strip=True)
                    if "RFC" in label:
                        page_data["rfc"] = value
                    if "CURP" in label:
                        page_data["curp"] = value
                    if "CP" in label:
                        page_data["cp"] = value
                    if "Nombre de la vialidad" in label:
                        page_data["calle"] = value
                    if "Numero exterior" in label or "NÃºmero exterior" in label:
                        page_data["n_ext"] = value

            vals = {}
            if page_data.get("rfc"):
                vals["vat"] = page_data["rfc"]
            if page_data.get("curp"):
                vals["x_curp"] = page_data["curp"]
            if page_data.get("cp"):
                vals["zip"] = page_data["cp"]
            calle = page_data.get("calle", "")
            nexten = page_data.get("n_ext", "")
            if calle:
                vals["street"] = ("%s %s" % (calle, nexten)).strip()
            return vals
        except Exception:
            _logger.exception("Error procesando CSF")
            return {}

    @api.onchange("x_csf_file")
    def _onchange_x_csf_file(self):
        for rec in self:
            vals = rec._extract_csf_values(rec.x_csf_file)
            for k, v in vals.items():
                rec[k] = v

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("x_csf_file"):
                vals.update(self._extract_csf_values(vals.get("x_csf_file")))
        return super().create(vals_list)

    def write(self, vals):
        update_vals = dict(vals)
        if vals.get("x_csf_file"):
            update_vals.update(self._extract_csf_values(vals.get("x_csf_file")))
        return super().write(update_vals)
