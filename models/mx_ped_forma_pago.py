# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxFormaPago(models.Model):
    _name = "mx.forma.pago"
    _description = "Catalogo de Formas de Pago (Apendice 13)"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True)
    scope = fields.Selection(
        [
            ("all", "Todos (510/557/514)"),
            ("510", "Cabecera 510"),
            ("557", "Partida 557"),
            ("514", "Virtual 514"),
        ],
        string="Alcance",
        required=True,
        default="all",
    )
    is_virtual_allowed = fields.Boolean(
        string="Permite virtual",
        default=True,
        help="Indica si aplica para operaciones/documentos virtuales (registro 514).",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ("mx_forma_pago_code_uniq", "unique(code)", "La clave de forma de pago debe ser unica."),
    ]


class MxPedContribucionGlobal(models.Model):
    _name = "mx.ped.contribucion.global"
    _description = "Pedimento - Contribucion global (registro 510)"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    tipo_contribucion = fields.Char(required=True)
    tasa = fields.Float()
    base = fields.Monetary(currency_field="currency_id")
    importe = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="operacion_id.currency_id", store=True, readonly=True)
    forma_pago_id = fields.Many2one(
        "mx.forma.pago",
        string="Forma de pago",
        domain="[('active','=',True), '|', ('scope','=','all'), ('scope','=','510')]",
        ondelete="restrict",
    )
    forma_pago_code = fields.Char(
        string="Forma de pago (clave)",
        related="forma_pago_id.code",
        store=True,
        readonly=True,
    )


class MxPedPartidaContribucion(models.Model):
    _name = "mx.ped.partida.contribucion"
    _description = "Pedimento - Contribucion por partida (registro 557)"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    partida_id = fields.Many2one("mx.ped.partida", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    tipo_contribucion = fields.Char(required=True)
    tasa = fields.Float()
    base = fields.Monetary(currency_field="currency_id")
    importe = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="operacion_id.currency_id", store=True, readonly=True)
    forma_pago_id = fields.Many2one(
        "mx.forma.pago",
        string="Forma de pago",
        domain="[('active','=',True), '|', ('scope','=','all'), ('scope','=','557')]",
        ondelete="restrict",
    )
    forma_pago_code = fields.Char(
        string="Forma de pago (clave)",
        related="forma_pago_id.code",
        store=True,
        readonly=True,
    )

    @api.onchange("partida_id")
    def _onchange_partida_id_sync_operacion(self):
        for rec in self:
            if rec.partida_id:
                rec.operacion_id = rec.partida_id.operacion_id

    @api.constrains("operacion_id", "partida_id")
    def _check_operacion_partida_match(self):
        for rec in self:
            if rec.partida_id and rec.operacion_id and rec.partida_id.operacion_id != rec.operacion_id:
                raise ValidationError("La partida seleccionada no corresponde a la operacion.")
