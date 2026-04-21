from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedDocumento(models.Model):
    _name = "mx.ped.documento"
    _description = "Pedimento - Documento"
    _rec_name = "display_name"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )
    source_lead_documento_id = fields.Many2one(
        "crm.lead.documento",
        string="Documento origen (Lead)",
        ondelete="set null",
        index=True,
        readonly=True,
        copy=False,
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
    institucion_financiera_514_id = fields.Many2one(
        "aduana.catalogo.institucion_financiera",
        string="Institucion financiera 514",
        ondelete="restrict",
    )
    institucion_emisora_514 = fields.Char(string="Institucion emisora 514")
    importe_total_amparado_514 = fields.Monetary(
        string="Importe total amparado 514",
        currency_field="company_currency_id",
        digits=(16, 2),
    )
    saldo_disponible_514 = fields.Monetary(
        string="Saldo disponible 514",
        currency_field="company_currency_id",
        digits=(16, 2),
    )
    importe_total_pagar_514 = fields.Monetary(
        string="Importe total a pagar 514",
        currency_field="company_currency_id",
        digits=(16, 2),
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
    show_advanced_info = fields.Boolean(
        related="operacion_id.show_advanced_info",
        readonly=True,
        store=False,
    )

    # Usa ir.attachment para subir archivos
    attachment_id = fields.Many2one("ir.attachment", string="Archivo")
    archivo_file = fields.Binary(string="Archivo")
    archivo_filename = fields.Char(string="Nombre archivo")
    display_name = fields.Char(
        string="Nombre",
        compute="_compute_display_name",
        store=False,
    )

    estatus = fields.Selection(
        [("pendiente", "Pendiente"), ("ok", "OK"), ("rechazado", "Rechazado")],
        default="pendiente",
        index=True,
    )

    notas = fields.Text()

    @api.depends("tipo", "folio", "remesa_id.folio", "partida_id.numero_partida")
    def _compute_display_name(self):
        for rec in self:
            tipo = dict(self._fields["tipo"].selection).get(rec.tipo, rec.tipo or "Documento")
            pieces = [tipo]
            if rec.folio:
                pieces.append(rec.folio)
            if rec.remesa_id and rec.remesa_id.folio:
                pieces.append("Remesa %s" % rec.remesa_id.folio)
            if rec.partida_id and rec.partida_id.numero_partida:
                pieces.append("Partida %s" % rec.partida_id.numero_partida)
            rec.display_name = " | ".join(pieces)

    @api.model
    def _name_search(self, name, domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            domain = [
                "|",
                ("folio", operator, name.strip()),
                ("tipo", operator, name.strip()),
            ] + domain
        return self._search(domain, limit=limit, order=order)

    def name_get(self):
        return [(rec.id, rec.display_name or ("Documento %s" % rec.id)) for rec in self]

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

    @api.onchange("forma_pago_id", "registro_codigo", "operacion_id", "institucion_financiera_514_id")
    def _onchange_fill_514_defaults(self):
        for rec in self:
            if (rec.registro_codigo or "").strip() != "514" or not rec.operacion_id:
                continue
            fp_code = (rec.forma_pago_code or "").strip()
            if rec.institucion_financiera_514_id:
                rec.institucion_emisora_514 = rec.institucion_financiera_514_id.name

            if fp_code == "12":
                rec.institucion_financiera_514_id = False
                rec.institucion_emisora_514 = "Aduanas"
            elif fp_code in {"4", "15"} and not rec.institucion_financiera_514_id:
                cuenta = rec.operacion_id.cuenta_aduanera_ids.sorted(lambda l: (l.sequence or 0, l.id))[:1]
                if cuenta and cuenta.institucion_financiera_id:
                    rec.institucion_financiera_514_id = cuenta.institucion_financiera_id
                    rec.institucion_emisora_514 = cuenta.institucion_financiera_id.name
            if fp_code == "12" and not rec.fecha and rec.operacion_id.fecha_pago:
                rec.fecha = rec.operacion_id.fecha_pago
            if fp_code in {"4", "15"} and not rec.fecha:
                cuenta = rec.operacion_id.cuenta_aduanera_ids.sorted(lambda l: (l.sequence or 0, l.id))[:1]
                if cuenta and cuenta.fecha_constancia:
                    rec.fecha = cuenta.fecha_constancia
            if fp_code in {"4", "15"} and not rec.folio:
                cuenta = rec.operacion_id.cuenta_aduanera_ids.sorted(lambda l: (l.sequence or 0, l.id))[:1]
                if cuenta and cuenta.folio_constancia:
                    rec.folio = cuenta.folio_constancia

    @api.model
    def _sync_514_storage_vals(self, vals, current=None):
        vals = dict(vals or {})
        registro_codigo = (vals.get("registro_codigo") if "registro_codigo" in vals else (current.registro_codigo if current else "")) or ""
        if str(registro_codigo).strip() != "514":
            return vals

        operacion = None
        operacion_id = vals.get("operacion_id") if "operacion_id" in vals else (current.operacion_id.id if current and current.operacion_id else False)
        if operacion_id:
            operacion = self.env["mx.ped.operacion"].browse(operacion_id)

        forma_pago = None
        forma_pago_id = vals.get("forma_pago_id") if "forma_pago_id" in vals else (current.forma_pago_id.id if current and current.forma_pago_id else False)
        if forma_pago_id:
            forma_pago = self.env["mx.forma.pago"].browse(forma_pago_id)
        fp_code = (forma_pago.code if forma_pago else (current.forma_pago_code if current else "")) or ""
        fp_code = str(fp_code).strip()

        institucion = None
        inst_id = vals.get("institucion_financiera_514_id") if "institucion_financiera_514_id" in vals else (
            current.institucion_financiera_514_id.id if current and current.institucion_financiera_514_id else False
        )
        if inst_id:
            institucion = self.env["aduana.catalogo.institucion_financiera"].browse(inst_id)

        if fp_code == "12":
            vals["institucion_financiera_514_id"] = False
            vals["institucion_emisora_514"] = "Aduanas"
            if operacion and not vals.get("fecha") and not (current and current.fecha):
                vals["fecha"] = operacion.fecha_pago or vals.get("fecha")
        else:
            if institucion:
                vals["institucion_emisora_514"] = institucion.name
            elif fp_code in {"4", "15"} and operacion:
                cuenta = operacion.cuenta_aduanera_ids.sorted(lambda l: (l.sequence or 0, l.id))[:1]
                if cuenta and cuenta.institucion_financiera_id:
                    vals.setdefault("institucion_financiera_514_id", cuenta.institucion_financiera_id.id)
                    vals["institucion_emisora_514"] = cuenta.institucion_financiera_id.name
                if cuenta and not vals.get("fecha") and not (current and current.fecha) and cuenta.fecha_constancia:
                    vals["fecha"] = cuenta.fecha_constancia
                if cuenta and not vals.get("folio") and not (current and current.folio) and cuenta.folio_constancia:
                    vals["folio"] = cuenta.folio_constancia

        return vals

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = [self._sync_514_storage_vals(vals) for vals in vals_list]
        records = super().create(normalized_vals_list)
        for rec in records:
            vals = rec._prepare_505_snapshot_vals()
            if vals:
                super(MxPedDocumento, rec).write(vals)
        return records

    def write(self, vals):
        vals = self._sync_514_storage_vals(vals, current=self[:1] if len(self) == 1 else None)
        return super().write(vals)

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
