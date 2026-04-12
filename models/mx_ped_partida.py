from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedPartida(models.Model):
    _name = "mx.ped.partida"
    _description = "Pedimento - Partida"
    _rec_name = "display_name"
    _order = "numero_partida asc, id asc"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )

    operacion_id = fields.Many2one(
        "mx.ped.operacion", required=True, ondelete="cascade", index=True
    )
    source_lead_line_id = fields.Many2one(
        "crm.lead.operacion.line",
        string="Partida origen (Lead)",
        ondelete="set null",
        index=True,
        readonly=True,
        copy=False,
    )
    source_lead_documento_id = fields.Many2one(
        "crm.lead.documento",
        string="Factura origen (Lead)",
        ondelete="set null",
        index=True,
        readonly=True,
        copy=False,
    )
    remesa_assignment_ids = fields.One2many(
        "mx.ped.consolidado.remesa.partida",
        "partida_id",
        string="Asignaciones remesa",
        readonly=True,
    )
    factura_documento_id = fields.Many2one(
        "mx.ped.documento",
        string="Factura / CFDI",
        ondelete="set null",
    )
    factura_documento_error = fields.Boolean(
        string="Error factura",
        default=False,
        copy=False,
    )
    factura_value_error = fields.Boolean(
        string="Error valores factura",
        default=False,
        copy=False,
    )
    factura_validation_note = fields.Char(
        string="Nota validacion factura",
        copy=False,
    )
    display_name = fields.Char(
        string="Nombre",
        compute="_compute_display_name",
        store=False,
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
    igi_rate = fields.Float(
        string="IGI (%)",
        digits=(16, 6),
        compute="_compute_tasas_fraccion",
        store=True,
        readonly=True,
    )
    iva_rate = fields.Float(
        string="IVA (%)",
        digits=(16, 6),
        compute="_compute_tasas_fraccion",
        store=True,
        readonly=True,
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

    # ── T-MEC / Complementario (registros 351 y 355) ─────────────────────────
    tmec_valor_mercancia_no_originaria = fields.Float(
        string="T-MEC: Valor mercancía no originaria",
        digits=(16, 2),
    )
    tmec_monto_igi_no_originaria = fields.Float(
        string="T-MEC: Monto IGI no originaria",
        digits=(16, 2),
    )
    tmec_impuesto_total_importacion = fields.Float(
        string="T-MEC: Impuesto total importación",
        digits=(16, 2),
    )
    tmec_monto_exento = fields.Float(
        string="T-MEC: Monto exento",
        digits=(16, 2),
    )
    tmec_clave_contribucion = fields.Char(
        string="T-MEC: Clave contribución (355)",
        size=3,
    )
    tmec_importe_pagado = fields.Float(
        string="T-MEC: Importe pagado (355)",
        digits=(16, 2),
    )
    tmec_fecha_pago = fields.Date(
        string="T-MEC: Fecha pago (355)",
    )

    # ── Cuentas Aduaneras de Garantía (registro 555) ──────────────────────────
    cta_garantia_institucion = fields.Char(
        string="Garantía: Institución emisora",
        size=10,
    )
    cta_garantia_numero = fields.Char(
        string="Garantía: Número de cuenta",
        size=20,
    )
    cta_garantia_folio = fields.Char(
        string="Garantía: Folio constancia",
        size=20,
    )
    cta_garantia_fecha = fields.Date(
        string="Garantía: Fecha constancia",
    )
    cta_garantia_tipo = fields.Char(
        string="Garantía: Tipo de garantía",
        size=2,
    )
    cta_garantia_valor_titulo = fields.Float(
        string="Garantía: Valor unitario título",
        digits=(16, 2),
    )
    cta_garantia_importe = fields.Float(
        string="Garantía: Importe total",
        digits=(16, 2),
    )
    cta_garantia_cantidad = fields.Float(
        string="Garantía: Cantidad unidades",
        digits=(16, 2),
    )
    cta_garantia_titulos = fields.Char(
        string="Garantía: Títulos asignados",
        size=30,
    )

    # ── Tasas por partida (registro 556) ─────────────────────────────────────
    tasa_clave_contribucion = fields.Char(
        string="Tasa: Clave contribución",
        size=3,
    )
    tasa_valor = fields.Float(
        string="Tasa: Valor",
        digits=(16, 4),
    )
    tasa_tipo = fields.Char(
        string="Tasa: Tipo de tasa",
        size=2,
    )

    forma_pago_sugerida_id = fields.Many2one(
        "mx.forma.pago",
        string="Forma de pago sugerida",
        domain="[('active','=',True), '|', ('scope','=','all'), ('scope','=','557')]",
        ondelete="restrict",
    )
    contribucion_ids = fields.One2many(
        "mx.ped.partida.contribucion",
        "partida_id",
        string="Contribuciones partida (557)",
        copy=True,
    )
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

    @api.depends("numero_partida", "fraccion_arancelaria", "fraccion_id.code", "descripcion")
    def _compute_display_name(self):
        for rec in self:
            partida = "Partida %s" % (rec.numero_partida or rec.id or "")
            fraccion = rec.fraccion_arancelaria or rec.fraccion_id.code or ""
            descripcion = " ".join((rec.descripcion or "").split())
            if len(descripcion) > 50:
                descripcion = descripcion[:47] + "..."
            pieces = [partida]
            if fraccion:
                pieces.append(fraccion)
            if descripcion:
                pieces.append(descripcion)
            rec.display_name = " | ".join(pieces)

    def _get_remesa_context(self):
        self.ensure_one()
        remesas = self.remesa_assignment_ids.mapped("remesa_id")
        return remesas[0] if len(remesas) == 1 else self.env["mx.ped.consolidado.remesa"]

    def _get_eligible_factura_documentos(self):
        self.ensure_one()
        docs = self.operacion_id.documento_ids.filtered(lambda d: d.tipo in ("factura", "cove", "otro"))
        remesas = self.remesa_assignment_ids.mapped("remesa_id")
        remesa_context = remesas[0] if len(remesas) == 1 else self.env["mx.ped.consolidado.remesa"]
        if remesa_context:
            docs = docs.filtered(lambda d: d.remesa_id == remesa_context)
        elif remesas:
            docs = docs.filtered(lambda d: not d.remesa_id)
        return docs

    def _get_default_factura_documento(self):
        self.ensure_one()
        docs = self._get_eligible_factura_documentos()
        if len(docs) == 1:
            return docs[0]
        previous = self.operacion_id.partida_ids.filtered(
            lambda p: p.id != self.id and (
                (p.numero_partida or 0) < (self.numero_partida or 999999999)
                or (not self.numero_partida and p.id < self.id)
            )
        ).sorted(lambda p: (p.numero_partida or 0, p.id))
        previous = previous[-1:] if previous else self.env["mx.ped.partida"]
        if previous and previous.factura_documento_id and previous.factura_documento_id in docs:
            return previous.factura_documento_id
        return docs.filtered(lambda d: d.es_documento_principal)[:1]

    @api.depends("value_usd", "operacion_id.lead_id.x_tipo_cambio")
    def _compute_value_mxn(self):
        for rec in self:
            tc = rec.operacion_id.lead_id.x_tipo_cambio or 0.0
            rec.value_mxn = (rec.value_usd or 0.0) * tc

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = list(args or [])
        domain = []
        if name:
            domain = [
                "|",
                "|",
                ("numero_partida", "ilike", name),
                ("fraccion_arancelaria", operator, name),
                ("descripcion", operator, name),
            ]
        recs = self.search(domain + args, limit=limit)
        return recs.name_get()

    def name_get(self):
        return [(rec.id, rec.display_name or ("Partida %s" % (rec.numero_partida or rec.id))) for rec in self]

    @api.onchange("operacion_id", "numero_partida", "remesa_assignment_ids", "factura_documento_id")
    def _onchange_factura_documento_id(self):
        domain = [("id", "=", 0)]
        for rec in self:
            docs = rec._get_eligible_factura_documentos() if rec.operacion_id else self.env["mx.ped.documento"]
            domain = [("id", "in", docs.ids)] if docs else [("id", "=", 0)]
            if rec.factura_documento_id and rec.factura_documento_id not in docs:
                rec.factura_documento_id = False
            if not rec.factura_documento_id:
                default_doc = rec._get_default_factura_documento()
                if default_doc:
                    rec.factura_documento_id = default_doc
        return {"domain": {"factura_documento_id": domain}}

    def _get_applicable_tasa(self):
        self.ensure_one()
        if not self.fraccion_id:
            return self.env["mx.ped.fraccion.tasa"]
        tipo = "importacion" if self.operacion_id.tipo_operacion != "exportacion" else "exportacion"
        tasa = self.fraccion_id.tasa_ids.filtered(
            lambda t: t.tipo_operacion == tipo and t.territorio == "general"
        )[:1]
        if not tasa:
            tasa = self.fraccion_id.tasa_ids.filtered(lambda t: t.tipo_operacion == tipo)[:1]
        return tasa

    @api.depends("fraccion_id", "fraccion_id.tasa_ids", "operacion_id.tipo_operacion")
    def _compute_tasas_fraccion(self):
        for rec in self:
            tasa = rec._get_applicable_tasa()
            rec.igi_rate = tasa.igi if tasa else 0.0
            rec.iva_rate = tasa.iva if tasa else 0.0

    @api.depends(
        "value_mxn",
        "igi_rate",
        "iva_rate",
    )
    def _compute_impuestos_estimados(self):
        icp = self.env["ir.config_parameter"].sudo()
        dta_rate = float(icp.get_param("mx_ped.dta_rate", "0.0") or 0.0)
        prv_rate = float(icp.get_param("mx_ped.prv_rate", "0.0") or 0.0)
        for rec in self:
            base = rec.value_mxn or 0.0
            rec.igi_estimado = base * ((rec.igi_rate or 0.0) / 100.0)
            rec.iva_estimado = (base + rec.igi_estimado) * ((rec.iva_rate or 0.0) / 100.0)
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

    @api.constrains("factura_documento_id", "operacion_id", "remesa_assignment_ids")
    def _check_factura_documento_integrity(self):
        for rec in self:
            if not rec.factura_documento_id:
                continue
            if rec.factura_documento_id.operacion_id != rec.operacion_id:
                raise ValidationError("La factura/CFDI asignada debe pertenecer a la misma operacion que la partida.")
            remesas = rec.remesa_assignment_ids.mapped("remesa_id")
            if len(remesas) == 1 and rec.factura_documento_id.remesa_id and rec.factura_documento_id.remesa_id != remesas[0]:
                raise ValidationError("La factura/CFDI de la partida debe pertenecer a la misma remesa.")
            if len(remesas) > 1 and rec.factura_documento_id.remesa_id:
                raise ValidationError("La partida esta dividida en multiples remesas; no puede usar una factura ligada a una sola remesa.")

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

    @api.model_create_multi
    def create(self, vals_list):
        normalized = []
        for vals in vals_list:
            vals = dict(vals)
            normalized.append(vals)
        records = super().create(vals_list)
        for rec, vals in zip(records, normalized):
            if not vals.get("factura_documento_id"):
                default_doc = rec._get_default_factura_documento()
                if default_doc:
                    rec.with_context(skip_auto_generated_refresh=True).write({"factura_documento_id": default_doc.id})
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        records = self.exists()
        if not records:
            return True
        res = super(MxPedPartida, records).write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        records = self.exists()
        if not records:
            return True
        operaciones = records.mapped("operacion_id")
        res = super(MxPedPartida, records).unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            operaciones._auto_refresh_generated_registros()
        return res
