# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedOperacionCuentaAduanera(models.Model):
    _name = "mx.ped.operacion.cuenta.aduanera"
    _description = "Operacion - Cuenta aduanera / garantia"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    institucion_financiera_id = fields.Many2one(
        "aduana.catalogo.institucion_financiera",
        string="Institucion emisora",
        ondelete="restrict",
    )
    institucion_emisora = fields.Char(
        string="Clave institucion emisora",
        related="institucion_financiera_id.code",
        store=True,
        readonly=True,
    )
    numero_contrato = fields.Char(string="Numero contrato", size=17)
    folio_constancia = fields.Char(string="Folio constancia", size=17)
    fecha_constancia = fields.Date(string="Fecha constancia")
    tipo_cuenta = fields.Char(string="Tipo cuenta", size=2, default="0")
    tipo_garantia_id = fields.Many2one(
        "aduana.catalogo.tipo_garantia",
        string="Tipo garantia",
        ondelete="restrict",
    )
    tipo_garantia = fields.Char(
        string="Clave tipo garantia",
        related="tipo_garantia_id.code",
        store=True,
        readonly=True,
    )
    valor_unitario_titulo = fields.Float(string="Valor unitario titulo", digits=(16, 4))
    total_garantia = fields.Float(string="Total garantia", digits=(16, 2))
    cantidad_um = fields.Float(string="Cantidad UM", digits=(16, 4))
    titulos_asignados = fields.Float(string="Titulos asignados", digits=(16, 2))
    notes = fields.Char(string="Notas")

    @api.constrains("tipo_cuenta")
    def _check_codes(self):
        for rec in self:
            for value, label in (
                (rec.tipo_cuenta, "Tipo cuenta"),
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res
