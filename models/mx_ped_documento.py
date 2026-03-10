from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedDocumento(models.Model):
    _name = "mx.ped.documento"
    _description = "Pedimento - Documento"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )
    remesa_id = fields.Many2one(
        "mx.ped.consolidado.remesa",
        string="Remesa consolidada",
        ondelete="set null",
        index=True,
    )
    es_documento_principal = fields.Boolean(
        string="Documento principal",
        default=False,
        help="Marca el documento principal o la relacion de facturas que acompana fisicamente a la remesa.",
    )

    partida_id = fields.Many2one("mx.ped.partida", ondelete="set null")
    aplica_partida_especifica = fields.Boolean(
        string="Aplica a una partida especifica",
        default=False,
        help="Marca esta opcion solo cuando el documento corresponda a una partida concreta dentro de la remesa.",
    )

    tipo = fields.Selection(
        [
            ("factura", "Factura"),
            ("packing", "Packing List"),
            ("bl_awb", "BL/AWB"),
            ("cove", "COVE"),
            ("edocument", "e-Document"),
            ("coo", "Certificado de Origen"),
            ("nom", "NOM / Permiso"),
            ("otro", "Otro"),
        ],
        default="otro",
        required=True,
        index=True,
    )
    registro_codigo = fields.Selection(
        [
            ("510", "510 - Contribuciones cabecera"),
            ("514", "514 - Documentos virtuales"),
            ("557", "557 - Contribuciones partida"),
            ("otro", "Otro"),
        ],
        string="Registro SAAI",
        default="otro",
        required=True,
        index=True,
    )
    forma_pago_id = fields.Many2one(
        "mx.forma.pago",
        string="Forma de pago",
        domain="[('active','=',True), '|', ('scope','=','all'), ('scope','=','514')]",
        ondelete="restrict",
    )
    forma_pago_code = fields.Char(
        string="Forma de pago (clave)",
        related="forma_pago_id.code",
        store=True,
        readonly=True,
    )

    folio = fields.Char()
    fecha = fields.Datetime()
    cfdi_termino_facturacion = fields.Char(string="Termino facturacion 505")
    cfdi_moneda_id = fields.Many2one("res.currency", string="Moneda documento 505")
    cfdi_valor_usd = fields.Monetary(
        string="Valor USD 505",
        currency_field="company_currency_id",
        digits=(16, 2),
    )
    cfdi_valor_moneda = fields.Monetary(
        string="Valor moneda documento 505",
        currency_field="cfdi_moneda_id",
        digits=(16, 2),
    )
    cfdi_pais_id = fields.Many2one("res.country", string="Pais documento 505")
    cfdi_estado_id = fields.Many2one("res.country.state", string="Entidad documento 505")
    cfdi_id_fiscal = fields.Char(string="Identificacion fiscal 505")
    counterparty_name_505 = fields.Char(string="Proveedor / comprador 505")
    counterparty_street_505 = fields.Char(string="Calle 505")
    counterparty_num_int_505 = fields.Char(string="Numero interior 505")
    counterparty_num_ext_505 = fields.Char(string="Numero exterior 505")
    counterparty_zip_505 = fields.Char(string="Codigo postal 505")
    counterparty_city_505 = fields.Char(string="Municipio / ciudad 505")
    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
        store=True,
    )

    # Usa ir.attachment para subir archivos
    attachment_id = fields.Many2one("ir.attachment", string="Archivo")
    archivo_file = fields.Binary(string="Archivo")
    archivo_filename = fields.Char(string="Nombre archivo")

    estatus = fields.Selection(
        [("pendiente", "Pendiente"), ("ok", "OK"), ("rechazado", "Rechazado")],
        default="pendiente",
        index=True,
    )

    notas = fields.Text()

    def action_open_full_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "view_id": self.env.ref("modulo_aduana_odoo.mx_ped_documento_remesa_view_form").id,
            "target": "new",
        }

    def _get_505_counterparty_partner(self):
        self.ensure_one()
        lead = self.operacion_id.lead_id
        if not lead:
            return self.env["res.partner"]
        return lead.x_counterparty_partner_id or self.env["res.partner"]

    def _prepare_505_snapshot_vals(self):
        self.ensure_one()
        lead = self.operacion_id.lead_id
        partner = self._get_505_counterparty_partner()
        vals = {}
        if not lead:
            return vals
        if not self.fecha:
            vals["fecha"] = lead.x_cfdi_fecha or (lead.x_cfdi_fecha_emision or False)
        if not self.folio:
            vals["folio"] = lead.x_cfdi_numero or lead.x_cfdi_uuid or False
        if not self.cfdi_termino_facturacion:
            vals["cfdi_termino_facturacion"] = lead.x_incoterm or lead.x_cfdi_termino_facturacion or False
        if not self.cfdi_moneda_id and lead.x_cfdi_moneda_id:
            vals["cfdi_moneda_id"] = lead.x_cfdi_moneda_id.id
        if not self.cfdi_valor_usd and lead.x_cfdi_valor_usd:
            vals["cfdi_valor_usd"] = lead.x_cfdi_valor_usd
        if not self.cfdi_valor_moneda and lead.x_cfdi_valor_moneda:
            vals["cfdi_valor_moneda"] = lead.x_cfdi_valor_moneda
        if not self.cfdi_pais_id:
            vals["cfdi_pais_id"] = (lead.x_cfdi_pais_id.id if lead.x_cfdi_pais_id else (partner.country_id.id if partner and partner.country_id else False))
        if not self.cfdi_estado_id:
            vals["cfdi_estado_id"] = (lead.x_cfdi_estado_id.id if lead.x_cfdi_estado_id else (partner.state_id.id if partner and partner.state_id else False))
        if not self.cfdi_id_fiscal:
            vals["cfdi_id_fiscal"] = lead.x_cfdi_id_fiscal or (partner.vat if partner else False)
        if not self.counterparty_name_505:
            vals["counterparty_name_505"] = lead.x_counterparty_name_505 or (partner.name if partner else False)
        if partner:
            if not self.counterparty_street_505:
                vals["counterparty_street_505"] = partner.x_street_name or partner.street or False
            if not self.counterparty_num_int_505:
                vals["counterparty_num_int_505"] = partner.x_street_number_int or False
            if not self.counterparty_num_ext_505:
                vals["counterparty_num_ext_505"] = partner.x_street_number_ext or False
            if not self.counterparty_zip_505:
                vals["counterparty_zip_505"] = partner.zip or False
            if not self.counterparty_city_505:
                vals["counterparty_city_505"] = partner.x_municipio or partner.city or False
        return vals

    @api.onchange("operacion_id", "remesa_id")
    def _onchange_fill_505_snapshot(self):
        for rec in self:
            if rec.remesa_id and not rec.operacion_id:
                rec.operacion_id = rec.remesa_id.operacion_id
            vals = rec._prepare_505_snapshot_vals() if rec.operacion_id else {}
            for key, value in vals.items():
                rec[key] = value

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            vals = rec._prepare_505_snapshot_vals()
            if vals:
                super(MxPedDocumento, rec).write(vals)
        return records

    @api.onchange("aplica_partida_especifica")
    def _onchange_aplica_partida_especifica(self):
        for rec in self:
            if not rec.aplica_partida_especifica:
                rec.partida_id = False

    @api.onchange("partida_id")
    def _onchange_partida_id(self):
        for rec in self:
            if rec.partida_id:
                rec.aplica_partida_especifica = True

    @api.constrains("remesa_id", "operacion_id", "partida_id")
    def _check_remesa_integrity(self):
        for rec in self:
            if rec.remesa_id and rec.remesa_id.operacion_id != rec.operacion_id:
                raise ValidationError("La remesa del documento debe pertenecer a la misma operacion.")
            if rec.partida_id and rec.partida_id.operacion_id != rec.operacion_id:
                raise ValidationError("La partida del documento debe pertenecer a la misma operacion.")
            if not rec.aplica_partida_especifica and rec.partida_id:
                raise ValidationError("Si el documento tiene partida, marca que aplica a una partida especifica.")

    @api.constrains("remesa_id", "es_documento_principal")
    def _check_single_documento_principal(self):
        for rec in self.filtered(lambda r: r.remesa_id and r.es_documento_principal):
            duplicate = self.search_count([
                ("id", "!=", rec.id),
                ("remesa_id", "=", rec.remesa_id.id),
                ("es_documento_principal", "=", True),
            ])
            if duplicate:
                raise ValidationError("Solo puede existir un documento principal por remesa.")
        for rec in self.filtered(lambda r: not r.remesa_id and r.es_documento_principal and r.operacion_id):
            duplicate = self.search_count([
                ("id", "!=", rec.id),
                ("operacion_id", "=", rec.operacion_id.id),
                ("remesa_id", "=", False),
                ("es_documento_principal", "=", True),
            ])
            if duplicate:
                raise ValidationError("Solo puede existir un documento principal a nivel operacion cuando no se usa remesa.")
