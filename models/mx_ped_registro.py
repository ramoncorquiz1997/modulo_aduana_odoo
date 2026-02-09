# -*- coding: utf-8 -*-
from odoo import fields, models


class MxPedRegistro(models.Model):
    _name = "mx.ped.registro"
    _description = "Pedimento - Registro"
    _order = "codigo asc, secuencia asc, id asc"

    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Operación",
        required=True,
        ondelete="cascade",
        index=True,
    )
    codigo = fields.Char(string="Código", required=True)
    secuencia = fields.Integer(default=1)
    valores = fields.Json(string="Valores")
