# -*- coding: utf-8 -*-
from odoo import fields, models


class AduanaLayoutRegistroTipo(models.Model):
    _name = "aduana.layout_registro_tipo"
    _description = "Aduana - Layout Tipo de Registro"
    _order = "orden, codigo"

    codigo = fields.Char(required=True, index=True)
    nombre = fields.Char(required=True)
    nivel = fields.Selection(
        [
            ("archivo", "Archivo"),
            ("cabecera", "Cabecera"),
            ("detalle", "Detalle"),
        ],
        required=True,
        default="cabecera",
    )
    orden = fields.Integer(default=10)
    activo = fields.Boolean(default=True)
    campo_ids = fields.One2many("aduana.layout_registro_campo", "registro_tipo_id")

    _sql_constraints = [
        ("aduana_layout_registro_tipo_codigo_uniq", "unique(codigo)", "El codigo de registro debe ser unico."),
    ]


class AduanaLayoutRegistroCampo(models.Model):
    _name = "aduana.layout_registro_campo"
    _description = "Aduana - Layout Campo por Registro"
    _order = "registro_tipo_id, secuencia"

    registro_tipo_id = fields.Many2one("aduana.layout_registro_tipo", required=True, ondelete="cascade", index=True)
    secuencia = fields.Integer(required=True)
    nombre_tecnico = fields.Char(required=True)
    etiqueta = fields.Char(required=True)
    tipo_dato = fields.Selection(
        [
            ("char", "Char"),
            ("int", "Int"),
            ("float", "Float"),
            ("date", "Date"),
            ("money", "Money"),
        ],
        required=True,
        default="char",
    )
    longitud = fields.Integer()
    requerido = fields.Boolean(default=False)
    default = fields.Char()
    origen_modelo = fields.Char()
    origen_campo = fields.Char()
    nota = fields.Text()

    _sql_constraints = [
        (
            "aduana_layout_registro_campo_seq_uniq",
            "unique(registro_tipo_id, secuencia)",
            "La secuencia debe ser unica por tipo de registro.",
        ),
        (
            "aduana_layout_registro_campo_nombre_uniq",
            "unique(registro_tipo_id, nombre_tecnico)",
            "El nombre tecnico debe ser unico por tipo de registro.",
        ),
    ]
