from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedConsolidadoRemesa(models.Model):
    _name = "mx.ped.consolidado.remesa"
    _description = "Pedimento consolidado - Remesa"
    _order = "operacion_id, sequence, id"

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Secuencia", default=10)
    name = fields.Char(
        string="Remesa",
        compute="_compute_name",
        store=True,
    )
    folio = fields.Char(string="Folio remesa", index=True)
    fecha_remesa = fields.Date(
        string="Fecha remesa",
        default=lambda self: fields.Date.context_today(self),
        required=True,
    )
    estado = fields.Selection(
        [
            ("borrador", "Borrador"),
            ("presentada", "Presentada"),
            ("cerrada", "Cerrada"),
            ("cancelada", "Cancelada"),
        ],
        string="Estado",
        default="borrador",
        required=True,
        index=True,
    )
    tipo_documento_fuente = fields.Selection(
        [
            ("cfdi", "CFDI"),
            ("equivalente", "Documento equivalente"),
            ("cove", "COVE"),
            ("otro", "Otro"),
        ],
        string="Documento fuente",
        default="cfdi",
        required=True,
    )
    cfdi_uuid = fields.Char(string="UUID CFDI", index=True)
    numero_documento = fields.Char(string="Numero documento")
    attachment_id = fields.Many2one("ir.attachment", string="Archivo soporte")
    transportista_id = fields.Many2one(
        "res.partner",
        string="Transportista",
        domain="[('x_contact_role','=','transportista')]",
    )
    chofer_id = fields.Many2one(
        "res.partner",
        string="Chofer",
        domain="[('x_contact_role','=','chofer'), ('parent_id','=', transportista_id)]",
    )
    gafete_id = fields.Many2one(
        "mx.anam.gafete",
        string="Gafete ANAM",
        domain="[('active','=',True), ('chofer_id','=',chofer_id)]",
    )
    placas = fields.Char(string="Placas")
    contenedor = fields.Char(string="Contenedor")
    candados = fields.Char(string="Candados")

    # ── Enlace formal con COVE ────────────────────────────────────────────────
    cove_id = fields.Many2one(
        "mx.cove",
        string="COVE",
        ondelete="set null",
        index=True,
        domain="[('operacion_id', '=', operacion_id)]",
        help="COVE VUCEM asociado a esta remesa. Al obtener el e-document "
             "de VUCEM se propaga automáticamente a Acuse de valor.",
    )
    cove_estado = fields.Selection(
        related="cove_id.estado",
        string="Estado COVE",
        readonly=True,
    )
    # acuse_valor: se auto-rellena desde cove_id.e_document.
    # Si no hay COVE formal, se puede capturar manualmente.
    acuse_valor = fields.Char(
        string="e-Document (acuse de valor)",
        compute="_compute_acuse_valor",
        inverse="_inverse_acuse_valor",
        store=True,
        help="Folio COVE devuelto por VUCEM. Se llena automáticamente cuando "
             "se obtiene el e-document del COVE ligado.",
    )
    acuse_valor_manual = fields.Char(
        string="Acuse de valor (manual)",
        help="Se usa solo si no hay un COVE formal ligado.",
    )
    acuse_presentacion = fields.Char(string="Acuse presentacion")
    avc_plazo_id = fields.Selection(
        [("1", "Semanal"), ("2", "Mensual")],
        string="Plazo AVC",
    )
    observaciones = fields.Text(string="Observaciones")
    partida_rel_ids = fields.One2many(
        "mx.ped.consolidado.remesa.partida",
        "remesa_id",
        string="Partidas asignadas",
        copy=True,
    )
    documento_ids = fields.One2many(
        "mx.ped.documento",
        "remesa_id",
        string="Documentos remesa",
        copy=True,
    )
    factura_documento_ids = fields.Many2many(
        "mx.ped.documento",
        string="Facturas comerciales de esta remesa",
        compute="_compute_factura_documento_ids",
        inverse="_inverse_factura_documento_ids",
    )
    factura_documento_disponible_ids = fields.Many2many(
        "mx.ped.documento",
        string="Facturas comerciales disponibles",
        compute="_compute_factura_documento_disponible_ids",
    )
    partida_count = fields.Integer(
        string="Partidas asignadas",
        compute="_compute_totals",
    )
    total_quantity = fields.Float(
        string="Cantidad asignada",
        digits=(16, 6),
        compute="_compute_totals",
    )
    total_value_usd = fields.Float(
        string="Valor USD asignado",
        digits=(16, 2),
        compute="_compute_totals",
    )

    _sql_constraints = [
        (
            "mx_ped_consolidado_remesa_operacion_folio_uniq",
            "unique(operacion_id, folio)",
            "El folio de remesa debe ser unico por operacion.",
        ),
    ]

    @api.depends("folio", "sequence", "operacion_id.name")
    def _compute_name(self):
        for rec in self:
            if rec.folio:
                rec.name = rec.folio
            elif rec.operacion_id:
                rec.name = "%s / Remesa %s" % (rec.operacion_id.name or _("Operacion"), rec.sequence or 0)
            else:
                rec.name = _("Remesa")

    @api.depends("partida_rel_ids.quantity", "partida_rel_ids.value_usd")
    def _compute_totals(self):
        for rec in self:
            rec.partida_count = len(rec.partida_rel_ids)
            rec.total_quantity = sum(rec.partida_rel_ids.mapped("quantity"))
            rec.total_value_usd = sum(rec.partida_rel_ids.mapped("value_usd"))

    @api.depends("cove_id", "cove_id.e_document", "acuse_valor_manual")
    def _compute_acuse_valor(self):
        for rec in self:
            if rec.cove_id and rec.cove_id.e_document:
                rec.acuse_valor = rec.cove_id.e_document
            else:
                rec.acuse_valor = rec.acuse_valor_manual or False

    def _inverse_acuse_valor(self):
        """Permite editar el campo directamente cuando no hay COVE formal."""
        for rec in self:
            if not rec.cove_id:
                rec.acuse_valor_manual = rec.acuse_valor

    def _get_single_factura_documento(self):
        self.ensure_one()
        docs = self.factura_documento_ids.filtered(lambda d: d.tipo in ("factura", "cove", "otro"))
        if not docs:
            docs = self.partida_rel_ids.mapped("partida_id.factura_documento_id").filtered(
                lambda d: d and d.tipo in ("factura", "cove", "otro")
            )
        return docs[:1] if len(docs) == 1 else self.env["mx.ped.documento"]

    def _autofill_documento_fuente_from_factura(self):
        for rec in self:
            if rec.tipo_documento_fuente != "cfdi" or (rec.cfdi_uuid or "").strip():
                continue
            doc = rec._get_single_factura_documento()
            if doc and (doc.folio or "").strip():
                rec.cfdi_uuid = (doc.folio or "").strip()

    @api.depends("operacion_id.documento_ids", "operacion_id.documento_ids.tipo", "operacion_id.documento_ids.remesa_id")
    def _compute_factura_documento_ids(self):
        for rec in self:
            docs = rec.operacion_id.documento_ids.filtered(
                lambda d: d.tipo in ("factura", "cove", "otro") and d.remesa_id == rec
            )
            rec.factura_documento_ids = docs

    @api.depends("operacion_id.documento_ids", "operacion_id.documento_ids.tipo", "operacion_id.documento_ids.remesa_id")
    def _compute_factura_documento_disponible_ids(self):
        for rec in self:
            docs = rec.operacion_id.documento_ids.filtered(
                lambda d: d.tipo in ("factura", "cove", "otro") and (not d.remesa_id or d.remesa_id == rec)
            )
            rec.factura_documento_disponible_ids = docs

    def _inverse_factura_documento_ids(self):
        for rec in self:
            available_docs = rec.operacion_id.documento_ids.filtered(
                lambda d: d.tipo in ("factura", "cove", "otro") and (not d.remesa_id or d.remesa_id == rec)
            )
            selected_docs = rec.factura_documento_ids.filtered(lambda d: d in available_docs)
            if selected_docs:
                selected_docs.write({"remesa_id": rec.id})
            to_unset = available_docs.filtered(lambda d: d.remesa_id == rec and d not in selected_docs)
            if to_unset:
                to_unset.write({"remesa_id": False})
            rec._autofill_documento_fuente_from_factura()

    @api.onchange("factura_documento_ids", "tipo_documento_fuente")
    def _onchange_factura_documento_ids_fill_uuid(self):
        self._autofill_documento_fuente_from_factura()

    @api.onchange("partida_rel_ids")
    def _onchange_partida_rel_ids_fill_uuid(self):
        self._autofill_documento_fuente_from_factura()

    def action_open_full_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "view_id": self.env.ref("modulo_aduana_odoo.mx_ped_consolidado_remesa_view_form").id,
            "target": "new",
        }

    def action_archive_and_close(self):
        self.ensure_one()
        self.active = False
        return {"type": "ir.actions.act_window_close"}

    @api.constrains("operacion_id")
    def _check_operacion_consolidada(self):
        for rec in self:
            if rec.operacion_id and not rec.operacion_id.es_consolidado:
                raise ValidationError(_("Solo puedes capturar remesas en operaciones marcadas como pedimento consolidado."))

    @api.constrains("fecha_remesa", "operacion_id", "operacion_id.fecha_apertura", "operacion_id.fecha_cierre")
    def _check_fecha_remesa(self):
        for rec in self:
            apertura = rec.operacion_id.fecha_apertura
            cierre = rec.operacion_id.fecha_cierre
            if apertura and rec.fecha_remesa and rec.fecha_remesa < apertura:
                raise ValidationError(_("La fecha de la remesa no puede ser menor a la fecha de apertura del consolidado."))
            if cierre and rec.fecha_remesa and rec.fecha_remesa > cierre:
                raise ValidationError(_("La fecha de la remesa no puede ser mayor a la fecha de cierre del consolidado."))

    @api.constrains("tipo_documento_fuente", "cfdi_uuid", "numero_documento")
    def _check_documento_fuente(self):
        for rec in self:
            if rec.tipo_documento_fuente == "cfdi" and not (rec.cfdi_uuid or "").strip():
                raise ValidationError(_("La remesa requiere UUID CFDI cuando el documento fuente es CFDI."))
            if rec.tipo_documento_fuente != "cfdi" and not (rec.numero_documento or "").strip():
                raise ValidationError(_("La remesa requiere numero de documento cuando el documento fuente no es CFDI."))

    @api.constrains("chofer_id", "transportista_id", "gafete_id")
    def _check_transportista_data(self):
        for rec in self:
            if rec.chofer_id and rec.transportista_id and rec.chofer_id.parent_id != rec.transportista_id:
                raise ValidationError(_("El chofer seleccionado no pertenece al transportista de la remesa."))
            if rec.gafete_id and rec.chofer_id and rec.gafete_id.chofer_id != rec.chofer_id:
                raise ValidationError(_("El gafete seleccionado no corresponde al chofer de la remesa."))
