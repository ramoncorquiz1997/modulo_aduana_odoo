from odoo import fields, models, _
from odoo.exceptions import ValidationError


class MxPedPartidaFacturaWizard(models.TransientModel):
    _name = "mx.ped.partida.factura.wizard"
    _description = "Asignacion masiva de factura a partidas"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, readonly=True)
    partida_ids = fields.Many2many(
        "mx.ped.partida",
        string="Partidas",
        required=True,
    )
    factura_documento_id = fields.Many2one(
        "mx.ped.documento",
        string="Factura / CFDI",
        required=True,
        domain="[('operacion_id', '=', operacion_id)]",
    )

    def action_apply(self):
        self.ensure_one()
        if any(p.operacion_id != self.operacion_id for p in self.partida_ids):
            raise ValidationError(_("Todas las partidas deben pertenecer a la misma operacion."))
        self.partida_ids.write({"factura_documento_id": self.factura_documento_id.id})
        return {"type": "ir.actions.act_window_close"}
