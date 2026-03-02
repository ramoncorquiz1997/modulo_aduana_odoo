# -*- coding: utf-8 -*-
import re

import requests

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxAnamGafete(models.Model):
    _name = "mx.anam.gafete"
    _description = "Gafete ANAM de Chofer"
    _order = "write_date desc, id desc"

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    chofer_id = fields.Many2one(
        "res.partner",
        string="Chofer",
        required=True,
        domain="[('x_contact_role','=','chofer')]",
        ondelete="cascade",
        index=True,
    )
    transportista_id = fields.Many2one(
        "res.partner",
        string="Transportista",
        related="chofer_id.parent_id",
        store=True,
        readonly=True,
    )
    numero_gafete = fields.Char(string="Numero de gafete", required=True, index=True)
    qr_url = fields.Char(string="URL QR", required=True)
    estado = fields.Selection(
        [
            ("vigente", "Vigente"),
            ("vencido", "Vencido"),
            ("indeterminado", "Indeterminado"),
            ("error", "Error de validacion"),
        ],
        string="Estado",
        default="indeterminado",
        index=True,
        required=True,
    )
    vencido_desde = fields.Date(string="Vencido desde")
    validado_el = fields.Datetime(string="Validado el", readonly=True)
    mensaje_validacion = fields.Text(string="Mensaje de validacion", readonly=True)
    html_snippet = fields.Text(string="Fragmento HTML", readonly=True)

    _sql_constraints = [
        (
            "mx_anam_gafete_numero_uniq",
            "unique(numero_gafete)",
            "El numero de gafete ya existe.",
        )
    ]

    @api.depends("numero_gafete", "chofer_id")
    def _compute_name(self):
        for rec in self:
            chofer = rec.chofer_id.name or "Chofer"
            numero = rec.numero_gafete or "Sin numero"
            rec.name = f"{numero} - {chofer}"

    @api.constrains("chofer_id")
    def _check_chofer_parent(self):
        for rec in self:
            if rec.chofer_id and rec.chofer_id.x_contact_role != "chofer":
                raise ValidationError("El contacto seleccionado debe tener rol Chofer.")
            if rec.chofer_id and not rec.chofer_id.parent_id:
                raise ValidationError("El chofer debe estar ligado a un transportista (contacto padre).")

    @api.constrains("qr_url")
    def _check_qr_url(self):
        for rec in self:
            txt = (rec.qr_url or "").strip().lower()
            if txt and not (txt.startswith("http://") or txt.startswith("https://")):
                raise ValidationError("La URL del QR debe iniciar con http:// o https://")

    def _parse_estado_desde_html(self, html_text):
        txt = (html_text or "").strip()
        compact = " ".join(txt.split())
        low = compact.lower()

        m = re.search(r"vencido\s+desde\s+(\d{4}-\d{2}-\d{2})", low)
        if m:
            return {
                "estado": "vencido",
                "vencido_desde": fields.Date.to_date(m.group(1)),
                "mensaje": f"VENCIDO DESDE {m.group(1)}",
                "snippet": compact[:1500],
            }

        m = re.search(r"vencido\s+desde\s+(\d{2}/\d{2}/\d{4})", low)
        if m:
            raw = m.group(1)
            d, mth, y = raw.split("/")
            iso = f"{y}-{mth}-{d}"
            return {
                "estado": "vencido",
                "vencido_desde": fields.Date.to_date(iso),
                "mensaje": f"VENCIDO DESDE {iso}",
                "snippet": compact[:1500],
            }

        if "vigente" in low and "vencido" not in low:
            return {
                "estado": "vigente",
                "vencido_desde": False,
                "mensaje": "Gafete vigente",
                "snippet": compact[:1500],
            }

        return {
            "estado": "indeterminado",
            "vencido_desde": False,
            "mensaje": "No se pudo determinar vigencia con el contenido recibido.",
            "snippet": compact[:1500],
        }

    def action_validar_qr_url(self):
        for rec in self:
            url = (rec.qr_url or "").strip()
            if not url:
                raise ValidationError("Captura la URL QR antes de validar.")
            try:
                resp = requests.get(url, timeout=25)
                if resp.status_code >= 400:
                    rec.write({
                        "estado": "error",
                        "validado_el": fields.Datetime.now(),
                        "mensaje_validacion": f"HTTP {resp.status_code}: {resp.text[:500]}",
                        "html_snippet": False,
                    })
                    continue
                parsed = rec._parse_estado_desde_html(resp.text or "")
                rec.write({
                    "estado": parsed["estado"],
                    "vencido_desde": parsed["vencido_desde"],
                    "validado_el": fields.Datetime.now(),
                    "mensaje_validacion": parsed["mensaje"],
                    "html_snippet": parsed["snippet"],
                })
            except Exception as err:
                rec.write({
                    "estado": "error",
                    "validado_el": fields.Datetime.now(),
                    "mensaje_validacion": str(err),
                    "html_snippet": False,
                })
        return True

    def action_open_qr_camera(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "mx_qr_camera_scanner",
            "params": {
                "model": self._name,
                "resId": self.id,
                "title": "Escanear QR de Gafete ANAM",
            },
        }

    def action_set_qr_url_from_camera(self, qr_url, auto_validate=True):
        for rec in self:
            value = (qr_url or "").strip()
            if not value:
                raise ValidationError("No se recibió un valor de QR.")
            rec.write({"qr_url": value})
            if auto_validate:
                rec.action_validar_qr_url()
        return True

    @api.model
    def cron_validar_gafetes_anam(self, limit=300):
        gafetes = self.search(
            [("active", "=", True), ("qr_url", "!=", False)],
            order="write_date asc, id asc",
            limit=limit,
        )
        gafetes.action_validar_qr_url()
        return True
