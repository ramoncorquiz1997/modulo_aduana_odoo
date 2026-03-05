# -*- coding: utf-8 -*-
from odoo import fields, models


class AduanaCatalogoTipoOperacion(models.Model):
    _name = "aduana.catalogo.tipo_operacion"
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
    _inherit = ["mail.thread", "mail.activity.mixin"]
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


class AduanaCatalogoInstitucionFinanciera(models.Model):
    _name = "aduana.catalogo.institucion_financiera"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Aduana - Catalogo Institucion Financiera"
    _order = "code"

    code = fields.Char(required=True, index=True, size=2)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "aduana_institucion_financiera_code_uniq",
            "unique(code)",
            "La clave de institucion financiera debe ser unica.",
        ),
    ]


class AduanaCatalogoTipoGarantia(models.Model):
    _name = "aduana.catalogo.tipo_garantia"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Aduana - Catalogo Tipo de Garantia"
    _order = "code"

    code = fields.Char(required=True, index=True, size=2)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "aduana_tipo_garantia_code_uniq",
            "unique(code)",
            "La clave de tipo de garantia debe ser unica.",
        ),
    ]


class AduanaCatalogoMedioTransporte(models.Model):
    _name = "aduana.catalogo.medio_transporte"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Aduana - Catalogo Medio de Transporte"
    _order = "code"

    code = fields.Char(required=True, index=True, size=2)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "aduana_medio_transporte_code_uniq",
            "unique(code)",
            "La clave de medio de transporte debe ser unica.",
        ),
    ]


class AduanaCatalogoPais(models.Model):
    _name = "aduana.catalogo.pais"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Aduana - Catalogo Paises"
    _order = "saai_fiii, saai_m3, id"

    saai_fiii = fields.Char(string="Clave SAAI FIII", required=True, index=True, size=3)
    saai_m3 = fields.Char(string="Clave SAAI M3", required=True, index=True, size=3)
    name = fields.Char(string="Pais", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "aduana_catalogo_pais_saai_fiii_uniq",
            "unique(saai_fiii)",
            "La Clave SAAI FIII ya existe.",
        ),
        (
            "aduana_catalogo_pais_saai_m3_uniq",
            "unique(saai_m3)",
            "La Clave SAAI M3 ya existe.",
        ),
    ]
