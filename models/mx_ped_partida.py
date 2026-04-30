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
    fraccion_id = fields.Many2one("mx.tigie.maestra", string="Fraccion arancelaria")
    fraccion_arancelaria = fields.Char(
        string="Fraccion (snapshot)",
        size=20,
        index=True,
        compute="_compute_fraccion_nico_snapshot",
        store=True,
        readonly=False,
    )
    nico_id = fields.Many2one(
        "mx.nico",
        string="NICO",
    )
    nico = fields.Char(
        string="NICO (snapshot)",
        size=2,
        compute="_compute_fraccion_nico_snapshot",
        store=True,
        readonly=False,
    )
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

    unidad_tarifa_id = fields.Many2one(
        "mx.ped.um",
        string="Unidad tarifa",
        help="Unidad de medida de tarifa (UMT) — definida por la TIGIE para la fracción arancelaria.",
    )
    unidad_tarifa = fields.Char(
        string="Unidad tarifa (código)",
        size=10,
        related="unidad_tarifa_id.code",
        store=True,
        readonly=True,
    )
    cantidad_tarifa = fields.Float(digits=(16, 5))

    unidad_comercial_id = fields.Many2one(
        "mx.ped.um",
        string="Unidad comercial",
        help="Unidad de medida comercial (UMC) — como viene expresada en la factura del proveedor.",
    )
    unidad_comercial = fields.Char(
        string="Unidad comercial (código)",
        size=10,
        related="unidad_comercial_id.code",
        store=True,
        readonly=True,
    )
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
    # Campos legacy — el 556 se genera desde partida_contribucion_ids (557) en la operación.
    tasa_clave_contribucion = fields.Char(string="Tasa: Clave contribución (legacy)", size=3)
    tasa_valor = fields.Float(string="Tasa: Valor (legacy)", digits=(16, 4))
    tasa_tipo = fields.Char(string="Tasa: Tipo de tasa (legacy)", size=2)

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
    identificador_ids = fields.One2many(
        "mx.ped.partida.identificador",
        "partida_id",
        string="Identificadores partida",
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
    def _name_search(self, name, domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            text_domain = [
                "|",
                ("fraccion_arancelaria", operator, name),
                ("descripcion", operator, name),
            ]
            # numero_partida es Integer: solo se puede comparar con = cuando el texto es numérico
            name_stripped = (name or "").strip()
            if name_stripped.isdigit():
                domain = [
                    "|",
                    ("numero_partida", "=", int(name_stripped)),
                    *text_domain,
                ] + domain
            else:
                domain = text_domain + domain
        return self._search(domain, limit=limit, order=order)

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
        """Devuelve un dict con 'igi' e 'iva' segun el tipo de operacion.
        Mantiene la firma anterior para no romper llamadas externas."""
        self.ensure_one()
        if not self.fraccion_id:
            return None
        tipo = "importacion" if self.operacion_id.tipo_operacion != "exportacion" else "exportacion"
        if tipo == "importacion":
            return {
                "igi": self.fraccion_id.arancel_importacion or 0.0,
                "iva": self.fraccion_id.iva_importacion or 0.0,
            }
        return {
            "igi": self.fraccion_id.arancel_exportacion or 0.0,
            "iva": 0.0,
        }

    @api.depends(
        "fraccion_id",
        "fraccion_id.arancel_importacion",
        "fraccion_id.arancel_exportacion",
        "fraccion_id.iva_importacion",
        "operacion_id.tipo_operacion",
    )
    def _compute_tasas_fraccion(self):
        for rec in self:
            tasa = rec._get_applicable_tasa()
            rec.igi_rate = tasa["igi"] if tasa else 0.0
            rec.iva_rate = tasa["iva"] if tasa else 0.0

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

    def _check_required_trade_fields(self):
        """Validación de campos requeridos para generar el pedimento.
        Se llama explícitamente desde action_validar, NO como constrains,
        para permitir guardar borradores parciales (ej. antes de asignar valor USD).
        """
        errors = []
        for rec in self:
            if not rec.quantity or rec.quantity <= 0:
                errors.append(f"Partida {rec.numero_partida or rec.id}: cantidad debe ser mayor a cero.")
            if not rec.value_usd or rec.value_usd <= 0:
                errors.append(f"Partida {rec.numero_partida or rec.id}: valor USD debe ser mayor a cero.")
        if errors:
            raise ValidationError("\n".join(errors))

    @api.depends("fraccion_id", "nico_id")
    def _compute_fraccion_nico_snapshot(self):
        for rec in self:
            if rec.fraccion_id and not rec.fraccion_arancelaria:
                rec.fraccion_arancelaria = rec.fraccion_id.fraccion_8 or ""
            if rec.nico_id and not rec.nico:
                rec.nico = rec.nico_id.code or ""

    @api.onchange("fraccion_id")
    def _onchange_fraccion_id(self):
        warning = {}
        for rec in self:
            fraccion = rec.fraccion_id
            if not fraccion:
                continue

            # — Snapshot de fraccion y NICO —
            rec.fraccion_arancelaria = fraccion.fraccion_8 or ""
            rec.nico = fraccion.nico or ""
            rec.nico_id = False  # NICO ahora viene de la TIGIE maestra, no del catalogo separado

            # — Descripcion —
            if not rec.descripcion:
                rec.descripcion = fraccion.descripcion_completa or ""

            # — Unidad de medida de tarifa (UMT) —
            if fraccion.unidad_medida:
                umt = self.env["mx.ped.um"].search(
                    [("code", "=", fraccion.unidad_medida), ("active", "=", True)], limit=1
                )
                if umt:
                    rec.unidad_tarifa_id = umt
                    if not rec.uom_id:
                        rec.uom_id = umt
                    # Auto-llenar cantidad_tarifa desde quantity solo si aún no tiene valor
                    if not rec.cantidad_tarifa and rec.quantity:
                        rec.cantidad_tarifa = rec.quantity
                    # Auto-llenar unidad_comercial si no está capturada
                    if not rec.unidad_comercial_id:
                        rec.unidad_comercial_id = umt
                    if not rec.cantidad_comercial and rec.quantity:
                        rec.cantidad_comercial = rec.quantity

            # — Limpiar regulatorias (ya no se auto-propagan desde M2M) —
            rec.nom_ids = [(5, 0, 0)]
            rec.permiso_ids = [(5, 0, 0)]
            rec.rrna_ids = [(5, 0, 0)]

            # — Aviso con regulaciones de la TIGIE —
            avisos = []
            if fraccion.regulaciones_economia:
                avisos.append("SE/COFEPRIS: " + fraccion.regulaciones_economia.strip())
            if fraccion.otras_dependencias:
                avisos.append("Otras: " + fraccion.otras_dependencias.strip())
            if fraccion.requires_labeling_default:
                avisos.append("Esta fraccion requiere etiquetado NOM.")
            if avisos:
                warning = {
                    "title": "Regulaciones aplicables — %s" % (fraccion.llave_10 or fraccion.fraccion_8),
                    "message": "\n".join(avisos),
                }

        if warning:
            return {"warning": warning}

    @api.onchange("quantity")
    def _onchange_quantity_sync_umt_umc(self):
        """Sincroniza cantidad_tarifa y cantidad_comercial con quantity cuando:
        - El campo todavía no tiene valor (captura inicial), O
        - La unidad de tarifa y la unidad comercial son iguales a uom_id
          (caso más común: misma unidad en factura y TIGIE → los tres deben cuadrar).
        Nunca sobreescribe si el usuario ya capturó un valor distinto adrede.
        """
        for rec in self:
            if not rec.quantity:
                continue
            # Si cantidad_tarifa no se ha llenado → tomar de quantity
            if not rec.cantidad_tarifa:
                rec.cantidad_tarifa = rec.quantity
            # Si cantidad_tarifa YA existe pero la unidad tarifa = unidad comercial = uom
            # (misma unidad en los tres lados) → mantener sincronizado
            elif (rec.unidad_tarifa_id and rec.uom_id
                  and rec.unidad_tarifa_id == rec.uom_id):
                rec.cantidad_tarifa = rec.quantity
            # Mismo patrón para cantidad_comercial
            if not rec.cantidad_comercial:
                rec.cantidad_comercial = rec.quantity
            elif (rec.unidad_comercial_id and rec.uom_id
                  and rec.unidad_comercial_id == rec.uom_id):
                rec.cantidad_comercial = rec.quantity

    @api.onchange("uom_id")
    def _onchange_uom_sync_comercial(self):
        """Cuando el usuario cambia la unidad principal, proponer la misma
        en unidad_comercial si aún no está capturada."""
        for rec in self:
            if rec.uom_id and not rec.unidad_comercial_id:
                rec.unidad_comercial_id = rec.uom_id

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

    def init(self):
        """Migración en caliente: enlaza unidad_tarifa_id / unidad_comercial_id
        para registros que ya tenían el código guardado como Char libre."""
        self.env.cr.execute("""
            UPDATE mx_ped_partida p
               SET unidad_tarifa_id = u.id
              FROM mx_ped_um u
             WHERE u.code = p.unidad_tarifa
               AND p.unidad_tarifa_id IS NULL
               AND p.unidad_tarifa IS NOT NULL
               AND p.unidad_tarifa != ''
        """)
        self.env.cr.execute("""
            UPDATE mx_ped_partida p
               SET unidad_comercial_id = u.id
              FROM mx_ped_um u
             WHERE u.code = p.unidad_comercial
               AND p.unidad_comercial_id IS NULL
               AND p.unidad_comercial IS NOT NULL
               AND p.unidad_comercial != ''
        """)

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
