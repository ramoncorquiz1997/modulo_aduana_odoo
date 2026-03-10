from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedConsolidadoRemesa(models.Model):
    _name = "mx.ped.consolidado.remesa"
    _description = "Pedimento consolidado - Remesa"
    _order = "operacion_id, sequence, id"

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
    acuse_valor = fields.Char(string="Acuse de valor")
    acuse_presentacion = fields.Char(string="Acuse presentacion")
    observaciones = fields.Text(string="Observaciones")

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
