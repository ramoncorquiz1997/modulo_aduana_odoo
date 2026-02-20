# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedNumeroControl(models.Model):
    _name = "mx.ped.numero.control"
    _description = "Control de consecutivo de pedimento"
    _order = "year_two desc, aduana_clave, patente"

    year_two = fields.Char(string="Ano (2 digitos)", required=True, size=2)
    aduana_clave = fields.Char(string="Aduana (2 digitos)", required=True, size=2)
    patente = fields.Char(string="Patente (4 digitos)", required=True, size=4)
    ultimo_consecutivo = fields.Integer(string="Consecutivo actual", default=0, required=True)
    active = fields.Boolean(default=True)
    log_ids = fields.One2many(
        "mx.ped.numero.control.log",
        "control_id",
        string="Bitacora de cambios",
        readonly=True,
    )

    display_name_key = fields.Char(
        string="Clave",
        compute="_compute_display_name_key",
        store=False,
    )

    _sql_constraints = [
        (
            "mx_ped_numero_control_unique",
            "unique(year_two, aduana_clave, patente)",
            "Ya existe un control para esa combinacion ano/aduana/patente.",
        ),
    ]

    @api.depends("year_two", "aduana_clave", "patente")
    def _compute_display_name_key(self):
        for rec in self:
            rec.display_name_key = f"{rec.year_two or '00'}-{rec.aduana_clave or '00'}-{rec.patente or '0000'}"

    def name_get(self):
        return [(rec.id, rec.display_name_key or str(rec.id)) for rec in self]

    @api.constrains("year_two", "aduana_clave", "patente", "ultimo_consecutivo")
    def _check_values(self):
        for rec in self:
            if not (rec.year_two or "").isdigit() or len(rec.year_two or "") != 2:
                raise ValidationError(_("Ano debe tener exactamente 2 digitos."))
            if not (rec.aduana_clave or "").isdigit() or len(rec.aduana_clave or "") != 2:
                raise ValidationError(_("Aduana debe tener exactamente 2 digitos."))
            if not (rec.patente or "").isdigit() or len(rec.patente or "") != 4:
                raise ValidationError(_("Patente debe tener exactamente 4 digitos."))
            if rec.ultimo_consecutivo < 0 or rec.ultimo_consecutivo > 999999:
                raise ValidationError(_("Consecutivo debe estar entre 0 y 999999."))

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            rec._create_log(old_value=0, new_value=rec.ultimo_consecutivo, note=_("Creacion de control"))
        return recs

    def write(self, vals):
        old_by_id = {}
        if "ultimo_consecutivo" in vals:
            old_by_id = {rec.id: rec.ultimo_consecutivo for rec in self}
        res = super().write(vals)
        if "ultimo_consecutivo" in vals:
            for rec in self:
                rec._create_log(old_value=old_by_id.get(rec.id, 0), new_value=rec.ultimo_consecutivo)
        return res

    def _create_log(self, old_value, new_value, note=False):
        changed_by_id = self.env.context.get("real_user_id") or self.env.user.id
        self.env["mx.ped.numero.control.log"].sudo().create({
            "control_id": self.id,
            "changed_by_id": changed_by_id,
            "old_value": old_value,
            "new_value": new_value,
            "note": note or "",
        })


class MxPedNumeroControlLog(models.Model):
    _name = "mx.ped.numero.control.log"
    _description = "Bitacora de cambios de consecutivo de pedimento"
    _order = "create_date desc, id desc"

    control_id = fields.Many2one(
        "mx.ped.numero.control",
        required=True,
        ondelete="cascade",
        index=True,
    )
    changed_by_id = fields.Many2one("res.users", string="Usuario", required=True, readonly=True)
    old_value = fields.Integer(string="Valor anterior", readonly=True)
    new_value = fields.Integer(string="Valor nuevo", readonly=True)
    note = fields.Char(string="Nota", readonly=True)
