# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AduanaSetupWizard(models.TransientModel):
    """Asistente de configuracion inicial para una agencia nueva en Aduanex."""
    _name = "aduana.setup.wizard"
    _description = "Asistente de configuracion inicial Aduanex"

    step = fields.Selection(
        [
            ("agencia", "1. Datos de la agencia"),
            ("vucem", "2. Credencial VUCEM"),
            ("catalogo", "3. Catalogos base"),
            ("listo", "4. Listo"),
        ],
        default="agencia",
        required=True,
    )

    # ── Paso 1: Agencia ──────────────────────────────────────────────────
    agente_id = fields.Many2one(
        "res.partner",
        string="Agente Aduanal",
        domain=[("x_contact_role", "=", "agente_aduanal")],
        help="Selecciona el contacto existente o crea uno nuevo con rol Agente Aduanal.",
    )
    agente_nombre = fields.Char(string="Nombre del agente")
    agente_rfc = fields.Char(string="RFC del agente")
    patente = fields.Char(string="Patente aduanal", size=4)
    num_autorizacion = fields.Char(string="Num. autorización aduanal")

    # ── Paso 2: VUCEM ────────────────────────────────────────────────────
    vucem_ambiente = fields.Selection(
        [("pruebas", "Pruebas (sandbox)"), ("produccion", "Producción")],
        string="Ambiente VUCEM",
        default="pruebas",
    )
    vucem_cert_file = fields.Binary(string="Certificado (.cer)")
    vucem_cert_filename = fields.Char(string="Nombre del certificado")
    vucem_key_file = fields.Binary(string="Llave privada (.key)")
    vucem_key_filename = fields.Char(string="Nombre de la llave")
    vucem_key_password = fields.Char(string="Contraseña de la llave")

    # ── Paso 3: Catálogos ────────────────────────────────────────────────
    aduana_seccion_ids = fields.Many2many(
        "mx.ped.aduana.seccion",
        string="Aduanas/Secciones activas",
        help="Selecciona las aduanas en las que opera tu agencia.",
    )

    # ── Computed helpers ─────────────────────────────────────────────────
    step_number = fields.Integer(compute="_compute_step_number")
    is_last_step = fields.Boolean(compute="_compute_step_number")

    _STEPS = ["agencia", "vucem", "catalogo", "listo"]

    @api.depends("step")
    def _compute_step_number(self):
        for rec in self:
            idx = rec._STEPS.index(rec.step) if rec.step in rec._STEPS else 0
            rec.step_number = idx + 1
            rec.is_last_step = rec.step == "listo"

    # ── Navegación ───────────────────────────────────────────────────────
    def action_next(self):
        self.ensure_one()
        if self.step == "agencia":
            self._step_agencia_validate()
            self._step_agencia_apply()
            self.step = "vucem"
        elif self.step == "vucem":
            self._step_vucem_apply()
            self.step = "catalogo"
        elif self.step == "catalogo":
            self.step = "listo"
        return self._reopen()

    def action_prev(self):
        self.ensure_one()
        idx = self._STEPS.index(self.step)
        if idx > 0:
            self.step = self._STEPS[idx - 1]
        return self._reopen()

    def action_finish(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Aduanex configurado"),
                "message": _(
                    "La agencia está lista. Ahora crea tu primer expediente desde CRM > Pipeline."
                ),
                "type": "success",
                "sticky": True,
            },
        }

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # ── Lógica de cada paso ──────────────────────────────────────────────
    def _step_agencia_validate(self):
        if not self.agente_id and not (self.agente_nombre and self.agente_rfc and self.patente):
            raise UserError(
                _("Selecciona un agente existente o ingresa nombre, RFC y patente para crear uno nuevo.")
            )

    def _step_agencia_apply(self):
        if self.agente_id:
            vals = {}
            if self.patente:
                vals["x_patente_aduanal"] = self.patente
            if self.num_autorizacion:
                vals["x_num_autorizacion_aduanal"] = self.num_autorizacion
            if vals:
                self.agente_id.write(vals)
        else:
            self.agente_id = self.env["res.partner"].create({
                "name": self.agente_nombre,
                "vat": self.agente_rfc.strip().upper(),
                "x_contact_role": "agente_aduanal",
                "x_patente_aduanal": self.patente or False,
                "x_num_autorizacion_aduanal": self.num_autorizacion or False,
                "is_company": True,
            })

    def _step_vucem_apply(self):
        if not (self.vucem_cert_file and self.vucem_key_file):
            return
        cred_model = self.env.get("mx.ped.credencial.ws")
        if cred_model is None:
            return
        existing = cred_model.search([
            ("agente_aduanal_id", "=", self.agente_id.id),
            ("ambiente", "=", self.vucem_ambiente),
        ], limit=1)
        vals = {
            "agente_aduanal_id": self.agente_id.id,
            "ambiente": self.vucem_ambiente,
            "cert_file": self.vucem_cert_file,
            "cert_filename": self.vucem_cert_filename or "cert.cer",
            "key_file": self.vucem_key_file,
            "key_filename": self.vucem_key_filename or "llave.key",
            "key_password": self.vucem_key_password or False,
        }
        if existing:
            existing.write(vals)
        else:
            cred_model.create(vals)
