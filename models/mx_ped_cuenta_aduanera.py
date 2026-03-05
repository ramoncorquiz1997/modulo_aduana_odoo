# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedOperacionCuentaAduanera(models.Model):
    _name = "mx.ped.operacion.cuenta.aduanera"
    _description = "Operacion - Cuenta aduanera / garantia (508)"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    institucion_emisora = fields.Char(string="Institucion emisora", size=2)
    numero_contrato = fields.Char(string="Numero contrato", size=17)
    folio_constancia = fields.Char(string="Folio constancia", size=17)
    fecha_constancia = fields.Date(string="Fecha constancia")
    tipo_cuenta = fields.Char(string="Tipo cuenta", size=2, default="0")
    tipo_garantia = fields.Char(string="Tipo garantia", size=2)
    valor_unitario_titulo = fields.Float(string="Valor unitario titulo", digits=(16, 4))
    total_garantia = fields.Float(string="Total garantia", digits=(16, 2))
    cantidad_um = fields.Float(string="Cantidad UM", digits=(16, 4))
    titulos_asignados = fields.Float(string="Titulos asignados", digits=(16, 2))
    notes = fields.Char(string="Notas")

    @api.constrains("institucion_emisora", "tipo_cuenta", "tipo_garantia")
    def _check_codes(self):
        for rec in self:
            for value, label in (
                (rec.institucion_emisora, "Institucion emisora"),
                (rec.tipo_cuenta, "Tipo cuenta"),
                (rec.tipo_garantia, "Tipo garantia"),
            ):
                txt = (value or "").strip()
                if txt and not txt.isdigit():
                    raise ValidationError("%s debe ser numerico." % label)

    @api.constrains("numero_contrato")
    def _check_numero_contrato(self):
        for rec in self:
            txt = (rec.numero_contrato or "").strip()
            if txt and not txt.isdigit():
                raise ValidationError("Numero contrato debe ser numerico.")

