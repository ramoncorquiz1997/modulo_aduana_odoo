from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    fraccion_arancelaria = fields.Char(string="Fraccion (snapshot)", size=20, index=True)
    nico_id = fields.Many2one(
        "mx.nico",
        string="NICO",
        domain="[('fraccion_id', '=', fraccion_id)]",
    )
    nico = fields.Char(string="NICO (snapshot)", size=2)
    descripcion = fields.Text()
    quantity = fields.Float(string="Cantidad", digits=(16, 6), default=1.0)
    uom_id = fields.Many2one("mx.ped.um", string="Unidad de medida")
    packages_line = fields.Integer(string="Bultos", default=0)
    gross_weight_line = fields.Float(string="Peso bruto", digits=(16, 3))
    net_weight_line = fields.Float(string="Peso neto", digits=(16, 3))
    value_usd = fields.Float(string="Valor USD", digits=(16, 2))
    value_mxn = fields.Float(
        string="Valor MXN",
        digits=(16, 2),
        compute="_compute_value_mxn",
        store=True,
    )

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

    pais_origen_id = fields.Many2one("res.country", string="Pais origen")
    pais_vendedor_id = fields.Many2one("res.country", string="Pais vendedor")

    observaciones = fields.Text()
    nom_ids = fields.Many2many(
        "mx.nom",
        "mx_ped_partida_nom_rel",
        "partida_id",
        "nom_id",
        string="NOM",
    )
    permiso_ids = fields.Many2many(
        "mx.permiso",
        "mx_ped_partida_permiso_rel",
        "partida_id",
        "permiso_id",
        string="Permisos",
    )
    rrna_ids = fields.Many2many(
        "mx.rrna",
        "mx_ped_partida_rrna_rel",
        "partida_id",
        "rrna_id",
        string="RRNA",
    )
    labeling_required = fields.Boolean(
        string="Requiere etiquetado",
        compute="_compute_labeling_required",
        store=True,
    )
    nom_compliance_status = fields.Selection(
        [
            ("pendiente", "Pendiente"),
            ("cumple", "Cumple"),
            ("no_aplica", "No aplica"),
        ],
        string="Cumplimiento NOM",
        default="pendiente",
    )
    docs_reference = fields.Char(string="Referencia documentos")
    notes_regulatorias = fields.Text(string="Notas regulatorias")
    iva_estimado = fields.Monetary(
        string="IVA estimado",
        currency_field="currency_id",
        compute="_compute_impuestos_estimados",
        store=True,
        readonly=True,
    )
    igi_estimado = fields.Monetary(
        string="IGI estimado",
        currency_field="currency_id",
        compute="_compute_impuestos_estimados",
        store=True,
        readonly=True,
    )
    dta_estimado = fields.Monetary(
        string="DTA estimado",
        currency_field="currency_id",
        compute="_compute_impuestos_estimados",
        store=True,
        readonly=True,
    )
    prv_estimado = fields.Monetary(
        string="PRV estimado",
        currency_field="currency_id",
        compute="_compute_impuestos_estimados",
        store=True,
        readonly=True,
    )

    @api.depends("nom_ids", "nom_ids.requires_labeling", "fraccion_id.requires_labeling_default")
    def _compute_labeling_required(self):
        for rec in self:
            rec.labeling_required = bool(
                rec.fraccion_id.requires_labeling_default
                or any(rec.nom_ids.mapped("requires_labeling"))
            )

    @api.depends("value_usd", "operacion_id.lead_id.x_tipo_cambio")
    def _compute_value_mxn(self):
        for rec in self:
            tc = rec.operacion_id.lead_id.x_tipo_cambio or 0.0
            rec.value_mxn = (rec.value_usd or 0.0) * tc

    @api.depends(
        "fraccion_id",
        "fraccion_id.tasa_ids",
        "operacion_id.tipo_operacion",
        "value_mxn",
    )
    def _compute_impuestos_estimados(self):
        icp = self.env["ir.config_parameter"].sudo()
        dta_rate = float(icp.get_param("mx_ped.dta_rate", "0.0") or 0.0)
        prv_rate = float(icp.get_param("mx_ped.prv_rate", "0.0") or 0.0)
        for rec in self:
            base = rec.value_mxn or 0.0
            tasa = False
            if rec.fraccion_id:
                tipo = "importacion" if rec.operacion_id.tipo_operacion != "exportacion" else "exportacion"
                tasa = rec.fraccion_id.tasa_ids.filtered(
                    lambda t: t.tipo_operacion == tipo and t.territorio == "general"
                )[:1]
                if not tasa:
                    tasa = rec.fraccion_id.tasa_ids.filtered(lambda t: t.tipo_operacion == tipo)[:1]
            igi_rate = tasa.igi if tasa else 0.0
            iva_rate = tasa.iva if tasa else 0.0
            rec.igi_estimado = base * (igi_rate / 100.0)
            rec.iva_estimado = (base + rec.igi_estimado) * (iva_rate / 100.0)
            rec.dta_estimado = base * (dta_rate / 100.0)
            rec.prv_estimado = base * (prv_rate / 100.0)

    @api.constrains("quantity", "value_usd")
    def _check_required_trade_fields(self):
        for rec in self:
            if not rec.quantity:
                raise ValidationError("La partida requiere cantidad.")
            if rec.quantity <= 0:
                raise ValidationError("La cantidad por partida debe ser mayor a cero.")
            if rec.value_usd is False or rec.value_usd is None or rec.value_usd <= 0:
                raise ValidationError("La partida requiere valor USD mayor a cero.")

    @api.onchange("fraccion_id")
    def _onchange_fraccion_id(self):
        for rec in self:
            fraccion = rec.fraccion_id
            if not fraccion:
                continue
            rec.fraccion_arancelaria = fraccion.code
            if rec.nico_id and rec.nico_id.fraccion_id != fraccion:
                rec.nico_id = False
            rec.nico = rec.nico_id.code if rec.nico_id else fraccion.nico
            if not rec.descripcion:
                rec.descripcion = fraccion.name
            if fraccion.um_id:
                rec.unidad_tarifa = fraccion.um_id.code
                rec.uom_id = fraccion.um_id.id
            rec.nom_ids = [(6, 0, fraccion.nom_default_ids.ids)]
            rec.permiso_ids = [(6, 0, fraccion.permiso_default_ids.ids)]
            rec.rrna_ids = [(6, 0, fraccion.rrna_default_ids.ids)]

    @api.onchange("nico_id")
    def _onchange_nico_id(self):
        for rec in self:
            rec.nico = rec.nico_id.code if rec.nico_id else (rec.fraccion_id.nico if rec.fraccion_id else False)

    def get_regulatory_summary_text(self):
        self.ensure_one()
        noms = ", ".join(self.nom_ids.mapped("code"))
        permisos = ", ".join(self.permiso_ids.mapped("code"))
        rrna = ", ".join(self.rrna_ids.mapped("code"))
        return (
            f"NOM: {noms or 'N/A'} ({self.nom_compliance_status or 'pendiente'}) | "
            f"PERMISO: {permisos or 'N/A'} | "
            f"RRNA: {rrna or 'N/A'}"
        )
