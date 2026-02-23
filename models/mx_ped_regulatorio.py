# -*- coding: utf-8 -*-
from odoo import fields, models


class MxNom(models.Model):
    _name = "mx.nom"
    _description = "Catalogo NOM"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    authority = fields.Selection(
        [
            ("SE", "SE"),
            ("SCFI", "SCFI"),
            ("SSA", "SSA"),
            ("SENER", "SENER"),
            ("COFEPRIS", "COFEPRIS"),
            ("SAT", "SAT"),
            ("OTRO", "Otro"),
        ],
        string="Autoridad",
        default="SE",
    )
    requires_labeling = fields.Boolean(string="Requiere etiquetado")
    doc_required = fields.Selection(
        [
            ("dictamen", "Dictamen"),
            ("certificado", "Certificado"),
            ("ninguno", "Ninguno"),
            ("otro", "Otro"),
        ],
        string="Documento requerido",
        default="ninguno",
    )
    notes = fields.Text()
    active = fields.Boolean(default=True)
    valid_from = fields.Date()
    valid_to = fields.Date()
    reference_url = fields.Char(string="URL referencia")

    _sql_constraints = [
        ("mx_nom_code_uniq", "unique(code)", "La clave NOM debe ser unica."),
    ]


class MxRrna(models.Model):
    _name = "mx.rrna"
    _description = "Catalogo RRNA"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    authority = fields.Selection(
        [
            ("SE", "SE"),
            ("SAT", "SAT"),
            ("COFEPRIS", "COFEPRIS"),
            ("SENER", "SENER"),
            ("SADER", "SADER"),
            ("OTRO", "Otro"),
        ],
        string="Autoridad",
        default="SE",
    )
    type = fields.Selection(
        [
            ("nom", "NOM"),
            ("permiso", "Permiso"),
            ("cupo", "Cupo"),
            ("aviso", "Aviso"),
            ("otro", "Otro"),
        ],
        string="Tipo",
        default="otro",
    )
    notes = fields.Text()
    active = fields.Boolean(default=True)
    valid_from = fields.Date()
    valid_to = fields.Date()
    reference_url = fields.Char(string="URL referencia")

    _sql_constraints = [
        ("mx_rrna_code_uniq", "unique(code)", "La clave RRNA debe ser unica."),
    ]


class MxPermiso(models.Model):
    _name = "mx.permiso"
    _description = "Catalogo Permisos"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    authority = fields.Selection(
        [
            ("COFEPRIS", "COFEPRIS"),
            ("SENER", "SENER"),
            ("SE", "SE"),
            ("SAT", "SAT"),
            ("SADER", "SADER"),
            ("OTRO", "Otro"),
        ],
        string="Autoridad",
        default="SE",
    )
    document_type = fields.Selection(
        [
            ("pdf", "PDF"),
            ("oficio", "Oficio"),
            ("permiso", "Permiso"),
            ("aviso", "Aviso"),
        ],
        string="Tipo documento",
        default="permiso",
    )
    requires_expiration = fields.Boolean(string="Requiere vencimiento")
    notes = fields.Text()
    active = fields.Boolean(default=True)
    valid_from = fields.Date()
    valid_to = fields.Date()
    reference_url = fields.Char(string="URL referencia")

    _sql_constraints = [
        ("mx_permiso_code_uniq", "unique(code)", "La clave Permiso debe ser unica."),
    ]


class MxNico(models.Model):
    _name = "mx.nico"
    _description = "Catalogo NICO"
    _order = "fraccion_id, code"

    code = fields.Char(required=True, size=2)
    name = fields.Char(required=True)
    fraccion_id = fields.Many2one("mx.ped.fraccion", required=True, ondelete="cascade", index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("mx_nico_fraccion_code_uniq", "unique(fraccion_id, code)", "NICO duplicado para la fraccion."),
    ]
