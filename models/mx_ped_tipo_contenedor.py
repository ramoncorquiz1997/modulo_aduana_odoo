# -*- coding: utf-8 -*-
from odoo import fields, models


class MxPedTipoContenedor(models.Model):
    _name = "mx.ped.tipo.contenedor"
    _description = "Catalogo Tipo de Contenedores y Vehiculos de Autotransporte"
    _order = "code"

    code = fields.Char(string="Clave", required=True, index=True)
    name = fields.Char(string="Descripcion", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("mx_ped_tipo_contenedor_code_uniq", "unique(code)", "La clave debe ser unica."),
    ]
