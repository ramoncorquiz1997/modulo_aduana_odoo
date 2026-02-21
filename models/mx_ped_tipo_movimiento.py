# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedTipoMovimiento(models.Model):
    _name = "mx.ped.tipo.movimiento"
    _description = "Catalogo de tipos de movimiento"
    _order = "code, id"
    _rec_name = "display_name"

    code = fields.Char(string="Clave", required=True, size=2)
    name = fields.Char(string="Descripcion", required=True)
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Notas")
    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
    )

    _sql_constraints = [
        ("mx_ped_tipo_movimiento_code_uniq", "unique(code)", "La clave del tipo de movimiento debe ser unica."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code") is not None:
                vals["code"] = str(vals["code"]).strip()
                if vals["code"].isdigit():
                    vals["code"] = str(int(vals["code"]))
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("code") is not None:
            vals["code"] = str(vals["code"]).strip()
            if vals["code"].isdigit():
                vals["code"] = str(int(vals["code"]))
        return super().write(vals)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code or ''} - {rec.name or ''}".strip(" -")

    @api.constrains("code")
    def _check_code(self):
        for rec in self:
            code = (rec.code or "").strip()
            if not code.isdigit():
                raise ValidationError(_("La clave debe ser numerica (1, 2, 3, ...)."))
            if int(code) < 1 or int(code) > 9:
                raise ValidationError(_("La clave debe estar entre 1 y 9."))
