# -*- coding: utf-8 -*-
import base64
import io
import logging
import re
import unicodedata

import requests

from odoo import api, fields, models
from odoo.exceptions import ValidationError

try:
    from PIL import Image
    from pyzbar.pyzbar import decode as qr_decode
except Exception:  # pragma: no cover
    Image = None
    qr_decode = None

_logger = logging.getLogger(__name__)


class MxAnamGafete(models.Model):
    _name = "mx.anam.gafete"
    _description = "Gafete ANAM de Chofer"
    _order = "write_date desc, id desc"

    name = fields.Char(string="Nombre", compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    chofer_id = fields.Many2one(
        "res.partner",
        string="Chofer",
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
    numero_gafete = fields.Char(string="Numero de gafete", index=True)
    qr_url = fields.Char(string="URL QR")
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

    @api.constrains("numero_gafete")
    def _check_numero_gafete_when_active(self):
        for rec in self:
            if rec.active and not (rec.numero_gafete or "").strip():
                raise ValidationError("El numero de gafete es obligatorio en registros activos.")

    @api.constrains("active", "chofer_id")
    def _check_active_requires_chofer(self):
        for rec in self:
            if rec.active and not rec.chofer_id:
                raise ValidationError("Selecciona un chofer para activar el gafete.")

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

    def _extract_folio_and_nombre(self, html_text):
        txt = html_text or ""
        folio = False
        nombre = False

        m = re.search(r'id=["\']folio["\'][^>]*>\s*([^<]+?)\s*<', txt, flags=re.IGNORECASE)
        if m:
            folio = (m.group(1) or "").strip()
        if not folio:
            m = re.search(r"folio[^0-9]*([0-9]{3,})", txt, flags=re.IGNORECASE)
            if m:
                folio = (m.group(1) or "").strip()

        m = re.search(r"nombre\s*:\s*([^<\r\n]{5,})", txt, flags=re.IGNORECASE)
        if m:
            nombre = " ".join((m.group(1) or "").strip().split())

        return folio or False, nombre or False

    @staticmethod
    def _normalize_person_name(name):
        txt = (name or "").strip().upper()
        if not txt:
            return ""
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        txt = re.sub(r"[^A-Z0-9 ]+", " ", txt)
        txt = " ".join(txt.split())
        return txt

    def _match_chofer_from_nombre(self, nombre):
        """Intenta resolver chofer por nombre sin arriesgar asignaciones ambiguas."""
        target = self._normalize_person_name(nombre)
        if not target:
            return False, "Nombre vacio"

        chofer_model = self.env["res.partner"]
        candidates = chofer_model.search([("x_contact_role", "=", "chofer"), ("active", "=", True)])
        if not candidates:
            return False, "No hay choferes activos en catalogo."

        exact = candidates.filtered(lambda c: self._normalize_person_name(c.name) == target)
        if len(exact) == 1:
            return exact, "Match exacto por nombre."
        if len(exact) > 1:
            return False, "Nombre ambiguo: existe mas de un chofer con el mismo nombre."

        partial = candidates.filtered(lambda c: target in self._normalize_person_name(c.name))
        if len(partial) == 1:
            return partial, "Match aproximado unico por nombre."
        if len(partial) > 1:
            return False, "Nombre ambiguo: hay multiples coincidencias aproximadas."

        return False, "No se encontro chofer por nombre."

    def action_validar_qr_url(self):
        for rec in self:
            url = (rec.qr_url or "").strip()
            if not url:
                raise ValidationError("Captura la URL QR antes de validar.")
            try:
                resp = requests.get(url, timeout=3, allow_redirects=True)
                if resp.status_code >= 400:
                    rec.write({
                        "estado": "error",
                        "validado_el": fields.Datetime.now(),
                        "mensaje_validacion": f"HTTP {resp.status_code}: {resp.text[:500]}",
                        "html_snippet": False,
                    })
                    continue
                html_text = resp.text or ""
                parsed = rec._parse_estado_desde_html(html_text)
                folio, nombre = rec._extract_folio_and_nombre(html_text)
                vals = {
                    "estado": parsed["estado"],
                    "vencido_desde": parsed["vencido_desde"],
                    "validado_el": fields.Datetime.now(),
                    "mensaje_validacion": parsed["mensaje"],
                    "html_snippet": parsed["snippet"],
                }
                if folio:
                    vals["numero_gafete"] = folio
                if nombre and not rec.chofer_id:
                    chofer, reason = rec._match_chofer_from_nombre(nombre)
                    if chofer:
                        vals["chofer_id"] = chofer.id
                        vals["mensaje_validacion"] = f"{vals['mensaje_validacion']} | Chofer asignado: {chofer.name} ({reason})"
                    else:
                        vals["mensaje_validacion"] = f"{vals['mensaje_validacion']} | Nombre detectado: {nombre}. {reason} Selecciona chofer manualmente."
                rec.write(vals)
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
        rec = self
        if not rec.id:
            if not rec.chofer_id or not rec.chofer_id.id:
                raise ValidationError("Guarda primero el chofer para poder escanear el gafete.")
            rec = self.create({
                "chofer_id": rec.chofer_id.id,
                "active": False,
            })
        return {
            "type": "ir.actions.client",
            "tag": "mx_qr_camera_scanner",
            "params": {
                "model": rec._name,
                "resId": rec.id,
                "res_id": rec.id,
                "title": "Escanear QR de Gafete ANAM",
            },
        }

    def action_set_qr_url_from_camera(self, qr_url, auto_validate=True):
        for rec in self:
            value = (qr_url or "").strip()
            if not value:
                raise ValidationError("No se recibió un valor de QR.")
            # Permite escanear primero sin bloquear por campos que aún no se conocen.
            rec.write({"qr_url": value, "active": False if not rec.numero_gafete else rec.active})
            if auto_validate:
                try:
                    with self.env.cr.savepoint():
                        rec.action_validar_qr_url()
                except Exception as err:
                    _logger.exception("Fallo validacion automatica de QR (gafete id=%s)", rec.id)
                    rec.write({
                        "estado": "error",
                        "validado_el": fields.Datetime.now(),
                        "mensaje_validacion": f"Error en validacion automatica: {err}",
                    })
            if rec.numero_gafete and rec.chofer_id and not rec.active:
                rec.active = True
        return True

    def action_decode_qr_image_from_camera(self, image_data):
        self.ensure_one()
        if not qr_decode or not Image:
            return False
        if not image_data:
            return False
        raw = image_data
        if "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            binary = base64.b64decode(raw)
            img = Image.open(io.BytesIO(binary))
            result = qr_decode(img)
            if not result:
                return False
            return result[0].data.decode("utf-8", errors="ignore")
        except Exception:
            return False

    def action_qr_decoder_status(self):
        self.ensure_one()
        missing = []
        if not Image:
            missing.append("Pillow")
        if not qr_decode:
            missing.append("pyzbar/zbar")
        if missing:
            return {
                "ready": False,
                "message": "Faltan dependencias de decoder servidor: %s." % ", ".join(missing),
            }
        return {
            "ready": True,
            "message": "Decoder servidor listo.",
        }

    @api.model
    def cron_validar_gafetes_anam(self, limit=300):
        gafetes = self.search(
            [("active", "=", True), ("qr_url", "!=", False)],
            order="write_date asc, id asc",
            limit=limit,
        )
        gafetes.action_validar_qr_url()
        return True
