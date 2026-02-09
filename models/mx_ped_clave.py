# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class MxPedClave(models.Model):
    _name = "mx.ped.clave"
    _description = "Catálogo Claves de Pedimento (Anexo 22)"
    _rec_name = "display_name"
    _order = "code"

    code = fields.Char(string="Clave", required=True, index=True)   # A1, A4, V1...
    name = fields.Char(string="Descripción", required=True)

    tipo_operacion = fields.Selection(
        selection=[
            ("importacion", "Importación"),
            ("exportacion", "Exportación"),
            ("ambas", "Ambas"),
        ],
        string="Tipo de operación",
        default="ambas",
        required=True,
    )

    regimen = fields.Selection(
        selection=[
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Depósito fiscal"),
            ("transito", "Tránsito"),
            ("cualquiera", "Cualquiera"),
        ],
        string="Régimen",
        default="cualquiera",
        required=True,
    )

    requiere_immex = fields.Boolean(string="Requiere IMMEX", default=False)
    active = fields.Boolean(default=True)

    vigente_desde = fields.Date(string="Vigente desde")
    vigente_hasta = fields.Date(string="Vigente hasta")

    note = fields.Text(string="Notas")

    display_name = fields.Char(compute="_compute_display_name", store=False)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} - {rec.name}"
