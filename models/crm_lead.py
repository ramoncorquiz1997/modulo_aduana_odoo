# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import base64


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
    x_fraccion_arancelaria = fields.Char(string="Fracción arancelaria")

    x_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Moneda",
        default=lambda self: self.env.company.currency_id,
    )

    x_valor_mercancia = fields.Monetary(
        string="Valor mercancía",
        currency_field="x_currency_id",
    )

    x_peso_kg = fields.Float(string="Peso (kg)")
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
    x_patente_agente = fields.Char(string="Patente")
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
    x_fraccion_arancelaria_id = fields.Many2one(
        comodel_name="mx.ped.fraccion",
        string="Fracción arancelaria principal",
        domain=[("active", "=", True)],
    )
    x_fraccion_arancelaria_principal = fields.Char(string="Fracción arancelaria principal")
    x_descripcion_mercancia = fields.Text(string="Descripción de mercancía")

    # --- Logística / embarque ---
    _MEDIO_TRANSPORTE_SELECTION = [
        ("01", "01 - Mar?timo"),
        ("02", "02 - Ferroviario de doble estiba"),
        ("03", "03 - Carretero-ferroviario"),
        ("04", "04 - A?reo"),
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
            rec.x_patente_agente = agent.x_patente_aduanal or rec.x_patente_agente
            rec.x_curp_agente = agent.x_curp or rec.x_curp_agente
    
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

    @api.onchange("x_fraccion_arancelaria_id")
    def _onchange_x_fraccion_arancelaria_id(self):
        for rec in self:
            fraccion = rec.x_fraccion_arancelaria_id
            if not fraccion:
                continue
            rec.x_fraccion_arancelaria_principal = fraccion.code
            rec.x_descripcion_mercancia = fraccion.name

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

    x_bultos = fields.Integer(string="Bultos")
    x_peso_bruto = fields.Float(string="Peso bruto")
    x_peso_neto = fields.Float(string="Peso neto")
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
    x_bl_awb = fields.Char(string="BL / AWB (Master)")
    x_house_bl_awb = fields.Char(string="House BL / AWB")
    x_booking = fields.Char(string="Booking")
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

    x_permisos_ids = fields.Many2many(
        comodel_name="crm.tag",
        relation="crm_lead_permisos_tag_rel",
        column1="lead_id",
        column2="tag_id",
        string="Permisos / regulaciones (import)",
    )

    x_normas_noms_text = fields.Text(string="NOM / Normas aplicables")
    x_etiquetado = fields.Boolean(string="Requiere etiquetado")

    x_cumplimiento_noms = fields.Selection(
        selection=[
            ("pendiente", "Pendiente"),
            ("cumple", "Cumple"),
            ("no_aplica", "No aplica"),
        ],
        string="Cumplimiento NOM",
    )

    x_certificado_origen = fields.Boolean(string="Certificado de origen")
    x_tratado_aplicable = fields.Char(string="Tratado aplicable")
    x_pedimento_rectificacion = fields.Boolean(string="Pedimento en rectificación")

    x_iva_estimado = fields.Monetary(string="IVA estimado", currency_field="x_currency_id")
    x_igi_estimado = fields.Monetary(string="IGI estimado", currency_field="x_currency_id")
    x_dta_estimado = fields.Monetary(string="DTA estimado", currency_field="x_currency_id")
    x_prv_estimado = fields.Monetary(string="PRV estimado", currency_field="x_currency_id")

    x_total_impuestos_estimado = fields.Monetary(
        string="Total impuestos (estimado)",
        currency_field="x_currency_id",
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
        create_flags = [bool(vals.pop("x_create_pedimento", False)) for vals in vals_list]
        leads = super().create(vals_list)
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
