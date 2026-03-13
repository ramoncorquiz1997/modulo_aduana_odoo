from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedConsolidadoRemesaPartida(models.Model):
    _name = "mx.ped.consolidado.remesa.partida"
    _description = "Pedimento consolidado - Asignacion de partida a remesa"
    _order = "remesa_id, sequence, id"

    remesa_id = fields.Many2one(
        "mx.ped.consolidado.remesa",
        required=True,
        ondelete="cascade",
        index=True,
    )
    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Operacion",
        related="remesa_id.operacion_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string="Secuencia", default=10)
    partida_id = fields.Many2one(
        "mx.ped.partida",
        string="Partida",
        required=True,
        ondelete="cascade",
        domain="[('operacion_id', '=', operacion_id)]",
    )
    quantity = fields.Float(string="Cantidad asignada", digits=(16, 6), required=True, default=1.0)
    value_usd = fields.Float(string="Valor USD asignado", digits=(16, 2), required=True, default=0.0)
    notes = fields.Char(string="Notas")

    _sql_constraints = [
        (
            "mx_ped_consolidado_remesa_partida_unique",
            "unique(remesa_id, partida_id)",
            "La partida ya esta asignada a esta remesa.",
        ),
    ]

    @api.onchange("partida_id")
    def _onchange_partida_id(self):
        for rec in self:
            if rec.partida_id:
                if not rec.quantity:
                    rec.quantity = rec.partida_id.quantity
                if not rec.value_usd:
                    rec.value_usd = rec.partida_id.value_usd

    @api.constrains("partida_id", "remesa_id")
    def _check_partida_operacion(self):
        for rec in self:
            if rec.partida_id.operacion_id != rec.remesa_id.operacion_id:
                raise ValidationError(_("La partida asignada debe pertenecer a la misma operacion que la remesa."))

    @api.constrains("quantity", "value_usd")
    def _check_positive_values(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("La cantidad asignada a la remesa debe ser mayor a cero."))
            if rec.value_usd <= 0:
                raise ValidationError(_("El valor USD asignado a la remesa debe ser mayor a cero."))

    @api.constrains("partida_id", "quantity", "value_usd")
    def _check_partida_totals(self):
        for rec in self:
            partida = rec.partida_id
            if not partida:
                continue
            domain = [("partida_id", "=", partida.id)]
            siblings = self.search(domain)
            total_qty = sum(siblings.mapped("quantity"))
            total_value = sum(siblings.mapped("value_usd"))
            if total_qty > (partida.quantity or 0.0) + 0.000001:
                raise ValidationError(
                    _("La suma de cantidades asignadas en remesas excede la cantidad de la partida %s.")
                    % (partida.numero_partida or partida.id,)
                )
            if total_value > (partida.value_usd or 0.0) + 0.01:
                raise ValidationError(
                    _("La suma de valor USD asignado en remesas excede el valor USD de la partida %s.")
                    % (partida.numero_partida or partida.id,)
                )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped("remesa_id")._autofill_documento_fuente_from_factura()
        return records

    def write(self, vals):
        res = super().write(vals)
        self.mapped("remesa_id")._autofill_documento_fuente_from_factura()
        return res

    def unlink(self):
        remesas = self.mapped("remesa_id")
        res = super().unlink()
        remesas._autofill_documento_fuente_from_factura()
        return res
