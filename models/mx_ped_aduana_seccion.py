# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MxPedAduanaSeccion(models.Model):
    _name = "mx.ped.aduana.seccion"
    _description = "Catalogo de Aduana-Seccion"
    _rec_name = "display_name"
    _order = "aduana, seccion"

    aduana = fields.Char(string="Aduana", required=True, size=2, index=True)
    seccion = fields.Char(string="Seccion", required=True, size=1, index=True)
    denominacion = fields.Char(string="Denominacion", required=True)
    active = fields.Boolean(default=True)

    code = fields.Char(string="Clave", compute="_compute_code", store=True)
    display_name = fields.Char(compute="_compute_display_name", store=False)

    _sql_constraints = [
        (
            "mx_ped_aduana_seccion_code_uniq",
            "unique(aduana, seccion)",
            "La combinacion Aduana-Seccion debe ser unica.",
        ),
    ]

    @api.depends("aduana", "seccion")
    def _compute_code(self):
        for rec in self:
            rec.aduana = (rec.aduana or "").strip()
            rec.seccion = (rec.seccion or "").strip()
            rec.code = f"{rec.aduana}{rec.seccion}" if rec.aduana and rec.seccion else False

    @api.depends("aduana", "seccion", "denominacion")
    def _compute_display_name(self):
        for rec in self:
            if rec.aduana and rec.seccion:
                rec.display_name = f"{rec.aduana}-{rec.seccion} {rec.denominacion or ''}".strip()
            else:
                rec.display_name = rec.denominacion or ""
