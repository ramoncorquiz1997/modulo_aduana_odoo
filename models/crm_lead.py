# -*- coding: utf-8 -*-
import base64
import io
import logging
import re
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None

_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    # Referencia ligera: el detalle del pedimento vive en aduana.pedimento
    x_pedimento_id = fields.Many2one(
        "aduana.pedimento",
        string="Pedimento",
        ondelete="set null",
        index=True,
    )
    x_pedimento_status = fields.Selection(
        [
            ("draft", "Borrador"),
            ("ready", "Listo"),
            ("generated", "Generado"),
            ("error", "Error"),
        ],
        string="Estado pedimento",
        default="draft",
    )
    x_pedimento_last_error = fields.Text(string="Ultimo error pedimento")

    # =========================================================
    # AGENCIA ADUANAL - DATOS BASE (LEAD COMO EXPEDIENTE)
    # =========================================================

    x_tipo_operacion = fields.Selection(
        selection=[
            ("importacion", "Importación"),
            ("exportacion", "Exportación"),
        ],
        string="Tipo de operación",
    )

    x_regimen = fields.Selection(
        selection=[
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Depósito fiscal"),
            ("transito", "Tránsito"),
        ],
        string="Régimen",
    )

    x_aduana_seccion_despacho_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana-seccion de despacho",
    )
    x_aduana = fields.Char(
        string="Aduana",
        related="x_aduana_seccion_despacho_id.code",
        store=True,
        readonly=True,
    )
    x_aduana_seccion_entrada_salida_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana-seccion entrada/salida",
    )
    x_aduana_seccion_entrada_salida = fields.Char(
        string="Aduana-sección entrada/salida",
        related="x_aduana_seccion_entrada_salida_id.code",
        store=True,
        readonly=True,
    )
    x_acuse_validacion = fields.Char(string="Acuse electrónico validación")

    x_incoterm = fields.Selection(
        selection=[
            ("EXW", "EXW"),
            ("FCA", "FCA"),
            ("FOB", "FOB"),
            ("CFR", "CFR"),
            ("CIF", "CIF"),
            ("DAP", "DAP"),
            ("DDP", "DDP"),
        ],
        string="Incoterm",
    )

    # --- Operación / mercancía (legacy / resumen) ---

    x_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
    )

    x_valor_mercancia = fields.Monetary(
        string="Valor mercancía",
        currency_field="x_currency_id",
    )

    x_peso_kg = fields.Float(
        string="Peso (kg)",
        compute="_compute_x_totales_partidas",
        store=True,
    )
    x_tipo_cambio = fields.Float(string="Tipo de cambio", digits=(16, 5))

    x_incrementable_fletes = fields.Monetary(
        string="Incrementables - Fletes",
        currency_field="x_currency_id",
    )
    x_incrementable_seguros = fields.Monetary(
        string="Incrementables - Seguros",
        currency_field="x_currency_id",
    )
    x_incrementable_embalajes = fields.Monetary(
        string="Incrementables - Embalajes",
        currency_field="x_currency_id",
    )
    x_incrementable_otros = fields.Monetary(
        string="Incrementables - Otros",
        currency_field="x_currency_id",
    )

    x_decrementable_fletes = fields.Monetary(
        string="Decrementables - Fletes",
        currency_field="x_currency_id",
    )
    x_decrementable_seguros = fields.Monetary(
        string="Decrementables - Seguros",
        currency_field="x_currency_id",
    )
    x_decrementable_carga = fields.Monetary(
        string="Decrementables - Carga",
        currency_field="x_currency_id",
    )
    x_decrementable_descarga = fields.Monetary(
        string="Decrementables - Descarga",
        currency_field="x_currency_id",
    )
    x_decrementable_otros = fields.Monetary(
        string="Decrementables - Otros",
        currency_field="x_currency_id",
    )

    # --- Identificación / responsables ---
    x_folio_operacion = fields.Char(string="Folio interno")
    x_referencia_cliente = fields.Char(string="Referencia del cliente")

    x_ejecutivo_id = fields.Many2one(
        comodel_name="res.users",
        string="Ejecutivo / Atención",
    )

    x_prioridad_operativa = fields.Selection(
        selection=[
            ("normal", "Normal"),
            ("urgente", "Urgente"),
        ],
        string="Prioridad",
        default="normal",
    )

    # --- Clasificación / aduana (resumen / header) ---
    x_agente_aduanal_id = fields.Many2one(
        "res.partner",
        string="Agente aduanal",
        domain="[('x_contact_role','=','agente_aduanal')]",
    )
    x_patente_agente = fields.Char(
        string="Patente",
        related="x_agente_aduanal_id.x_patente_aduanal",
        readonly=True,
    )
    x_curp_agente = fields.Char(string="CURP agente / apoderado")

    x_tipo_despacho = fields.Selection(
        selection=[
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("retorno", "Retorno"),
            ("deposito_fiscal", "Depósito fiscal"),
            ("transito", "Tránsito"),
        ],
        string="Tipo de despacho",
    )

    x_clave_pedimento_id = fields.Many2one(
        comodel_name="mx.ped.clave",
        string="Clave de pedimento",
    )
    x_clave_pedimento = fields.Char(
        string="Clave de pedimento (código)",
        related="x_clave_pedimento_id.code",
        store=True,
        readonly=True,
    )

    # --- Logística / embarque ---
    _MEDIO_TRANSPORTE_SELECTION = [
        ("01", "01 - Marítimo"),
        ("02", "02 - Ferroviario de doble estiba"),
        ("03", "03 - Carretero-ferroviario"),
        ("04", "04 - Aéreo"),
        ("05", "05 - Postal"),
        ("06", "06 - Ferroviario"),
        ("07", "07 - Carretero"),
        ("08", "08 - Tuber?a"),
        ("10", "10 - Cables"),
        ("11", "11 - Ductos"),
        ("12", "12 - Peatonal"),
        ("98", "98 - Sin presentaci?n f?sica"),
        ("99", "99 - Otros"),
    ]

    x_modo_transporte = fields.Selection(
        selection=[
            ("terrestre", "Terrestre"),
            ("aereo", "Aéreo"),
            ("maritimo", "Marítimo"),
            ("ferro", "Ferroviario"),
        ],
        string="Modo de transporte",
    )
    x_medio_transporte_salida = fields.Selection(
        selection=_MEDIO_TRANSPORTE_SELECTION,
        string="Medio transporte salida (cve)",
        help="Clave Ap?ndice 3 Anexo 22 para salida de aduana-secci?n de despacho.",
    )
    x_medio_transporte_arribo = fields.Selection(
        selection=_MEDIO_TRANSPORTE_SELECTION,
        string="Medio transporte arribo (cve)",
        help="Clave Ap?ndice 3 Anexo 22 para arribo a aduana-secci?n.",
    )
    x_medio_transporte_entrada_salida = fields.Selection(
        selection=_MEDIO_TRANSPORTE_SELECTION,
        string="Medio transporte entrada/salida (cve)",
        help="Clave Ap?ndice 3 Anexo 22 para entrada/salida a territorio nacional.",
    )
    x_origen_destino_mercancia = fields.Char(string="Origen/Destino mercancía (cve)")

    x_transportista_id = fields.Many2one(
        comodel_name="res.partner",
        string="Transportista",
        domain="[('x_contact_role','=','transportista')]",
    )
    x_transportista_rfc = fields.Char(
        string="RFC transportista",
        related="x_transportista_id.vat",
        readonly=True,
    )
    x_transportista_curp = fields.Char(
        string="CURP transportista",
        related="x_transportista_id.x_curp",
        readonly=True,
    )
    x_transportista_domicilio = fields.Char(
        string="Domicilio fiscal transportista",
        related="x_transportista_id.contact_address",
        readonly=True,
    )
    x_transportista_calle = fields.Char(
        string="Calle transportista",
        related="x_transportista_id.x_street_name",
        readonly=True,
    )
    x_transportista_num_ext = fields.Char(
        string="Num. exterior transportista",
        related="x_transportista_id.x_street_number_ext",
        readonly=True,
    )
    x_transportista_num_int = fields.Char(
        string="Num. interior transportista",
        related="x_transportista_id.x_street_number_int",
        readonly=True,
    )
    x_transportista_colonia = fields.Char(
        string="Colonia transportista",
        related="x_transportista_id.x_colonia",
        readonly=True,
    )
    x_transportista_municipio = fields.Char(
        string="Municipio transportista",
        related="x_transportista_id.x_municipio",
        readonly=True,
    )
    x_transportista_localidad = fields.Char(
        string="Localidad transportista",
        related="x_transportista_id.x_localidad",
        readonly=True,
    )
    x_transportista_estado_id = fields.Many2one(
        "res.country.state",
        string="Estado transportista",
        related="x_transportista_id.state_id",
        readonly=True,
    )
    x_transportista_cp = fields.Char(
        string="CP transportista",
        related="x_transportista_id.zip",
        readonly=True,
    )
    x_transporte_pais_id = fields.Many2one(
        comodel_name="res.country",
        string="País del medio de transporte",
    )
    x_transporte_identificador = fields.Char(string="Identificador de transporte")

    x_pais_origen_id = fields.Many2one(
        comodel_name="res.country",
        string="País de origen",
    )

    x_pais_destino_id = fields.Many2one(
        comodel_name="res.country",
        string="País de destino",
    )

    x_lugar_carga = fields.Char(string="Lugar de carga")
    x_lugar_descarga = fields.Char(string="Lugar de descarga")

    x_fecha_estimada_arribo = fields.Date(string="Fecha estimada de arribo")
    x_fecha_estimada_salida = fields.Date(string="Fecha estimada de salida")
    x_fecha_recoleccion = fields.Date(string="Fecha de recolección")
    x_fecha_entrega = fields.Date(string="Fecha de entrega")

    # --- Partes involucradas ---
    x_exportador_id = fields.Many2one("res.partner", string="Exportador")
    x_exportador_name = fields.Char(string="Exportador (texto)")

    x_importador_id = fields.Many2one("res.partner", string="Importador")
    x_importador_name = fields.Char(string="Importador (texto)")

    x_proveedor_id = fields.Many2one("res.partner", string="Proveedor")
    x_proveedor_name = fields.Char(string="Proveedor (texto)")

    x_consignatario_name = fields.Char(string="Consignatario")
    x_destinatario_final_name = fields.Char(string="Destinatario final")

    # --- Documentos / control documental ---
    x_docs_requeridos_ids = fields.Many2many(
        comodel_name="crm.tag",
        relation="crm_lead_docs_requeridos_tag_rel",
        column1="lead_id",
        column2="tag_id",
        string="Documentos requeridos",
    )

    x_docs_faltantes_text = fields.Text(string="Documentos faltantes")
    x_bl_file = fields.Binary(string="Archivo B/L (PDF)")
    x_bl_filename = fields.Char(string="Nombre archivo B/L")
    x_bl_last_read = fields.Datetime(string="Ultima lectura B/L", readonly=True)

    x_docs_completos = fields.Boolean(
        string="Documentación completa",
        compute="_compute_x_docs_completos",
        store=True,
    )

    x_visible_portal = fields.Boolean(string="Visible en portal", default=True)

    @api.onchange("x_agente_aduanal_id")
    def _onchange_x_agente_aduanal_id(self):
        for rec in self:
            agent = rec.x_agente_aduanal_id
            if not agent:
                continue
            rec.x_curp_agente = agent.x_curp or rec.x_curp_agente

    def write(self, vals):
        res = super().write(vals)
        if "x_bl_file" in vals and not self.env.context.get("skip_bl_autoparse"):
            for rec in self:
                rec._autofill_from_bl(onchange_mode=False)
        return res
    
    @api.onchange("x_modo_transporte")
    def _onchange_x_modo_transporte_set_default_codes(self):
        """Sugiere claves Ap?ndice 3 cuando se elige modo general."""
        mapping = {
            "maritimo": "01",
            "aereo": "04",
            "ferro": "06",
            "terrestre": "07",
        }
        code = mapping.get(self.x_modo_transporte)
        if not code:
            return
        if not self.x_medio_transporte_salida:
            self.x_medio_transporte_salida = code
        if not self.x_medio_transporte_arribo:
            self.x_medio_transporte_arribo = code
        if not self.x_medio_transporte_entrada_salida:
            self.x_medio_transporte_entrada_salida = code

    @api.onchange("x_transportista_id")
    def _onchange_x_transportista_id(self):
        for rec in self:
            if rec.x_transportista_id and not rec.x_transporte_pais_id:
                rec.x_transporte_pais_id = rec.x_transportista_id.country_id

    def action_generate_pedimento_xml(self):
        self.ensure_one()
        
        # Generamos una estructura simplificada del Anexo 22 para el MVP
        # Usamos los campos que ya tienes en tu vista
        xml_data = f"""<?xml version="1.0" encoding="UTF-8"?>
    <archivo_validador_aduana>
        <registro_501_datos_generales>
            <aduana_seccion>{self.x_aduana or ''}</aduana_seccion>
            <patente>{self.x_patente_agente or ''}</patente>
            <clave_pedimento>{self.x_clave_pedimento or ''}</clave_pedimento>
            <tipo_operacion>{self.x_tipo_operacion or ''}</tipo_operacion>
            <regimen>{self.x_regimen or ''}</regimen>
        </registro_501_datos_generales>
        <registro_505_facturas>
            <numero_factura>{self.x_proveedor_invoice_number or 'SIN FACTURA'}</numero_factura>
            <incoterm>{self.x_incoterm or ''}</incoterm>
            <valor_factura>{self.x_valor_factura or 0.0}</valor_factura>
            <moneda>{self.x_currency_id.name or 'MXN'}</moneda>
        </registro_505_facturas>
        <logistica>
            <transporte>{self.x_modo_transporte or ''}</transporte>
            <bultos>{self.x_bultos or 0}</bultos>
            <peso_bruto>{self.x_peso_bruto or 0.0}</peso_bruto>
        </logistica>
    </archivo_validador_aduana>
    """

        # Codificación a Base64 para descarga
        xml_base64 = base64.b64encode(xml_data.encode('utf-8'))
        
        # Crear el adjunto en Odoo
        attachment = self.env['ir.attachment'].create({
            'name': f'XML_Aduana_{self.x_folio_operacion or "SIN_FOLIO"}.xml',
            'type': 'binary',
            'datas': xml_base64,
            'mimetype': 'application/xml',
        })

        # Acción para descargar inmediatamente
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _extract_bl_pdf_text(self, pdf_bytes):
        if not PdfReader:
            raise UserError(_("Falta dependencia PyPDF2 en el servidor para leer PDF de B/L."))
        reader = PdfReader(io.BytesIO(pdf_bytes))
        chunks = []
        for page in reader.pages[:3]:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks)

    def _parse_bl_text(self, text):
        clean = re.sub(r"[ \t]+", " ", text or "")

        def _pick(patterns):
            for pat in patterns:
                m = re.search(pat, clean, re.IGNORECASE | re.MULTILINE)
                if m:
                    return (m.group(1) or "").strip()
            return False

        # Container number can come glued with "/40'" or other chars.
        container = False
        for tok in re.findall(r"[A-Z0-9'/-]+", clean.upper()):
            candidate = re.sub(r"[^A-Z0-9]", "", tok)
            if re.match(r"^[A-Z]{4}\d{7}$", candidate):
                container = candidate
                break

        return {
            "bl_no": _pick([
                r"\bB/?L\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-]+)",
                r"\bMBL\s*[:#]?\s*([A-Z0-9\-]+)",
                r"\bMASTER\s*B/?L\s*[:#]?\s*([A-Z0-9\-]+)",
            ]),
            "booking": _pick([
                r"\bBOOKING(?:\s*NO\.?)?\s*[:#]?\s*([A-Z0-9\-]+)",
            ]),
            "container": container,
            "seal": _pick([r"\b(?:SEAL\s*NO\.?\s*[:#]?\s*|/)([A-Z0-9]{6,})\b"]),
            "kgs": _pick([r"(\d{1,6}(?:\.\d{1,3})?)\s*KGS\b"]),
            "cbm": _pick([r"(\d+(?:\.\d+)?)\s*CBM\b"]),
            "bultos": _pick([
                r"/\s*(\d+)\s+[A-Z ]{2,20}/",
                r"\b(\d+)\s+(?:WOODEN\s+CASES?|PACKAGES?|PKGS?)\b",
            ]),
            "loading": _pick([r"Port of Loading\s*([A-Z0-9 ,\-\(\)]+)"]),
            "discharge": _pick([r"Port of discharge:\s*Place of delivery\s*([A-Z0-9 ,\-\(\)\/]+)"]),
            "vessel": _pick([r"Ocean Vessel\s+Voy\.?No\.\s+Port of Loading\s*([A-Z0-9 .,\-\(\)]+)"]),
        }

    def action_read_bl(self):
        self.ensure_one()
        if not self.x_bl_file:
            raise UserError(_("Sube primero el archivo B/L en PDF en el lead."))

        self._autofill_from_bl(onchange_mode=False, raise_if_empty=True)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("B/L procesado"),
                "message": _("Campos logísticos del lead actualizados. Al crear pedimento se arrastran desde aquí."),
                "type": "success",
                "sticky": False,
            },
        }

    @api.onchange("x_bl_file")
    def _onchange_x_bl_file_autoread(self):
        for rec in self:
            rec._autofill_from_bl(onchange_mode=True)

    def _autofill_from_bl(self, onchange_mode=False, raise_if_empty=False):
        self.ensure_one()
        if not self.x_bl_file:
            return
        try:
            pdf_bytes = base64.b64decode(self.x_bl_file)
            parsed = self._parse_bl_text(self._extract_bl_pdf_text(pdf_bytes))
        except Exception:
            _logger.exception("B/L parse error on lead %s (%s)", self.id, self.name)
            if raise_if_empty:
                raise
            return

        vals = self._bl_vals_from_parsed(parsed)
        if not vals:
            _logger.warning("B/L parsed without mapped values on lead %s (%s).", self.id, self.name)
            if raise_if_empty:
                raise UserError(_("No se detectaron datos utiles en el B/L. Revisa calidad del PDF."))
            return

        missing = [k for k, v in parsed.items() if not v and k in ("bl_no", "booking", "container", "seal", "bultos", "kgs", "cbm")]
        if missing:
            _logger.warning("B/L parse parcial lead %s: faltantes=%s", self.id, ",".join(missing))
        _logger.info("B/L parse lead %s: extraidos=%s", self.id, ",".join(sorted(vals.keys())))

        vals["x_bl_last_read"] = fields.Datetime.now()
        if onchange_mode:
            for key, value in vals.items():
                self[key] = value
        else:
            self.with_context(skip_bl_autoparse=True).write(vals)

    def _bl_vals_from_parsed(self, parsed):
        vals = {}
        if parsed.get("bl_no"):
            vals["x_guia_manifiesto"] = parsed["bl_no"]
            vals["x_tipo_guia"] = "M"
        if parsed.get("booking"):
            vals["x_booking"] = parsed["booking"]
        if parsed.get("container"):
            vals["x_num_contenedor"] = parsed["container"]
        if parsed.get("seal"):
            vals["x_num_sello"] = parsed["seal"]
        if parsed.get("bultos"):
            try:
                vals["x_bultos"] = int(float(parsed["bultos"]))
            except Exception:
                pass
        if parsed.get("kgs"):
            try:
                vals["x_peso_bruto"] = float(parsed["kgs"])
            except Exception:
                pass
        if parsed.get("cbm"):
            try:
                vals["x_volumen_cbm"] = float(parsed["cbm"])
            except Exception:
                pass
        if parsed.get("loading"):
            vals["x_lugar_carga"] = parsed["loading"]
        if parsed.get("discharge"):
            vals["x_lugar_descarga"] = parsed["discharge"]
        if parsed.get("vessel"):
            note = f"B/L vessel/voy: {parsed['vessel']}"
            vals["description"] = f"{(self.description or '').strip()}\n{note}".strip()
        return vals

    @api.depends("x_docs_faltantes_text")
    def _compute_x_docs_completos(self):
        for rec in self:
            rec.x_docs_completos = not bool((rec.x_docs_faltantes_text or "").strip())

    # --- Valores y cantidades ---
    x_valor_factura = fields.Monetary(
        string="Valor factura (total)",
        currency_field="x_currency_id",
    )

    x_valor_aduana_estimado = fields.Monetary(
        string="Valor aduana (estimado)",
        currency_field="x_currency_id",
    )

    x_bultos = fields.Integer(string="Bultos", compute="_compute_x_totales_partidas", store=True)
    x_peso_bruto = fields.Float(string="Peso bruto", compute="_compute_x_totales_partidas", store=True)
    x_peso_neto = fields.Float(string="Peso neto", compute="_compute_x_totales_partidas", store=True)
    x_volumen_cbm = fields.Float(string="Volumen (CBM)")

    x_tipo_empaque = fields.Selection(
        selection=[
            ("cajas", "Cajas"),
            ("tarimas", "Tarimas"),
            ("granel", "Granel"),
            ("otro", "Otro"),
        ],
        string="Tipo de empaque",
    )

    x_numero_paquetes = fields.Integer(string="Número de paquetes")

    # --- Transporte / guías ---
    x_tipo_guia = fields.Selection(
        selection=[
            ("M", "M - Master"),
            ("H", "H - House"),
        ],
        string="Identificador de guía",
    )
    x_guia_manifiesto = fields.Char(string="Guía o manifiesto", size=20)
    x_booking = fields.Char(string="Booking")
    x_tipo_contenedor_id = fields.Many2one(
        comodel_name="mx.ped.tipo.contenedor",
        string="Tipo de contenedor/vehículo",
        domain=[("active", "=", True)],
    )
    x_num_contenedor = fields.Char(string="Número de contenedor")
    x_num_sello = fields.Char(string="Número de sello")

    # --- CFDI / documento equivalente ---
    x_cfdi_fecha = fields.Date(string="Fecha CFDI / doc equivalente")
    x_cfdi_numero = fields.Char(string="Número CFDI / acuse")
    x_cfdi_termino_facturacion = fields.Char(string="Término facturación")
    x_cfdi_moneda_id = fields.Many2one("res.currency", string="Moneda CFDI")
    x_cfdi_valor_usd = fields.Monetary(
        string="Valor total USD (CFDI)",
        currency_field="x_currency_id",
    )
    x_cfdi_valor_moneda = fields.Monetary(
        string="Valor total CFDI (moneda)",
        currency_field="x_cfdi_moneda_id",
    )
    x_cfdi_pais_id = fields.Many2one("res.country", string="País CFDI")
    x_cfdi_estado_id = fields.Many2one("res.country.state", string="Entidad CFDI")
    x_cfdi_id_fiscal = fields.Char(string="Identificación fiscal proveedor/comprador")

    # --- Pedimento / resultado (legacy/resumen) ---
    x_num_pedimento = fields.Char(string="Número de pedimento")
    x_fecha_pago_pedimento = fields.Date(string="Fecha de pago pedimento")
    x_fecha_liberacion = fields.Date(string="Fecha de liberación")

    x_semaforo = fields.Selection(
        selection=[
            ("verde", "Verde"),
            ("rojo", "Rojo"),
        ],
        string="Semáforo",
    )

    x_incidente_text = fields.Text(string="Incidencias")

    # --- Costos / facturación agencia ---
    x_cotizacion_total = fields.Monetary(
        string="Cotización total",
        currency_field="x_currency_id",
    )

    x_costo_estimado = fields.Monetary(
        string="Costo estimado",
        currency_field="x_currency_id",
    )

    x_factura_emitida = fields.Boolean(string="Factura emitida")
    x_factura_ref = fields.Char(string="Folio de factura")

    x_metodo_cobro = fields.Selection(
        selection=[
            ("transferencia", "Transferencia"),
            ("efectivo", "Efectivo"),
            ("credito", "Crédito"),
            ("otro", "Otro"),
        ],
        string="Método de cobro",
    )

    x_pago_confirmado = fields.Boolean(string="Pago confirmado")

    # --- Importación (extras) ---
    x_purchase_order = fields.Char(string="PO / Orden de compra")
    x_proveedor_invoice_number = fields.Char(string="Factura proveedor (número)")
    x_condiciones_pago = fields.Text(string="Condiciones de pago")

    x_tipo_compra = fields.Selection(
        selection=[
            ("materia_prima", "Materia prima"),
            ("refaccion", "Refacción"),
            ("maquinaria", "Maquinaria"),
            ("consumo", "Consumo"),
            ("otro", "Otro"),
        ],
        string="Tipo de compra",
    )

    x_override_estimados = fields.Boolean(
        string="Override estimados",
        help="Permite capturar impuestos estimados manuales en cabecera.",
    )
    x_iva_estimado_manual = fields.Monetary(string="IVA estimado manual", currency_field="x_currency_id")
    x_igi_estimado_manual = fields.Monetary(string="IGI estimado manual", currency_field="x_currency_id")
    x_dta_estimado_manual = fields.Monetary(string="DTA estimado manual", currency_field="x_currency_id")
    x_prv_estimado_manual = fields.Monetary(string="PRV estimado manual", currency_field="x_currency_id")

    x_operacion_line_ids = fields.One2many(
        comodel_name="crm.lead.operacion.line",
        inverse_name="lead_id",
        string="Mercancias / Partidas",
        copy=True,
    )
    x_resumen_permisos = fields.Char(string="Resumen permisos", compute="_compute_x_import_summaries", store=False)
    x_resumen_rrna = fields.Char(string="Resumen RRNA", compute="_compute_x_import_summaries", store=False)
    x_resumen_noms = fields.Text(string="Resumen NOMs", compute="_compute_x_import_summaries", store=False)
    x_resumen_etiquetado = fields.Char(
        string="Resumen etiquetado",
        compute="_compute_x_import_summaries",
        store=False,
    )

    # Legacy cabecera: se conservan para compatibilidad y migracion.
    x_permisos_ids = fields.Many2many(
        comodel_name="crm.tag",
        relation="crm_lead_permisos_tag_rel",
        column1="lead_id",
        column2="tag_id",
        string="Permisos / regulaciones (import) [Legacy]",
    )

    x_normas_noms_text = fields.Text(string="NOM / Normas aplicables [Legacy]")
    x_etiquetado = fields.Boolean(string="Requiere etiquetado [Legacy]")

    x_cumplimiento_noms = fields.Selection(
        selection=[
            ("pendiente", "Pendiente"),
            ("cumple", "Cumple"),
            ("no_aplica", "No aplica"),
        ],
        string="Cumplimiento NOM [Legacy]",
    )

    x_certificado_origen = fields.Boolean(string="Certificado de origen")
    x_tratado_aplicable = fields.Char(string="Tratado aplicable")
    x_pedimento_rectificacion = fields.Boolean(string="Pedimento en rectificación")

    x_iva_estimado = fields.Monetary(
        string="IVA estimado",
        currency_field="x_currency_id",
        compute="_compute_x_impuestos_estimados",
        inverse="_inverse_x_impuestos_estimados",
        store=True,
    )
    x_igi_estimado = fields.Monetary(
        string="IGI estimado",
        currency_field="x_currency_id",
        compute="_compute_x_impuestos_estimados",
        inverse="_inverse_x_impuestos_estimados",
        store=True,
    )
    x_dta_estimado = fields.Monetary(
        string="DTA estimado",
        currency_field="x_currency_id",
        compute="_compute_x_impuestos_estimados",
        inverse="_inverse_x_impuestos_estimados",
        store=True,
    )
    x_prv_estimado = fields.Monetary(
        string="PRV estimado",
        currency_field="x_currency_id",
        compute="_compute_x_impuestos_estimados",
        inverse="_inverse_x_impuestos_estimados",
        store=True,
    )

    x_total_impuestos_estimado = fields.Monetary(
        string="Total impuestos (estimado)",
        currency_field="x_currency_id",
        compute="_compute_x_impuestos_estimados",
        inverse="_inverse_x_impuestos_estimados",
        store=True,
    )

    x_total_pagado_real = fields.Monetary(
        string="Total pagado (real)",
        currency_field="x_currency_id",
    )

    x_recinto_fiscalizado = fields.Char(string="Recinto fiscalizado")
    x_almacenaje = fields.Boolean(string="Almacenaje")
    x_citas_almacen = fields.Text(string="Citas / almacén")

    x_transportista_entrega = fields.Many2one(
        comodel_name="res.partner",
        string="Transportista (entrega)",
    )

    x_direccion_entrega_final = fields.Text(string="Dirección entrega final")

    # --- Exportación (extras) ---
    x_sales_order = fields.Char(string="SO / Orden de venta")
    x_invoice_export_number = fields.Char(string="Factura exportación (número)")

    x_cliente_extranjero_name = fields.Char(string="Cliente extranjero")
    x_direccion_destino_final = fields.Text(string="Dirección destino final")
    x_condiciones_venta = fields.Text(string="Condiciones de venta")

    x_regulaciones_exportacion_ids = fields.Many2many(
        comodel_name="crm.tag",
        relation="crm_lead_reg_exp_tag_rel",
        column1="lead_id",
        column2="tag_id",
        string="Regulaciones (export)",
    )

    x_certificados_exportacion_ids = fields.Many2many(
        comodel_name="crm.tag",
        relation="crm_lead_cert_exp_tag_rel",
        column1="lead_id",
        column2="tag_id",
        string="Certificados (export)",
    )

    x_licencia_exportacion = fields.Boolean(string="Licencia de exportación")

    x_motivo_exportacion = fields.Selection(
        selection=[
            ("venta", "Venta"),
            ("retorno", "Retorno"),
            ("muestra", "Muestra"),
            ("reparacion", "Reparación"),
            ("otro", "Otro"),
        ],
        string="Motivo de exportación",
    )

    x_punto_salida = fields.Char(string="Punto de salida")

    x_transportista_salida = fields.Many2one(
        comodel_name="res.partner",
        string="Transportista (salida)",
        domain="[('x_contact_role','=','transportista')]",
    )

    x_fecha_cruce = fields.Date(string="Fecha de cruce")
    x_fecha_zarpe = fields.Date(string="Fecha de zarpe")
    x_fecha_vuelo = fields.Date(string="Fecha de vuelo")

    x_prueba_entrega = fields.Boolean(string="Prueba de entrega (POD)")

    # =========================================================
    # ✅ LO CORRECTO: CRM como EXPEDIENTE + RELACIÓN A PEDIMENTOS
    # =========================================================

    x_ped_operacion_ids = fields.One2many(
        comodel_name="mx.ped.operacion",
        inverse_name="lead_id",
        string="Pedimentos / Operaciones",
        copy=False,
    )

    x_ped_operacion_count = fields.Integer(
        compute="_compute_x_ped_operacion_count",
        string="Pedimentos",
    )

    x_last_ped_operacion_id = fields.Many2one(
        comodel_name="mx.ped.operacion",
        compute="_compute_x_last_ped_operacion_id",
        string="Último pedimento",
        store=True,
    )

        # =========================================================
    # ✅ RESUMEN (READ-ONLY) DEL ÚLTIMO PEDIMENTO PARA EL FORM DEL LEAD
    # =========================================================

    x_ped_num_pedimento = fields.Char(
        string="Número de pedimento (último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )
    x_ped_fecha_pago = fields.Date(
        string="Fecha de pago (último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )
    x_ped_semaforo = fields.Selection(
        selection=[("verde", "Verde"), ("rojo", "Rojo")],
        string="Semáforo (último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )
    x_ped_fecha_liberacion = fields.Date(
        string="Fecha de liberación (último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )

    x_ped_aduana_clave = fields.Char(
        string="Aduana (clave, último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )
    x_ped_patente = fields.Char(
        string="Patente (último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )
    x_ped_clave_pedimento = fields.Char(
        string="Clave pedimento (último)",
        compute="_compute_x_ped_resumen",
        store=True,
        readonly=True,
    )

    @api.depends(
        "x_last_ped_operacion_id",
        "x_last_ped_operacion_id.pedimento_numero",
        "x_last_ped_operacion_id.fecha_pago",
        "x_last_ped_operacion_id.semaforo",
        "x_last_ped_operacion_id.fecha_liberacion",
        "x_last_ped_operacion_id.aduana_clave",
        "x_last_ped_operacion_id.patente",
        "x_last_ped_operacion_id.clave_pedimento",
    )
    def _compute_x_ped_resumen(self):
        for rec in self:
            op = rec.x_last_ped_operacion_id
            rec.x_ped_num_pedimento = op.pedimento_numero if op else False
            rec.x_ped_fecha_pago = op.fecha_pago if op else False
            rec.x_ped_semaforo = op.semaforo if op else False
            rec.x_ped_fecha_liberacion = op.fecha_liberacion if op else False
            rec.x_ped_aduana_clave = op.aduana_clave if op else False
            rec.x_ped_patente = op.patente if op else False
            rec.x_ped_clave_pedimento = op.clave_pedimento if op else False

    @api.depends("x_ped_operacion_ids")
    def _compute_x_ped_operacion_count(self):
        counts = self.env["mx.ped.operacion"].read_group(
            [("lead_id", "in", self.ids)],
            ["lead_id"],
            ["lead_id"],
        )
        mapped = {c["lead_id"][0]: c["lead_id_count"] for c in counts}
        for rec in self:
            rec.x_ped_operacion_count = mapped.get(rec.id, 0)

    @api.depends("x_ped_operacion_ids")
    def _compute_x_last_ped_operacion_id(self):
        for rec in self:
            rec.x_last_ped_operacion_id = rec.x_ped_operacion_ids.sorted(
                key=lambda r: r.create_date or fields.Datetime.now(),
                reverse=True
            )[:1] or False

    @api.depends(
        "x_operacion_line_ids",
        "x_operacion_line_ids.permiso_ids",
        "x_operacion_line_ids.rrna_ids",
        "x_operacion_line_ids.nom_ids",
        "x_operacion_line_ids.labeling_required",
    )
    def _compute_x_import_summaries(self):
        for rec in self:
            permiso_names = sorted({name for name in rec.x_operacion_line_ids.mapped("permiso_ids.name") if name})
            rrna_names = sorted({name for name in rec.x_operacion_line_ids.mapped("rrna_ids.name") if name})
            nom_names = sorted({name for name in rec.x_operacion_line_ids.mapped("nom_ids.code") if name})
            tagged = len(rec.x_operacion_line_ids.filtered("labeling_required"))
            total = len(rec.x_operacion_line_ids)

            rec.x_resumen_permisos = ", ".join(permiso_names) if permiso_names else "Sin permisos"
            rec.x_resumen_rrna = ", ".join(rrna_names) if rrna_names else "Sin RRNA"
            rec.x_resumen_noms = ", ".join(nom_names) if nom_names else "Sin NOMs"
            rec.x_resumen_etiquetado = f"{tagged}/{total} con etiquetado" if total else "Sin partidas"

    @api.depends(
        "x_operacion_line_ids",
        "x_operacion_line_ids.packages_line",
        "x_operacion_line_ids.gross_weight_line",
        "x_operacion_line_ids.net_weight_line",
        "x_operacion_line_ids.value_mxn",
    )
    def _compute_x_totales_partidas(self):
        for rec in self:
            lines = rec.x_operacion_line_ids
            rec.x_bultos = int(sum(lines.mapped("packages_line") or [0]))
            rec.x_peso_bruto = sum(lines.mapped("gross_weight_line") or [0.0])
            rec.x_peso_neto = sum(lines.mapped("net_weight_line") or [0.0])
            rec.x_peso_kg = rec.x_peso_bruto
            rec.x_valor_mercancia = sum(lines.mapped("value_mxn") or [0.0])

    @api.depends(
        "x_override_estimados",
        "x_iva_estimado_manual",
        "x_igi_estimado_manual",
        "x_dta_estimado_manual",
        "x_prv_estimado_manual",
        "x_operacion_line_ids.iva_estimado",
        "x_operacion_line_ids.igi_estimado",
        "x_operacion_line_ids.dta_estimado",
        "x_operacion_line_ids.prv_estimado",
    )
    def _compute_x_impuestos_estimados(self):
        for rec in self:
            if rec.x_override_estimados:
                rec.x_iva_estimado = rec.x_iva_estimado_manual
                rec.x_igi_estimado = rec.x_igi_estimado_manual
                rec.x_dta_estimado = rec.x_dta_estimado_manual
                rec.x_prv_estimado = rec.x_prv_estimado_manual
            else:
                rec.x_iva_estimado = sum(rec.x_operacion_line_ids.mapped("iva_estimado"))
                rec.x_igi_estimado = sum(rec.x_operacion_line_ids.mapped("igi_estimado"))
                rec.x_dta_estimado = sum(rec.x_operacion_line_ids.mapped("dta_estimado"))
                rec.x_prv_estimado = sum(rec.x_operacion_line_ids.mapped("prv_estimado"))
            rec.x_total_impuestos_estimado = (
                rec.x_iva_estimado + rec.x_igi_estimado + rec.x_dta_estimado + rec.x_prv_estimado
            )

    def _inverse_x_impuestos_estimados(self):
        for rec in self:
            if not rec.x_override_estimados:
                continue
            rec.x_iva_estimado_manual = rec.x_iva_estimado
            rec.x_igi_estimado_manual = rec.x_igi_estimado
            rec.x_dta_estimado_manual = rec.x_dta_estimado
            rec.x_prv_estimado_manual = rec.x_prv_estimado

    def action_migrar_importacion_legacy(self):
        nom_model = self.env["mx.nom"].sudo()
        permiso_model = self.env["mx.permiso"].sudo()
        rrna_model = self.env["mx.rrna"].sudo()
        for rec in self:
            if rec.x_operacion_line_ids:
                lines = rec.x_operacion_line_ids
            else:
                line_vals = {
                    "lead_id": rec.id,
                    "name": rec.name or _("Partida"),
                    "nom_compliance_status": rec.x_cumplimiento_noms or "pendiente",
                }
                lines = self.env["crm.lead.operacion.line"].create(line_vals)

            if rec.x_permisos_ids:
                permiso_ids = []
                rrna_ids = []
                for tag in rec.x_permisos_ids:
                    code = (tag.name or "").strip()[:64]
                    permiso = permiso_model.search([("code", "=", code)], limit=1)
                    if not permiso:
                        permiso = permiso_model.create({"code": code or "LEGACY", "name": tag.name or code})
                    permiso_ids.append(permiso.id)

                    rrna = rrna_model.search([("code", "=", code)], limit=1)
                    if not rrna:
                        rrna = rrna_model.create({"code": code or "LEGACY", "name": tag.name or code})
                    rrna_ids.append(rrna.id)
                lines.write({"permiso_ids": [(6, 0, permiso_ids)]})
                lines.write({"rrna_ids": [(6, 0, rrna_ids)]})

            text_nom = (rec.x_normas_noms_text or "").strip()
            if text_nom:
                code = text_nom.split()[0][:64]
                nom = nom_model.search([("code", "=", code)], limit=1)
                if not nom:
                    nom = nom_model.create({
                        "code": code or "LEGACY_NOM",
                        "name": text_nom[:255],
                        "requires_labeling": bool(rec.x_etiquetado),
                    })
                lines.write({"nom_ids": [(4, nom.id)]})
            if rec.x_etiquetado and not text_nom:
                lines.write({"notes_regulatorias": _("Legacy: requiere etiquetado en cabecera.")})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Migracion importacion"),
                "message": _("Se migraron datos legacy de cabecera a partidas."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_crear_pedimento(self):
        """
        Crea una cabecera (mx.ped.operacion) desde el lead copiando datos base.
        El lead sigue siendo el EXPEDIENTE; el pedimento vive en su modelo.
        """
        self.ensure_one()

        currency = self.x_currency_id or self.env.company.currency_id

        # nombre humano del pedimento (si no hay numero aún)
        name = self.x_num_pedimento or self.x_folio_operacion or self.name or _("Operación")

        op = self.env["mx.ped.operacion"].create({
            "lead_id": self.id,
            "name": name,

            "tipo_operacion": self.x_tipo_operacion,
            "regimen": self.x_regimen,
            "incoterm": self.x_incoterm,

            "aduana_seccion_despacho_id": self.x_aduana_seccion_despacho_id.id or False,
            "aduana_clave": (self.x_aduana or ""),
            "aduana_seccion_entrada_salida_id": self.x_aduana_seccion_entrada_salida_id.id or False,
            "acuse_validacion": (self.x_acuse_validacion or ""),
            "agente_aduanal_id": self.x_agente_aduanal_id.id or False,
            "patente": (self.x_agente_aduanal_id.x_patente_aduanal or self.x_patente_agente or ""),
            "curp_agente": (self.x_curp_agente or ""),
            "clave_pedimento_id": self.x_clave_pedimento_id.id or False,

            "currency_id": currency.id,

            "pedimento_numero": (self.x_num_pedimento or ""),
            "fecha_pago": self.x_fecha_pago_pedimento,
            "fecha_liberacion": self.x_fecha_liberacion,
            "semaforo": self.x_semaforo,
            "observaciones": (self.x_incidente_text or ""),
        })

        lineas = self.x_operacion_line_ids
        if not lineas:
            lineas = self.env["crm.lead.operacion.line"].create({
                "lead_id": self.id,
                "numero_partida": 1,
                "name": self.name or _("Partida"),
            })

        for idx, line in enumerate(lineas.sorted(lambda l: (l.numero_partida or 999999, l.sequence or 0, l.id)), start=1):
            self.env["mx.ped.partida"].create({
                "operacion_id": op.id,
                "numero_partida": line.numero_partida or idx,
                "fraccion_id": line.fraccion_id.id or False,
                "fraccion_arancelaria": line.fraccion_arancelaria,
                "uom_id": line.uom_id.id or False,
                "quantity": line.quantity,
                "packages_line": line.packages_line,
                "gross_weight_line": line.gross_weight_line,
                "net_weight_line": line.net_weight_line,
                "value_usd": line.value_usd,
                "precio_unitario": line.precio_unitario,
                "nico": line.nico,
                "descripcion": line.name,
                "nom_ids": [(6, 0, line.nom_ids.ids)],
                "permiso_ids": [(6, 0, line.permiso_ids.ids)],
                "rrna_ids": [(6, 0, line.rrna_ids.ids)],
                "labeling_required": line.labeling_required,
                "nom_compliance_status": line.nom_compliance_status,
                "docs_reference": line.docs_reference,
                "notes_regulatorias": line.notes_regulatorias,
                "igi_estimado": line.igi_estimado,
                "iva_estimado": line.iva_estimado,
                "dta_estimado": line.dta_estimado,
                "prv_estimado": line.prv_estimado,
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Pedimento"),
            "res_model": "mx.ped.operacion",
            "view_mode": "form",
            "res_id": op.id,
            "target": "current",
        }

    @api.model_create_multi
    def create(self, vals_list):
        has_bl_file = [bool(vals.get("x_bl_file")) for vals in vals_list]
        create_flags = [bool(vals.pop("x_create_pedimento", False)) for vals in vals_list]
        leads = super().create(vals_list)
        for i, lead in enumerate(leads):
            if has_bl_file[i]:
                lead._autofill_from_bl(onchange_mode=False)
        for i, lead in enumerate(leads):
            # Solo crea automaticamente si el flujo lo pide por contexto/flag.
            create_flag = self.env.context.get("create_pedimento") or create_flags[i]
            if not create_flag or lead.x_pedimento_id:
                continue
            ped = self.env["aduana.pedimento"].create({
                "lead_id": lead.id,
                "name": lead.name or _("Nuevo"),
            })
            lead.x_pedimento_id = ped.id
        return leads

    def action_open_aduana_pedimento(self):
        self.ensure_one()
        if not self.x_pedimento_id:
            ped = self.env["aduana.pedimento"].create({
                "lead_id": self.id,
                "name": self.name or _("Nuevo"),
            })
            self.x_pedimento_id = ped.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Pedimento"),
            "res_model": "aduana.pedimento",
            "view_mode": "form",
            "res_id": self.x_pedimento_id.id,
            "target": "current",
        }


class CrmLeadOperacionLine(models.Model):
    _name = "crm.lead.operacion.line"
    _description = "Caso - Mercancia / Partida Importacion"
    _order = "numero_partida asc, sequence asc, id asc"

    lead_id = fields.Many2one("crm.lead", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    numero_partida = fields.Integer(string="Numero de partida")
    name = fields.Char(string="Descripcion", required=True)
    fraccion_id = fields.Many2one(
        "mx.ped.fraccion",
        string="Fraccion arancelaria",
        domain=[("active", "=", True)],
    )
    nico_id = fields.Many2one(
        "mx.nico",
        string="NICO",
        domain="[('fraccion_id', '=', fraccion_id)]",
    )
    fraccion_arancelaria = fields.Char(string="Fraccion (snapshot)", size=10)
    nico = fields.Char(string="NICO (snapshot)", size=2)
    quantity = fields.Float(string="Cantidad", digits=(16, 6), default=1.0)
    uom_id = fields.Many2one("mx.ped.um", string="Unidad de medida")
    packages_line = fields.Integer(string="Bultos", default=0)
    gross_weight_line = fields.Float(string="Peso bruto", digits=(16, 3))
    net_weight_line = fields.Float(string="Peso neto", digits=(16, 3))
    value_usd = fields.Float(string="Valor USD", digits=(16, 2))
    precio_unitario = fields.Float(string="Precio unitario", digits=(16, 6))
    value_mxn = fields.Float(
        string="Valor MXN",
        digits=(16, 2),
        compute="_compute_value_mxn",
        store=True,
    )
    nom_ids = fields.Many2many(
        "mx.nom",
        "crm_lead_operacion_line_nom_rel",
        "line_id",
        "nom_id",
        string="NOM",
    )
    permiso_ids = fields.Many2many(
        "mx.permiso",
        "crm_lead_operacion_line_permiso_rel",
        "line_id",
        "permiso_id",
        string="Permisos",
    )
    rrna_ids = fields.Many2many(
        "mx.rrna",
        "crm_lead_operacion_line_rrna_rel",
        "line_id",
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
    currency_id = fields.Many2one(
        related="lead_id.x_currency_id",
        string="Moneda",
        readonly=True,
    )
    igi_estimado = fields.Monetary(
        string="IGI estimado",
        currency_field="currency_id",
        compute="_compute_impuestos_estimados",
        store=True,
        readonly=True,
    )
    iva_estimado = fields.Monetary(
        string="IVA estimado",
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("numero_partida"):
                continue
            lead_id = vals.get("lead_id")
            if not lead_id:
                continue
            last = self.search([("lead_id", "=", lead_id)], order="numero_partida desc, id desc", limit=1)
            vals["numero_partida"] = max(last.numero_partida or 0, 0) + 1
        return super().create(vals_list)

    @api.constrains("lead_id", "numero_partida")
    def _check_numero_partida(self):
        for rec in self:
            if not rec.numero_partida:
                continue
            if rec.numero_partida <= 0:
                raise ValidationError(_("El numero de partida debe ser mayor a cero."))
            dup = self.search_count([
                ("id", "!=", rec.id),
                ("lead_id", "=", rec.lead_id.id),
                ("numero_partida", "=", rec.numero_partida),
            ])
            if dup:
                raise ValidationError(_("El numero de partida debe ser unico por lead."))

    @api.depends("nom_ids", "nom_ids.requires_labeling", "fraccion_id.requires_labeling_default")
    def _compute_labeling_required(self):
        for rec in self:
            rec.labeling_required = bool(
                rec.fraccion_id.requires_labeling_default
                or any(rec.nom_ids.mapped("requires_labeling"))
            )

    @api.depends("value_usd", "lead_id.x_tipo_cambio")
    def _compute_value_mxn(self):
        for rec in self:
            tc = rec.lead_id.x_tipo_cambio or 0.0
            rec.value_mxn = (rec.value_usd or 0.0) * tc

    @api.depends(
        "fraccion_id",
        "fraccion_id.tasa_ids",
        "lead_id.x_tipo_operacion",
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
                tipo = "importacion" if rec.lead_id.x_tipo_operacion != "exportacion" else "exportacion"
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
                raise UserError(_("La linea requiere cantidad."))
            if rec.quantity <= 0:
                raise UserError(_("La cantidad por linea debe ser mayor a cero."))
            if rec.value_usd is False or rec.value_usd is None or rec.value_usd <= 0:
                raise UserError(_("La linea requiere valor USD mayor a cero."))

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
            if not rec.name:
                rec.name = fraccion.name
            if fraccion.um_id:
                rec.uom_id = fraccion.um_id.id
            rec.nom_ids = [(6, 0, fraccion.nom_default_ids.ids)]
            rec.permiso_ids = [(6, 0, fraccion.permiso_default_ids.ids)]
            rec.rrna_ids = [(6, 0, fraccion.rrna_default_ids.ids)]

    @api.onchange("nico_id")
    def _onchange_nico_id(self):
        for rec in self:
            rec.nico = rec.nico_id.code if rec.nico_id else (rec.fraccion_id.nico if rec.fraccion_id else False)

    def action_load_regulatory_defaults(self):
        for rec in self:
            fraccion = rec.fraccion_id
            if not fraccion:
                continue
            rec.nom_ids = [(6, 0, fraccion.nom_default_ids.ids)]
            rec.permiso_ids = [(6, 0, fraccion.permiso_default_ids.ids)]
            rec.rrna_ids = [(6, 0, fraccion.rrna_default_ids.ids)]
        return True

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
