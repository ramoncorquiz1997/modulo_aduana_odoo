# -*- coding: utf-8 -*-
from odoo import fields, models


class AduanaCatalogoTipoOperacion(models.Model):
    _name = "aduana.catalogo.tipo_operacion"
    _description = "Aduana - Catalogo Tipo de Operacion"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("aduana_tipo_operacion_code_uniq", "unique(code)", "El codigo de tipo de operacion debe ser unico."),
    ]


class AduanaCatalogoRegimen(models.Model):
    _name = "aduana.catalogo.regimen"
    _description = "Aduana - Catalogo Regimen"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("aduana_regimen_code_uniq", "unique(code)", "El codigo de regimen debe ser unico."),
    ]


class AduanaCatalogoAduana(models.Model):
    _name = "aduana.catalogo.aduana"
    _description = "Aduana - Catalogo Aduana/Seccion"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("aduana_aduana_code_uniq", "unique(code)", "La clave de aduana debe ser unica."),
    ]


class AduanaCatalogoClavePedimento(models.Model):
    _name = "aduana.catalogo.clave_pedimento"
    _description = "Aduana - Catalogo Clave Pedimento"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    tipo_operacion_id = fields.Many2one("aduana.catalogo.tipo_operacion", ondelete="set null")
    regimen_id = fields.Many2one("aduana.catalogo.regimen", ondelete="set null")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("aduana_clave_pedimento_code_uniq", "unique(code)", "La clave de pedimento debe ser unica."),
    ]
