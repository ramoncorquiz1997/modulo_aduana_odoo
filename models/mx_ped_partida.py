from odoo import api, fields, models


class MxPedPartida(models.Model):
    _name = "mx.ped.partida"
    _description = "Pedimento - Partida"
    _order = "numero_partida asc, id asc"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )

    numero_partida = fields.Integer()
    fraccion_id = fields.Many2one("mx.ped.fraccion", string="Fraccion arancelaria")
    fraccion_arancelaria = fields.Char(size=20, index=True)
    nico = fields.Char(size=2)
    descripcion = fields.Text()

    unidad_tarifa = fields.Char(size=10)
    cantidad_tarifa = fields.Float(digits=(16, 5))

    unidad_comercial = fields.Char(size=10)
    cantidad_comercial = fields.Float(digits=(16, 5))

    precio_unitario = fields.Float(digits=(16, 6))
    valor_comercial = fields.Monetary(currency_field="currency_id")
    valor_aduana = fields.Monetary(currency_field="currency_id")

    currency_id = fields.Many2one(
        related="operacion_id.currency_id", store=True, readonly=True
    )

    pais_origen_id = fields.Many2one("res.country", string="País origen")
    pais_vendedor_id = fields.Many2one("res.country", string="País vendedor")

    observaciones = fields.Text()

    @api.onchange("fraccion_id")
    def _onchange_fraccion_id(self):
        for rec in self:
            fraccion = rec.fraccion_id
            if not fraccion:
                continue
            rec.fraccion_arancelaria = fraccion.code
            rec.nico = fraccion.nico
            if not rec.descripcion:
                rec.descripcion = fraccion.name
            if fraccion.um_id:
                rec.unidad_tarifa = fraccion.um_id.code
