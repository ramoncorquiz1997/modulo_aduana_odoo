# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedCredencialWs(models.Model):
    _name = "mx.ped.credencial.ws"
    _description = "Credenciales WS Pedimentos"
    _order = "company_id, ambiente, partner_id, id"

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    ambiente = fields.Selection(
        [("pruebas", "Pruebas"), ("produccion", "Produccion")],
        default="produccion",
        required=True,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Agente aduanal",
        domain="[('x_contact_role','=','agente_aduanal')]",
        ondelete="cascade",
        help="Si se define, aplica solo para ese agente. Si va vacio, funciona como default de la empresa.",
    )
    is_default = fields.Boolean(
        string="Default empresa/ambiente",
        help="Solo una credencial default por empresa y ambiente.",
    )
    ws_username = fields.Char(string="WS Usuario", required=True)
    ws_password = fields.Char(string="WS Password", required=True, groups="base.group_system")

    cert_file = fields.Binary(string="Certificado (.cer)")
    cert_filename = fields.Char(string="Nombre certificado")
    key_file = fields.Binary(string="Llave privada (.key)")
    key_filename = fields.Char(string="Nombre llave")
    key_password = fields.Char(string="Password llave", groups="base.group_system")

    vigencia_desde = fields.Date(string="Vigencia desde")
    vigencia_hasta = fields.Date(string="Vigencia hasta")
    notes = fields.Text(string="Notas")

    @api.constrains("is_default", "partner_id")
    def _check_default_without_partner(self):
        for rec in self:
            if rec.is_default and rec.partner_id:
                raise ValidationError("La credencial default no debe tener agente aduanal asignado.")

    @api.constrains("is_default", "company_id", "ambiente", "active")
    def _check_single_default(self):
        for rec in self.filtered("is_default"):
            dup = self.search_count([
                ("id", "!=", rec.id),
                ("is_default", "=", True),
                ("company_id", "=", rec.company_id.id),
                ("ambiente", "=", rec.ambiente),
                ("active", "=", True),
            ])
            if dup:
                raise ValidationError("Solo puede existir una credencial default activa por empresa y ambiente.")

    @api.constrains("partner_id", "company_id", "ambiente", "active")
    def _check_single_active_per_partner(self):
        for rec in self.filtered(lambda r: r.partner_id and r.active):
            dup = self.search_count([
                ("id", "!=", rec.id),
                ("partner_id", "=", rec.partner_id.id),
                ("company_id", "=", rec.company_id.id),
                ("ambiente", "=", rec.ambiente),
                ("active", "=", True),
            ])
            if dup:
                raise ValidationError("Ya existe otra credencial activa para este agente, empresa y ambiente.")


class ResPartner(models.Model):
    _inherit = "res.partner"

    ws_credencial_ids = fields.One2many(
        "mx.ped.credencial.ws",
        "partner_id",
        string="Credenciales WS",
    )
