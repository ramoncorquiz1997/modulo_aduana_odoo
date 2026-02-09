from odoo import fields, models


class MxPedEvento(models.Model):
    _name = "mx.ped.evento"
    _description = "Pedimento - Evento / Bitácora"
    _order = "fecha desc, id desc"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )

    usuario_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    tipo = fields.Selection(
        [
            ("nota", "Nota"),
            ("consulta_vucem", "Consulta VUCEM"),
            ("validacion", "Validación"),
            ("error", "Error"),
        ],
        default="nota",
        index=True,
    )

    fecha = fields.Datetime(default=fields.Datetime.now, required=True)

    request_xml = fields.Text()
    response_xml = fields.Text()
    detalle = fields.Text()