# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedEstructuraRegla(models.Model):
    _name = "mx.ped.estructura.regla"
    _description = "Regla de estructura por tipo de movimiento"
    _order = "priority desc, id desc"

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(string="Prioridad", default=10)

    tipo_movimiento = fields.Selection(
        [
            ("1", "1 - Pedimento nuevo"),
            ("2", "2 - Eliminacion"),
            ("3", "3 - Desistimiento"),
            ("5", "5 - Informe Industria Automotriz"),
            ("6", "6 - Pedimento complementario"),
            ("7", "7 - Despacho anticipado"),
            ("8", "8 - Confirmacion de pago"),
            ("9", "9 - Global complementario"),
        ],
        string="Tipo de movimiento",
        required=True,
    )
    clave_pedimento_id = fields.Many2one("mx.ped.clave", string="Clave de pedimento (opcional)")
    tipo_operacion = fields.Selection(
        [("importacion", "Importacion"), ("exportacion", "Exportacion"), ("ambas", "Ambas")],
        string="Tipo de operacion",
        default="ambas",
    )
    regimen = fields.Selection(
        [
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Deposito fiscal"),
            ("transito", "Transito"),
            ("cualquiera", "Cualquiera"),
        ],
        string="Regimen",
        default="cualquiera",
    )
    line_ids = fields.One2many(
        "mx.ped.estructura.regla.line",
        "regla_id",
        string="Registros requeridos",
        copy=True,
    )


class MxPedEstructuraReglaLine(models.Model):
    _name = "mx.ped.estructura.regla.line"
    _description = "Regla de estructura - lineas"
    _order = "sequence, id"

    regla_id = fields.Many2one(
        "mx.ped.estructura.regla",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    registro_tipo_id = fields.Many2one(
        "mx.ped.layout.registro",
        string="Registro (catalogo layout)",
        required=True,
        ondelete="restrict",
        help="Selecciona el registro desde tu catalogo de Registros (Layout).",
    )
    registro_codigo = fields.Char(string="Codigo registro", readonly=True, size=3)
    required = fields.Boolean(string="Obligatorio", default=True)
    min_occurs = fields.Integer(string="Min ocurrencias", default=1)
    max_occurs = fields.Integer(
        string="Max ocurrencias",
        default=1,
        help="Usa 0 para ilimitado.",
    )

    @api.onchange("registro_tipo_id")
    def _onchange_registro_tipo_id(self):
        for rec in self:
            if rec.registro_tipo_id and rec.registro_tipo_id.codigo:
                rec.registro_codigo = rec.registro_tipo_id.codigo

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            registro_tipo_id = vals.get("registro_tipo_id")
            if registro_tipo_id and not vals.get("registro_codigo"):
                tipo = self.env["mx.ped.layout.registro"].browse(registro_tipo_id)
                vals["registro_codigo"] = tipo.codigo or False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("registro_tipo_id"):
            tipo = self.env["mx.ped.layout.registro"].browse(vals["registro_tipo_id"])
            vals["registro_codigo"] = tipo.codigo or False
        return super().write(vals)

    @api.constrains("registro_tipo_id", "registro_codigo", "min_occurs", "max_occurs")
    def _check_line(self):
        for rec in self:
            if rec.registro_tipo_id and rec.registro_tipo_id.codigo:
                rec.registro_codigo = rec.registro_tipo_id.codigo
            if not rec.registro_codigo:
                raise ValidationError(_("Debes seleccionar un registro del catalogo."))
            if not (rec.registro_codigo or "").isdigit():
                raise ValidationError(_("El codigo de registro debe ser numerico (ej. 500, 506)."))
            if len(rec.registro_codigo) != 3:
                raise ValidationError(_("El codigo de registro debe tener 3 digitos."))
            if rec.min_occurs < 0:
                raise ValidationError(_("Min ocurrencias no puede ser negativo."))
            if rec.max_occurs < 0:
                raise ValidationError(_("Max ocurrencias no puede ser negativo."))
            if rec.max_occurs and rec.max_occurs < rec.min_occurs:
                raise ValidationError(_("Max ocurrencias no puede ser menor que Min ocurrencias."))
