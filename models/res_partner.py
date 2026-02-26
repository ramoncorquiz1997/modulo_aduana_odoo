# -*- coding: utf-8 -*-
import base64
import json
import logging
import requests
import ssl
import urllib3
from odoo import api, fields, models
from odoo.exceptions import UserError

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
    _DOC_FILENAME_PAIRS = [
        ("x_csf_file", "x_csf_filename"),
        ("x_pf_programa_fomento_file", "x_pf_programa_fomento_filename"),
        ("x_pf_fotos_instalaciones_file", "x_pf_fotos_instalaciones_filename"),
        ("x_pf_sellos_vucem_file", "x_pf_sellos_vucem_filename"),
        ("x_pf_contrato_servicios_file", "x_pf_contrato_servicios_filename"),
        ("x_pf_carta_69b_file", "x_pf_carta_69b_filename"),
        ("x_pf_cuestionario_oea_ctpat_file", "x_pf_cuestionario_oea_ctpat_filename"),
        ("x_pf_autorizacion_shipper_export_file", "x_pf_autorizacion_shipper_export_filename"),
        ("x_pf_convenio_confidencialidad_file", "x_pf_convenio_confidencialidad_filename"),
        ("x_pf_info_atencion_ce_file", "x_pf_info_atencion_ce_filename"),
        ("x_pf_opinion_cumplimiento_mensual_file", "x_pf_opinion_cumplimiento_mensual_filename"),
        ("x_pf_pantalla_domicilio_localizado_file", "x_pf_pantalla_domicilio_localizado_filename"),
        ("x_pm_acta_constitutiva_file", "x_pm_acta_constitutiva_filename"),
        ("x_pm_poder_representante_file", "x_pm_poder_representante_filename"),
        ("x_pm_doc_propiedad_posesion_file", "x_pm_doc_propiedad_posesion_filename"),
        ("x_pm_rep_identificacion_file", "x_pm_rep_identificacion_filename"),
        ("x_pm_rep_rfc_csf_file", "x_pm_rep_rfc_csf_filename"),
        ("x_pm_rep_opinion_cumplimiento_file", "x_pm_rep_opinion_cumplimiento_filename"),
        ("x_pm_acta_verificacion_domicilio_file", "x_pm_acta_verificacion_domicilio_filename"),
        ("x_pm_comprobante_domicilio_file", "x_pm_comprobante_domicilio_filename"),
        ("x_pm_opinion_32d_file", "x_pm_opinion_32d_filename"),
        ("x_pm_carta_encomienda_file", "x_pm_carta_encomienda_filename"),
        ("x_pm_acuse_encargo_conferido_file", "x_pm_acuse_encargo_conferido_filename"),
        ("x_pm_programa_fomento_file", "x_pm_programa_fomento_filename"),
        ("x_pm_sellos_vucem_file", "x_pm_sellos_vucem_filename"),
        ("x_pm_fotos_instalaciones_file", "x_pm_fotos_instalaciones_filename"),
        ("x_pm_contrato_servicios_file", "x_pm_contrato_servicios_filename"),
        ("x_pm_carta_69b_file", "x_pm_carta_69b_filename"),
        ("x_pm_cuestionarios_oea_ctpat_file", "x_pm_cuestionarios_oea_ctpat_filename"),
        ("x_pm_autorizacion_shipper_export_file", "x_pm_autorizacion_shipper_export_filename"),
        ("x_pm_convenio_confidencialidad_file", "x_pm_convenio_confidencialidad_filename"),
    ]

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
    x_street_name = fields.Char(string="Calle")
    x_street_number_ext = fields.Char(string="Numero exterior")
    x_street_number_int = fields.Char(string="Numero interior")
    x_colonia = fields.Char(string="Colonia")
    x_municipio = fields.Char(string="Municipio")
    x_localidad = fields.Char(string="Localidad")
    x_csf_filename = fields.Char(string="Nombre de archivo CSF")
    x_csf_file = fields.Binary(string="CSF (PDF)")
    # Persona fisica - expediente documental
    x_pf_programa_fomento_filename = fields.Char(string="Programa fomento / certificacion")
    x_pf_programa_fomento_file = fields.Binary(string="Programa fomento / certificacion")
    x_pf_fotos_instalaciones_filename = fields.Char(string="Fotografias instalaciones")
    x_pf_fotos_instalaciones_file = fields.Binary(string="Fotografias instalaciones")
    x_pf_sellos_vucem_filename = fields.Char(string="Sellos VUCEM")
    x_pf_sellos_vucem_file = fields.Binary(string="Sellos VUCEM")
    x_pf_contrato_servicios_filename = fields.Char(string="Contrato servicios")
    x_pf_contrato_servicios_file = fields.Binary(string="Contrato servicios")
    x_pf_carta_69b_filename = fields.Char(string="Carta 69-B/49 Bis")
    x_pf_carta_69b_file = fields.Binary(string="Carta 69-B/49 Bis")
    x_pf_cuestionario_oea_ctpat_filename = fields.Char(string="Cuestionarios OEA/CTPAT")
    x_pf_cuestionario_oea_ctpat_file = fields.Binary(string="Cuestionarios OEA/CTPAT")
    x_pf_autorizacion_shipper_export_filename = fields.Char(string="Autorizacion Shipper Export")
    x_pf_autorizacion_shipper_export_file = fields.Binary(string="Autorizacion Shipper Export")
    x_pf_convenio_confidencialidad_filename = fields.Char(string="Convenio confidencialidad")
    x_pf_convenio_confidencialidad_file = fields.Binary(string="Convenio confidencialidad")
    x_pf_info_atencion_ce_filename = fields.Char(string="Info atencion Comercio Exterior")
    x_pf_info_atencion_ce_file = fields.Binary(string="Info atencion Comercio Exterior")
    x_pf_opinion_cumplimiento_mensual_filename = fields.Char(string="Opinion cumplimiento mensual")
    x_pf_opinion_cumplimiento_mensual_file = fields.Binary(string="Opinion cumplimiento mensual")
    x_pf_pantalla_domicilio_localizado_filename = fields.Char(string="Pantalla domicilio localizado")
    x_pf_pantalla_domicilio_localizado_file = fields.Binary(string="Pantalla domicilio localizado")

    # Persona moral - expediente documental
    x_pm_acta_constitutiva_filename = fields.Char(string="Acta constitutiva")
    x_pm_acta_constitutiva_file = fields.Binary(string="Acta constitutiva")
    x_pm_poder_representante_filename = fields.Char(string="Poder representante legal")
    x_pm_poder_representante_file = fields.Binary(string="Poder representante legal")
    x_pm_doc_propiedad_posesion_filename = fields.Char(string="Documento propiedad/posesion")
    x_pm_doc_propiedad_posesion_file = fields.Binary(string="Documento propiedad/posesion")
    x_pm_rep_identificacion_filename = fields.Char(string="Identificacion representante")
    x_pm_rep_identificacion_file = fields.Binary(string="Identificacion representante")
    x_pm_rep_rfc_csf_filename = fields.Char(string="RFC personal representante (CSF)")
    x_pm_rep_rfc_csf_file = fields.Binary(string="RFC personal representante (CSF)")
    x_pm_rep_opinion_cumplimiento_filename = fields.Char(string="Opinion cumplimiento representante")
    x_pm_rep_opinion_cumplimiento_file = fields.Binary(string="Opinion cumplimiento representante")
    x_pm_acta_verificacion_domicilio_filename = fields.Char(string="Acta verificacion domicilio")
    x_pm_acta_verificacion_domicilio_file = fields.Binary(string="Acta verificacion domicilio")
    x_pm_comprobante_domicilio_filename = fields.Char(string="Comprobante domicilio")
    x_pm_comprobante_domicilio_file = fields.Binary(string="Comprobante domicilio")
    x_pm_opinion_32d_filename = fields.Char(string="Opinion cumplimiento 32-D")
    x_pm_opinion_32d_file = fields.Binary(string="Opinion cumplimiento 32-D")
    x_pm_carta_encomienda_filename = fields.Char(string="Carta encomienda")
    x_pm_carta_encomienda_file = fields.Binary(string="Carta encomienda")
    x_pm_acuse_encargo_conferido_filename = fields.Char(string="Acuse encargo conferido")
    x_pm_acuse_encargo_conferido_file = fields.Binary(string="Acuse encargo conferido")
    x_pm_programa_fomento_filename = fields.Char(string="Programa fomento/certificacion")
    x_pm_programa_fomento_file = fields.Binary(string="Programa fomento/certificacion")
    x_pm_sellos_vucem_filename = fields.Char(string="Sellos VUCEM")
    x_pm_sellos_vucem_file = fields.Binary(string="Sellos VUCEM")
    x_pm_fotos_instalaciones_filename = fields.Char(string="Fotografias instalaciones")
    x_pm_fotos_instalaciones_file = fields.Binary(string="Fotografias instalaciones")
    x_pm_contrato_servicios_filename = fields.Char(string="Contrato servicios")
    x_pm_contrato_servicios_file = fields.Binary(string="Contrato servicios")
    x_pm_carta_69b_filename = fields.Char(string="Carta 69-B")
    x_pm_carta_69b_file = fields.Binary(string="Carta 69-B")
    x_pm_cuestionarios_oea_ctpat_filename = fields.Char(string="Cuestionarios OEA/CTPAT")
    x_pm_cuestionarios_oea_ctpat_file = fields.Binary(string="Cuestionarios OEA/CTPAT")
    x_pm_autorizacion_shipper_export_filename = fields.Char(string="Autorizacion Shipper Export")
    x_pm_autorizacion_shipper_export_file = fields.Binary(string="Autorizacion Shipper Export")
    x_pm_convenio_confidencialidad_filename = fields.Char(string="Convenio confidencialidad")
    x_pm_convenio_confidencialidad_file = fields.Binary(string="Convenio confidencialidad")
    x_rule_engine_strict = fields.Selection(
        [
            ("inherit", "Heredar global"),
            ("strict", "Forzar STRICT"),
            ("relaxed", "Forzar no strict"),
        ],
        string="Motor reglas STRICT",
        default="inherit",
    )

    def _wa_param(self, key):
        return self.env["ir.config_parameter"].sudo().get_param(key)

    def _wa_normalize_phone(self, raw):
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        if len(digits) == 10:
            digits = f"52{digits}"
        return digits

    def _wa_send_message(self, to, payload):
        token = self._wa_param("modulo_aduana_odoo.whatsapp_token")
        phone_number_id = self._wa_param("modulo_aduana_odoo.whatsapp_phone_number_id")
        _logger.info(
            "WA send init partner=%s to=%s has_token=%s phone_number_id=%s",
            self.id,
            to,
            bool(token),
            phone_number_id or "",
        )
        if not token or not phone_number_id:
            raise UserError("Falta configurar WhatsApp en Parametros del sistema (token y phone_number_id).")
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {"messaging_product": "whatsapp", "to": to}
        body.update(payload)
        _logger.info("WA request url=%s payload_type=%s", url, payload.get("type"))
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
        _logger.info("WA response status=%s body=%s", resp.status_code, resp.text[:1000])
        if resp.status_code >= 300:
            raise UserError(f"No se pudo enviar WhatsApp ({resp.status_code}): {resp.text}")
        return resp

    def action_request_missing_documents(self):
        sent_to = []
        for rec in self:
            to = rec._wa_normalize_phone(rec.mobile or rec.phone)
            _logger.info(
                "WA request docs partner=%s name=%s mobile=%s phone=%s normalized=%s has_csf=%s",
                rec.id,
                rec.name,
                rec.mobile or "",
                rec.phone or "",
                to,
                bool(rec.x_csf_file),
            )
            if not to:
                raise UserError("El contacto no tiene telefono/mobile valido para WhatsApp.")

            missing_rows = []
            if not rec.x_csf_file:
                missing_rows.append({"id": "send_csf", "title": "Enviar CSF"})

            if not missing_rows:
                raise UserError("No hay documentos faltantes por solicitar (CSF ya cargado).")

            # Prepara sesion para que, al llegar el archivo, se procese como CSF.
            session_model = self.env["mx.wa.session"].sudo()
            session = session_model.search([("wa_id", "=", to)], limit=1)
            vals = {"partner_id": rec.id}
            if len(missing_rows) == 1 and missing_rows[0]["id"] == "send_csf":
                vals["expected_doc_type"] = "csf"
            if session:
                session.write(vals)
            else:
                vals["wa_id"] = to
                session_model.create(vals)

            payload = {
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": "Tenemos documentos pendientes. Selecciona cual enviar:"},
                    "action": {
                        "button": "Seleccionar",
                        "sections": [{"title": "Pendientes", "rows": missing_rows}],
                    },
                },
            }
            rec._wa_send_message(to, payload)
            sent_to.append(to)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "WhatsApp",
                "message": f"Solicitud enviada a: {', '.join(sent_to)}",
                "type": "success",
                "sticky": False,
            },
        }

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
                    if "Numero interior" in label or "NÃºmero interior" in label:
                        page_data["n_int"] = value
                    if "Colonia" in label:
                        page_data["colonia"] = value
                    if "Municipio" in label or "Demarcacion Territorial" in label:
                        page_data["municipio"] = value
                    if "Localidad" in label:
                        page_data["localidad"] = value

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
                vals["x_street_name"] = calle
            if page_data.get("n_ext"):
                vals["x_street_number_ext"] = page_data["n_ext"]
            if page_data.get("n_int"):
                vals["x_street_number_int"] = page_data["n_int"]
            if page_data.get("colonia"):
                vals["x_colonia"] = page_data["colonia"]
            if page_data.get("municipio"):
                vals["x_municipio"] = page_data["municipio"]
            if page_data.get("localidad"):
                vals["x_localidad"] = page_data["localidad"]
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

    @api.onchange("x_street_name", "x_street_number_ext", "x_street_number_int")
    def _onchange_split_address(self):
        for rec in self:
            if not rec.x_street_name:
                continue
            street = " ".join(filter(None, [rec.x_street_name, rec.x_street_number_ext]))
            if rec.x_street_number_int:
                street = f"{street} INT {rec.x_street_number_int}"
            rec.street = street

    @api.model
    def _fill_missing_document_filenames(self, vals):
        for file_field, filename_field in self._DOC_FILENAME_PAIRS:
            if vals.get(file_field) and not vals.get(filename_field):
                vals[filename_field] = "%s.pdf" % file_field.replace("_file", "")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._fill_missing_document_filenames(vals)
            if vals.get("x_csf_file"):
                vals.update(self._extract_csf_values(vals.get("x_csf_file")))
        return super().create(vals_list)

    def write(self, vals):
        update_vals = dict(vals)
        self._fill_missing_document_filenames(update_vals)
        if vals.get("x_csf_file"):
            update_vals.update(self._extract_csf_values(vals.get("x_csf_file")))
        return super().write(update_vals)
