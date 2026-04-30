# -*- coding: utf-8 -*-
import base64
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter
from datetime import date, datetime
import xml.etree.ElementTree as ET

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


class MxPedOperacion(models.Model):
    _name = "mx.ped.operacion"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Pedimento / Operación Aduanera"
    _order = "create_date desc, id desc"
    _LAYOUT_EMPTY = "__LAYOUT_EMPTY__"

    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        string="Operación (Lead)",
        required=True,
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(string="Referencia", required=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    def action_open_full_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    # ==========================
    # Clasificación
    # ==========================
    tipo_operacion = fields.Selection(
        [("importacion", "Importación"), ("exportacion", "Exportación")],
        string="Tipo",
    )
    regimen = fields.Selection(
        [
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Depósito fiscal"),
            ("transito", "Tránsito"),
        ],
        string="Régimen",
    )
    incoterm = fields.Selection(
        [
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

    aduana_seccion_despacho_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana-seccion de despacho",
    )
    aduana_clave = fields.Char(string="Aduana (clave)")  # ej 070
    agente_aduanal_id = fields.Many2one(
        "res.partner",
        string="Agente aduanal",
        domain="[('x_contact_role','=','agente_aduanal')]",
    )
    patente = fields.Char(string="Patente")
    clave_pedimento_id = fields.Many2one(
        "mx.ped.clave",
        string="Clave pedimento",
    )

    clave_pedimento = fields.Char(
        string="Clave pedimento (código)",
        related="clave_pedimento_id.code",
        store=True,
        readonly=True,
    )
    tipo_movimiento = fields.Selection(
        [
            ("1", "1 - Pedimento nuevo"),
            ("2", "2 - Eliminación"),
            ("3", "3 - Desistimiento"),
            ("5", "5 - Informe Industria Automotriz"),
            ("6", "6 - Pedimento complementario"),
            ("7", "7 - Despacho anticipado"),
            ("8", "8 - Confirmación de pago"),
            ("9", "9 - Global complementario"),
        ],
        string="Tipo de movimiento",
        default="1",
    )
    es_rectificacion = fields.Boolean(
        string="Rectificacion",
        help="Usa esta marca cuando el movimiento 1 corresponda a rectificacion.",
    )
    modo_export_consolidado = fields.Selection(
        [
            ("pedimento_final", "Pedimento final"),
            ("por_remesa", "Por remesa"),
        ],
        string="Modo export consolidado",
        default="pedimento_final",
        required=True,
        help="Solo aplica cuando la operacion es un pedimento consolidado.",
    )
    formas_pago_claves = fields.Char(
        string="Formas de pago (claves)",
        help="Solo para movimiento 8. Captura claves separadas por coma, ej. 5,6,8,9",
    )
    estructura_escenario = fields.Selection(
        [
            ("normal", "Pedimento normal"),
            ("transito", "Transito"),
            ("rectificacion", "Rectificacion"),
            ("eliminacion_desistimiento", "Eliminacion / Desistimiento"),
            ("industria_automotriz", "Industria automotriz"),
            ("complementario", "Complementario"),
            ("despacho_anticipado", "Despacho anticipado"),
            ("confirmacion_pago", "Confirmacion de pago"),
            ("global_complementario", "Global complementario"),
            ("generico", "Generico"),
        ],
        string="Escenario de estructura",
        compute="_compute_estructura_escenario",
        store=False,
    )
    show_descargo_ui = fields.Boolean(
        string="Mostrar descargos 512",
        compute="_compute_show_descargo_ui",
        store=False,
    )
    show_compensacion_ui = fields.Boolean(
        string="Mostrar compensaciones 513",
        compute="_compute_show_compensacion_ui",
        store=False,
    )
    show_documentos_forma_pago_ui = fields.Boolean(
        string="Mostrar documentos de formas de pago 514",
        compute="_compute_show_documentos_forma_pago_ui",
        store=False,
    )
    aduana_seccion_entrada_salida_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana-seccion entrada/salida",
    )
    aduana_seccion_entrada_salida = fields.Char(
        string="Aduana-seccion entrada/salida (codigo)",
        related="aduana_seccion_entrada_salida_id.code",
        store=True,
        readonly=True,
    )
    acuse_validacion = fields.Char(string="Acuse electronico validacion", size=8)
    curp_agente = fields.Char(string="CURP agente/apoderado")
    ws_ambiente = fields.Selection(
        [("pruebas", "Pruebas"), ("produccion", "Produccion")],
        string="Ambiente WS",
        default="pruebas",
        required=True,
    )
    ws_credencial_id = fields.Many2one(
        "mx.ped.credencial.ws",
        string="Credencial WS",
        domain="[('active','=',True),('company_id','=',company_id),('ambiente','=',ws_ambiente)]",
        ondelete="restrict",
    )
    avc_numero = fields.Char(string="Numero AVC", readonly=True, copy=False)
    avc_estatus = fields.Char(string="Estatus AVC", readonly=True, copy=False)
    avc_fecha_emision = fields.Char(string="Fecha emision AVC", readonly=True, copy=False)
    avc_fecha_vigencia = fields.Char(string="Fecha vigencia AVC", readonly=True, copy=False)
    avc_url_detail = fields.Char(string="URL detalle AVC", readonly=True, copy=False)
    avc_last_sync = fields.Datetime(string="Ultima consulta AVC", readonly=True, copy=False)
    avc_sync_error = fields.Text(string="Error AVC", readonly=True, copy=False)
    avc_folio_validacion = fields.Text(string="Folio validacion AVC", readonly=True, copy=False)
    avc_validacion_agencia = fields.Text(string="Firma validacion agencia", readonly=True, copy=False)
    avc_peticion_json = fields.Text(string="Peticion JSON firmada", readonly=True, copy=False)
    avc_modalidad_cruce_id = fields.Selection(
        [("1", "Vehicular"), ("2", "Peatonal"), ("4", "Virtual")],
        string="Modalidad cruce AVC",
        default="1",
    )
    avc_tipo_documento_id = fields.Selection(
        [("1", "Pedimentos"), ("2", "Arribo transito"), ("3", "AGA 15"), ("4", "Otros documentos"), ("5", "Cuaderno ATA")],
        string="Tipo documento AVC",
        default="1",
    )
    avc_pedimento_subtipo = fields.Selection(
        [
            ("normal", "Pedimento normal"),
            ("parte_2", "Parte II"),
            ("remesa_previo_consolidado", "Remesa previo consolidado"),
            ("aviso_electronico", "Aviso electronico"),
        ],
        string="Subtipo pedimento AVC",
        default="normal",
    )
    avc_tag = fields.Char(string="TAG AVC", size=24)
    avc_numero_gafete = fields.Char(string="Numero gafete AVC", size=24)
    avc_transportista_id = fields.Many2one(
        "res.partner",
        string="Transportista AVC",
        domain="[('x_contact_role','=','transportista')]",
    )
    avc_chofer_id = fields.Many2one(
        "res.partner",
        string="Chofer AVC",
        domain="[('x_contact_role','=','chofer'), ('parent_id','=', avc_transportista_id)]",
    )
    avc_gafete_id = fields.Many2one(
        "mx.anam.gafete",
        string="Gafete ANAM",
        domain="[('active','=',True), ('chofer_id','=',avc_chofer_id)]",
    )
    avc_fast_id = fields.Char(string="FAST ID AVC", size=50)
    avc_datos_adicionales = fields.Char(string="Datos adicionales AVC", size=500)
    avc_es_consolidacion_carga = fields.Boolean(string="Consolidacion de carga AVC")
    avc_consolidacion_autorizacion_1 = fields.Char(string="Autorizacion consolidacion 1", size=4)
    avc_consolidacion_autorizacion_2 = fields.Char(string="Autorizacion consolidacion 2", size=4)
    avc_parte2_consecutivo = fields.Integer(string="Consecutivo parte II AVC")
    avc_remesa_id = fields.Many2one(
        "mx.ped.consolidado.remesa",
        string="Remesa AVC",
        domain="[('operacion_id', '=', id)]",
    )
    avc_aviso_electronico_folio = fields.Char(string="Folio aviso electronico AVC")
    avc_aviso_electronico_plazo_id = fields.Selection(
        [("1", "Semanal"), ("2", "Mensual")],
        string="Plazo aviso electronico AVC",
    )
    avc_aviso_electronico_consecutivo = fields.Integer(string="Consecutivo aviso electronico AVC")

    cliente_id = fields.Many2one(
        "res.partner",
        string="Contacto / Cliente",
        related="lead_id.partner_id",
        store=True,
        readonly=True,
    )
    importador_id = fields.Many2one(
        "res.partner",
        string="Importador",
        related="lead_id.x_importador_id",
        store=True,
        readonly=True,
    )
    exportador_id = fields.Many2one(
        "res.partner",
        string="Exportador",
        related="lead_id.x_exportador_id",
        store=True,
        readonly=True,
    )
    proveedor_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        related="lead_id.x_proveedor_id",
        store=True,
        readonly=True,
    )
    participante_id = fields.Many2one(
        "res.partner",
        string="Importador/Exportador efectivo",
        compute="_compute_participante",
    )
    participante_rfc = fields.Char(
        string="RFC importador/exportador",
        compute="_compute_participante_data",
    )
    participante_curp = fields.Char(
        string="CURP importador/exportador",
        compute="_compute_participante_data",
    )
    participante_nombre = fields.Char(
        string="Nombre importador/exportador",
        compute="_compute_participante_data",
    )

    # ==========================
    # Resultado oficial/operativo
    # ==========================
    pedimento_numero = fields.Char(string="Número de pedimento")
    fecha_pago = fields.Date(string="Fecha de pago")
    fecha_liberacion = fields.Date(string="Fecha de liberación")
    semaforo = fields.Selection(
        [("verde", "Verde"), ("rojo", "Rojo")],
        string="Semáforo",
    )

    # Moneda
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    observaciones = fields.Text(string="Observaciones")
    observacion_line_ids = fields.One2many(
        "mx.ped.operacion.observacion",
        "operacion_id",
        string="Observaciones 511",
        copy=True,
    )
    descargo_line_ids = fields.One2many(
        "mx.ped.operacion.descargo",
        "operacion_id",
        string="Descargos 512",
        copy=True,
    )
    compensacion_line_ids = fields.One2many(
        "mx.ped.operacion.compensacion",
        "operacion_id",
        string="Compensaciones 513",
        copy=True,
    )
    # ----------------------------------------
    # Campos para registro 701 – Rectificación
    # Nombres en rect_* para coincidir con el mapeo de crm_lead
    # ----------------------------------------
    rect_pedimento_original = fields.Char(string="Pedimento original (Rectif.)", size=7)
    rect_patente_original = fields.Char(string="Patente original (Rectif.)", size=4)
    rect_aduana_original_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana sección original (Rectif.)",
    )
    rect_aduana_original = fields.Char(
        string="Aduana original código (Rectif.)",
        related="rect_aduana_original_id.code",
        store=True,
        readonly=True,
    )
    rect_clave_pedimento_original_id = fields.Many2one(
        "mx.ped.clave",
        string="Clave pedimento original (Rectif.)",
    )
    rect_clave_pedimento_original = fields.Char(
        string="Clave pedimento original código (Rectif.)",
        related="rect_clave_pedimento_original_id.code",
        store=True,
        readonly=True,
    )
    rect_fecha_pago_original = fields.Date(string="Fecha operación original (Rectif.)")
    # ----------------------------------------
    # Campos para registro 800 – Cancelación / Desistimiento
    # ----------------------------------------
    motivo_cancelacion = fields.Text(
        string="Motivo de cancelación/desistimiento (800)",
        help="Texto libre que se transmite en el registro 800 (movimiento 2=Cancelación, 3=Desistimiento).",
    )
    # Diferencias de contribuciones 702
    contribucion_702_ids = fields.One2many(
        "mx.ped.operacion.contribucion",
        "operacion_id",
        string="Diferencias contribuciones (702)",
        copy=True,
    )
    # ----------------------------------------
    # Campos para registro 302 – Prueba Suficiente (Complementario CT)
    # ----------------------------------------
    prueba_suficiente_302_ids = fields.One2many(
        "mx.ped.operacion.prueba.suficiente",
        "operacion_id",
        string="Prueba suficiente (302)",
        copy=True,
    )
    bl_file = fields.Binary(string="Archivo B/L (PDF)")
    bl_filename = fields.Char(string="Nombre archivo B/L")
    bl_last_read = fields.Datetime(string="Ultima lectura B/L", readonly=True)

    invoice_ids = fields.One2many(
        "account.move",
        "x_ped_operacion_id",
        string="Facturas",
    )
    invoice_count = fields.Integer(
        string="Conteo facturas",
        compute="_compute_invoice_count",
    )

    # ==========================
    # Layout y registros (VOCE/SAAI)
    # ==========================
    layout_id = fields.Many2one(
        "mx.ped.layout",
        string="Layout",
        help="Define los registros y campos del archivo de validación.",
    )
    estructura_regla_id = fields.Many2one(
        "mx.ped.estructura.regla",
        string="Regla de estructura",
        help="Define qu? registros debe contener la operaci?n seg?n tipo de movimiento.",
    )
    fecha_operacion = fields.Date(
        string="Fecha operacion",
        default=lambda self: fields.Date.context_today(self),
        required=True,
        help="Se usa para resolver automaticamente el rulepack normativo vigente.",
    )
    rulepack_id = fields.Many2one(
        "mx.ped.rulepack",
        string="Rulepack normativo",
        ondelete="restrict",
        help="Version normativa data-driven aplicada a esta operacion.",
    )
    strict_mode_policy = fields.Selection(
        [
            ("inherit", "Heredar"),
            ("strict", "Forzar STRICT"),
            ("relaxed", "Forzar no strict"),
        ],
        string="Modo STRICT",
        default="inherit",
    )
    strict_mode_effective = fields.Boolean(
        string="STRICT efectivo",
        compute="_compute_strict_mode_effective",
        store=False,
    )
    rule_trace_json = fields.Json(string="Trazabilidad de reglas", readonly=True, copy=False)
    rule_trace_at = fields.Datetime(string="Ultima evaluación de reglas", readonly=True, copy=False)
    show_acuse_ui = fields.Boolean(
        string="Mostrar acuse",
        compute="_compute_process_ui_flags",
        store=False,
    )
    show_formas_pago_ui = fields.Boolean(
        string="Mostrar formas pago",
        compute="_compute_process_ui_flags",
        store=False,
    )
    show_advanced = fields.Boolean(
        string="Modo avanzado",
        default=False,
        help="Muestra secciones tecnicas (510/557/514) para captura avanzada.",
    )
    show_advanced_info = fields.Boolean(
        string="Info avanzada",
        default=False,
        help="Muestra campos tecnicos y de control para auditoria y solucion de errores.",
    )
    send_505_contingency = fields.Boolean(
        string="Enviar 505 de contingencia",
        default=False,
        help=(
            "Cuando esta activo, el registro 505 se exporta con los campos extendidos "
            "de contingencia. Si esta desactivado, se dejan vacios los campos que el "
            "lineamiento reserva para contingencia o casos especiales."
        ),
    )
    es_consolidado = fields.Boolean(
        string="Pedimento consolidado",
        help="Marca la operacion cuando el despacho se manejara mediante remesas.",
    )
    consolidado_estado = fields.Selection(
        [
            ("no_aplica", "No aplica"),
            ("abierto", "Abierto"),
            ("en_proceso", "En proceso"),
            ("pendiente_cierre", "Pendiente de cierre"),
            ("cerrado", "Cerrado"),
        ],
        string="Estado consolidado",
        compute="_compute_consolidado_estado",
        store=True,
        readonly=True,
    )
    fecha_apertura = fields.Date(
        string="Fecha apertura consolidado",
        help="Fecha en que se abre la captura operativa del consolidado.",
    )
    fecha_cierre = fields.Date(
        string="Fecha cierre consolidado",
        help="Fecha de cierre operativo del consolidado.",
    )
    periodicidad_cierre = fields.Selection(
        [
            ("manual", "Manual"),
            ("semanal", "Semanal"),
            ("quincenal", "Quincenal"),
            ("mensual", "Mensual"),
        ],
        string="Periodicidad cierre",
        default="manual",
    )

    registro_ids = fields.One2many(
        comodel_name="mx.ped.registro",
        inverse_name="operacion_id",
        string="Registros",
        copy=True,
    )

    # ==========================
    # Partidas / Mercancías
    # ==========================
    partida_ids = fields.One2many(
        comodel_name="mx.ped.partida",
        inverse_name="operacion_id",
        string="Partidas / Mercancías",
        copy=True,
    )
    contribucion_global_ids = fields.One2many(
        "mx.ped.contribucion.global",
        "operacion_id",
        string="Contribuciones cabecera (510)",
        copy=True,
    )
    partida_contribucion_ids = fields.One2many(
        "mx.ped.partida.contribucion",
        "operacion_id",
        string="Contribuciones partidas (557)",
        copy=True,
    )
    documento_ids = fields.One2many(
        "mx.ped.documento",
        "operacion_id",
        string="Documentos",
        copy=True,
    )
    documento_514_ids = fields.One2many(
        "mx.ped.documento",
        "operacion_id",
        string="Documentos de formas de pago (514)",
        domain=[("registro_codigo", "=", "514")],
        copy=True,
    )
    identificador_pedimento_ids = fields.One2many(
        "mx.ped.operacion.identificador",
        "operacion_id",
        string="Identificadores de operacion",
        copy=True,
    )
    partida_identificador_ids = fields.One2many(
        "mx.ped.partida.identificador",
        "operacion_id",
        string="Identificadores de partida",
        copy=True,
    )
    cuenta_aduanera_ids = fields.One2many(
        "mx.ped.operacion.cuenta.aduanera",
        "operacion_id",
        string="Cuentas aduaneras/garantia",
        copy=True,
    )
    remesa_ids = fields.One2many(
        "mx.ped.consolidado.remesa",
        "operacion_id",
        string="Remesas",
        domain=[("active", "=", True)],
        copy=True,
    )

    partida_count = fields.Integer(
        string="Partidas",
        compute="_compute_partida_count",
    )
    remesa_count = fields.Integer(
        string="Remesas",
        compute="_compute_remesa_count",
    )
    cove_ids = fields.One2many(
        "mx.cove",
        "operacion_id",
        string="COVEs",
        copy=False,
    )
    cove_count = fields.Integer(
        string="COVEs",
        compute="_compute_cove_count",
    )
    mv_ids = fields.One2many(
        "mx.ped.mv",
        "operacion_id",
        string="Manifestaciones de Valor",
        copy=False,
    )
    proveedor_ids = fields.One2many(
        related="lead_id.x_proveedor_ids",
        string="Proveedores / Facturas",
        readonly=False,
    )
    mv_count = fields.Integer(
        string="MVs",
        compute="_compute_mv_count",
    )
    total_packages_line = fields.Integer(
        string="Total bultos",
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_gross_weight = fields.Float(
        string="Total peso bruto",
        digits=(16, 3),
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_net_weight = fields.Float(
        string="Total peso neto",
        digits=(16, 3),
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_value_usd = fields.Float(
        string="Total valor USD",
        digits=(16, 2),
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_value_mxn = fields.Float(
        string="Total valor MXN",
        digits=(16, 2),
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_igi_estimado = fields.Monetary(
        string="Total IGI estimado",
        currency_field="currency_id",
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_iva_estimado = fields.Monetary(
        string="Total IVA estimado",
        currency_field="currency_id",
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_dta_estimado = fields.Monetary(
        string="Total DTA estimado",
        currency_field="currency_id",
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_prv_estimado = fields.Monetary(
        string="Total PRV estimado",
        currency_field="currency_id",
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    total_impuestos_estimados = fields.Monetary(
        string="Total impuestos estimados",
        currency_field="currency_id",
        compute="_compute_totales_partidas",
        store=True,
        readonly=True,
    )
    crm_factura_resumen = fields.Text(
        string="Resumen factura-partidas",
        compute="_compute_crm_factura_resumen",
        store=False,
        readonly=True,
    )

    @api.depends("partida_ids")
    def _compute_partida_count(self):
        for rec in self:
            rec.partida_count = len(rec.partida_ids)

    @api.depends("remesa_ids")
    def _compute_remesa_count(self):
        for rec in self:
            rec.remesa_count = len(rec.remesa_ids)

    @api.depends("cove_ids")
    def _compute_cove_count(self):
        for rec in self:
            rec.cove_count = len(rec.cove_ids)

    @api.depends("mv_ids")
    def _compute_mv_count(self):
        for rec in self:
            rec.mv_count = len(rec.mv_ids)

    def action_view_mvs(self):
        """Abre la lista de MVs de esta operación, o el form si solo hay una."""
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": "Manifestaciones de Valor",
            "res_model": "mx.ped.mv",
            "view_mode": "list,form",
            "domain": [("operacion_id", "=", self.id)],
            "context": {
                "default_operacion_id": self.id,
                "default_rfc_importador": self.importador_id.vat if self.importador_id else False,
            },
        }
        if self.mv_count == 1:
            action["view_mode"] = "form"
            action["res_id"] = self.mv_ids[0].id
        return action

    @api.depends(
        "partida_ids.factura_documento_id",
        "partida_ids.numero_partida",
        "partida_ids.value_usd",
        "documento_ids.folio",
        "documento_ids.es_documento_principal",
    )
    def _compute_crm_factura_resumen(self):
        for rec in self:
            summary = []
            docs = rec.partida_ids.mapped("factura_documento_id")
            for doc in docs.sorted(lambda d: (d.es_documento_principal is not True, d.id)):
                linked = rec.partida_ids.filtered(lambda p: p.factura_documento_id == doc)
                if not linked:
                    continue
                partida_nums = ", ".join(str(n) for n in linked.mapped("numero_partida") if n)
                summary.append(
                    "%s -> Partidas %s | Valor Total USD: %.2f"
                    % (
                        doc.display_name or doc.folio or _("Sin folio"),
                        partida_nums or "-",
                        sum(linked.mapped("value_usd")),
                    )
                )
            rec.crm_factura_resumen = "\n".join(summary) if summary else False

    @api.depends("es_consolidado", "fecha_cierre", "remesa_ids.estado")
    def _compute_consolidado_estado(self):
        for rec in self:
            if not rec.es_consolidado:
                rec.consolidado_estado = "no_aplica"
                continue
            states = set(rec.remesa_ids.mapped("estado"))
            if rec.fecha_cierre:
                rec.consolidado_estado = "cerrado"
            elif not states:
                rec.consolidado_estado = "abierto"
            elif states <= {"cerrada"}:
                rec.consolidado_estado = "pendiente_cierre"
            else:
                rec.consolidado_estado = "en_proceso"

    @api.onchange("es_consolidado")
    def _onchange_es_consolidado(self):
        for rec in self:
            if rec.es_consolidado and not rec.fecha_apertura:
                rec.fecha_apertura = fields.Date.context_today(rec)
            if not rec.es_consolidado:
                rec.fecha_apertura = False
                rec.fecha_cierre = False
                rec.periodicidad_cierre = "manual"

    @api.constrains("es_consolidado", "fecha_apertura", "fecha_cierre")
    def _check_consolidado_fechas(self):
        for rec in self:
            if not rec.es_consolidado:
                continue
            if rec.fecha_apertura and rec.fecha_cierre and rec.fecha_cierre < rec.fecha_apertura:
                raise ValidationError(_("La fecha de cierre del consolidado no puede ser menor a la fecha de apertura."))

    @api.depends(
        "partida_ids.packages_line",
        "partida_ids.gross_weight_line",
        "partida_ids.net_weight_line",
        "partida_ids.value_usd",
        "partida_ids.value_mxn",
        "partida_ids.igi_estimado",
        "partida_ids.iva_estimado",
        "partida_ids.dta_estimado",
        "partida_ids.prv_estimado",
    )
    def _compute_totales_partidas(self):
        for rec in self:
            partidas = rec.partida_ids
            rec.total_packages_line = int(sum(partidas.mapped("packages_line")))
            rec.total_gross_weight = sum(partidas.mapped("gross_weight_line"))
            rec.total_net_weight = sum(partidas.mapped("net_weight_line"))
            rec.total_value_usd = sum(partidas.mapped("value_usd"))
            rec.total_value_mxn = sum(partidas.mapped("value_mxn"))
            rec.total_igi_estimado = sum(partidas.mapped("igi_estimado"))
            rec.total_iva_estimado = sum(partidas.mapped("iva_estimado"))
            rec.total_dta_estimado = sum(partidas.mapped("dta_estimado"))
            rec.total_prv_estimado = sum(partidas.mapped("prv_estimado"))
            rec.total_impuestos_estimados = (
                rec.total_igi_estimado + rec.total_iva_estimado + rec.total_dta_estimado + rec.total_prv_estimado
            )

    @api.depends("tipo_operacion", "importador_id", "exportador_id")
    def _compute_participante(self):
        for rec in self:
            if rec.tipo_operacion == "exportacion":
                rec.participante_id = rec.exportador_id
            else:
                rec.participante_id = rec.importador_id

    @api.depends(
        "tipo_operacion",
        "importador_id",
        "importador_id.vat",
        "importador_id.x_curp",
        "importador_id.name",
        "exportador_id",
        "exportador_id.vat",
        "exportador_id.x_curp",
        "exportador_id.name",
    )
    def _compute_participante_data(self):
        for rec in self:
            partner = rec.exportador_id if rec.tipo_operacion == "exportacion" else rec.importador_id
            rec.participante_rfc = partner.vat if partner else False
            rec.participante_curp = partner.x_curp if partner else False
            rec.participante_nombre = partner.name if partner else False

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids.filtered(lambda m: m.move_type == "out_invoice"))

    @api.depends("strict_mode_policy", "cliente_id.x_rule_engine_strict", "participante_id.x_rule_engine_strict")
    def _compute_strict_mode_effective(self):
        for rec in self:
            rec.strict_mode_effective = rec._is_strict_mode()

    @api.depends("tipo_movimiento", "clave_pedimento_id", "tipo_operacion", "regimen", "fecha_operacion", "rulepack_id")
    def _compute_process_ui_flags(self):
        for rec in self:
            show_acuse = False
            show_formas = False
            for rule in rec._get_process_stage_rules("pre_validate"):
                payload = rule.payload_json or {}
                if rule.action_type == "require_field" and payload.get("field") == "acuse_validacion":
                    show_acuse = True
                if rule.action_type == "require_formas_pago":
                    show_formas = True
                if rule.stop:
                    break
            rec.show_acuse_ui = show_acuse
            rec.show_formas_pago_ui = show_formas

    @api.depends("tipo_movimiento", "regimen", "clave_pedimento_id", "clave_pedimento_id.requiere_immex", "clave_pedimento_id.saai_structure_type")
    def _compute_show_descargo_ui(self):
        for rec in self:
            clave_code = (rec.clave_pedimento or "").strip().upper()
            structure_type = (rec.clave_pedimento_id.saai_structure_type or "").strip()
            is_non_immex = not bool(rec.clave_pedimento_id.requiere_immex)
            rec.show_descargo_ui = bool(any([
                rec.tipo_movimiento in {"2", "3", "6", "7"},
                structure_type in {"complementario", "despacho_anticipado", "eliminacion_desistimiento"},
                rec.regimen == "deposito_fiscal" and clave_code != "IA",
                rec.regimen == "temporal" and is_non_immex,
            ]))

    @api.depends(
        "contribucion_global_ids.forma_pago_code",
        "partida_contribucion_ids.forma_pago_code",
        "partida_ids.forma_pago_sugerida_id.code",
        "documento_ids.forma_pago_code",
    )
    def _compute_show_compensacion_ui(self):
        for rec in self:
            rec.show_compensacion_ui = rec._has_forma_pago_code("12")

    @api.depends(
        "contribucion_global_ids.forma_pago_code",
        "partida_contribucion_ids.forma_pago_code",
        "partida_ids.forma_pago_sugerida_id.code",
        "documento_ids.forma_pago_code",
    )
    def _compute_show_documentos_forma_pago_ui(self):
        required_codes = {"2", "4", "7", "12", "15", "19", "22"}
        for rec in self:
            rec.show_documentos_forma_pago_ui = bool(rec._get_declared_formas_pago_codes() & required_codes)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("layout_id"):
                latest_layout = self._get_latest_layout()
                if latest_layout:
                    vals["layout_id"] = latest_layout.id
        records = super().create(vals_list)
        for rec in records:
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()
            if not rec.ws_credencial_id:
                rec.ws_credencial_id = rec._resolve_ws_credencial().id or False
        records._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {"fecha_operacion", "tipo_operacion", "regimen", "clave_pedimento_id", "tipo_movimiento", "tipo_movimiento_id", "es_rectificacion"}
        refresh_fields = {
            "layout_id",
            "lead_id",
            # Cambios en la clasificación del pedimento regeneran todos los registros
            # para que el layout y las condition rules del rulepack apliquen correctamente.
            "tipo_movimiento",
            "tipo_movimiento_id",
            "tipo_operacion",
            "regimen",
            "clave_pedimento_id",
            "es_rectificacion",
            "incoterm",
            "send_505_contingency",
            "aduana_seccion_despacho_id",
            "aduana_clave",
            "aduana_seccion_entrada_salida_id",
            "acuse_validacion",
            "agente_aduanal_id",
            "patente",
            "curp_agente",
            "pedimento_numero",
            "fecha_pago",
            "fecha_liberacion",
            "semaforo",
            "observaciones",
        }
        if trigger_fields.intersection(vals.keys()):
            for rec in self:
                rec.rulepack_id = rec._resolve_rulepack()
                rec.estructura_regla_id = rec._resolve_estructura_regla()
        if (
            not self.env.context.get("skip_auto_generated_refresh")
            and refresh_fields.intersection(vals.keys())
        ):
            self._auto_refresh_generated_registros()
        if {"agente_aduanal_id", "ws_ambiente", "company_id"}.intersection(vals.keys()) and "ws_credencial_id" not in vals:
            for rec in self:
                rec.ws_credencial_id = rec._resolve_ws_credencial().id or False
        return res

    def _auto_refresh_generated_registros(self):
        for rec in self:
            if not rec.layout_id:
                rec.layout_id = rec._get_latest_layout().id or False
            rec_ctx = rec.with_context(skip_auto_generated_refresh=True)
            # Siempre actualizar contribuciones desde fracciones arancelarias.
            rec_ctx.action_generar_contribuciones_557()
            if not rec.layout_id or not rec.lead_id:
                continue
            # action_cargar_desde_lead ya llama action_generar_contribuciones_557 al final,
            # pero la llamada anterior asegura que las contribuciones estén actualizadas
            # incluso cuando se accede sin regenerar registros VOCE.
            rec_ctx.action_cargar_desde_lead()
            rec_ctx._sync_registro_ids_from_tecnicos()

    def _get_latest_layout(self):
        return self.env["mx.ped.layout"].search(
            [("active", "=", True)],
            order="id desc",
            limit=1,
        )

    @api.onchange("lead_id")
    def _onchange_lead_id_fill_defaults(self):
        if not self.lead_id:
            return
        lead = self.lead_id
        defaults = {
            "tipo_operacion": lead.x_tipo_operacion or False,
            "regimen": lead.x_regimen or False,
            "incoterm": lead.x_incoterm or False,
            "aduana_seccion_despacho_id": lead.x_aduana_seccion_despacho_id or False,
            "aduana_clave": lead.x_aduana or False,
            "aduana_seccion_entrada_salida_id": lead.x_aduana_seccion_entrada_salida_id or False,
            "acuse_validacion": lead.x_acuse_validacion or False,
            "agente_aduanal_id": lead.x_agente_aduanal_id or False,
            "patente": (lead.x_agente_aduanal_id.x_patente_aduanal or lead.x_patente_agente or False),
            "curp_agente": lead.x_curp_agente or False,
            "clave_pedimento_id": lead.x_clave_pedimento_id or False,
            "currency_id": lead.x_currency_id or self.env.company.currency_id,
            "pedimento_numero": lead.x_num_pedimento or False,
            "fecha_pago": lead.x_fecha_pago_pedimento or False,
            "fecha_liberacion": lead.x_fecha_liberacion or False,
            "semaforo": lead.x_semaforo or False,
            "observaciones": lead.x_incidente_text or False,
            "avc_transportista_id": lead.x_transportista_ids[:1].transportista_id or False,
            # Rectificación: datos del pedimento original
            "es_rectificacion": lead.x_es_rectificacion or False,
            "rect_pedimento_original": lead.x_rect_pedimento_original or False,
            "rect_fecha_pago_original": lead.x_rect_fecha_pago_original or False,
        }
        for field_name, value in defaults.items():
            if field_name in self._fields and not self[field_name]:
                self[field_name] = value

    @api.onchange("aduana_seccion_despacho_id")
    def _onchange_aduana_seccion_despacho_id(self):
        for rec in self:
            if rec.aduana_seccion_despacho_id:
                rec.aduana_clave = rec.aduana_seccion_despacho_id.code

    @api.onchange("agente_aduanal_id")
    def _onchange_agente_aduanal_id(self):
        for rec in self:
            agent = rec.agente_aduanal_id
            if not agent:
                continue
            rec.patente = agent.x_patente_aduanal or rec.patente
            rec.curp_agente = agent.x_curp or rec.curp_agente
            rec.ws_credencial_id = rec._resolve_ws_credencial().id or rec.ws_credencial_id

    @api.onchange("ws_ambiente", "company_id")
    def _onchange_ws_context(self):
        for rec in self:
            rec.ws_credencial_id = rec._resolve_ws_credencial().id or rec.ws_credencial_id

    @api.onchange("avc_transportista_id")
    def _onchange_avc_transportista_id(self):
        for rec in self:
            if rec.avc_chofer_id and rec.avc_chofer_id.parent_id != rec.avc_transportista_id:
                rec.avc_chofer_id = False
            if rec.avc_gafete_id and rec.avc_gafete_id.transportista_id != rec.avc_transportista_id:
                rec.avc_gafete_id = False

    @api.onchange("avc_chofer_id")
    def _onchange_avc_chofer_id(self):
        for rec in self:
            if rec.avc_chofer_id and rec.avc_chofer_id.parent_id:
                rec.avc_transportista_id = rec.avc_chofer_id.parent_id
            if rec.avc_gafete_id and rec.avc_gafete_id.chofer_id != rec.avc_chofer_id:
                rec.avc_gafete_id = False
            if rec.avc_chofer_id and not rec.avc_gafete_id:
                gafete = self.env["mx.anam.gafete"].search([
                    ("active", "=", True),
                    ("chofer_id", "=", rec.avc_chofer_id.id),
                ], order="validado_el desc, id desc", limit=1)
                if gafete:
                    rec.avc_gafete_id = gafete

    @api.onchange("avc_gafete_id")
    def _onchange_avc_gafete_id(self):
        for rec in self:
            if rec.avc_gafete_id:
                rec.avc_chofer_id = rec.avc_gafete_id.chofer_id
                rec.avc_transportista_id = rec.avc_gafete_id.transportista_id
                rec.avc_numero_gafete = rec.avc_gafete_id.numero_gafete

    def _resolve_ws_credencial(self):
        self.ensure_one()
        model = self.env["mx.ped.credencial.ws"]
        dom_base = [
            ("active", "=", True),
            ("company_id", "=", self.company_id.id or self.env.company.id),
            ("ambiente", "=", self.ws_ambiente or "produccion"),
        ]
        if self.agente_aduanal_id:
            by_agent = model.search(dom_base + [("partner_id", "=", self.agente_aduanal_id.id)], limit=1)
            if by_agent:
                return by_agent
        by_default = model.search(dom_base + [("is_default", "=", True), ("partner_id", "=", False)], limit=1)
        if by_default:
            return by_default
        return model.search(dom_base + [("partner_id", "=", False)], limit=1)

    @api.onchange("tipo_movimiento")
    def _onchange_tipo_movimiento_clear_acuse(self):
        for rec in self:
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.onchange("clave_pedimento_id", "tipo_operacion", "regimen", "fecha_operacion")
    def _onchange_estructura_regla_context(self):
        for rec in self:
            if rec.clave_pedimento_id and rec.clave_pedimento_id.tipo_movimiento_id:
                rec.tipo_movimiento = rec.clave_pedimento_id.tipo_movimiento_id.code
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.onchange("es_rectificacion", "formas_pago_claves")
    def _onchange_estructura_regla_flags(self):
        for rec in self:
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.depends("tipo_movimiento", "clave_pedimento_id", "es_rectificacion")
    def _compute_estructura_escenario(self):
        for rec in self:
            rec.estructura_escenario = rec._detect_escenario_estructura()

    @api.constrains("tipo_movimiento", "acuse_validacion", "clave_pedimento_id")
    def _check_acuse_validacion(self):
        # Saltear durante creación desde wizard de desistimiento/eliminación:
        # el acuse lo retorna el SAAI después de presentar el TXT, no antes.
        # Durante la creación desde el wizard el acuse se escribe en un paso
        # posterior (después de action_cargar_desde_lead). Se salta para evitar
        # falso positivo; la constraint correrá en el write subsecuente.
        if self.env.context.get("creating_desistimiento"):
            return
        for rec in self:
            stage_rules = rec._get_process_stage_rules("pre_validate")
            for rule in stage_rules:
                payload = rule.payload_json or {}
                if rule.action_type != "require_field":
                    continue
                if payload.get("field") != "acuse_validacion":
                    continue
                acuse = (rec.acuse_validacion or "").strip()
                if not acuse:
                    raise ValidationError(_("Regla %s: el acuse de validacion es obligatorio.") % (rule.name,))
                expected_len = int(payload.get("length") or 0)
                if expected_len and len(acuse) != expected_len:
                    raise ValidationError(
                        _("Regla %s: el acuse de validacion debe tener %s caracteres.")
                        % (rule.name, expected_len)
                    )
                forbidden = str(payload.get("forbidden_value") or "").strip()
                if forbidden and acuse == forbidden:
                    raise ValidationError(
                        _("Regla %s: el acuse de validacion no puede ser %s.")
                        % (rule.name, forbidden)
                    )
                if rule.stop:
                    break

    def action_view_partidas(self):
        """Abre las partidas de esta operación (útil para smart button)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Partidas"),
            "res_model": "mx.ped.partida",
            "view_mode": "list,form",
            "domain": [("operacion_id", "=", self.id)],
            "context": {"default_operacion_id": self.id},
            "target": "current",
        }

    def action_ver_coves(self):
        """Abre los COVEs ligados a esta operación (smart button)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("COVEs"),
            "res_model": "mx.cove",
            "view_mode": "list,form",
            "domain": [("operacion_id", "=", self.id)],
            "context": {"default_operacion_id": self.id},
            "target": "current",
        }

    def action_generar_cove(self):
        """Abre un COVE nuevo pre-llenado con los datos de esta operación.

        Se pre-rellenan todos los campos disponibles en la operación.
        El agente completa los campos faltantes (credencial, correo) y guarda.
        """
        self.ensure_one()

        # Documento principal de tipo factura como fuente para datos del emisor
        doc_principal = self.documento_ids.filtered(
            lambda d: d.tipo in ("factura", "cove") and d.es_documento_principal
        ).sorted(lambda d: d.id)[:1]
        if not doc_principal:
            doc_principal = self.documento_ids.filtered(
                lambda d: d.tipo in ("factura", "cove")
            ).sorted(lambda d: d.id)[:1]

        # Determinar tipo de operación (selección VUCEM)
        mov = (self.tipo_movimiento or "").strip()
        tipo_op = "TOCE.IMP" if mov in ("1", "2", "3", "4", "5", "6") else "TOCE.EXP"

        ctx = dict(self.env.context)
        ctx["default_operacion_id"] = self.id
        ctx["default_tipo_operacion"] = tipo_op
        ctx["default_name"] = self.name or _("Nuevo COVE")

        # Pre-llenar emisor (exportador/proveedor) desde el documento principal
        if doc_principal:
            doc = doc_principal
            ctx["default_emisor_nombre"] = doc.counterparty_name_505 or ""
            ctx["default_emisor_calle"] = doc.counterparty_street_505 or ""
            ctx["default_emisor_numero_exterior"] = doc.counterparty_num_ext_505 or ""
            ctx["default_emisor_numero_interior"] = doc.counterparty_num_int_505 or ""
            ctx["default_emisor_codigo_postal"] = doc.counterparty_zip_505 or ""
            ctx["default_emisor_municipio"] = doc.counterparty_city_505 or ""
            if doc.cfdi_pais_id:
                ctx["default_emisor_pais"] = doc.cfdi_pais_id.code or ""
            ctx["default_numero_factura_original"] = doc.folio or ""

        # Pre-llenar destinatario (importador) desde la operación
        if self.importador_id:
            ctx["default_dest_nombre"] = self.importador_id.name or ""
            ctx["default_dest_identificacion"] = self.importador_id.vat or ""
            if self.importador_id.street:
                ctx["default_dest_calle"] = self.importador_id.street or ""
            if self.importador_id.zip:
                ctx["default_dest_codigo_postal"] = self.importador_id.zip or ""
            if self.importador_id.city:
                ctx["default_dest_municipio"] = self.importador_id.city or ""
            if self.importador_id.country_id:
                ctx["default_dest_pais"] = self.importador_id.country_id.code or ""

        return {
            "type": "ir.actions.act_window",
            "name": _("Nuevo COVE"),
            "res_model": "mx.cove",
            "view_mode": "form",
            "target": "current",
            "context": ctx,
        }

    def _get_tipo_movimiento_effective(self):
        self.ensure_one()
        if self.clave_pedimento_id and self.clave_pedimento_id.tipo_movimiento_id:
            return self.clave_pedimento_id.tipo_movimiento_id.code
        return self.tipo_movimiento

    def _get_clave_policy_map(self):
        self.ensure_one()
        policy_rules = []
        clave = self.clave_pedimento_id
        if not clave:
            return policy_rules

        for line in clave.registro_policy_ids.sorted(lambda l: (-l.priority, l.sequence, l.id)):
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            policy_rules.append({
                "code": code,
                "policy": line.policy,
                "scope": line.scope or "pedimento",
                "priority": line.priority,
                "stop": bool(line.stop),
                "min": max(line.min_occurs or 0, 0),
                "max": max(line.max_occurs or 0, 0),
                "identifier": (line.required_identifier_code or "").strip().upper(),
                "line_id": line.id,
            })

        policy_rules.sort(key=lambda r: (-r["priority"], r["code"], r["line_id"]))
        return policy_rules

    def _payload_has_token(self, payload, token):
        token = (token or "").strip().upper()
        if not token:
            return True
        payload = payload or {}
        for value in payload.values():
            if isinstance(value, str):
                tokens = {part.upper() for part in re.findall(r"[A-Za-z0-9]+", value)}
                if token in tokens:
                    return True
        return False

    def _extract_partida_number(self, payload):
        payload = payload or {}
        if not isinstance(payload, dict):
            return None

        candidates = {
            "partida",
            "numero_partida",
            "num_partida",
            "partida_numero",
            "secuencia_partida",
            "partida_seq",
        }
        for key, value in payload.items():
            key_norm = str(key or "").strip().lower()
            if key_norm not in candidates:
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                digits = "".join(ch for ch in value if ch.isdigit())
                if digits:
                    return int(digits)
        return None

    def _get_partida_numbers_for_validation(self):
        self.ensure_one()
        numbers = [p.numero_partida for p in self.partida_ids if p.numero_partida]
        if numbers:
            return sorted(set(numbers))

        inferred = []
        for reg in self.registro_ids:
            num = self._extract_partida_number(reg.valores)
            if num:
                inferred.append(num)
        return sorted(set(inferred))

    def _get_partida_meta_map(self):
        self.ensure_one()
        meta = {}
        for partida in self.partida_ids:
            if partida.numero_partida:
                meta[partida.numero_partida] = {
                    "fraccion_id": partida.fraccion_id.id if partida.fraccion_id else False,
                    "fraccion_capitulo": partida.fraccion_id.capitulo if partida.fraccion_id else False,
                }
        return meta

    def _resolve_rulepack(self):
        self.ensure_one()
        op_date = self.fecha_operacion or fields.Date.context_today(self)
        packs = self.env["mx.ped.rulepack"].search(
            [
                ("active", "=", True),
                ("state", "=", "active"),
                ("fecha_inicio", "<=", op_date),
                "|",
                ("fecha_fin", "=", False),
                ("fecha_fin", ">=", op_date),
            ],
            order="priority desc, fecha_inicio desc, id desc",
            limit=1,
        )
        return packs[:1]

    def _get_rulepack_effective(self):
        self.ensure_one()
        return self.rulepack_id or self._resolve_rulepack()

    def _is_strict_mode(self):
        self.ensure_one()
        if self.strict_mode_policy == "strict":
            return True
        if self.strict_mode_policy == "relaxed":
            return False

        partner_mode = (
            self.participante_id.x_rule_engine_strict
            or self.cliente_id.x_rule_engine_strict
            or "inherit"
        )
        if partner_mode == "strict":
            return True
        if partner_mode == "relaxed":
            return False

        raw = self.env["ir.config_parameter"].sudo().get_param("mx_ped.rule_engine.strict_mode", "false")
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _get_source_weights(self, rulepack):
        return {
            "estructura": int((rulepack.weight_estructura if rulepack else 10) or 10),
            "clave": int((rulepack.weight_clave if rulepack else 20) or 20),
            "condition": int((rulepack.weight_condition if rulepack else 30) or 30),
        }

    def action_open_partida_factura_wizard(self):
        self.ensure_one()
        wizard = self.env["mx.ped.partida.factura.wizard"].create({
            "operacion_id": self.id,
            "partida_ids": [(6, 0, self.partida_ids.ids)],
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "mx.ped.partida.factura.wizard",
            "view_mode": "form",
            "view_id": self.env.ref("modulo_aduana_odoo.mx_ped_partida_factura_wizard_view_form").id,
            "res_id": wizard.id,
            "target": "new",
        }

    def _clear_partida_factura_flags(self):
        self.ensure_one()
        self.partida_ids.with_context(skip_auto_generated_refresh=True).write({
            "factura_documento_error": False,
            "factura_value_error": False,
            "factura_validation_note": False,
        })

    def _validate_partida_facturas_505(self):
        self.ensure_one()
        partidas = self.partida_ids
        if not partidas:
            return
        self._clear_partida_factura_flags()
        missing = partidas.filtered(lambda p: not p.factura_documento_id)
        if missing:
            self.write({"show_advanced_info": True, "show_advanced": True})
            missing.with_context(skip_auto_generated_refresh=True).write({
                "factura_documento_error": True,
                "factura_validation_note": "Sin factura / CFDI asignado.",
            })
            nums = ", ".join(str(n) for n in missing.mapped("numero_partida") if n)
            raise UserError(_("Existen partidas sin factura/CFDI asignado: %s") % (nums or len(missing)))

        docs = partidas.mapped("factura_documento_id")
        for doc in docs:
            linked = partidas.filtered(lambda p: p.factura_documento_id == doc)
            total_usd = sum(linked.mapped("value_usd"))
            doc_usd = doc.cfdi_valor_usd or 0.0
            if abs(total_usd - doc_usd) > 0.01:
                self.write({"show_advanced_info": True, "show_advanced": True})
                linked.with_context(skip_auto_generated_refresh=True).write({
                    "factura_value_error": True,
                    "factura_validation_note": "El Valor USD de las partidas no cuadra con el 505 de la factura.",
                })
                raise UserError(
                    _("La suma de Valor USD de las partidas ligadas a %s no cuadra con el valor USD del 505. Partidas=%.2f Documento=%.2f")
                    % (doc.display_name or doc.folio or doc.id, total_usd, doc_usd)
                )
            # Nota: no se compara valor_comercial vs cfdi_valor_moneda porque están en
            # monedas distintas (valor_comercial usa la moneda de la operación; el documento
            # puede ser en USD u otra). El chequeo de value_usd cubre la validación.

    def _compute_specificity(self, rule, source):
        score = 0
        if source in ("selector", "condition", "process"):
            if getattr(rule, "tipo_movimiento_id", False):
                score += 30
            if getattr(rule, "clave_pedimento_id", False):
                score += 25
            if hasattr(rule, "escenario_code") and getattr(rule, "escenario_code", "") not in ("", "any"):
                score += 20
            if getattr(rule, "regimen", "") not in ("", "cualquiera"):
                score += 15
            if getattr(rule, "tipo_operacion", "") not in ("", "ambas"):
                score += 10
            if getattr(rule, "is_virtual", "") not in ("", "any"):
                score += 8
            if getattr(rule, "scope", "") == "partida":
                score += 5
            if getattr(rule, "fraccion_id", False):
                score += 22
            elif getattr(rule, "fraccion_capitulo", False):
                score += 12
            if getattr(rule, "forma_pago_match", "any") != "any":
                score += 12
            if getattr(rule, "forma_pago_id", False) or getattr(rule, "forma_pago_code", False):
                score += 8
        elif source == "clave":
            if getattr(rule, "scope", "") == "partida":
                score += 5
        return score

    def _build_rule_context(self, escenario_code=None):
        self.ensure_one()
        clave = self.clave_pedimento_id
        mov = self._get_tipo_movimiento_effective()
        fraccion_ids = {p.fraccion_id.id for p in self.partida_ids if p.fraccion_id}
        fraccion_capitulos = {p.fraccion_id.capitulo for p in self.partida_ids if p.fraccion_id and p.fraccion_id.capitulo}
        declared_formas_pago = {
            str(code).strip()
            for code in self._get_declared_formas_pago_codes()
            if str(code).strip()
        }
        return {
            "tipo_movimiento": mov,
            "tipo_operacion": self.tipo_operacion or "",
            "regimen": self.regimen or "",
            "clave_id": clave.id if clave else False,
            "is_virtual": bool(clave and clave.is_virtual),
            "escenario": escenario_code or "",
            "fraccion_ids": fraccion_ids,
            "fraccion_capitulos": fraccion_capitulos,
            "declared_formas_pago": declared_formas_pago,
            "es_rectificacion": bool(self.es_rectificacion),
        }

    def _rule_condition_match(self, rule, context):
        mov_code = rule.tipo_movimiento_id.code if getattr(rule, "tipo_movimiento_id", False) else False
        if mov_code and mov_code != context.get("tipo_movimiento"):
            return False
        if getattr(rule, "tipo_operacion", False) and rule.tipo_operacion not in ("", "ambas"):
            if rule.tipo_operacion != context.get("tipo_operacion"):
                return False
        if getattr(rule, "regimen", False) and rule.regimen not in ("", "cualquiera"):
            if rule.regimen != context.get("regimen"):
                return False
        if getattr(rule, "clave_pedimento_id", False) and rule.clave_pedimento_id.id != context.get("clave_id"):
            return False
        if getattr(rule, "is_virtual", False) and rule.is_virtual != "any":
            expected_virtual = (rule.is_virtual == "yes")
            if expected_virtual != bool(context.get("is_virtual")):
                return False
        rule_es_rect = getattr(rule, "es_rectificacion", "any") or "any"
        if rule_es_rect != "any":
            expected_rect = (rule_es_rect == "yes")
            if expected_rect != bool(context.get("es_rectificacion")):
                return False
        if hasattr(rule, "escenario_code") and rule.escenario_code and rule.escenario_code != "any":
            if rule.escenario_code != context.get("escenario"):
                return False
        if hasattr(rule, "fraccion_id") and rule.fraccion_id:
            if rule.fraccion_id.id not in (context.get("fraccion_ids") or set()):
                return False
        if hasattr(rule, "fraccion_capitulo") and (rule.fraccion_capitulo or "").strip():
            cap = (rule.fraccion_capitulo or "").strip()
            if cap not in (context.get("fraccion_capitulos") or set()):
                return False
        forma_pago_match = getattr(rule, "forma_pago_match", "any") or "any"
        forma_pago_code = ""
        if getattr(rule, "forma_pago_id", False):
            forma_pago_code = str(rule.forma_pago_id.code or "").strip()
        if not forma_pago_code:
            forma_pago_code = str(getattr(rule, "forma_pago_code", "") or "").strip()
        declared = context.get("declared_formas_pago") or set()
        if forma_pago_match == "present":
            if not forma_pago_code or forma_pago_code not in declared:
                return False
        elif forma_pago_match == "absent":
            if forma_pago_code and forma_pago_code in declared:
                return False
        return True

    def _select_rulepack_scenario(self):
        self.ensure_one()
        strict = self._is_strict_mode()
        rulepack = self._get_rulepack_effective()
        if not rulepack:
            if strict:
                raise UserError(_("Modo STRICT: no existe rulepack vigente para la fecha de operacion."))
            return {
                "scenario": self.env["mx.ped.rulepack.scenario"],
                "estructura_rule": self.env["mx.ped.estructura.regla"],
                "winner_selector": False,
                "selector_trace": {"candidates": [], "winner_selector_id": False},
            }

        context = self._build_rule_context()
        selectors = rulepack.selector_ids.filtered(lambda r: r.active).sorted(
            key=lambda r: (-r.priority, r.sequence, r.id)
        )
        selected = self.env["mx.ped.rulepack.scenario"]
        winner_selector = False
        selector_candidates = []
        for selector in selectors:
            matched = self._rule_condition_match(selector, context)
            selector_candidates.append({
                "selector_id": selector.id,
                "priority": selector.priority,
                "specificity_score": self._compute_specificity(selector, "selector"),
                "stop": bool(selector.stop),
                "matched": bool(matched),
                "scenario_id": selector.scenario_id.id if selector.scenario_id else False,
                "conditions": {
                    "tipo_movimiento_id": selector.tipo_movimiento_id.id if selector.tipo_movimiento_id else False,
                    "tipo_operacion": selector.tipo_operacion,
                    "regimen": selector.regimen,
                    "clave_pedimento_id": selector.clave_pedimento_id.id if selector.clave_pedimento_id else False,
                    "is_virtual": selector.is_virtual,
                },
            })
            if not matched:
                continue
            selected = selector.scenario_id
            winner_selector = selector
            if selector.stop:
                break

        if not selected:
            selected = rulepack.scenario_ids.filtered(lambda s: s.active and s.is_default)[:1]
        if not selected:
            selected = rulepack.scenario_ids.filtered(lambda s: s.active)[:1]
        if not selected and strict:
            raise UserError(_("Modo STRICT: no hay escenario seleccionable en el rulepack vigente."))
        if strict and selected and not selected.estructura_regla_id:
            raise UserError(_("Modo STRICT: el escenario seleccionado no tiene regla de estructura base."))

        return {
            "scenario": selected,
            "estructura_rule": selected.estructura_regla_id if selected else self.env["mx.ped.estructura.regla"],
            "winner_selector": winner_selector,
            "selector_trace": {
                "candidates": selector_candidates,
                "winner_selector_id": winner_selector.id if winner_selector else False,
            },
        }

    def _get_process_stage_rules(self, stage):
        self.ensure_one()
        rulepack = self._get_rulepack_effective()
        if not rulepack:
            return self.env["mx.ped.rulepack.process.rule"]
        context = self._build_rule_context()
        rules = rulepack.process_rule_ids.filtered(lambda r: r.active and r.stage == stage).sorted(
            key=lambda r: (-r.priority, -self._compute_specificity(r, "process"), r.sequence, r.id)
        )
        return rules.filtered(lambda r: self._rule_condition_match(r, context))

    def _resolve_estructura_regla(self):
        self.ensure_one()
        selected_data = self._select_rulepack_scenario()
        if selected_data.get("estructura_rule"):
            return selected_data["estructura_rule"]
        if self._is_strict_mode():
            raise UserError(_("Modo STRICT: no se pudo resolver una regla de estructura."))
        mov = self._get_tipo_movimiento_effective()
        if not mov:
            return self.env["mx.ped.estructura.regla"]
        detected_escenario = self._detect_escenario_estructura()
        rules = self.env["mx.ped.estructura.regla"].search(
            [
                ("active", "=", True),
                "|",
                ("tipo_movimiento_id.code", "=", mov),
                ("tipo_movimiento", "=", mov),
            ],
            order="priority desc, id desc",
        )
        best = self.env["mx.ped.estructura.regla"]
        best_score = -1
        for rule in rules:
            score = 0
            if rule.escenario and rule.escenario != "generico":
                if rule.escenario != detected_escenario:
                    continue
                score += 4
            if rule.clave_pedimento_id:
                if rule.clave_pedimento_id != self.clave_pedimento_id:
                    continue
                score += 3
            if rule.tipo_operacion and rule.tipo_operacion != "ambas":
                if rule.tipo_operacion != self.tipo_operacion:
                    continue
                score += 2
            if rule.regimen and rule.regimen != "cualquiera":
                if rule.regimen != self.regimen:
                    continue
                score += 1
            if score > best_score:
                best = rule
                best_score = score
        return best

    def _detect_escenario_estructura(self):
        self.ensure_one()
        selected_data = self._select_rulepack_scenario()
        selected_scenario = selected_data.get("scenario")
        if selected_scenario:
            return selected_scenario.code

        clave_structure = (self.clave_pedimento_id.saai_structure_type or "auto") if self.clave_pedimento_id else "auto"
        if clave_structure and clave_structure != "auto":
            return clave_structure
        if self._is_strict_mode():
            raise UserError(_("Modo STRICT: no se pudo determinar escenario de estructura."))
        return "generico"

    def _is_transito(self):
        self.ensure_one()
        code = (self.clave_pedimento_id.code or "").upper()
        return bool(code and (code.startswith("T") or code in {"TR"}))

    def _is_rectificacion(self):
        self.ensure_one()
        if self.es_rectificacion:
            return True
        return any((line.codigo or "") == "701" for line in self.registro_ids)

    def _parse_formas_pago_claves(self):
        self.ensure_one()
        raw = (self.formas_pago_claves or "").strip()
        if not raw:
            return set()
        return {token for token in re.findall(r"\d+", raw)}

    def _get_declared_formas_pago_codes(self):
        """Arma el set de formas declaradas desde 510 + 557 + 514."""
        self.ensure_one()
        codes = {
            str(code).strip()
            for code in self.contribucion_global_ids.mapped("forma_pago_code")
            if code
        }
        codes |= {
            str(code).strip()
            for code in self.partida_contribucion_ids.mapped("forma_pago_code")
            if code
        }
        # Fuente primaria en captura operativa: selector por partida.
        codes |= {
            str(code).strip()
            for code in self.partida_ids.mapped("forma_pago_sugerida_id.code")
            if code
        }
        docs_514 = self.documento_ids.filtered(
            lambda d: (d.registro_codigo or "").strip() == "514"
        )
        codes |= {
            str(code).strip()
            for code in docs_514.mapped("forma_pago_code")
            if code
        }
        # Compatibilidad temporal con captura legacy.
        if not codes:
            codes = self._parse_formas_pago_claves()
        return codes

    def action_generar_contribuciones_557(self):
        """Genera/actualiza 557 desde partidas usando impuestos estimados."""
        self.ensure_one()
        contrib_model = self.env["mx.ped.partida.contribucion"]
        icp = self.env["ir.config_parameter"].sudo()
        dta_rate = float(icp.get_param("mx_ped.dta_rate", "0.0") or 0.0)
        prv_rate = float(icp.get_param("mx_ped.prv_rate", "0.0") or 0.0)
        managed_codes = {"IGI", "IVA", "DTA", "PRV", "IEPS"}
        managed_contrib_codes = {1, 3, 6, 15, 22}
        for partida in self.partida_ids:
            tipo = "importacion" if self.tipo_operacion != "exportacion" else "exportacion"
            # Usa fraccion_id Many2one (mx.tigie.maestra — modelo plano); si no está enlazado,
            # intenta resolverlo por código en la misma tabla maestra.
            fraccion = partida.fraccion_id
            if not fraccion and (partida.fraccion_arancelaria or "").strip():
                frac_code = partida.fraccion_arancelaria.strip()
                # Intenta primero por llave_10 (fraccion+nico), luego por fraccion_8
                if len(frac_code) == 10:
                    fraccion = self.env["mx.tigie.maestra"].search(
                        [("llave_10", "=", frac_code)], limit=1
                    )
                if not fraccion:
                    fraccion = self.env["mx.tigie.maestra"].search(
                        [("fraccion_8", "=", frac_code[:8])], limit=1
                    )
                if fraccion:
                    partida.with_context(skip_auto_generated_refresh=True).write(
                        {"fraccion_id": fraccion.id}
                    )

            # mx.tigie.maestra es un modelo plano: las tasas están directamente en los campos
            # arancel_importacion / arancel_exportacion / iva_importacion.
            # No existen tasa_ids ni contribucion_extra_ids.
            if fraccion:
                igi_rate = fraccion.arancel_importacion if tipo == "importacion" else fraccion.arancel_exportacion
                iva_rate = fraccion.iva_importacion if tipo == "importacion" else 0.0
            else:
                igi_rate = 0.0
                iva_rate = 0.0

            candidates = [
                ("IGI", partida.igi_estimado or 0.0, igi_rate),
                ("IVA", partida.iva_estimado or 0.0, iva_rate),
                ("DTA", partida.dta_estimado or 0.0, dta_rate),
                ("PRV", partida.prv_estimado or 0.0, prv_rate),
            ]
            # IEPS y contribuciones extra no están en el modelo TIGIE plano;
            # si se requieren se capturan manualmente en la partida.

            normalized_candidates = []
            for item in candidates:
                if len(item) == 3:
                    tax_code, amount, rate = item
                    contribucion = self._find_contribucion_catalog(tax_code)
                    contrib_id = contribucion.id if contribucion else False
                else:
                    tax_code, amount, rate, contrib_id = item
                # Per lineamiento SAAI M3 v9.0, campo "Tasa" del registro 556:
                # "Cuando la tasa sea 0, no será necesario declarar este registro."
                # Lo mismo aplica para 557. Solo se incluyen contribuciones con tasa > 0.
                if float(rate or 0.0) > 0 or amount > 0:
                    normalized_candidates.append((tax_code, amount, rate, contrib_id))

            existing_lines = partida.contribucion_ids.filtered(lambda c: c.operacion_id == self)
            existing_by_tipo = {}
            for line in existing_lines:
                line_tokens = set()
                raw_tipo = self._norm_contrib_key(line.tipo_contribucion)
                if raw_tipo:
                    line_tokens.add(raw_tipo)
                    line_tokens |= {piece for piece in raw_tipo.split("/") if piece}
                if getattr(line, "contribucion_id", False):
                    abbr = self._norm_contrib_key(line.contribucion_id.abbreviation)
                    if abbr:
                        line_tokens.add(abbr)
                        line_tokens |= {piece for piece in abbr.split("/") if piece}
                    line_code = int(line.contribucion_id.code or 0)
                    reverse_map = {1: "DTA", 3: "IVA", 4: "ISAN", 6: "IGI", 7: "REC", 15: "PRV", 22: "IEPS"}
                    if line_code in reverse_map:
                        line_tokens.add(reverse_map[line_code])
                for token in line_tokens:
                    existing_by_tipo[token] = line
            candidate_codes = set()

            for tax_code, amount, rate, contrib_id in normalized_candidates:
                contribucion = self.env["aduana.catalogo.contribucion"].browse(contrib_id) if contrib_id else self._find_contribucion_catalog(tax_code)
                if not contribucion:
                    continue
                candidate_codes.add(self._norm_contrib_key(tax_code))
                line = existing_by_tipo.get(self._norm_contrib_key(tax_code))
                if line:
                    line.with_context(skip_auto_generated_refresh=True).write({
                        "contribucion_id": contribucion.id,
                        "forma_pago_id": (
                            partida.forma_pago_sugerida_id.id
                            if partida.forma_pago_sugerida_id
                            else (line.forma_pago_id.id if line.forma_pago_id else False)
                        ),
                        "importe": amount,
                        "base": partida.value_mxn or 0.0,
                        "tasa": rate,
                    })
                    continue
                contrib_model.with_context(skip_auto_generated_refresh=True).create({
                    "operacion_id": self.id,
                    "partida_id": partida.id,
                    "contribucion_id": contribucion.id,
                    "tipo_contribucion": tax_code,
                    "tasa": rate,
                    "base": partida.value_mxn or 0.0,
                    "importe": amount,
                    "forma_pago_id": partida.forma_pago_sugerida_id.id if partida.forma_pago_sugerida_id else False,
                })

            # Limpia solo las contribuciones autogestionadas que ya no aplican.
            stale_managed = existing_lines.filtered(
                lambda l: (
                    self._norm_contrib_key(l.tipo_contribucion) in managed_codes
                    or any(piece in managed_codes for piece in self._norm_contrib_key(l.tipo_contribucion).split("/") if piece)
                    or (l.contribucion_id and int(l.contribucion_id.code or 0) not in {0} and l.contribucion_id.code not in managed_contrib_codes)
                ) and (
                    self._norm_contrib_key(l.tipo_contribucion) not in candidate_codes
                    and not any(piece in candidate_codes for piece in self._norm_contrib_key(l.tipo_contribucion).split("/") if piece)
                )
            )
            if stale_managed:
                stale_managed.with_context(skip_auto_generated_refresh=True).unlink()
        self._sync_contribuciones_510_from_557()
        return True

    def _sync_contribuciones_510_from_557(self):
        """Consolida 557 para mantener 510 sincronizado sin captura manual."""
        self.ensure_one()
        grouped = {}
        for line in self.partida_contribucion_ids.sorted(
            lambda l: ((l.partida_id.numero_partida or 0) if l.partida_id else 0, l.sequence or 0, l.id)
        ):
            tipo = (line.tipo_contribucion or "").strip().upper()
            contrib_id = line.contribucion_id.id if getattr(line, "contribucion_id", False) else False
            if not tipo and not contrib_id:
                continue
            tasa = float(line.tasa or 0.0)
            forma_pago_id = line.forma_pago_id.id if line.forma_pago_id else False
            key = (contrib_id or tipo, tasa, forma_pago_id)
            if key not in grouped:
                grouped[key] = {
                    "contribucion_id": contrib_id,
                    "tipo_contribucion": tipo,
                    "tasa": tasa,
                    "base": 0.0,
                    "importe": 0.0,
                    "forma_pago_id": forma_pago_id,
                }
            grouped[key]["base"] += float(line.base or 0.0)
            grouped[key]["importe"] += float(line.importe or 0.0)

        # 510 no debe transmitir montos cero.
        grouped = {k: v for k, v in grouped.items() if float(v.get("importe") or 0.0) > 0.0}

        existing_by_key = {}
        stale_existing = self.env["mx.ped.contribucion.global"]
        for rec in self.contribucion_global_ids:
            key = (
                rec.contribucion_id.id if getattr(rec, "contribucion_id", False) else (rec.tipo_contribucion or "").strip().upper(),
                float(rec.tasa or 0.0),
                rec.forma_pago_id.id if rec.forma_pago_id else False,
            )
            if key not in existing_by_key:
                existing_by_key[key] = rec
            stale_existing |= rec

        global_model = self.env["mx.ped.contribucion.global"].with_context(skip_auto_generated_refresh=True)
        used = self.env["mx.ped.contribucion.global"]
        for item in grouped.values():
            key = (
                item.get("contribucion_id") or item["tipo_contribucion"],
                float(item["tasa"] or 0.0),
                item["forma_pago_id"],
            )
            line = existing_by_key.get(key)
            vals = {
                "contribucion_id": item.get("contribucion_id"),
                "tipo_contribucion": item["tipo_contribucion"],
                "tasa": item["tasa"],
                "base": item["base"],
                "importe": item["importe"],
                "forma_pago_id": item["forma_pago_id"],
            }
            if line:
                line.with_context(skip_auto_generated_refresh=True).write(vals)
                used |= line
            else:
                vals["operacion_id"] = self.id
                created = global_model.create(vals)
                used |= created

        stale = (stale_existing - used)
        if stale:
            stale.with_context(skip_auto_generated_refresh=True).unlink()

    @staticmethod
    def _norm_contrib_key(value):
        txt = (value or "").strip().upper()
        if not txt:
            return ""
        return re.sub(r"[^A-Z0-9/]+", "", txt)

    def _find_contribucion_catalog(self, raw_value):
        token = self._norm_contrib_key(raw_value)
        if not token:
            return self.env["aduana.catalogo.contribucion"]

        catalog = self.env["aduana.catalogo.contribucion"].search([("active", "=", True)])
        fallback_map = {
            "DTA": 1,
            "IVA": 3,
            "ISAN": 4,
            "IGI": 6,
            "IGE": 6,
            "REC": 7,
            "PRV": 15,
            "IEPS": 22,
        }

        fallback_code = fallback_map.get(token)
        if fallback_code:
            by_code = catalog.filtered(lambda rec: rec.code == fallback_code)[:1]
            if by_code:
                return by_code

        for rec in catalog:
            candidates = {
                self._norm_contrib_key(rec.abbreviation),
                self._norm_contrib_key(rec.contribucion),
                self._norm_contrib_key(str(rec.code)),
            }
            if token in candidates:
                return rec
        return self.env["aduana.catalogo.contribucion"]

    def _resolve_ap12_contrib_code(self, tipo_contribucion):
        """Resuelve la clave Ap.12 desde el tipo capturado en 557 (IGI/IVA/DTA/PRV...)."""
        if hasattr(tipo_contribucion, "contribucion_id") and tipo_contribucion.contribucion_id:
            return tipo_contribucion.contribucion_id.code
        token = self._norm_contrib_key(tipo_contribucion)
        if not token:
            return False

        fallback_map = {
            "DTA": 1,
            "IVA": 3,
            "ISAN": 4,
            "IGI": 6,
            "IGE": 6,
            "REC": 7,
            "PRV": 15,
            "IEPS": 22,
        }
        if token in fallback_map:
            return fallback_map[token]

        catalog = self.env["aduana.catalogo.contribucion"].search([("active", "=", True)])
        for rec in catalog:
            abbr = self._norm_contrib_key(rec.abbreviation)
            if not abbr:
                continue
            parts = {p for p in abbr.split("/") if p}
            if token == abbr or token in parts:
                return rec.code
        return False

    def _build_509_sources_from_partida_contribuciones(self):
        """Consolida lineas 557 para construir registros 509 a nivel pedimento."""
        self.ensure_one()
        grouped = {}
        tipo_tasa_default = str(
            self.env["ir.config_parameter"].sudo().get_param("mx_ped.tipo_tasa_default", "1") or "1"
        ).strip()

        lines = self.partida_contribucion_ids.sorted(
            lambda l: ((l.partida_id.numero_partida or 0) if l.partida_id else 0, l.sequence or 0, l.id)
        )
        for line in lines:
            if float(line.importe or 0.0) <= 0.0:
                continue
            ap12_code = self._resolve_ap12_contrib_code(line.tipo_contribucion)
            if not ap12_code:
                continue
            tasa = line.tasa if line.tasa not in (None, False) else 0.0
            tipo_tasa = tipo_tasa_default
            key = (int(ap12_code), float(tasa), tipo_tasa)
            if key not in grouped:
                grouped[key] = {
                    "clave_contribucion": int(ap12_code),
                    "tipo_contribucion": line.tipo_contribucion,
                    "tasa": tasa,
                    "tipo_tasa": tipo_tasa,
                    "base": 0.0,
                    "importe": 0.0,
                    "pedimento_numero": self.pedimento_numero or "",
                }
            grouped[key]["base"] += float(line.base or 0.0)
            grouped[key]["importe"] += float(line.importe or 0.0)

        return sorted(
            grouped.values(),
            key=lambda x: (x.get("clave_contribucion") or 0, x.get("tasa") or 0.0, x.get("tipo_tasa") or ""),
        )

    def _has_forma_pago_code(self, code):
        target = str(code or "").strip()
        if not target:
            return False
        return target in self._get_declared_formas_pago_codes()

    def _get_508_validation_reference_date(self):
        self.ensure_one()
        return self.fecha_pago or self.fecha_operacion or fields.Date.context_today(self)

    @staticmethod
    def _sanitize_511_text(value):
        txt = (value or "").strip()
        if not txt:
            return ""
        for ch in ("'", '"', "´", "*", "-", "_"):
            txt = txt.replace(ch, " ")
        txt = txt.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        txt = " ".join(txt.split())
        return txt[:120].strip()

    @staticmethod
    def _sanitize_512_pedimento(value):
        text = re.sub(r"\D+", "", str(value or ""))
        return text[:7]

    @staticmethod
    def _sanitize_512_patente(value):
        text = re.sub(r"\D+", "", str(value or ""))
        return text[:4]

    @staticmethod
    def _sanitize_512_fraction(value):
        text = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
        return text[:8]

    @staticmethod
    def _sanitize_512_numeric_code(value, size=2):
        text = re.sub(r"\D+", "", str(value or ""))
        return text[:size]

    def _get_511_observation_lines(self):
        self.ensure_one()
        lines = []
        explicit_lines = self.observacion_line_ids.sorted(lambda l: (l.sequence or 0, l.id))
        explicit_lines = explicit_lines.sorted(lambda l: ((l.sequence or 999999), l.id))
        for idx, line in enumerate(explicit_lines, start=1):
            clean_text = self._sanitize_511_text(line.texto)
            if clean_text:
                seq = line.sequence if line.sequence and line.sequence > 0 else idx
                lines.append({"sequence": seq, "texto": clean_text, "__source_id": line.id})
        return lines

    def _get_512_descargo_lines(self):
        self.ensure_one()
        lines = []
        explicit_lines = self.descargo_line_ids.sorted(lambda l: ((l.sequence or 999999), l.id))
        for idx, line in enumerate(explicit_lines, start=1):
            seq = line.sequence if line.sequence and line.sequence > 0 else idx
            fraccion = self._sanitize_512_fraction(line.fraccion_original or (line.fraccion_original_id.code if line.fraccion_original_id else ""))
            unidad_code = self._sanitize_512_numeric_code(
                line.unidad_medida_original_code or (line.unidad_medida_original_id.code if line.unidad_medida_original_id else ""),
                size=2,
            )
            aduana_code = (line.aduana_seccion_original or (line.aduana_seccion_original_id.code if line.aduana_seccion_original_id else "")).strip().upper()[:3]
            clave_doc = (line.clave_documento_original or (line.clave_documento_original_id.code if line.clave_documento_original_id else "")).strip().upper()[:2]
            fecha_txt = ""
            if line.fecha_operacion_original:
                fecha_txt = fields.Date.to_string(line.fecha_operacion_original)
            lines.append({
                "sequence": seq,
                "patente_original": self._sanitize_512_patente(line.patente_original),
                "pedimento_original": self._sanitize_512_pedimento(line.pedimento_original),
                "aduana_seccion_original": aduana_code,
                "clave_documento_original": clave_doc,
                "fecha_operacion_original": fecha_txt,
                "fraccion_original": fraccion,
                "unidad_medida_original": unidad_code,
                "cantidad_umt_original": line.cantidad_umt_original,
                "__source_id": line.id,
            })
        return lines

    @staticmethod
    def _sanitize_513_pedimento(value):
        text = re.sub(r"\D+", "", str(value or ""))
        return text[:7]

    @staticmethod
    def _sanitize_513_patente(value):
        text = re.sub(r"\D+", "", str(value or ""))
        return text[:4]

    def _get_513_compensacion_lines(self):
        self.ensure_one()
        if not self._has_forma_pago_code("12"):
            return []
        lines = []
        explicit_lines = self.compensacion_line_ids.sorted(lambda l: ((l.sequence or 999999), l.id))
        for idx, line in enumerate(explicit_lines, start=1):
            seq = line.sequence if line.sequence and line.sequence > 0 else idx
            aduana_code = (line.aduana_seccion_original or (line.aduana_seccion_original_id.code if line.aduana_seccion_original_id else "")).strip().upper()[:3]
            fecha_txt = ""
            if line.fecha_pago_original:
                fecha_txt = fields.Date.to_string(line.fecha_pago_original)
            contrib_code = ""
            if line.contribucion_compensada_id and line.contribucion_compensada_id.code is not None:
                contrib_code = str(line.contribucion_compensada_id.code).strip()
            lines.append({
                "sequence": seq,
                "patente_original": self._sanitize_513_patente(line.patente_original),
                "pedimento_original": self._sanitize_513_pedimento(line.pedimento_original),
                "aduana_seccion_original": aduana_code,
                "fecha_pago_original": fecha_txt,
                "contribucion_compensada": contrib_code,
                "importe_compensado": line.importe_compensado,
                "__source_id": line.id,
            })
        return lines

    def _validate_508_cuenta_aduanera_rules(self):
        """Valida condicion base de 508 contra formas de pago y calidad de datos."""
        self.ensure_one()
        has_fp4_or_15 = self._has_forma_pago_code("4") or self._has_forma_pago_code("15")
        has_508 = bool(self.cuenta_aduanera_ids)
        validation_ref_date = self._get_508_validation_reference_date()

        if has_fp4_or_15 and not has_508:
            raise ValidationError(_("Existe forma de pago 4 o 15, pero no hay lineas de cuenta aduanera (508)."))

        # NOTA: 508 es condicional; su presencia no siempre implica forma de pago 4/15.
        # El caso de exportacion con DMCA se controla por regla de negocio/rulepack.

        for line in self.cuenta_aduanera_ids:
            contrato = (line.numero_contrato or "").strip()
            folio = (line.folio_constancia or "").strip()
            if not contrato or len(contrato) != 17 or not contrato.isdigit() or set(contrato) == {"0"}:
                raise ValidationError(_("508: numero de contrato invalido en la linea %s.") % (line.sequence or line.id))
            if not folio or len(folio) > 17 or not folio.isalnum() or set(folio) == {"0"}:
                raise ValidationError(_("508: folio de constancia invalido en la linea %s.") % (line.sequence or line.id))
            if line.fecha_constancia and validation_ref_date and line.fecha_constancia > validation_ref_date:
                raise ValidationError(
                    _("508: la fecha de constancia no puede ser posterior a la fecha de validacion/referencia del pedimento en la linea %s.")
                    % (line.sequence or line.id)
                )
            if has_fp4_or_15:
                missing = []
                if not line.valor_unitario_titulo:
                    missing.append(_("valor unitario del titulo"))
                if not line.cantidad_um:
                    missing.append(_("cantidad en unidades de medida"))
                if not line.titulos_asignados:
                    missing.append(_("titulos asignados"))
                if missing:
                    raise ValidationError(
                        _("508: con forma de pago 4 o 15 son obligatorios %s en la linea %s.")
                        % (", ".join(missing), (line.sequence or line.id))
                    )
            if (
                line.valor_unitario_titulo
                and line.titulos_asignados
                and line.total_garantia
                and abs((line.valor_unitario_titulo * line.titulos_asignados) - line.total_garantia) > 0.02
            ):
                raise ValidationError(
                    _("508: incoherencia en montos (valor_unitario*titulos != total_garantia) en la linea %s.")
                    % (line.sequence or line.id)
                )

    def _validate_513_compensacion_rules(self):
        self.ensure_one()
        has_fp12 = self._has_forma_pago_code("12")
        has_513 = bool(self.compensacion_line_ids)

        if has_fp12 and not has_513:
            raise ValidationError(_("Existe forma de pago 12, pero no hay lineas de compensacion (513)."))

    def _validate_514_virtual_rules(self):
        self.ensure_one()
        required_codes = {"2", "4", "7", "12", "15", "19", "22"}
        declared = self._get_declared_formas_pago_codes()
        needed = declared & required_codes
        docs_514 = self.documento_ids.filtered(lambda d: (d.registro_codigo or "").strip() == "514")
        if needed and not docs_514:
            raise ValidationError(
                _("Existen formas de pago virtuales %s, pero no hay documentos 514.")
                % (", ".join(sorted(needed, key=lambda x: int(x))))
            )
        for code in sorted(needed, key=lambda x: int(x)):
            matching_docs = docs_514.filtered(lambda d: (d.forma_pago_code or "").strip() == code)
            if not matching_docs:
                raise ValidationError(_("Falta documento 514 para la forma de pago %s.") % code)
            for doc in matching_docs:
                if code == "12" and (doc.institucion_emisora_514 or "").strip() != "Aduanas":
                    raise ValidationError(_("514: con forma de pago 12 la institucion emisora debe ser Aduanas."))
                if not (doc.institucion_emisora_514 or "").strip():
                    raise ValidationError(_("514: la dependencia o institucion emisora es obligatoria."))
                if not (doc.folio or "").strip():
                    raise ValidationError(_("514: el numero de documento es obligatorio."))
                if not doc.fecha:
                    raise ValidationError(_("514: la fecha de expedicion es obligatoria."))
                if doc.importe_total_amparado_514 in (None, False) or doc.importe_total_amparado_514 <= 0:
                    raise ValidationError(_("514: el importe total amparado debe ser mayor a cero."))
                if doc.saldo_disponible_514 in (None, False) or doc.saldo_disponible_514 < 0:
                    raise ValidationError(_("514: el saldo disponible es obligatorio."))
                if doc.importe_total_pagar_514 in (None, False) or doc.importe_total_pagar_514 <= 0:
                    raise ValidationError(_("514: el importe total a pagar debe ser mayor a cero."))

    def _build_sync_payload_from_layout(self, layout_reg, source, code):
        """Construye payload usando campo.nombre y heuristicas por codigo."""
        values = {}
        fields_by_order = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)

        def _read_attr(obj, name):
            if not obj or not name:
                return None
            if isinstance(obj, dict):
                return obj.get(name)
            if hasattr(obj, name):
                return getattr(obj, name)
            return None

        def _pick_by_name(norm_name, default=None):
            # 510 / 557
            if "forma" in norm_name and "pago" in norm_name:
                return _read_attr(source, "forma_pago_code") or default
            if "pedimento" in norm_name and ("numero" in norm_name or "num" in norm_name or norm_name == "pedimento"):
                return _read_attr(source, "pedimento_numero") or self.pedimento_numero or default
            if "tipo" in norm_name and "tasa" in norm_name:
                return _read_attr(source, "tipo_tasa") or default
            if "importe" in norm_name or "monto" in norm_name:
                return _read_attr(source, "importe") if _read_attr(source, "importe") not in (None, False) else default
            if "base" in norm_name:
                return _read_attr(source, "base") if _read_attr(source, "base") not in (None, False) else default
            if "tasa" in norm_name:
                return _read_attr(source, "tasa") if _read_attr(source, "tasa") not in (None, False) else default
            if "clave" in norm_name and ("contrib" in norm_name or "impuesto" in norm_name):
                return (
                    _read_attr(source, "clave_contribucion")
                    or _read_attr(source, "contribucion_code")
                    or _read_attr(source, "tipo_contribucion")
                    or default
                )
            if "contrib" in norm_name or "impuesto" in norm_name:
                return _read_attr(source, "tipo_contribucion") or default

            # 557 / 514: numero de partida
            if norm_name in {"partida", "numero_partida", "num_partida", "partida_numero", "secuencia_partida", "partida_seq"}:
                partida = _read_attr(source, "partida_id")
                if partida and partida.numero_partida:
                    return partida.numero_partida
                return default

            # 557: fraccion_arancelaria viene de la partida relacionada.
            # El source object es mx.ped.partida.contribucion, que no tiene fraccion_arancelaria
            # directamente — se resuelve vía partida_id.
            if "fraccion" in norm_name and "arancelaria" in norm_name:
                partida = _read_attr(source, "partida_id")
                if partida:
                    frac = (
                        (_read_attr(partida, "fraccion_arancelaria") or "").strip()
                        or (partida.fraccion_id.code if _read_attr(partida, "fraccion_id") else "")
                    )
                    return frac or default
                return default

            # 514
            if code == "514":
                if "folio" in norm_name or "documento" in norm_name:
                    return _read_attr(source, "folio") or default
                if "fecha" in norm_name:
                    return _read_attr(source, "fecha") or default
                if norm_name in {"tipo", "tipo_doc", "tipo_documento"}:
                    return _read_attr(source, "tipo") or default

            return default

        for campo in fields_by_order:
            source_name = (
                campo.source_field_id.name
                if getattr(campo, "source_field_id", False)
                else campo.source_field
            ) or campo.nombre
            value = _read_attr(source, source_name)
            if value in (None, "", False):
                norm = self._norm_layout_token(campo.nombre)
                value = _pick_by_name(norm, default=value)
            value = self._json_safe_layout_value(value)
            if value not in (None, "", False):
                values[campo.nombre] = value
        return values

    def _sync_registro_ids_from_tecnicos(self):
        """Sincroniza registro_ids para codigos tecnicos (509/510/557/514)."""
        self.ensure_one()
        if not self.layout_id:
            return
        # Asegura 557/509 al dia aun cuando no hubo write previo en UI.
        self.with_context(skip_auto_generated_refresh=True).action_generar_contribuciones_557()

        layout_regs = {
            reg.codigo: reg
            for reg in self.layout_id.registro_ids.filtered(lambda r: r.codigo in {"509", "510", "557", "514"})
        }
        if not layout_regs:
            return

        desired = []
        if "509" in layout_regs:
            fuentes_509 = self._build_509_sources_from_partida_contribuciones()
            for idx, src in enumerate(fuentes_509, start=1):
                key = f"509:{src.get('clave_contribucion')}:{src.get('tasa')}:{src.get('tipo_tasa')}"
                payload = self._build_sync_payload_from_layout(layout_regs["509"], src, "509")
                payload["__sync_origin"] = "tecnico"
                payload["__sync_key"] = key
                desired.append({
                    "codigo": "509",
                    "secuencia": idx,
                    "key": key,
                    "valores": payload,
                })

        if "510" in layout_regs:
            for idx, line in enumerate(self.contribucion_global_ids.sorted(lambda l: (l.sequence or 0, l.id)), start=1):
                key = f"510:{line.id}"
                payload = self._build_sync_payload_from_layout(layout_regs["510"], line, "510")
                payload["__sync_origin"] = "tecnico"
                payload["__sync_key"] = key
                desired.append({
                    "codigo": "510",
                    "secuencia": idx,
                    "key": key,
                    "valores": payload,
                })

        if "557" in layout_regs:
            # 557 solo se genera cuando hay importe real > 0.
            # Para contribuciones exentas (tasa 0%, importe 0) el registro 557 no
            # debe aparecer per lineamiento — la tasa exenta se declara en 556.
            partida_contribs = self.partida_contribucion_ids.filtered(
                lambda l: (l.importe or 0.0) > 0
            ).sorted(
                lambda l: ((l.partida_id.numero_partida or 0) if l.partida_id else 0, l.sequence or 0, l.id)
            )
            for idx, line in enumerate(partida_contribs, start=1):
                key = f"557:{line.id}"
                payload = self._build_sync_payload_from_layout(layout_regs["557"], line, "557")
                payload["__sync_origin"] = "tecnico"
                payload["__sync_key"] = key
                desired.append({
                    "codigo": "557",
                    "secuencia": idx,
                    "key": key,
                    "valores": payload,
                })

        if "514" in layout_regs:
            docs = self.documento_ids.filtered(lambda d: (d.registro_codigo or "").strip() == "514").sorted(
                lambda d: (d.fecha or fields.Datetime.now(), d.id)
            )
            for idx, doc in enumerate(docs, start=1):
                key = f"514:{doc.id}"
                payload = self._build_514_valores(layout_regs["514"], doc)
                payload["__sync_origin"] = "tecnico"
                payload["__sync_key"] = key
                desired.append({
                    "codigo": "514",
                    "secuencia": idx,
                    "key": key,
                    "valores": payload,
                })

        by_key = {}
        stale = self.env["mx.ped.registro"]
        for reg in self.registro_ids.filtered(lambda r: (r.codigo or "") in {"509", "510", "557", "514"}):
            vals = reg.valores or {}
            if isinstance(vals, dict) and vals.get("__sync_origin") == "tecnico" and vals.get("__sync_key"):
                by_key[vals.get("__sync_key")] = reg
                stale |= reg

        used = self.env["mx.ped.registro"]
        reg_model = self.env["mx.ped.registro"]
        for item in desired:
            reg = by_key.get(item["key"])
            if reg:
                reg.write({"secuencia": item["secuencia"], "valores": item["valores"]})
                used |= reg
            else:
                created = reg_model.create({
                    "operacion_id": self.id,
                    "codigo": item["codigo"],
                    "secuencia": item["secuencia"],
                    "valores": item["valores"],
                })
                used |= created

        (stale - used).unlink()

    def _apply_registro_diff(self, desired):
        """Aplica un diff inteligente sobre registro_ids.

        ``desired`` es una lista de dicts con estructura::

            {
                "codigo":    str,
                "secuencia": int,
                "key":       str,   # __sync_key único
                "valores":   dict,  # ya incluye __sync_origin="auto" y __sync_key
            }

        Estrategia:
        - Registros con ``__sync_origin == "auto"`` son gestionados por este método.
        - Registros sin ``__sync_origin`` (creados manualmente) se preservan intactos.
        - Si el registro existente tiene la misma key → actualizar secuencia + valores.
        - Si la key es nueva → crear.
        - Si una key "auto" ya no está en desired → eliminar.
        - Primera ejecución (migración): si no existen registros "auto" pero sí hay
          registros no-técnicos sin __sync_origin, se reemplazan en bloque para
          evitar duplicados tras el primer deploy con este sistema.
        """
        self.ensure_one()
        TECNICO_CODES = {"509", "510", "557", "514"}
        reg_model = self.env["mx.ped.registro"]

        # Separar registros existentes por categoría
        auto_regs = self.env["mx.ped.registro"]   # gestionados por este método
        manual_regs = self.env["mx.ped.registro"]  # creados manualmente (sin origin)
        legacy_regs = self.env["mx.ped.registro"]  # sin origin, no técnicos

        for reg in self.registro_ids:
            if (reg.codigo or "") in TECNICO_CODES:
                continue  # los técnicos son responsabilidad de _sync_registro_ids_from_tecnicos
            vals = reg.valores or {}
            origin = vals.get("__sync_origin") if isinstance(vals, dict) else None
            if origin == "auto":
                auto_regs |= reg
            else:
                legacy_regs |= reg

        # Migración de primera ejecución: si no hay registros "auto" todavía
        # pero sí hay legacy no-técnicos, los borramos para que el diff los recree
        # correctamente (evita duplicados el primer día tras el deploy).
        if not auto_regs and legacy_regs:
            legacy_regs.unlink()
            auto_regs = self.env["mx.ped.registro"]

        # Índice por __sync_key para búsqueda O(1)
        by_key = {}
        for reg in auto_regs:
            vals = reg.valores or {}
            if isinstance(vals, dict) and vals.get("__sync_key"):
                by_key[vals["__sync_key"]] = reg

        used = self.env["mx.ped.registro"]
        for item in desired:
            reg = by_key.get(item["key"])
            if reg:
                # Actualizar solo si algo cambió (evita writes innecesarios)
                needs_update = (
                    reg.secuencia != item["secuencia"]
                    or reg.valores != item["valores"]
                )
                if needs_update:
                    reg.write({"secuencia": item["secuencia"], "valores": item["valores"]})
                used |= reg
            else:
                created = reg_model.create({
                    "operacion_id": self.id,
                    "codigo":       item["codigo"],
                    "secuencia":    item["secuencia"],
                    "valores":      item["valores"],
                })
                used |= created

        # Eliminar registros "auto" que ya no están en desired
        (auto_regs - used).unlink()

    def _relax_technical_required_states(self, states):
        """Relaja min/required en registros cuando no hay fuente de datos."""
        self.ensure_one()
        relaxed = dict(states or {})
        docs_514 = self.documento_ids.filtered(lambda d: (d.registro_codigo or "").strip() == "514")

        # Registros técnicos: solo requeridos si tienen fuente de datos.
        has_source = {
            "509": bool(self._build_509_sources_from_partida_contribuciones()),
            "510": bool(self.contribucion_global_ids),
            "514": bool(docs_514),
            "557": bool(self.partida_contribucion_ids),
        }
        # Registros opcionales por naturaleza: nunca bloquean si no hay datos.
        # 556 = tasas por partida (solo si la fracción tiene contribuciones),
        # 353/351/355/358 = T-MEC/TLCUEM (solo si se usan tratados).
        has_source_optional = {
            "556": bool(self.partida_contribucion_ids),
            "351": any(p.tmec_valor_mercancia_no_originaria for p in self.partida_ids),
            "353": any(p.tmec_valor_mercancia_no_originaria for p in self.partida_ids),
            "355": any(p.tmec_clave_contribucion for p in self.partida_ids),
            "358": any(p.tmec_clave_contribucion for p in self.partida_ids),
        }
        has_source.update(has_source_optional)

        for code, present in has_source.items():
            if present or code not in relaxed:
                continue
            state = dict(relaxed.get(code) or {})
            state["required"] = False
            state["min"] = 0
            relaxed[code] = state
        return relaxed

    def _validate_cancel_desist_structure(self):
        """Movimientos 2/3: estructura minima 500/800/801 sin mezclar otros."""
        self.ensure_one()
        mov = self._get_tipo_movimiento_effective()
        if mov not in {"2", "3"}:
            return
        codes = {(line.codigo or "").strip() for line in self.registro_ids if line.codigo}
        required = {"500", "800", "801"}
        missing = sorted(required - codes)
        extras = sorted(code for code in (codes - required) if code)
        if missing:
            raise ValidationError(
                _("Movimiento %s requiere estructura minima 500/800/801. Faltan: %s")
                % (mov, ", ".join(missing))
            )
        if extras:
            raise ValidationError(
                _("Movimiento %s no permite mezclar otros registros. No permitidos: %s")
                % (mov, ", ".join(extras))
            )

    def _run_process_stage_checks(self, stage):
        self.ensure_one()
        stage_rules = self._get_process_stage_rules(stage)
        for rule in stage_rules:
            payload = rule.payload_json or {}
            action = rule.action_type
            if action == "require_formas_pago":
                allowed = set(str(v) for v in (payload.get("allowed") or []))
                current = self._get_declared_formas_pago_codes()
                if not current:
                    raise ValidationError(
                        _("Regla %s: declara formas de pago en 510/557/514.") % (rule.name,)
                    )
                if allowed:
                    invalid = sorted(current - allowed, key=lambda x: int(x))
                    if invalid:
                        raise ValidationError(
                            _("Regla %s: formas permitidas %s. No permitidas: %s")
                            % (rule.name, ", ".join(sorted(allowed, key=lambda x: int(x))), ", ".join(invalid))
                        )
            elif action == "require_field":
                field_name = payload.get("field")
                if not field_name:
                    continue
                value = getattr(self, field_name, False)
                if not value:
                    raise ValidationError(_("Regla %s: el campo %s es obligatorio.") % (rule.name, field_name))
            elif action == "forbid_field":
                field_name = payload.get("field")
                if not field_name:
                    continue
                value = getattr(self, field_name, False)
                if value:
                    raise ValidationError(_("Regla %s: el campo %s debe estar vacio.") % (rule.name, field_name))
            if rule.stop:
                break

    def _validate_confirmacion_pago_formas(self):
        self.ensure_one()
        self._validate_cancel_desist_structure()
        self._run_process_stage_checks("pre_validate")
        self._validate_508_cuenta_aduanera_rules()
        self._validate_513_compensacion_rules()
        self._validate_514_virtual_rules()

    def _validate_510_forma_pago_required(self):
        self.ensure_one()
        missing = self.contribucion_global_ids.filtered(
            lambda l: (l.importe or 0.0) > 0 and not ((l.forma_pago_code or "").strip())
        )
        if not missing:
            return

        labels = []
        for line in missing:
            contrib = (
                (line.contribucion_id.abbreviation or "").strip()
                or (line.contribucion_id.contribucion or "").strip()
                or (line.tipo_contribucion or "").strip()
                or str(line.id)
            )
            labels.append(contrib)

        raise UserError(
            _("Falta la forma de pago en registro 510 para: %s")
            % (", ".join(labels))
        )

    def _normalize_structure_rules(self, estructura_rule, source_weight):
        normalized = []
        if not estructura_rule:
            return normalized
        for line in estructura_rule.line_ids.sorted(lambda l: (l.sequence, l.id)):
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            min_occ = max(line.min_occurs or 0, 0)
            if line.required:
                min_occ = max(min_occ, 1)
            normalized.append({
                "rule_id": line.id,
                "source": "estructura",
                "source_weight": source_weight,
                "specificity_score": 0,
                "priority": 0,
                "scope": "pedimento",
                "record_code": code,
                "policy": "required" if line.required else "optional",
                "min": min_occ,
                "max": max(line.max_occurs or 0, 0),
                "sequence": line.sequence or 0,
                "identifier": "",
                "stop": False,
                "active": True,
                "applies": True,
                "extra": {"estructura_regla_id": estructura_rule.id},
            })
        return normalized

    def _normalize_clave_rules(self, source_weight):
        normalized = []
        clave = self.clave_pedimento_id
        if not clave:
            return normalized
        for line in clave.registro_policy_ids.sorted(lambda l: (-l.priority, l.sequence, l.id)):
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            normalized.append({
                "rule_id": line.id,
                "source": "clave",
                "source_weight": source_weight,
                "specificity_score": self._compute_specificity(line, "clave"),
                "priority": line.priority or 0,
                "scope": line.scope or "pedimento",
                "record_code": code,
                "policy": line.policy,
                "min": max(line.min_occurs or 0, 0),
                "max": max(line.max_occurs or 0, 0),
                "sequence": line.sequence or 0,
                "identifier": (line.required_identifier_code or "").strip().upper(),
                "stop": bool(line.stop),
                "active": True,
                "applies": True,
                "extra": {"clave_id": clave.id},
            })
        return normalized

    def _normalize_condition_rules(self, condition_rules, source_weight):
        normalized = []
        for rule in condition_rules:
            if (rule.target_type or "record") != "record":
                continue
            if rule.policy not in {"required", "optional", "forbidden"}:
                continue
            normalized.append({
                "rule_id": rule.id,
                "source": "condition",
                "source_weight": source_weight,
                "specificity_score": self._compute_specificity(rule, "condition"),
                "priority": rule.priority or 0,
                "scope": rule.scope or "pedimento",
                "record_code": (rule.registro_codigo or "").strip(),
                "policy": rule.policy,
                "min": max(rule.min_occurs or 0, 0),
                "max": max(rule.max_occurs or 0, 0),
                "sequence": rule.sequence or 0,
                "identifier": (rule.required_identifier_code or "").strip().upper(),
                "stop": bool(rule.stop),
                "active": bool(rule.active),
                "applies": True,
                "extra": {
                    "fraccion_id": rule.fraccion_id.id if rule.fraccion_id else False,
                    "fraccion_capitulo": (rule.fraccion_capitulo or "").strip(),
                    "forma_pago_id": rule.forma_pago_id.id if getattr(rule, "forma_pago_id", False) else False,
                    "forma_pago_code": (rule.forma_pago_code or "").strip(),
                    "forma_pago_match": rule.forma_pago_match or "any",
                },
            })
        return normalized

    def _is_empty_rule_value(self, value):
        if value is None or value is False:
            return True
        if isinstance(value, str):
            return value.strip() == ""
        return False

    def _get_field_rules_for_record(self, codigo_registro, partida_num=None):
        """Reglas target=campo aplicables al registro (y partida, si aplica)."""
        self.ensure_one()
        record_code = str(codigo_registro or "").strip().zfill(3)
        if not record_code:
            return self.env["mx.ped.rulepack.condition.rule"]

        rules = self._get_dynamic_condition_rules().filtered(
            lambda r: (r.target_type or "record") == "field"
            and (r.registro_codigo or "").strip().zfill(3) == record_code
            and r.policy in {"require_field", "forbid_field", "default_field", "warn_field"}
        )
        if not rules:
            return rules

        partida_meta = self._get_partida_meta_map()

        def _partida_scope_match(rule):
            scope = rule.scope or "pedimento"
            if scope != "partida":
                return True
            if not partida_num:
                return False
            meta = partida_meta.get(partida_num, {})
            if rule.fraccion_id and rule.fraccion_id.id != meta.get("fraccion_id"):
                return False
            if (rule.fraccion_capitulo or "").strip():
                if (rule.fraccion_capitulo or "").strip() != str(meta.get("fraccion_capitulo") or "").strip():
                    return False
            return True

        return rules.filtered(_partida_scope_match).sorted(
            key=lambda r: (-r.priority, -self._compute_specificity(r, "condition"), r.sequence, r.id)
        )

    def _apply_field_rules_to_vals(self, codigo_registro, vals_dict, partida_num=None, validate_only=False):
        """Aplica reglas de campo sobre valores JSON (sin omitir columnas del layout)."""
        self.ensure_one()
        effective = dict(vals_dict or {})
        rules = self._get_field_rules_for_record(codigo_registro, partida_num=partida_num)
        # Para eliminación/desistimiento (mov 2/3) el acuse electrónico lo
        # asigna el SAAI tras presentar el TXT. Se omiten las reglas require_field
        # que lo exigen para permitir la exportación/validación inicial.
        for rule in rules:
            field_name = (rule.field_id.nombre or "").strip() if rule.field_id else ""
            if not field_name:
                continue

            current = effective.get(field_name)
            policy = rule.policy

            if policy == "forbid_field":
                effective[field_name] = ""
            elif policy == "default_field":
                if self._is_empty_rule_value(current) and not self._is_empty_rule_value(rule.default_value):
                    effective[field_name] = rule.default_value
            elif policy == "require_field":
                if self._is_empty_rule_value(current):
                    # Fallback: la regla puede usar un nombre de campo diferente
                    # al que el layout usa como clave en el dict de valores.
                    # Caso concreto: "Acuse Electrónico de Validación" (nombre
                    # human-readable del campo en la regla) vs "acuse_validacion"
                    # (snake_case que usa el layout). Para desistimiento/eliminación
                    # el lineamiento SAAI VOCE M3 pág. 35 exige el acuse del
                    # pedimento original; lo leemos directo del modelo.
                    if "acuse" in field_name.lower() and self._get_tipo_movimiento_effective() in {"2", "3"}:
                        acuse_model = (self.acuse_validacion or "").strip()
                        if acuse_model:
                            effective[field_name] = acuse_model  # inyectar en TXT
                        else:
                            raise ValidationError(
                                _("Regla %s: registro %s campo %s es obligatorio. "
                                  "Para eliminación/desistimiento debe ser el acuse "
                                  "(8 caracteres) del pedimento original que se cancela.")
                                % (rule.name or rule.id, str(codigo_registro or "").zfill(3), field_name)
                            )
                    else:
                        raise ValidationError(
                            _("Regla %s: registro %s campo %s es obligatorio.")
                            % (rule.name or rule.id, str(codigo_registro or "").zfill(3), field_name)
                        )
            elif policy == "warn_field":
                # Hook no bloqueante: se conserva para futura trazabilidad de advertencias.
                pass

            if rule.stop:
                break

        return effective

    def _validate_field_rules_on_registros(self):
        """Valida require_field sobre el set real que se exportara.

        Para eliminación/desistimiento (mov 2/3) el acuse del pedimento
        original es obligatorio en el campo 6 del registro 500 (Lineamientos
        SAAI VOCE M3, pág. 35). La validación del acuse se maneja en
        _apply_field_rules_to_vals, que lo inyecta desde self.acuse_validacion
        cuando la clave del campo no coincide con la del dict de valores.
        """
        self.ensure_one()
        for reg in self.registro_ids:
            code = (reg.codigo or "").strip()
            if not code:
                continue
            partida_num = self._extract_partida_number(reg.valores)
            self._apply_field_rules_to_vals(code, reg.valores or {}, partida_num=partida_num, validate_only=True)

    def _rule_sort_key(self, item):
        return (
            -(item.get("priority") or 0),
            -(item.get("specificity_score") or 0),
            -(item.get("source_weight") or 0),
            item.get("rule_id") or 0,
        )

    def _apply_rule_to_state(self, state, rule_item):
        policy = rule_item.get("policy")
        min_occ = max(rule_item.get("min") or 0, 0)
        max_occ = max(rule_item.get("max") or 0, 0)
        identifier = (rule_item.get("identifier") or "").strip().upper()

        if policy == "forbidden":
            state["forbidden"] = True
            state["required"] = False
            state["min"] = 0
            state["max"] = 0
        elif policy == "required" and not state.get("forbidden"):
            state["required"] = True
            state["min"] = max(state["min"], max(min_occ, 1))
        elif policy == "optional" and not state.get("forbidden"):
            state["min"] = max(state["min"], min_occ)

        if max_occ and not state.get("forbidden"):
            state["max"] = max_occ if not state["max"] else min(state["max"], max_occ)
        if identifier:
            state["identifier"] = identifier

    def _build_record_plan(self):
        """Construye plan determinista: normaliza reglas, aplica precedencias y guarda explicabilidad."""
        self.ensure_one()
        selected = self._select_rulepack_scenario()
        scenario = selected.get("scenario")
        estructura_rule = self.estructura_regla_id or selected.get("estructura_rule") or self._resolve_estructura_regla()
        rulepack = self._get_rulepack_effective()

        weights = self._get_source_weights(rulepack)
        condition_rules = self._get_dynamic_condition_rules()

        normalized = []
        normalized.extend(self._normalize_structure_rules(estructura_rule, weights["estructura"]))
        normalized.extend(self._normalize_clave_rules(weights["clave"]))
        normalized.extend(self._normalize_condition_rules(condition_rules, weights["condition"]))
        normalized = [n for n in normalized if n.get("record_code")]

        grouped = {}
        for item in normalized:
            key = (item.get("record_code"), item.get("scope") or "pedimento")
            grouped.setdefault(key, []).append(item)
        for key in list(grouped.keys()):
            grouped[key] = sorted(grouped[key], key=self._rule_sort_key)

        base_states = {}
        for item in normalized:
            if item.get("source") != "estructura" or (item.get("scope") or "pedimento") != "pedimento":
                continue
            code = item["record_code"]
            state = base_states.setdefault(code, {"required": False, "forbidden": False, "min": 0, "max": 0, "identifier": ""})
            self._apply_rule_to_state(state, item)

        states = {}
        record_resolution = {}
        trace_rows = []
        partida_policies = []

        for (code, scope), items in grouped.items():
            if scope == "partida":
                partida_policies.extend(items)
                continue
            state = dict(base_states.get(code, {"required": False, "forbidden": False, "min": 0, "max": 0, "identifier": ""}))
            winner = None
            blocked = False
            candidates = []
            for item in items:
                row = {
                    "rule_id": item["rule_id"],
                    "source": item["source"],
                    "record_code": code,
                    "scope": scope,
                    "policy": item["policy"],
                    "priority": item["priority"],
                    "source_weight": item["source_weight"],
                    "specificity_score": item["specificity_score"],
                    "min": item["min"],
                    "max": item["max"],
                    "sequence": item.get("sequence") or 0,
                    "identifier": item["identifier"],
                    "stop": item["stop"],
                    "matched": True,
                    "applied": False,
                    "blocked": False,
                }
                if blocked:
                    row["blocked"] = True
                    candidates.append(row)
                    continue
                self._apply_rule_to_state(state, item)
                row["applied"] = True
                candidates.append(row)
                if winner is None:
                    winner = row
                if item.get("stop"):
                    blocked = True

            if state.get("forbidden"):
                state["required"] = False
                state["min"] = 0
                state["max"] = 0
            states[code] = state
            record_resolution[f"{code}|{scope}"] = {
                "base_state": base_states.get(code, {"required": False, "forbidden": False, "min": 0, "max": 0, "identifier": ""}),
                "winner_rule_id": winner["rule_id"] if winner else False,
                "winner_source": winner["source"] if winner else False,
                "candidates": candidates,
                "final_state": state,
            }
            trace_rows.extend(candidates)

        diff = {"added_records": [], "removed_records": [], "changed_records": []}
        final_keys = set(states.keys())
        base_keys = set(base_states.keys())
        diff["added_records"] = sorted(list(final_keys - base_keys))
        diff["removed_records"] = sorted(list(base_keys - final_keys))
        for code in sorted(final_keys & base_keys):
            if states[code] != base_states[code]:
                diff["changed_records"].append({"key": f"{code}|pedimento", "from": base_states[code], "to": states[code]})

        return {
            "rulepack": rulepack,
            "scenario": scenario,
            "rule": estructura_rule,
            "states": states,
            "base_states": base_states,
            "trace": trace_rows,
            "record_resolution": record_resolution,
            "selector_trace": selected.get("selector_trace") or {"candidates": [], "winner_selector_id": False},
            "winner_selector_id": selected.get("winner_selector").id if selected.get("winner_selector") else False,
            "partida_policies": sorted(partida_policies, key=self._rule_sort_key),
            "normalized_rules": normalized,
            "diff_base_final": diff,
            "weights": weights,
        }

    def _get_record_order_map(self):
        self.ensure_one()
        plan = self._build_record_plan()
        resolution = plan.get("record_resolution") or {}
        order_map = {}
        for key, meta in resolution.items():
            code = (key.split("|", 1)[0] or "").strip()
            if not code:
                continue
            candidates = meta.get("candidates") or []
            winner_sequence = None
            for candidate in candidates:
                if candidate.get("applied"):
                    winner_sequence = candidate.get("sequence") or 0
                    break
            order_map[code] = winner_sequence if winner_sequence is not None else 0
        return order_map

    def _layout_registro_sort_key(self, layout_reg, order_map=None):
        self.ensure_one()
        code = (layout_reg.codigo or "").strip()
        layout_order = layout_reg.orden or 0
        if order_map is None:
            order_map = self._get_record_order_map()
        rule_sequence = order_map.get(code)
        if rule_sequence and rule_sequence > 0:
            return (rule_sequence, layout_order, code, layout_reg.id)
        return (999999, layout_order, code, layout_reg.id)

    # Orden canónico Lineamientos TR cuando el registro no está definido en el layout.
    _CANONICAL_REGISTRO_ORDER = {
        # Complementario (CT) – van antes del encabezado 500
        "301":   5, "302":   6,
        "500":  10, "501":  20, "502":  25, "516":  27, "503":  30, "504":  35,
        "520":  37, "505":  40, "506":  45, "507":  50, "508":  55, "509":  60,
        "510":  65, "511":  70, "512":  75, "513":  80, "514":  85,
        "601":  88, "701":  89, "702":  90,
        "551": 100, "552": 105, "553": 110, "554": 115, "555": 120,
        "556": 125, "557": 130, "558": 135, "560": 140,
        "351": 150, "352": 155, "353": 160, "355": 165, "358": 170,
        "800": 900, "801": 910,
    }

    def _registro_export_sort_key(self, reg, order_map=None):
        self.ensure_one()
        code = (reg.codigo or "").strip()
        if order_map is None:
            order_map = self._get_record_order_map()
        rule_sequence = order_map.get(code)
        partida_num = self._extract_partida_number(reg.valores) or 0
        if rule_sequence and rule_sequence > 0:
            return (rule_sequence, code, partida_num, reg.secuencia or 0, reg.id)
        layout_reg = self._get_layout_registro(code)
        if layout_reg:
            return (999999, layout_reg.orden, code, partida_num, reg.secuencia or 0, reg.id)
        canonical = self._CANONICAL_REGISTRO_ORDER.get(code, 500)
        return (999999, canonical, code, partida_num, reg.secuencia or 0, reg.id)

    def _store_rule_trace(self, plan):
        self.ensure_one()
        if not self.id or self.env.context.get("skip_rule_trace_write"):
            return
        plan = plan or {}
        trace_rows = plan.get("trace") or []
        truncated = False
        if len(trace_rows) > 500:
            trace_rows = trace_rows[:500]
            truncated = True
        trace_payload = {
            "meta": {
                "operation_id": self.id,
                "generated_at": fields.Datetime.now().isoformat(),
                "strict_mode": self._is_strict_mode(),
                "rulepack_id": plan.get("rulepack").id if plan.get("rulepack") else False,
                "rulepack_code": plan.get("rulepack").code if plan.get("rulepack") else False,
                "fecha_operacion": str(self.fecha_operacion or ""),
                "trace_truncated": truncated,
            },
            "selector_trace": plan.get("selector_trace") or {"candidates": [], "winner_selector_id": False},
            "winner_selector_id": plan.get("winner_selector_id") or False,
            "records": plan.get("record_resolution") or {},
            "diff_base_final": plan.get("diff_base_final") or {},
            "states": plan.get("states") or {},
            "trace": trace_rows,
            "errors": plan.get("errors") or [],
        }
        self.with_context(skip_rule_trace_write=True).write({
            "rule_trace_json": trace_payload,
            "rule_trace_at": fields.Datetime.now(),
        })

    def _get_stage_allowed_codes(self, stage):
        self.ensure_one()
        rules = self._get_process_stage_rules(stage)
        allowed = None
        for rule in rules:
            if rule.action_type != "allow_only_records":
                continue
            payload = rule.payload_json or {}
            rule_codes = {str(code).zfill(3) for code in (payload.get("codes") or []) if str(code).strip()}
            if allowed is None:
                allowed = rule_codes
            else:
                allowed &= rule_codes
            if rule.stop:
                break
        return allowed

    def _get_dynamic_condition_rules(self):
        self.ensure_one()
        rulepack = self._get_rulepack_effective()
        if not rulepack:
            return self.env["mx.ped.rulepack.condition.rule"]
        context = self._build_rule_context(self._detect_escenario_estructura())
        rules = rulepack.condition_rule_ids.filtered(lambda r: r.active).sorted(
            key=lambda r: (-r.priority, r.sequence, r.id)
        )
        return rules.filtered(lambda r: self._rule_condition_match(r, context))

    def _get_allowed_codes_from_regla(self):
        self.ensure_one()
        plan = self._build_record_plan()
        self._store_rule_trace(plan)
        states = plan["states"]

        # Sin regla base no restringimos layout para evitar omisiones no deseadas.
        if not plan["rule"]:
            return None

        allowed = {code for code, state in states.items() if not state.get("forbidden")}
        return allowed if allowed else None

    def _validate_registros_vs_estructura(self):
        self.ensure_one()
        # Para eliminación/desistimiento (mov 2/3) la estructura válida es
        # exclusivamente 500/800/801. _validate_cancel_desist_structure() ya
        # la verifica antes de llegar aquí; el plan de rulepack completo
        # (que exige 502, partidas, etc.) no aplica y se omite.
        if self._get_tipo_movimiento_effective() in {"2", "3"}:
            return
        counts = Counter((r.codigo or "") for r in self.registro_ids)
        errors = []

        plan = self._build_record_plan()
        self._store_rule_trace(plan)
        states = self._relax_technical_required_states(plan["states"])

        for code, state in states.items():
            present = counts.get(code, 0)
            min_occ = max(state.get("min") or 0, 0)
            max_occ = max(state.get("max") or 0, 0)

            if state.get("forbidden"):
                if present > 0:
                    errors.append(_("Registro %s esta prohibido para este contexto y se encontraron %s.") % (code, present))
                continue

            if state.get("required") and present < max(min_occ, 1):
                errors.append(_("Falta registro %s (min %s, actual %s).") % (code, max(min_occ, 1), present))
            elif min_occ and present < min_occ:
                errors.append(_("Falta registro %s (min %s, actual %s).") % (code, min_occ, present))

            if max_occ and present > max_occ:
                errors.append(_("Registro %s excede maximo (%s > %s).") % (code, present, max_occ))

            identifier = (state.get("identifier") or "").strip().upper()
            if identifier and present:
                has_identifier = any(
                    self._payload_has_token(reg.valores, identifier)
                    for reg in self.registro_ids
                    if (reg.codigo or "") == code
                )
                if not has_identifier:
                    errors.append(_("Registro %s exige identificador %s.") % (code, identifier))

        # Reglas con alcance partida: se validan por cada numero_partida.
        partida_policies = [p for p in (plan.get("partida_policies") or []) if (p.get("scope") or "pedimento") == "partida"]
        if partida_policies:
            partida_numbers = self._get_partida_numbers_for_validation()
            partida_meta = self._get_partida_meta_map()
            if not partida_numbers:
                errors.append(_(
                    "Existen reglas de alcance partida pero no hay numero_partida capturado en partidas o registros."
                ))
            else:
                per_partida_counts = {}
                per_partida_has_identifier = {}
                for reg in self.registro_ids:
                    code = (reg.codigo or "").strip()
                    partida_num = self._extract_partida_number(reg.valores)
                    if not partida_num:
                        continue
                    per_partida_counts[(partida_num, code)] = per_partida_counts.get((partida_num, code), 0) + 1
                    for policy in partida_policies:
                        if policy.get("record_code") != code:
                            continue
                        identifier = (policy.get("identifier") or "").strip().upper()
                        if identifier and self._payload_has_token(reg.valores, identifier):
                            per_partida_has_identifier[(partida_num, code)] = True

                for partida_num in partida_numbers:
                    partida_state = {}
                    blocked_codes = set()
                    meta = partida_meta.get(partida_num, {})
                    fraccion_id = meta.get("fraccion_id")
                    for policy in partida_policies:
                        code = policy.get("record_code")
                        if not code or code in blocked_codes:
                            continue
                        policy_fraccion = (policy.get("extra") or {}).get("fraccion_id")
                        policy_capitulo = ((policy.get("extra") or {}).get("fraccion_capitulo") or "").strip()
                        if policy_fraccion and policy_fraccion != fraccion_id:
                            continue
                        if policy_capitulo and not str(partida_meta.get(partida_num, {}).get("fraccion_capitulo", "")).strip() == policy_capitulo:
                            continue
                        state = partida_state.setdefault(code, {
                            "required": False,
                            "forbidden": False,
                            "min": 0,
                            "max": 0,
                            "identifier": "",
                        })
                        policy_type = policy.get("policy")
                        min_occ = max(policy.get("min") or 0, 0)
                        max_occ = max(policy.get("max") or 0, 0)
                        identifier = (policy.get("identifier") or "").strip().upper()

                        if policy_type == "forbidden":
                            state["forbidden"] = True
                            state["required"] = False
                            state["min"] = 0
                            state["max"] = 0
                        elif policy_type == "required" and not state["forbidden"]:
                            state["required"] = True
                            state["min"] = max(state["min"], max(min_occ, 1))
                        elif policy_type == "optional" and not state["forbidden"]:
                            state["min"] = max(state["min"], min_occ)

                        if max_occ and not state["forbidden"]:
                            state["max"] = max_occ if not state["max"] else min(state["max"], max_occ)
                        if identifier:
                            state["identifier"] = identifier
                        if policy.get("stop"):
                            blocked_codes.add(code)

                    for code, state in partida_state.items():
                        present = per_partida_counts.get((partida_num, code), 0)
                        min_occ = max(state.get("min") or 0, 0)
                        max_occ = max(state.get("max") or 0, 0)

                        if state.get("forbidden"):
                            if present > 0:
                                errors.append(_(
                                    "Partida %s: registro %s esta prohibido y se encontraron %s."
                                ) % (partida_num, code, present))
                            continue

                        if state.get("required") and present < max(min_occ, 1):
                            errors.append(_(
                                "Partida %s: falta registro %s (min %s, actual %s)."
                            ) % (partida_num, code, max(min_occ, 1), present))
                        elif min_occ and present < min_occ:
                            errors.append(_(
                                "Partida %s: falta registro %s (min %s, actual %s)."
                            ) % (partida_num, code, min_occ, present))

                        if max_occ and present > max_occ:
                            errors.append(_(
                                "Partida %s: registro %s excede maximo (%s > %s)."
                            ) % (partida_num, code, present, max_occ))

                        identifier = (state.get("identifier") or "").strip().upper()
                        if identifier and present and not per_partida_has_identifier.get((partida_num, code), False):
                            errors.append(_(
                                "Partida %s: registro %s exige identificador %s."
                            ) % (partida_num, code, identifier))

        if errors:
            plan["errors"] = errors
            self._store_rule_trace(plan)
            raise UserError("\n".join(errors))

    def _prune_forbidden_registros(self):
        self.ensure_one()
        if not self.registro_ids:
            return
        plan = self._build_record_plan()
        states = plan.get("states") or {}
        forbidden_codes = {
            code for code, state in states.items()
            if state.get("forbidden")
        }
        if not forbidden_codes:
            return
        forbidden_regs = self.registro_ids.filtered(lambda r: (r.codigo or "").strip() in forbidden_codes)
        if forbidden_regs:
            forbidden_regs.unlink()

    def action_preparar_estructura(self):
        for rec in self:
            plan = rec._build_record_plan()
            rule = plan.get("rule")
            if not rule and not plan.get("states"):
                raise UserError(_("No existe una regla de estructura para este contexto."))
            if rule:
                rec.estructura_regla_id = rule
            counts = Counter((r.codigo or "") for r in rec.registro_ids)
            new_lines = []
            states = plan.get("states") or {}
            line_order = {}
            if rule:
                for idx, line in enumerate(rule.line_ids.sorted(lambda l: (l.sequence, l.id)), start=1):
                    code = (line.registro_codigo or "").strip()
                    if code and code not in line_order:
                        line_order[code] = idx

            for code in sorted(states.keys(), key=lambda c: (line_order.get(c, 9999), c)):
                state = states[code]
                if state.get("forbidden"):
                    continue
                min_occurs = max(state.get("min") or 0, 0)
                if state.get("required"):
                    min_occurs = max(min_occurs, 1)
                needed = min_occurs - counts.get(code, 0)
                seq_base = counts.get(code, 0)
                for i in range(max(needed, 0)):
                    new_lines.append((0, 0, {
                        "codigo": code,
                        "secuencia": seq_base + i + 1,
                        "valores": {},
                    }))
                counts[code] = counts.get(code, 0) + max(needed, 0)
            if new_lines:
                rec.write({"registro_ids": new_lines})
            rec._store_rule_trace(plan)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Estructura preparada"),
                "message": _("Registros base agregados según regla de estructura."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_simular_estructura(self):
        self.ensure_one()
        plan = self._build_record_plan()
        states = self._relax_technical_required_states(plan.get("states") or {})
        counts = Counter((r.codigo or "") for r in self.registro_ids)

        missing = []
        forbidden = []
        for code, state in sorted(states.items()):
            present = counts.get(code, 0)
            min_occ = max(state.get("min") or 0, 0)
            if state.get("required"):
                min_occ = max(min_occ, 1)
            if state.get("forbidden"):
                if present:
                    forbidden.append(f"{code}({present})")
                continue
            if min_occ and present < min_occ:
                missing.append(f"{code}({present}/{min_occ})")

        summary = [
            _("Regla: %s") % (plan.get("rule").display_name if plan.get("rule") else _("sin regla")),
            _("Faltantes: %s") % (", ".join(missing) if missing else _("ninguno")),
            _("Prohibidos presentes: %s") % (", ".join(forbidden) if forbidden else _("ninguno")),
        ]
        plan["errors"] = []
        if missing:
            plan["errors"].append(_("Faltan registros obligatorios."))
        if forbidden:
            plan["errors"].append(_("Hay registros prohibidos capturados."))
        self._store_rule_trace(plan)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Simulacion de estructura"),
                "message": "\n".join(summary),
                "type": "warning" if (missing or forbidden) else "success",
                "sticky": bool(missing or forbidden),
            },
        }

    def action_explain_ruleplan(self):
        self.ensure_one()
        plan = self._build_record_plan()
        self._store_rule_trace(plan)
        payload = self.rule_trace_json or {}
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        attachment = self.env["ir.attachment"].create({
            "name": f"RULEPLAN_{self.name or self.id}.json",
            "type": "binary",
            "datas": base64.b64encode(data),
            "mimetype": "application/json",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _get_invoice_partner(self):
        self.ensure_one()
        lead = self.lead_id
        partner = lead.partner_id or lead.x_importador_id or lead.x_exportador_id
        if not partner:
            raise UserError(
                _("La operación no tiene cliente para facturar. Define Cliente/Importador/Exportador en el Lead.")
            )
        return partner

    def _get_invoice_origin(self):
        self.ensure_one()
        parts = [self.name or ""]
        if self.pedimento_numero:
            parts.append(f"PED-{self.pedimento_numero}")
        return " / ".join([p for p in parts if p])

    def _prepare_optional_invoice_lines(self):
        self.ensure_one()
        lead = self.lead_id
        concepts = [
            (_("Honorarios aduanales"), lead.x_costo_estimado),
            (_("DTA estimado"), lead.x_dta_estimado),
            (_("PRV estimado"), lead.x_prv_estimado),
            (_("IGI estimado"), lead.x_igi_estimado),
            (_("IVA estimado"), lead.x_iva_estimado),
        ]
        lines = []
        for name, amount in concepts:
            if amount and amount > 0:
                lines.append((0, 0, {
                    "name": name,
                    "quantity": 1.0,
                    "price_unit": amount,
                }))
        return lines

    def action_crear_factura(self):
        self.ensure_one()
        partner = self._get_invoice_partner()
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "currency_id": self.currency_id.id,
            "invoice_origin": self._get_invoice_origin(),
            "x_ped_operacion_id": self.id,
        })

        line_vals = self._prepare_optional_invoice_lines()
        if line_vals:
            try:
                move.write({"invoice_line_ids": line_vals})
            except Exception:
                # Fallback: keep invoice linked even if product/account setup is incomplete.
                move.write({
                    "invoice_line_ids": [(0, 0, {
                        "display_type": "line_note",
                        "name": _("No se pudieron crear líneas automáticas. Revisa cuentas/productos de facturación."),
                    })]
                })

        if self.lead_id:
            self.lead_id.write({
                "x_factura_emitida": True,
                "x_factura_ref": move.name or str(move.id),
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Factura"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_facturas(self):
        self.ensure_one()
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        action["domain"] = [("x_ped_operacion_id", "=", self.id), ("move_type", "=", "out_invoice")]
        action["context"] = {
            "default_move_type": "out_invoice",
            "default_partner_id": self._get_invoice_partner().id,
            "default_currency_id": self.currency_id.id,
            "default_x_ped_operacion_id": self.id,
            "default_invoice_origin": self._get_invoice_origin(),
        }
        return action

    # ==========================
    # Exportación TXT / XML
    # ==========================
    def _get_layout_registro(self, codigo):
        self.ensure_one()
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        matches = self.layout_id.registro_ids.filtered(lambda r: r.codigo == codigo)
        if not matches:
            raise UserError(_("No existe layout para el registro %s.") % codigo)
        return matches.sorted(lambda r: r.orden or 0)[0]

    def _format_txt_value(self, campo, val):
        if val == self._LAYOUT_EMPTY:
            return ""
        if val is False or val is None:
            return ""
        txt = str(val)

        # Sanea caracteres de control para no romper el TXT por renglones/columnas.
        txt = txt.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        txt = txt.replace("|", " ")
        txt = " ".join(txt.split())

        # Normaliza tipo de operaci?n (1/2). Si el layout pide 2 d?gitos, se rellena.
        source_name = (
            campo.source_field_id.name
            if getattr(campo, "source_field_id", False)
            else campo.source_field
        ) or campo.nombre
        if source_name in ("tipo_operacion", "x_tipo_operacion"):
            normalized = txt.strip().lower()
            if normalized in ("importacion", "1", "01"):
                txt = "1"
            elif normalized in ("exportacion", "2", "02"):
                txt = "2"
            if campo.longitud == 2:
                txt = txt.zfill(2)

        if campo.tipo == "N":
            decimals = None
            if campo.formato and "," in campo.formato:
                try:
                    _, decimal_part = str(campo.formato).split(",", 1)
                    decimals = int(decimal_part)
                except Exception:
                    decimals = None

            if decimals is not None:
                try:
                    numeric = float(val)
                except Exception:
                    numeric = None
                if numeric is not None:
                    if campo.layout_export_format == "pipe":
                        txt = f"{numeric:.{decimals}f}".rstrip("0").rstrip(".")
                    else:
                        txt = f"{numeric:.{decimals}f}".replace(".", "")
                        if campo.longitud:
                            txt = txt.zfill(campo.longitud)
                else:
                    txt = txt.replace(",", "")
            else:
                txt = "".join(ch for ch in txt if ch.isdigit())
        # Normaliza paises a clave corta cuando el campo es de pais y longitud pequena.
        # Evita errores tipo "excede longitud 3" por valores como "MEXICO".
        source_norm = (source_name or "").strip().lower()
        if (
            campo.tipo in ("A", "AN")
            and campo.longitud
            and campo.longitud <= 3
            and ("pais" in source_norm or "country" in source_norm)
        ):
            txt = self._normalize_country_token(txt, campo.longitud)
        return txt

    def _normalize_country_token(self, raw_value, max_len):
        token = (raw_value or "").strip()
        if not token:
            return ""

        # Si ya cabe, no tocar.
        if len(token) <= max_len:
            return token

        upper = token.upper()
        country_model = self.env["res.country"].sudo()

        country = country_model.search([("code", "=", upper)], limit=1)
        if not country:
            country = country_model.search([("name", "=ilike", token)], limit=1)
        if not country:
            country = country_model.search([("name", "ilike", token)], limit=1)

        if country and country.code:
            code = country.code.strip().upper()
            if len(code) <= max_len:
                return code

        # Ultimo recurso: truncar para no romper exportacion.
        return token[:max_len]

    def _build_txt_line(self, layout_registro, valores, partida_num=None):
        layout = layout_registro.layout_id
        campos = layout_registro.campo_ids.sorted(lambda c: c.orden or c.pos_ini or 0)
        effective_vals = self._apply_field_rules_to_vals(
            layout_registro.codigo,
            dict(valores or {}),
            partida_num=partida_num,
        )

        if layout.export_format == "pipe":
            parts = []
            for campo in campos:
                val = effective_vals.get(campo.nombre)
                if (val is None or val == "" or val is False) and layout_registro.codigo == "501":
                    val = self._get_501_field_fallback_value(campo)
                if val in (None, ""):
                    if campo.default:
                        val = campo.default
                    elif campo.requerido:
                        raise UserError(
                            _("Falta el campo requerido %s en registro %s.")
                            % (campo.nombre, layout_registro.codigo)
                        )
                    else:
                        val = ""

                txt = self._format_txt_value(campo, val)
                if campo.longitud and len(txt) > campo.longitud:
                    raise UserError(
                        _("El campo %s excede la longitud %s.")
                        % (campo.nombre, campo.longitud)
                    )
                parts.append(txt)

            return (layout.field_separator or "|").join(parts)

        line = [" "] * 2000
        max_pos = 0
        for campo in campos:
            if not campo.pos_ini or not campo.pos_fin:
                raise UserError(
                    _("El campo %s del registro %s no tiene posiciones válidas.")
                    % (campo.nombre, layout_registro.codigo)
                )
            length = campo.longitud or (campo.pos_fin - campo.pos_ini + 1)

            val = effective_vals.get(campo.nombre)
            if (val is None or val == "" or val is False) and layout_registro.codigo == "501":
                val = self._get_501_field_fallback_value(campo)
            if val in (None, ""):
                if campo.default:
                    val = campo.default
                elif campo.requerido:
                    raise UserError(
                        _("Falta el campo requerido %s en registro %s.")
                        % (campo.nombre, layout_registro.codigo)
                    )
                else:
                    val = ""

            txt = self._format_txt_value(campo, val)

            if len(txt) > length:
                raise UserError(
                    _("El campo %s excede la longitud %s.")
                    % (campo.nombre, length)
                )

            if campo.tipo in ("A", "AN", "F"):
                txt = txt.ljust(length)
            else:
                txt = txt.rjust(length, "0")

            pos_ini = campo.pos_ini - 1
            pos_fin = pos_ini + length
            if pos_fin > len(line):
                line.extend([" "] * (pos_fin - len(line)))
            line[pos_ini:pos_fin] = list(txt)
            max_pos = max(max_pos, pos_fin)

        return "".join(line[:max_pos])

    def _get_501_field_fallback_value(self, campo):
        self.ensure_one()
        source_name = (campo.source_field_id.name if getattr(campo, "source_field_id", False) else campo.source_field) or ""
        campo_name = self._norm_layout_token(campo.nombre)
        source_norm = self._norm_layout_token(source_name)
        token = f"{campo_name} {source_norm}".strip()
        token_compact = token.replace(" ", "").replace("_", "")
        source_compact = source_norm.replace(" ", "").replace("_", "")

        if source_compact == "totalgrossweight" or "pesobruto" in token_compact:
            return self.total_gross_weight
        if source_compact == "totalnetweight" or "pesoneto" in token_compact:
            return self.total_net_weight
        if source_compact == "totalpackagesline" or "bulto" in token_compact or "paquete" in token_compact:
            return self.total_packages_line
        return None

    def _build_txt_line_pipe_direct(self, codigo, valores):
        """Serializa un registro sin layout_reg usando pipe, en el orden de inserción del dict valores.
        Usado para registros auto-inyectados (502/503/504) que no tienen entrada en el layout activo.
        """
        sep = (self.layout_id.field_separator or "|") if self.layout_id else "|"
        parts = [str(v) if v not in (None, False) else "" for v in (valores or {}).values()]
        return sep.join(parts)

    def _build_export_lines_from_registros(self, registros):
        self.ensure_one()
        lines = []
        for reg in registros:
            layout_reg = self._get_layout_registro(reg.codigo)
            partida_num = self._extract_partida_number(reg.valores)
            if layout_reg:
                lines.append(self._build_txt_line(layout_reg, reg.valores, partida_num=partida_num))
            else:
                lines.append(self._build_txt_line_pipe_direct(reg.codigo, reg.valores))
        return lines

    def _build_remesa_txt_member_name(self, remesa, suffix=".txt"):
        self.ensure_one()
        token = (remesa.folio or remesa.name or f"remesa_{remesa.sequence or remesa.id}").strip()
        token = re.sub(r"[^A-Za-z0-9._-]+", "_", token).strip("._-") or f"remesa_{remesa.id}"
        pedimento = re.sub(r"[^A-Za-z0-9._-]+", "_", str(self.pedimento_numero or self.name or self.id))
        return f"{pedimento}_{token}{suffix}"

    def _build_remesa_zip_name(self):
        self.ensure_one()
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(self.pedimento_numero or self.name or self.id)).strip("._-")
        return f"{base or 'pedimento'}_remesas.zip"

    def _get_remesa_514_registros(self, remesa):
        self.ensure_one()
        layout_reg = self._get_layout_registro("514")
        if not layout_reg:
            return []
        docs = remesa.documento_ids.filtered(lambda d: (d.registro_codigo or "").strip() == "514").sorted(
            lambda d: (d.fecha or fields.Datetime.now(), d.id)
        )
        registros = []
        for secuencia, doc in enumerate(docs, start=1):
            payload = self._build_514_valores(layout_reg, doc)
            registros.append({
                "codigo": "514",
                "secuencia": secuencia,
                "valores": payload,
            })
        return registros

    def _get_remesa_557_registros(self, remesa):
        """Genera registros 557 pro-rateados por valor/cantidad para una remesa.

        Cada contribucion de cada partida asignada a la remesa se incluye con
        importe y base proporcionales a la fraccion de valor USD (o cantidad si
        value_usd es cero) que corresponde a esta remesa respecto al total de
        la partida.  La tasa porcentual se mantiene intacta.
        """
        self.ensure_one()
        layout_reg = self._get_layout_registro("557")
        if not layout_reg:
            return []

        registros = []
        secuencia = 0
        ordered_rel = remesa.partida_rel_ids.sorted(
            lambda rel: (
                (rel.partida_id.numero_partida or 0) if rel.partida_id else 0,
                rel.sequence or 0,
                rel.id,
            )
        )

        for remesa_rel in ordered_rel:
            partida = remesa_rel.partida_id
            if not partida:
                continue

            # ── Calcular ratio de prorrateo ──────────────────────────────
            total_value = partida.value_usd or 0.0
            total_qty = partida.quantity or 0.0
            remesa_value = remesa_rel.value_usd or 0.0
            remesa_qty = remesa_rel.quantity or 0.0

            if total_value > 0:
                ratio = remesa_value / total_value
            elif total_qty > 0:
                ratio = remesa_qty / total_qty
            else:
                ratio = 1.0

            # ── Una linea 557 por cada contribucion de esta partida ──────
            contribs = partida.contribucion_ids.filtered(
                lambda c: c.operacion_id == self
            ).sorted(lambda c: (c.sequence or 0, c.id))

            for contrib in contribs:
                secuencia += 1
                # Payload base usando la misma heuristica que el flujo normal
                payload = self._build_sync_payload_from_layout(layout_reg, contrib, "557")

                # Sobrescribir importe y base con los valores prorrateados.
                # La tasa (porcentaje) no se proratea, es una propiedad de la
                # fraccion arancelaria y aplica igual independientemente de la
                # cantidad de cada remesa.
                payload["importe"] = round((contrib.importe or 0.0) * ratio, 2)
                if (contrib.base or 0.0) > 0:
                    payload["base"] = round((contrib.base or 0.0) * ratio, 2)

                # Garantizar fraccion y numero de partida correctos
                payload["fraccion_arancelaria"] = (
                    partida.fraccion_arancelaria
                    or (partida.fraccion_id.code if partida.fraccion_id else "")
                )
                payload["numero_partida"] = partida.numero_partida or 0

                registros.append({
                    "codigo": "557",
                    "secuencia": secuencia,
                    "valores": payload,
                })

        return registros

    def _remesa_partida_override_value(self, campo, remesa_rel, base_val):
        self.ensure_one()
        partida = remesa_rel.partida_id
        source_name = (campo.source_field_id.name if getattr(campo, "source_field_id", False) else campo.source_field) or ""
        token = self._norm_layout_token(f"{campo.nombre} {source_name}")
        source_norm = self._norm_layout_token(source_name)
        tipo_cambio = self.lead_id.x_tipo_cambio or 0.0

        quantity_tokens = {
            "quantity",
            "cantidad",
            "cantidadumt",
            "cantidadumc",
            "cantidadcomercial",
            "cantidadtarifa",
        }
        value_usd_tokens = {
            "valueusd",
            "valorusd",
            "valaduanausd",
            "valoraduanausd",
        }
        value_mxn_tokens = {
            "valuemxn",
            "valormxn",
        }

        if source_norm in quantity_tokens or ("cantidad" in token and "precio" not in token):
            return remesa_rel.quantity
        if source_norm in value_usd_tokens or ("valor" in token and "usd" in token):
            return remesa_rel.value_usd
        if source_norm in value_mxn_tokens or ("valor" in token and "mxn" in token):
            return (remesa_rel.value_usd or 0.0) * tipo_cambio

        return base_val

    def _build_remesa_partida_payload(self, layout_reg, remesa_rel):
        self.ensure_one()
        partida = remesa_rel.partida_id
        valores = {}
        for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0):
            val = self._field_value_for_layout(campo, partida=partida)
            val = self._remesa_partida_override_value(campo, remesa_rel, val)
            if val in (None, "", False) and campo.default:
                val = campo.default
            val = self._json_safe_layout_value(val)
            if val not in (None, "", False):
                valores[campo.nombre] = val
        return valores

    def _get_remesa_partida_registros(self, remesa, codes):
        self.ensure_one()
        code_set = {str(code).zfill(3) for code in (codes or [])}
        layout_regs = {
            reg.codigo: reg
            for reg in self.layout_id.registro_ids.filtered(lambda r: (r.codigo or "").strip() in code_set)
        }
        registros = []
        ordered_rel = remesa.partida_rel_ids.sorted(
            lambda rel: ((rel.partida_id.numero_partida or 0) if rel.partida_id else 0, rel.sequence or 0, rel.id)
        )
        for code in sorted(code_set):
            layout_reg = layout_regs.get(code)
            if not layout_reg:
                continue
            for secuencia, remesa_rel in enumerate(ordered_rel, start=1):
                registros.append({
                    "codigo": code,
                    "secuencia": secuencia,
                    "valores": self._build_remesa_partida_payload(layout_reg, remesa_rel),
                })
        return registros

    def _build_remesa_export_registros(self, remesa):
        self.ensure_one()
        excluded_codes = {"514", "557", "551", "552", "553", "554", "555", "556", "558"}
        order_map = self._get_record_order_map()
        base_regs = [
            reg for reg in self.registro_ids.sorted(lambda r: self._registro_export_sort_key(r, order_map=order_map))
            if (reg.codigo or "").strip() not in excluded_codes
        ]
        remesa_regs = list(base_regs)
        remesa_regs.extend(self._get_remesa_557_registros(remesa))
        remesa_regs.extend(self._get_remesa_514_registros(remesa))
        remesa_regs.extend(self._get_remesa_partida_registros(remesa, {"551", "552", "553", "554", "555", "556", "558"}))
        remesa_regs.sort(
            key=lambda r: (
                order_map.get((r["codigo"] if isinstance(r, dict) else (r.codigo or "")).strip()) or 999999,
                (self._get_layout_registro(r["codigo"] if isinstance(r, dict) else r.codigo).orden if self._get_layout_registro(r["codigo"] if isinstance(r, dict) else r.codigo) else 0),
                (r["codigo"] if isinstance(r, dict) else r.codigo),
                (r["secuencia"] if isinstance(r, dict) else (r.secuencia or 0)),
            )
        )
        return remesa_regs

    def _build_remesa_txt_data(self, remesa):
        self.ensure_one()
        registros = self._build_remesa_export_registros(remesa)
        lines = []
        for reg in registros:
            if isinstance(reg, dict):
                layout_reg = self._get_layout_registro(reg["codigo"])
                partida_num = self._extract_partida_number(reg["valores"])
                lines.append(self._build_txt_line(layout_reg, reg["valores"], partida_num=partida_num))
            else:
                layout_reg = self._get_layout_registro(reg.codigo)
                partida_num = self._extract_partida_number(reg.valores)
                if layout_reg:
                    lines.append(self._build_txt_line(layout_reg, reg.valores, partida_num=partida_num))
                else:
                    lines.append(self._build_txt_line_pipe_direct(reg.codigo, reg.valores))
        sep = self._get_record_separator()
        return sep.join(lines)

    def action_validar_operacion(self):
        """Abre el wizard de validación mostrando todos los errores y advertencias de una vez."""
        self.ensure_one()
        wizard = self.env["mx.ped.validacion.wizard"].ejecutar_para_operacion(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Validación del Pedimento"),
            "res_model": "mx.ped.validacion.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _get_record_separator(self):
        """Devuelve el separador de registros normalizado como carácter real.
        Si el layout guarda la secuencia literal \\n (2 chars) en lugar del
        carácter newline real, lo convierte para que el TXT tenga saltos de
        línea correctos y splitlines() funcione en el parser de proforma.
        """
        raw = (self.layout_id.record_separator if self.layout_id else None) or "\n"
        # Normaliza secuencias de escape literales (ej. "\\n" → "\n")
        raw = raw.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
        return raw

    def action_export_txt(self):
        self.ensure_one()
        self._auto_refresh_generated_registros()
        self._sync_registro_ids_from_tecnicos()
        self._prune_forbidden_registros()
        self._validate_confirmacion_pago_formas()
        self._validate_510_forma_pago_required()
        self._validate_partida_facturas_505()
        self._run_process_stage_checks("export")
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))
        self._validate_field_rules_on_registros()
        self._validate_registros_vs_estructura()

        if self.es_consolidado and self.modo_export_consolidado == "por_remesa":
            # ── Validación legal: el pedimento consolidado debe estar pagado ──
            # Emitir TXT de remesas de un pedimento sin pago es un riesgo legal
            # (art. 36-A LCA: las remesas amparan mercancía contra el pedimento pagado).
            if not self.fecha_pago:
                raise UserError(_(
                    "El pedimento consolidado no tiene fecha de pago registrada.\n\n"
                    "No se pueden exportar TXT de remesas hasta que el pedimento "
                    "principal esté pagado. Captura la fecha de pago en la pestaña "
                    "de datos generales."
                ))
            remesas = self.remesa_ids.filtered("active").sorted(lambda r: (r.sequence or 0, r.id))
            if not remesas:
                raise UserError(_("No hay remesas activas para exportar en modo por remesa."))

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for remesa in remesas:
                    txt_data = self._build_remesa_txt_data(remesa)
                    zip_file.writestr(self._build_remesa_txt_member_name(remesa), txt_data.encode("utf-8"))

            attachment = self.env["ir.attachment"].create({
                "name": self._build_remesa_zip_name(),
                "type": "binary",
                "datas": base64.b64encode(zip_buffer.getvalue()),
                "mimetype": "application/zip",
                "res_model": self._name,
                "res_id": self.id,
            })
            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{attachment.id}?download=true",
                "target": "self",
            }

        lines = []
        order_map = self._get_record_order_map()
        for reg in self.registro_ids.sorted(lambda r: self._registro_export_sort_key(r, order_map=order_map)):
            layout_reg = self._get_layout_registro(reg.codigo)
            partida_num = self._extract_partida_number(reg.valores)
            if layout_reg:
                lines.append(self._build_txt_line(layout_reg, reg.valores, partida_num=partida_num))
            else:
                lines.append(self._build_txt_line_pipe_direct(reg.codigo, reg.valores))

        sep = self._get_record_separator()
        txt_data = sep.join(lines)
        attachment = self.env["ir.attachment"].create({
            "name": self._build_txt_filename(),
            "type": "binary",
            "datas": base64.b64encode(txt_data.encode("utf-8")),
            "mimetype": "text/plain",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_export_proforma(self):
        self.ensure_one()
        # ── Reutiliza toda la validación y construcción del TXT ──
        self._auto_refresh_generated_registros()
        self._sync_registro_ids_from_tecnicos()
        self._validate_confirmacion_pago_formas()
        self._validate_partida_facturas_505()
        self._run_process_stage_checks("export")
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))
        self._validate_field_rules_on_registros()
        self._validate_registros_vs_estructura()

        lines = []
        order_map = self._get_record_order_map()
        for reg in self.registro_ids.sorted(lambda r: self._registro_export_sort_key(r, order_map=order_map)):
            layout_reg = self._get_layout_registro(reg.codigo)
            partida_num = self._extract_partida_number(reg.valores)
            if layout_reg:
                lines.append(self._build_txt_line(layout_reg, reg.valores, partida_num=partida_num))
            else:
                lines.append(self._build_txt_line_pipe_direct(reg.codigo, reg.valores))

        sep = self._get_record_separator()
        txt_data = sep.join(lines)

        # ── Datos del agente desde la operación/compañía ──
        agente = self._get_agente_data()

        # ── Generar PDF ──
        from .pedimento_proforma_v2 import generar_proforma
        pdf_bytes = generar_proforma(txt_data, agente)

        pedimento_ref = re.sub(r"[^A-Za-z0-9_-]+", "", (self.pedimento_numero or self.name or "").strip())
        pdf_name = "proforma_%s.pdf" % (pedimento_ref or self.id)

        attachment = self.env["ir.attachment"].create({
            "name": pdf_name,
            "type": "binary",
            "datas": base64.b64encode(pdf_bytes),
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _get_agente_data(self):
        """Extrae datos del agente aduanal desde la operación o la compañía."""
        # Ajusta los campos según cómo los tengas guardados en tu modelo
        company = self.env.company
        return {
            "nombre":           getattr(self, "agente_nombre", "") or company.name,
            "rfc":              getattr(self, "agente_rfc",    "") or company.vat or "",
            "curp":             getattr(self, "agente_curp",   ""),
            "patente":          getattr(self, "patente",       ""),
            "mandatario_nombre":getattr(self, "mandatario_nombre", ""),
            "mandatario_rfc":   getattr(self, "mandatario_rfc",    ""),
            "mandatario_curp":  getattr(self, "mandatario_curp",   ""),
            "num_serie_cert":   getattr(self, "num_serie_cert",    ""),
            "firma_electronica":getattr(self, "fiel",               ""),
        }

    def _proforma_text(self, value, decimals=2):
        if value in (False, None, ""):
            return ""
        if isinstance(value, datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, date):
            return fields.Date.to_string(value)
        if isinstance(value, float):
            return f"{value:.{decimals}f}"
        if isinstance(value, int):
            return str(value)
        return str(self._extract_value(value) or "")

    def _proforma_date(self, value):
        if not value:
            return ""
        dt = fields.Date.to_date(value)
        return dt.strftime("%d%m%Y") if dt else ""

    def _proforma_partner_address(self, partner):
        if not partner:
            return ""
        street = " ".join(
            part for part in [partner.x_street_name or partner.street, partner.x_street_number_ext] if part
        ).strip()
        if partner.x_street_number_int:
            street = f"{street} INT {partner.x_street_number_int}".strip()
        pieces = [
            street,
            partner.x_colonia,
            partner.x_municipio or partner.city,
            partner.state_id.code if partner.state_id and hasattr(partner.state_id, "code") else (partner.state_id.name if partner.state_id else ""),
            partner.zip,
            partner.country_id.code if partner.country_id and hasattr(partner.country_id, "code") else (partner.country_id.name if partner.country_id else ""),
        ]
        return ", ".join(piece for piece in pieces if piece)

    def _get_proforma_505_document(self):
        self.ensure_one()
        docs = self.documento_ids.filtered(lambda d: d.tipo in ("factura", "cove", "otro"))
        return docs.sorted(lambda d: (d.es_documento_principal is not True, d.id))[:1]

    def _get_proforma_fecha_map(self):
        self.ensure_one()
        fecha_map = {}
        if not self.lead_id:
            return fecha_map
        for line in self.lead_id.x_fecha_506_ids.sorted(lambda l: (l.sequence or 0, l.id)):
            if line.tipo_fecha_code and line.fecha and line.tipo_fecha_code not in fecha_map:
                fecha_map[line.tipo_fecha_code] = line.fecha
        return fecha_map

    def _build_proforma_contribucion(self, contrib_line):
        from .pedimento_proforma_v2 import Contribucion

        return Contribucion(
            clave=self._proforma_text(contrib_line.tipo_contribucion),
            tipo_tasa="",
            tasa=self._proforma_text(contrib_line.tasa, decimals=6),
            importe=self._proforma_text(contrib_line.importe),
            forma_pago=self._proforma_text(contrib_line.forma_pago_code),
        )

    def _build_proforma_identificador(self, ident_line):
        from .pedimento_proforma_v2 import Identificador

        return Identificador(
            clave=self._proforma_text(ident_line.code),
            comp1=(ident_line.complemento1 or "").strip() or "NULO",
            comp2=(ident_line.complemento2 or "").strip() or "NULO",
            comp3=(ident_line.complemento3 or "").strip() or "NULO",
        )

    def _build_proforma_guia_list(self):
        from .pedimento_proforma_v2 import Guia

        if not self.lead_id:
            return []
        return [
            Guia(
                numero=(g.numero or "").strip(),
                identificador=(g.identificador or "M").strip(),
            )
            for g in self.lead_id.x_guia_ids.sorted(lambda g: (g.sequence or 0, g.id))
            if (g.numero or "").strip()
        ]

    def _build_proforma_contenedor_list(self):
        from .pedimento_proforma_v2 import Contenedor

        if not self.lead_id:
            return []
        return [
            Contenedor(
                numero=(c.numero or "").strip(),
                tipo=self._proforma_text(c.tipo_contenedor_id),
            )
            for c in self.lead_id.x_contenedor_ids.sorted(lambda c: (c.sequence or 0, c.id))
            if (c.numero or "").strip()
        ]

    def _build_proforma_partida(self, partida):
        from .pedimento_proforma_v2 import Partida

        contribuciones = [
            self._build_proforma_contribucion(line)
            for line in partida.contribucion_ids.sorted(lambda l: (l.sequence or 0, l.id))
        ]
        precio_pagado = partida.valor_comercial or partida.value_mxn or 0.0
        return Partida(
            secuencia=self._proforma_text(partida.numero_partida),
            fraccion=self._proforma_text(partida.fraccion_arancelaria or partida.fraccion_id),
            subdivision=self._proforma_text(partida.nico),
            vinculacion="",
            met_valoracion="",
            umc=self._proforma_text(partida.uom_id),
            cantidad_umc=self._proforma_text(partida.quantity, decimals=6),
            umt=self._proforma_text(partida.unidad_tarifa or partida.unidad_comercial),
            cantidad_umt=self._proforma_text(partida.cantidad_tarifa or partida.cantidad_comercial, decimals=5),
            pais_venta=self._proforma_text(partida.pais_vendedor_id),
            pais_origen=self._proforma_text(partida.pais_origen_id),
            descripcion=(partida.descripcion or "").strip(),
            val_aduana_usd=self._proforma_text(partida.value_usd),
            imp_precio_pag=self._proforma_text(precio_pagado),
            precio_pagado=self._proforma_text(precio_pagado),
            precio_unit=self._proforma_text(partida.precio_unitario, decimals=6),
            val_agregado=self._proforma_text(partida.valor_aduana),
            marca="",
            modelo="",
            codigo_producto="",
            contribuciones=contribuciones,
            identificadores=[
                self._build_proforma_identificador(line)
                for line in partida.identificador_ids.sorted(lambda l: (l.sequence or 0, l.id))
            ],
            observaciones=(partida.observaciones or partida.notes_regulatorias or "").strip(),
        )

    def _build_proforma_pedimento(self):
        from .pedimento_proforma_v2 import Pedimento

        self.ensure_one()
        lead = self.lead_id
        participante = self.participante_id or self.importador_id or self.exportador_id
        transportista_line = lead.x_transportista_ids[:1] if lead else self.env["crm.lead.transportista"]
        transportista = transportista_line.transportista_id if transportista_line else self.env["res.partner"]
        doc_505 = self._get_proforma_505_document()
        fechas = self._get_proforma_fecha_map()
        contribuciones_globales = [
            self._build_proforma_contribucion(line)
            for line in self.contribucion_global_ids.sorted(lambda l: (l.sequence or 0, l.id))
        ]
        partidas = [
            self._build_proforma_partida(partida)
            for partida in self.partida_ids.sorted(lambda p: (p.numero_partida or 0, p.id))
        ]
        identificadores = [
            self._build_proforma_identificador(line)
            for line in self.identificador_pedimento_ids.sorted(lambda l: (l.sequence or 0, l.id))
        ]
        total_liquidacion = sum(line.importe or 0.0 for line in self.contribucion_global_ids)

        ped = Pedimento()
        ped.num_pedimento = (self.pedimento_numero or "").strip()
        ped.tipo_operacion = "IMP" if self.tipo_operacion != "exportacion" else "EXP"
        ped.clave_pedimento = self._proforma_text(self.clave_pedimento or self.clave_pedimento_id)
        ped.regimen = self._proforma_text(self.regimen)
        ped.destino_origen = self._proforma_text(lead.x_origen_destino_mercancia if lead else "")
        ped.tipo_cambio = self._proforma_text(lead.x_tipo_cambio if lead else 0.0, decimals=5)
        ped.peso_bruto = self._proforma_text(self.total_gross_weight or (lead.x_peso_bruto if lead else 0.0), decimals=3)
        ped.aduana_es = self._proforma_text(self.aduana_clave or self.aduana_seccion_despacho_id)
        ped.medio_transporte_entrada = self._proforma_text(lead.x_medio_transporte_entrada_salida if lead else "")
        ped.medio_transporte_arribo = self._proforma_text(lead.x_medio_transporte_arribo if lead else "")
        ped.medio_transporte_salida = self._proforma_text(lead.x_medio_transporte_salida if lead else "")
        ped.valor_dolares = self._proforma_text(self.total_value_usd or (lead.x_cfdi_valor_usd if lead else 0.0))
        ped.valor_aduana = self._proforma_text((lead.x_valor_aduana_estimado if lead else 0.0) or sum(p.valor_aduana or 0.0 for p in self.partida_ids))
        ped.precio_pagado_valor_comercial = self._proforma_text(
            (lead.x_valor_factura if lead else 0.0) or sum(p.valor_comercial or p.value_mxn or 0.0 for p in self.partida_ids)
        )
        ped.rfc = self._proforma_text(self.participante_rfc or (participante.vat if participante else ""))
        ped.nombre_razon_social = self._proforma_text(self.participante_nombre or (participante.name if participante else ""))
        ped.curp = self._proforma_text(self.participante_curp or (participante.x_curp if participante else ""))
        ped.domicilio = self._proforma_partner_address(participante)
        ped.val_seguros = self._proforma_text(lead.x_incrementable_seguros if lead else 0.0)
        ped.seguros = self._proforma_text(lead.x_incrementable_seguros if lead else 0.0)
        ped.fletes = self._proforma_text(lead.x_incrementable_fletes if lead else 0.0)
        ped.embalajes = self._proforma_text(lead.x_incrementable_embalajes if lead else 0.0)
        ped.otros_incrementables = self._proforma_text(lead.x_incrementable_otros if lead else 0.0)
        ped.codigo_aceptacion = self._proforma_text(self.acuse_validacion)
        ped.codigo_barras = ""
        ped.clave_seccion_aduanera = self._proforma_text(self.aduana_seccion_entrada_salida or self.aduana_seccion_despacho_id)
        _first_contenedor = lead.x_contenedor_ids[:1] if lead else self.env["crm.lead.contenedor"]
        _first_candado = lead.x_candado_ids[:1] if lead else self.env["crm.lead.candado"]
        ped.marcas_numeros_bultos = " / ".join(
            value
            for value in [
                self._proforma_text(_first_contenedor.numero if _first_contenedor else ""),
                self._proforma_text(_first_candado.num_candado if _first_candado else ""),
                self._proforma_text(lead.x_bultos if lead else 0),
            ]
            if value
        )
        ped.fecha_entrada = self._proforma_date(fechas.get("01") or self.fecha_operacion)
        ped.fecha_pago = self._proforma_date(fechas.get("02") or self.fecha_pago)
        ped.fecha_presentacion = self._proforma_date(fechas.get("05"))
        ped.fecha_extraccion = self._proforma_date(fechas.get("03"))
        ped.tasas = contribuciones_globales
        ped.contribuciones_liq = contribuciones_globales
        ped.total_efectivo = self._proforma_text(total_liquidacion)
        ped.total_otros = ""
        ped.total_total = self._proforma_text(total_liquidacion)
        ped.num_acuse_valor = self._proforma_text(doc_505.folio if doc_505 else "")
        ped.vinculacion_505 = ""
        incoterm_text = (
            (doc_505.cfdi_termino_facturacion.code if doc_505 and doc_505.cfdi_termino_facturacion else "")
            or self.incoterm or ""
        )
        ped.incoterm = self._proforma_text(incoterm_text)
        ped.transporte_id = self._proforma_text(transportista_line.transporte_identificador if transportista_line else "")
        ped.transporte_pais = self._proforma_text(transportista_line.transporte_pais_id if transportista_line else "")
        ped.transportista_nombre = self._proforma_text(transportista.name if transportista else "")
        ped.transportista_rfc = self._proforma_text(transportista_line.rfc if transportista_line else "")
        ped.transportista_curp = self._proforma_text(transportista_line.curp if transportista_line else "")
        ped.transportista_domicilio = self._proforma_text(
            (transportista_line.domicilio if transportista_line else "") or self._proforma_partner_address(transportista)
        )
        ped.candado1 = self._proforma_text(_first_candado.num_candado if _first_candado else "")
        ped.candado2 = ""
        ped.guias = self._build_proforma_guia_list()
        ped.contenedores = self._build_proforma_contenedor_list()
        ped.identificadores = identificadores
        ped.observaciones = (self.observaciones or "").strip()
        ped.partidas = partidas
        ped.agente = self._get_agente_data()
        return ped

    # ── Proforma por remesa ───────────────────────────────────────────────

    def _build_proforma_contribucion_remesa(self, contrib, ratio):
        """Igual que _build_proforma_contribucion pero con importe prorrateado.

        La tasa porcentual no cambia (es propiedad de la fraccion arancelaria);
        solo el importe y la base se multiplican por el ratio de la remesa.
        """
        from .pedimento_proforma_v2 import Contribucion
        return Contribucion(
            clave=self._proforma_text(contrib.tipo_contribucion or contrib.contribucion_code),
            tipo_tasa="",
            tasa=self._proforma_text(contrib.tasa, decimals=6),
            importe=self._proforma_text(round((contrib.importe or 0.0) * ratio, 2)),
            forma_pago=self._proforma_text(contrib.forma_pago_code),
        )

    def _build_proforma_partida_remesa(self, partida, remesa_rel):
        """Construye el bloque Partida con los valores propios de la remesa.

        Cantidad y valor USD vienen de la asignacion de remesa (remesa_rel).
        Las contribuciones 557 se prorratean con la misma logica que el TXT.
        """
        from .pedimento_proforma_v2 import Partida

        total_value = partida.value_usd or 0.0
        total_qty = partida.quantity or 0.0
        remesa_value = remesa_rel.value_usd or 0.0
        remesa_qty = remesa_rel.quantity or 0.0

        if total_value > 0:
            ratio = remesa_value / total_value
        elif total_qty > 0:
            ratio = remesa_qty / total_qty
        else:
            ratio = 1.0

        tipo_cambio = self.lead_id.x_tipo_cambio or 0.0
        valor_mxn = round(remesa_value * tipo_cambio, 2)

        precio_unit = (
            round(remesa_value / remesa_qty, 6) if remesa_qty else
            (partida.precio_unitario or 0.0)
        )

        contribuciones = [
            self._build_proforma_contribucion_remesa(c, ratio)
            for c in partida.contribucion_ids.filtered(
                lambda c: c.operacion_id == self
            ).sorted(lambda c: (c.sequence or 0, c.id))
        ]

        return Partida(
            secuencia=self._proforma_text(partida.numero_partida),
            fraccion=self._proforma_text(partida.fraccion_arancelaria or partida.fraccion_id),
            subdivision=self._proforma_text(partida.nico),
            vinculacion="",
            met_valoracion="",
            umc=self._proforma_text(partida.uom_id),
            cantidad_umc=self._proforma_text(remesa_qty, decimals=6),
            umt=self._proforma_text(partida.unidad_tarifa or partida.unidad_comercial),
            cantidad_umt=self._proforma_text(
                round((partida.cantidad_tarifa or partida.cantidad_comercial or 0.0) * ratio, 5),
                decimals=5,
            ),
            pais_venta=self._proforma_text(partida.pais_vendedor_id),
            pais_origen=self._proforma_text(partida.pais_origen_id),
            descripcion=(partida.descripcion or "").strip(),
            val_aduana_usd=self._proforma_text(remesa_value),
            imp_precio_pag=self._proforma_text(valor_mxn),
            precio_pagado=self._proforma_text(valor_mxn),
            precio_unit=self._proforma_text(precio_unit, decimals=6),
            val_agregado=self._proforma_text(round((partida.valor_aduana or 0.0) * ratio, 2)),
            marca="",
            modelo="",
            codigo_producto="",
            contribuciones=contribuciones,
            identificadores=[
                self._build_proforma_identificador(line)
                for line in partida.identificador_ids.sorted(lambda l: (l.sequence or 0, l.id))
            ],
            observaciones=(partida.observaciones or partida.notes_regulatorias or "").strip(),
        )

    def _build_proforma_pedimento_remesa(self, remesa):
        """Construye el dataclass Pedimento para una remesa especifica.

        Parte del pedimento completo (_build_proforma_pedimento) y sobreescribe:
        - Partidas: solo las asignadas a esta remesa, con valores prorrateados.
        - Contribuciones 557: prorrateadas.
        - Transportista/placas/candados: datos propios de la remesa.
        - Valor USD / Valor aduana: suma de la remesa.
        - Fecha entrada: fecha de la remesa.
        - Observaciones: las del pedimento + las de la remesa.
        - num_pedimento: incluye el folio de la remesa para identificarla.
        """
        # Construimos la base del pedimento completo y luego sobreescribimos
        ped = self._build_proforma_pedimento()

        # ── Identificacion de la remesa ──────────────────────────────────
        folio_remesa = (remesa.folio or remesa.name or "Remesa").strip()
        ped.num_pedimento = (
            (ped.num_pedimento + " / " if ped.num_pedimento else "") + folio_remesa
        )

        # ── Totales propios de la remesa ─────────────────────────────────
        total_value_usd = sum(rel.value_usd or 0.0 for rel in remesa.partida_rel_ids)
        tipo_cambio = self.lead_id.x_tipo_cambio or 0.0
        total_value_mxn = round(total_value_usd * tipo_cambio, 2)

        # Ratio global de la remesa sobre el pedimento (para peso bruto)
        pedimento_value_usd = sum(
            p.value_usd or 0.0 for p in self.partida_ids
        ) or 1.0
        ratio_global = total_value_usd / pedimento_value_usd
  
        ped.valor_dolares = self._proforma_text(total_value_usd)
        ped.valor_aduana = self._proforma_text(total_value_mxn)
        ped.precio_pagado_valor_comercial = self._proforma_text(total_value_mxn)
        ped.peso_bruto = self._proforma_text(
            round((self.total_gross_weight or 0.0) * ratio_global, 3), decimals=3
        )

        # ── Contribuciones 557 prorrateadas a nivel pedimento ────────────
        # Se recalculan sumando los prorrateados de cada partida de esta remesa
        contribs_por_tipo: dict = {}
        ordered_rel = remesa.partida_rel_ids.sorted(
            lambda r: ((r.partida_id.numero_partida or 0) if r.partida_id else 0, r.id)
        )
        for rel in ordered_rel:
            partida = rel.partida_id
            if not partida:
                continue
            pv = partida.value_usd or 0.0
            qv = partida.quantity or 0.0
            rv = rel.value_usd or 0.0
            rq = rel.quantity or 0.0
            ratio = (rv / pv) if pv > 0 else ((rq / qv) if qv > 0 else 1.0)
            for contrib in partida.contribucion_ids.filtered(lambda c: c.operacion_id == self):
                key = contrib.tipo_contribucion or str(contrib.contribucion_code)
                entry = contribs_por_tipo.setdefault(key, {
                    "contrib": contrib,
                    "importe": 0.0,
                })
                entry["importe"] += round((contrib.importe or 0.0) * ratio, 2)

        from .pedimento_proforma_v2 import Contribucion
        contribuciones_remesa = [
            Contribucion(
                clave=self._proforma_text(v["contrib"].tipo_contribucion or v["contrib"].contribucion_code),
                tipo_tasa="",
                tasa=self._proforma_text(v["contrib"].tasa, decimals=6),
                importe=self._proforma_text(round(v["importe"], 2)),
                forma_pago=self._proforma_text(v["contrib"].forma_pago_code),
            )
            for v in contribs_por_tipo.values()
        ]
        ped.tasas = contribuciones_remesa
        ped.contribuciones_liq = contribuciones_remesa
        total_liq = sum(v["importe"] for v in contribs_por_tipo.values())
        ped.total_efectivo = self._proforma_text(round(total_liq, 2))
        ped.total_total = self._proforma_text(round(total_liq, 2))

        # ── Transportista de la remesa ───────────────────────────────────
        transportista = remesa.transportista_id
        if transportista:
            ped.transportista_nombre = self._proforma_text(transportista.name)
            ped.transportista_rfc = self._proforma_text(transportista.vat or "")
            ped.transportista_curp = self._proforma_text(
                transportista.x_curp if hasattr(transportista, "x_curp") else ""
            )
            ped.transportista_domicilio = self._proforma_partner_address(transportista)

        # ── Fecha y datos logisticos de la remesa ────────────────────────
        if remesa.fecha_remesa:
            ped.fecha_entrada = self._proforma_date(remesa.fecha_remesa)

        if remesa.candados:
            ped.candado1 = self._proforma_text(remesa.candados)
            ped.candado2 = ""

        if remesa.contenedor:
            from .pedimento_proforma_v2 import Contenedor
            ped.contenedores = [Contenedor(numero=remesa.contenedor, tipo="")]

        if remesa.placas:
            ped.transporte_id = self._proforma_text(remesa.placas)

        # ── Acuse de presentacion de la remesa ───────────────────────────
        if remesa.acuse_presentacion:
            ped.codigo_aceptacion = self._proforma_text(remesa.acuse_presentacion)

        # ── Observaciones: pedimento + remesa ────────────────────────────
        obs_parts = [p for p in [self.observaciones or "", remesa.observaciones or ""] if p.strip()]
        ped.observaciones = " | ".join(obs_parts)

        # ── Partidas: solo las de esta remesa, valores prorrateados ──────
        ped.partidas = [
            self._build_proforma_partida_remesa(rel.partida_id, rel)
            for rel in ordered_rel
            if rel.partida_id
        ]

        return ped

    def action_export_proforma(self):
        """Exporta la proforma en PDF.

        - Pedimento normal o consolidado modo 'pedimento_final': un solo PDF.
        - Consolidado modo 'por_remesa': ZIP con un PDF por remesa, cada uno
          con los valores (cantidades, importes, contribuciones) prorrateados
          segun la fraccion asignada a esa remesa.
        """
        self.ensure_one()
        self._auto_refresh_generated_registros()
        self._sync_registro_ids_from_tecnicos()
        self._validate_confirmacion_pago_formas()
        self._validate_partida_facturas_505()
        self._run_process_stage_checks("export")

        from .pedimento_proforma_v2 import PedimentoPDF

        pedimento_ref = re.sub(
            r"[^A-Za-z0-9_-]+", "",
            (self.pedimento_numero or self.name or "").strip(),
        )

        # ── Consolidado por remesa: ZIP con un PDF por remesa ────────────
        if self.es_consolidado and self.modo_export_consolidado == "por_remesa":
            remesas = self.remesa_ids.filtered("active").sorted(
                lambda r: (r.sequence or 0, r.id)
            )
            if not remesas:
                raise UserError(_("No hay remesas activas para exportar."))

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for remesa in remesas:
                    ped = self._build_proforma_pedimento_remesa(remesa)
                    pdf_bytes = PedimentoPDF(ped).build()
                    # Nombre del archivo: pedimento_remesaFOLIO.pdf
                    folio_token = re.sub(
                        r"[^A-Za-z0-9_-]+", "_",
                        (remesa.folio or remesa.name or f"remesa_{remesa.sequence or remesa.id}").strip(),
                    ).strip("._-") or f"remesa_{remesa.id}"
                    pdf_name = f"proforma_{pedimento_ref}_{folio_token}.pdf"
                    zf.writestr(pdf_name, pdf_bytes)

            zip_name = f"proformas_{pedimento_ref or self.id}.zip"
            attachment = self.env["ir.attachment"].create({
                "name": zip_name,
                "type": "binary",
                "datas": base64.b64encode(zip_buffer.getvalue()),
                "mimetype": "application/zip",
                "res_model": self._name,
                "res_id": self.id,
            })
            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{attachment.id}?download=true",
                "target": "self",
            }

        # ── Pedimento normal o consolidado 'pedimento_final': un PDF ─────
        ped = self._build_proforma_pedimento()
        pdf_bytes = PedimentoPDF(ped).build()

        pdf_name = "proforma_%s.pdf" % (pedimento_ref or self.id)
        attachment = self.env["ir.attachment"].create({
            "name": pdf_name,
            "type": "binary",
            "datas": base64.b64encode(pdf_bytes),
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _get_agente_data(self):
        """Construye el bloque de agente para la proforma desde operacion/partner."""
        from .pedimento_proforma_v2 import AgenteAduanal

        self.ensure_one()
        company = self.env.company
        agente = self.agente_aduanal_id or (self.lead_id.x_agente_aduanal_id if self.lead_id else self.env["res.partner"])
        return AgenteAduanal(
            nombre=self._proforma_text(agente.name if agente else company.name),
            rfc=self._proforma_text(agente.vat if agente else company.vat),
            curp=self._proforma_text(self.curp_agente or (agente.x_curp if agente else "")),
            patente=self._proforma_text(self.patente or (agente.x_patente_aduanal if agente else "")),
            mandatario_nombre="",
            mandatario_rfc="",
            mandatario_curp="",
            num_serie_cert="",
            firma_electronica="",
        )

    def action_export_xml(self):
        self.ensure_one()
        self._auto_refresh_generated_registros()
        self._sync_registro_ids_from_tecnicos()
        self._validate_confirmacion_pago_formas()
        self._validate_partida_facturas_505()
        self._run_process_stage_checks("export")
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))
        self._validate_field_rules_on_registros()
        self._validate_registros_vs_estructura()

        root = ET.Element("pedimento", layout=(self.layout_id.name or ""))
        order_map = self._get_record_order_map()
        for reg in self.registro_ids.sorted(lambda r: self._registro_export_sort_key(r, order_map=order_map)):
            reg_el = ET.SubElement(
                root,
                "registro",
                codigo=str(reg.codigo or ""),
                secuencia=str(reg.secuencia or 1),
            )
            layout_reg = self._get_layout_registro(reg.codigo)
            partida_num = self._extract_partida_number(reg.valores)
            effective_vals = self._apply_field_rules_to_vals(
                layout_reg.codigo,
                dict(reg.valores or {}),
                partida_num=partida_num,
            )
            for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or 0):
                val = effective_vals.get(campo.nombre)
                if val in (None, ""):
                    val = campo.default or ""
                campo_el = ET.SubElement(reg_el, "campo", nombre=campo.nombre or "")
                campo_el.text = str(val)

        xml_data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        attachment = self.env["ir.attachment"].create({
            "name": f"PEDIMENTO_{self.name}.xml",
            "type": "binary",
            "datas": base64.b64encode(xml_data),
            "mimetype": "application/xml",
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _get_avc_tipo_operacion_id(self):
        self.ensure_one()
        return 2 if self.tipo_operacion == "exportacion" else 1

    def _get_avc_headers(self):
        self.ensure_one()
        cred = self.ws_credencial_id
        if not cred:
            raise UserError(_("No hay credencial WS configurada para esta operacion."))
        token = cred.get_avc_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get_avc_api_url(self, suffix):
        self.ensure_one()
        cred = self.ws_credencial_id
        if not cred:
            raise UserError(_("No hay credencial WS configurada para esta operacion."))
        base = (cred.avc_api_base_url or "").strip().rstrip("/")
        if not base:
            raise UserError(_("La credencial WS no tiene AVC API Base URL configurada."))
        return f"{base}/{suffix.lstrip('/')}"

    def _build_avc_pedimento_llave(self, numero_pedimento, aduana, autorizacion, consecutivo=0):
        self.ensure_one()
        pedimento = "".join(ch for ch in str(numero_pedimento or "") if ch.isalnum())[:7].zfill(7)
        aduana_digits = "".join(ch for ch in str(aduana or "") if ch.isdigit())[:2].zfill(2)
        autorizacion_digits = "".join(ch for ch in str(autorizacion or "") if ch.isdigit())[:4].zfill(4)
        consecutivo_txt = "".join(ch for ch in str(consecutivo or 0) if ch.isdigit()).zfill(12)
        return f"{pedimento}{aduana_digits}{autorizacion_digits}{consecutivo_txt}"

    def _build_avc_llave_normal(self):
        self.ensure_one()
        return self._build_avc_pedimento_llave(
            self.pedimento_numero,
            self.aduana_clave,
            self.patente,
            consecutivo=0,
        )

    def _build_avc_llave_parte2(self):
        self.ensure_one()
        return self._build_avc_pedimento_llave(
            self.pedimento_numero,
            self.aduana_clave,
            self.patente,
            consecutivo=self.avc_parte2_consecutivo,
        )

    def _build_avc_llave_remesa(self, remesa):
        self.ensure_one()
        return self._build_avc_pedimento_llave(
            self.pedimento_numero,
            self.aduana_clave,
            self.patente,
            consecutivo=(remesa.sequence if remesa else 0),
        )

    def _build_avc_llave_aviso_electronico(self):
        self.ensure_one()
        return self._build_avc_pedimento_llave(
            self.pedimento_numero,
            self.aduana_clave,
            self.patente,
            consecutivo=self.avc_aviso_electronico_consecutivo,
        )

    def _get_avc_consolidacion_payload(self):
        self.ensure_one()
        if not self.avc_es_consolidacion_carga:
            return False
        auth_1 = "".join(ch for ch in str(self.avc_consolidacion_autorizacion_1 or "") if ch.isdigit())[:4]
        auth_2 = "".join(ch for ch in str(self.avc_consolidacion_autorizacion_2 or "") if ch.isdigit())[:4]
        if not auth_1 or not auth_2:
            raise UserError(_("Para consolidacion de carga AVC se requieren ambas autorizaciones."))
        return {
            "autorizacion_1": auth_1.zfill(4),
            "autorizacion_2": auth_2.zfill(4),
        }

    def _build_avc_pedimento_item(self, subtipo):
        self.ensure_one()
        pedimento = (self.pedimento_numero or "").strip()
        rfc = (self.participante_rfc or "").strip()
        if not pedimento:
            raise UserError(_("Falta numero de pedimento para generar AVC."))
        if not rfc:
            raise UserError(_("Falta RFC del importador/exportador para generar AVC."))

        item = {
            "numero_pedimento": pedimento,
            "rfc": rfc,
        }
        if self.avc_es_consolidacion_carga:
            autorizacion = "".join(ch for ch in str(self.patente or "") if ch.isdigit())[:4]
            if not autorizacion:
                raise UserError(_("Falta patente/autorizacion para consolidacion de carga AVC."))
            item["autorizacion"] = autorizacion.zfill(4)

        if subtipo == "normal":
            return "normal", item
        if subtipo == "parte_2":
            if not self.avc_parte2_consecutivo:
                raise UserError(_("Para AVC parte II se requiere consecutivo."))
            item["consecutivo"] = self.avc_parte2_consecutivo
            return "parte_2", item
        if subtipo == "remesa_previo_consolidado":
            remesa = self.avc_remesa_id
            if not remesa:
                raise UserError(_("Selecciona una remesa para AVC previo consolidado."))
            factura = (remesa.acuse_valor or "").strip()
            if not factura:
                raise UserError(_("La remesa AVC requiere acuse de valor para generar previo consolidado."))
            if not remesa.avc_plazo_id:
                raise UserError(_("La remesa AVC requiere plazo para generar previo consolidado."))
            item.update({
                "consecutivo": remesa.sequence or 0,
                "factura": factura,
                "plazo_id": int(remesa.avc_plazo_id),
            })
            return "remesa_previo_consolidado", item
        if subtipo == "aviso_electronico":
            if not (self.avc_aviso_electronico_folio or "").strip():
                raise UserError(_("Para AVC aviso electronico se requiere folio."))
            if not self.avc_aviso_electronico_plazo_id:
                raise UserError(_("Para AVC aviso electronico se requiere plazo."))
            if not self.avc_aviso_electronico_consecutivo:
                raise UserError(_("Para AVC aviso electronico se requiere consecutivo."))
            item.update({
                "folio": (self.avc_aviso_electronico_folio or "").strip(),
                "plazo_id": int(self.avc_aviso_electronico_plazo_id),
                "consecutivo": self.avc_aviso_electronico_consecutivo,
            })
            return "aviso_electronico", item
        raise UserError(_("Subtipo de pedimento AVC no soportado: %s") % subtipo)

    def _build_avc_payload(self):
        self.ensure_one()
        aduana = "".join(ch for ch in str(self.aduana_clave or "") if ch.isdigit())[:2]
        if len(aduana) != 2:
            raise UserError(_("La aduana debe contener 2 digitos para AVC."))

        modalidad = int(self.avc_modalidad_cruce_id or "1")
        if modalidad == 1 and not (self.avc_tag or "").strip():
            raise UserError(_("Para modalidad vehicular AVC se requiere TAG."))
        if modalidad == 2 and not (self.avc_numero_gafete or "").strip():
            raise UserError(_("Para modalidad peatonal AVC se requiere numero de gafete."))

        payload = {
            "aduana": aduana,
            "tipo_operacion_id": self._get_avc_tipo_operacion_id(),
            "modalidad_cruce_id": modalidad,
            "tipo_documento_id": int(self.avc_tipo_documento_id or "1"),
        }
        if int(self.avc_tipo_documento_id or "1") == 1:
            subtipo = self.avc_pedimento_subtipo or "normal"
            bucket, item = self._build_avc_pedimento_item(subtipo)
            payload["documentos_aduanales"] = {
                "pedimentos": {
                    bucket: [item],
                }
            }
        consolidacion = self._get_avc_consolidacion_payload()
        if consolidacion:
            payload["consolidacion_carga"] = consolidacion
        if (self.avc_tag or "").strip():
            payload["tag"] = (self.avc_tag or "").strip()
        numero_gafete = (self.avc_numero_gafete or "").strip() or (self.avc_gafete_id.numero_gafete or "").strip()
        if numero_gafete:
            payload["numero_gafete"] = numero_gafete
        if (self.avc_fast_id or "").strip():
            payload["fast_id"] = (self.avc_fast_id or "").strip()
        if (self.avc_datos_adicionales or "").strip():
            payload["datos_adicionales"] = (self.avc_datos_adicionales or "").strip()
        autorizacion = "".join(ch for ch in str(self.patente or "") if ch.isdigit())
        if autorizacion:
            payload["autorizacion"] = autorizacion.zfill(4)[:4]
        return payload

    def _check_avc_gafete(self):
        self.ensure_one()
        if self.avc_modalidad_cruce_id != "2":
            return
        if not self.avc_gafete_id and not (self.avc_numero_gafete or "").strip():
            raise UserError(_("Para modalidad peatonal debes seleccionar un gafete ANAM o capturar el numero de gafete."))
        gafete = self.avc_gafete_id
        if not gafete:
            return
        if gafete.estado == "vencido":
            fecha = gafete.vencido_desde.strftime("%Y-%m-%d") if gafete.vencido_desde else "sin fecha"
            raise UserError(_("El gafete seleccionado esta vencido desde %s.") % fecha)
        if gafete.estado == "error":
            raise UserError(_("El gafete seleccionado tiene error de validacion. Revalida el QR antes de generar AVC."))
        if gafete.estado == "indeterminado":
            raise UserError(_("El gafete seleccionado tiene estado indeterminado. Valida su QR antes de generar AVC."))

    def _write_avc_response(self, data):
        self.ensure_one()
        folio = data.get("folio_validacion") or {}
        vals = {
            "avc_numero": (data.get("numero_avc") or self.avc_numero or "").strip() or False,
            "avc_estatus": (data.get("estatus") or self.avc_estatus or "").strip() or False,
            "avc_fecha_emision": data.get("fecha_emision") or self.avc_fecha_emision or False,
            "avc_fecha_vigencia": data.get("fecha_vigencia") or self.avc_fecha_vigencia or False,
            "avc_url_detail": data.get("url_detail") or self.avc_url_detail or False,
            "avc_folio_validacion": json.dumps(folio, ensure_ascii=False) if isinstance(folio, (dict, list)) else (folio or False),
            "avc_validacion_agencia": (folio.get("validacion_agencia") if isinstance(folio, dict) else False) or data.get("validacion_agencia") or False,
            "avc_peticion_json": (folio.get("peticion_json") if isinstance(folio, dict) else False) or data.get("peticion_json") or False,
            "avc_last_sync": fields.Datetime.now(),
            "avc_sync_error": False,
        }
        self.write(vals)

    def action_avc_generar(self):
        self.ensure_one()
        # Para remesa previo consolidado el pedimento principal debe estar pagado.
        if (self.avc_pedimento_subtipo or "normal") == "remesa_previo_consolidado":
            if not self.fecha_pago:
                raise UserError(_(
                    "No se puede generar AVC de remesa (previo consolidado) si el "
                    "pedimento consolidado principal no tiene fecha de pago registrada.\n\n"
                    "Registra la fecha de pago antes de generar el AVC de remesa."
                ))
        self._check_avc_gafete()
        headers = self._get_avc_headers()
        payload = self._build_avc_payload()
        url = self._get_avc_api_url("/aviso-de-cruce")
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=40)
            if resp.status_code >= 400:
                raise UserError(_("Error AVC (%s): %s") % (resp.status_code, resp.text))
            data = resp.json() if resp.text else {}
            self._write_avc_response(data)
        except Exception as err:
            self.write({
                "avc_last_sync": fields.Datetime.now(),
                "avc_sync_error": str(err),
            })
            raise
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("AVC"),
                "message": _("Aviso de cruce generado correctamente."),
                "type": "success",
                "sticky": False,
            },
        }

    def _avc_consultar_status(self):
        self.ensure_one()
        if not self.avc_numero:
            raise UserError(_("No hay numero AVC para consultar."))
        headers = self._get_avc_headers()
        url = self._get_avc_api_url(f"/aviso-de-cruce/{self.avc_numero}")
        resp = requests.get(url, headers=headers, timeout=40)
        if resp.status_code >= 400:
            raise UserError(_("Error AVC consulta (%s): %s") % (resp.status_code, resp.text))
        data = resp.json() if resp.text else {}
        self._write_avc_response(data)

    def action_avc_consultar(self):
        self.ensure_one()
        try:
            self._avc_consultar_status()
        except Exception as err:
            self.write({
                "avc_last_sync": fields.Datetime.now(),
                "avc_sync_error": str(err),
            })
            raise
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("AVC"),
                "message": _("Consulta AVC actualizada."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_avc_eliminar(self):
        self.ensure_one()
        if not self.avc_numero:
            raise UserError(_("No hay numero AVC para eliminar."))
        headers = self._get_avc_headers()
        url = self._get_avc_api_url("/aviso-de-cruce")
        payload = {"numero_avc": self.avc_numero}
        try:
            resp = requests.delete(url, headers=headers, json=payload, timeout=40)
            if resp.status_code >= 400:
                raise UserError(_("Error AVC eliminar (%s): %s") % (resp.status_code, resp.text))
            data = resp.json() if resp.text else {}
            self._write_avc_response(data)
        except Exception as err:
            self.write({
                "avc_last_sync": fields.Datetime.now(),
                "avc_sync_error": str(err),
            })
            raise
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("AVC"),
                "message": _("Aviso de cruce eliminado."),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def cron_avc_sync_status(self, limit=200):
        recs = self.search([("avc_numero", "!=", False), ("ws_credencial_id", "!=", False)], limit=limit)
        for rec in recs:
            try:
                rec._avc_consultar_status()
            except Exception as err:
                rec.write({
                    "avc_last_sync": fields.Datetime.now(),
                    "avc_sync_error": str(err),
                })
        return True

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

        bl_no = _pick([
            r"\bB/?L\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-]+)",
            r"\bMBL\s*[:#]?\s*([A-Z0-9\-]+)",
            r"\bMASTER\s*B/?L\s*[:#]?\s*([A-Z0-9\-]+)",
        ])
        container = _pick([r"\b([A-Z]{4}\d{7})\b"])
        seal = _pick([r"\b(?:SEAL\s*NO\.?\s*[:#]?\s*|/)([A-Z0-9]{6,})\b"])
        kgs = _pick([r"(\d+(?:\.\d+)?)\s*KGS\b"])
        cbm = _pick([r"(\d+(?:\.\d+)?)\s*CBM\b"])
        bultos = _pick([
            r"/\s*(\d+)\s+[A-Z ]{2,20}/",
            r"\b(\d+)\s+(?:WOODEN\s+CASES?|PACKAGES?|PKGS?)\b",
        ])
        loading = _pick([r"Port of Loading\s*([A-Z0-9 ,\-\(\)]+)"])
        discharge = _pick([r"Port of discharge:\s*Place of delivery\s*([A-Z0-9 ,\-\(\)\/]+)"])
        vessel_line = _pick([r"Ocean Vessel\s+Voy\.?No\.\s+Port of Loading\s*([A-Z0-9 .,\-\(\)]+)"])

        return {
            "bl_no": bl_no,
            "container": container,
            "seal": seal,
            "kgs": kgs,
            "cbm": cbm,
            "bultos": bultos,
            "loading": loading,
            "discharge": discharge,
            "vessel": vessel_line,
        }

    def action_read_bl(self):
        self.ensure_one()
        if not self.bl_file:
            raise UserError(_("Sube primero el archivo B/L en PDF."))
        if not self.lead_id:
            raise UserError(_("La operacion requiere un Lead asociado para cargar datos del B/L."))

        pdf_bytes = base64.b64decode(self.bl_file)
        text = self._extract_bl_pdf_text(pdf_bytes)
        parsed = self._parse_bl_text(text)
        if not any(parsed.values()):
            raise UserError(_("No se detectaron datos utiles en el B/L. Revisa calidad del PDF."))

        lead_vals = {}
        if parsed.get("bl_no"):
            self.lead_id.x_guia_ids.create({
                "lead_id": self.lead_id.id,
                "numero": parsed["bl_no"][:20],
                "identificador": "M",
            })
        if parsed.get("container"):
            self.lead_id.x_contenedor_ids.create({
                "lead_id": self.lead_id.id,
                "numero": parsed["container"][:12],
            })
        if parsed.get("seal"):
            self.lead_id.x_candado_ids.create({
                "lead_id": self.lead_id.id,
                "transporte_identificador": parsed.get("container", "")[:17],
                "num_candado": parsed["seal"][:21],
            })
        if parsed.get("bultos"):
            try:
                lead_vals["x_bultos"] = int(float(parsed["bultos"]))
            except Exception:
                pass
        if parsed.get("kgs"):
            try:
                lead_vals["x_peso_bruto"] = float(parsed["kgs"])
            except Exception:
                pass
        if parsed.get("cbm"):
            try:
                lead_vals["x_volumen_cbm"] = float(parsed["cbm"])
            except Exception:
                pass
        if parsed.get("loading"):
            lead_vals["x_lugar_carga"] = parsed["loading"]
        if parsed.get("discharge"):
            lead_vals["x_lugar_descarga"] = parsed["discharge"]

        if lead_vals:
            self.lead_id.write(lead_vals)
        if parsed.get("vessel"):
            note = f"B/L vessel/voy: {parsed['vessel']}"
            self.observaciones = f"{(self.observaciones or '').strip()}\n{note}".strip()
        self.bl_last_read = fields.Datetime.now()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("B/L procesado"),
                "message": _("Datos cargados al lead vinculado."),
                "type": "success",
                "sticky": False,
            },
        }

    def _build_txt_filename(self):
        self.ensure_one()
        patente_raw = (
            self.patente
            or (self.agente_aduanal_id.x_patente_aduanal if self.agente_aduanal_id else "")
            or (self.lead_id.x_agente_aduanal_id.x_patente_aduanal if self.lead_id and self.lead_id.x_agente_aduanal_id else "")
            or (self.lead_id.x_patente_agente if self.lead_id else "")
        )
        patente = "".join(ch for ch in str(patente_raw or "") if ch.isdigit())
        if not patente:
            raise UserError(_("Falta la patente para construir el nombre SAAI (mppppnnn.ddd)."))
        if len(patente) > 4:
            raise UserError(_("La patente debe tener maximo 4 digitos para el nombre SAAI."))
        patente = patente.zfill(4)

        today = fields.Date.context_today(self)
        julian_day = today.timetuple().tm_yday
        ddd = f"{julian_day:03d}"
        prefix = f"m{patente}"
        regex = re.compile(rf"^{prefix}(\d{{3}})\.{ddd}$")

        existing = self.env["ir.attachment"].search([
            ("name", "=like", f"{prefix}%.{ddd}"),
            ("mimetype", "=", "text/plain"),
        ])
        seq = 0
        for att in existing:
            m = regex.match(att.name or "")
            if m:
                seq = max(seq, int(m.group(1)))
        seq += 1
        if seq > 999:
            raise UserError(_("Se alcanzo el consecutivo diario maximo (999) para la patente %s.") % patente)

        # Formato obligatorio SAAI M3: mppppnnn.ddd
        return f"{prefix}{seq:03d}.{ddd}"

    def _get_pedimento_number_parts(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        yy = f"{today.year % 100:02d}"
        year_last_digit = str(today.year)[-1]

        aduana_digits = "".join(ch for ch in str(self.aduana_clave or "") if ch.isdigit())
        if len(aduana_digits) < 2:
            raise UserError(_("La aduana debe tener al menos 2 digitos para generar el numero de pedimento."))
        aa = aduana_digits[:2]

        patente_raw = (
            self.patente
            or (self.agente_aduanal_id.x_patente_aduanal if self.agente_aduanal_id else "")
            or (self.lead_id.x_agente_aduanal_id.x_patente_aduanal if self.lead_id and self.lead_id.x_agente_aduanal_id else "")
            or (self.lead_id.x_patente_agente if self.lead_id else "")
        )
        patente_digits = "".join(ch for ch in str(patente_raw or "") if ch.isdigit())
        if not patente_digits:
            raise UserError(_("Falta la patente para generar el numero de pedimento."))
        if len(patente_digits) > 4:
            raise UserError(_("La patente debe tener maximo 4 digitos."))
        pppp = patente_digits.zfill(4)
        return yy, aa, pppp, year_last_digit

    def _next_pedimento_consecutivo(self, yy, aa, pppp):
        self.ensure_one()
        control_model = self.env["mx.ped.numero.control"].sudo()
        control = control_model.search([
            ("year_two", "=", yy),
            ("aduana_clave", "=", aa),
            ("patente", "=", pppp),
        ], limit=1)
        if not control:
            control = control_model.with_context(real_user_id=self.env.user.id).create({
                "year_two": yy,
                "aduana_clave": aa,
                "patente": pppp,
                "ultimo_consecutivo": 0,
            })

        self.env.cr.execute(
            "SELECT ultimo_consecutivo FROM mx_ped_numero_control WHERE id = %s FOR UPDATE",
            [control.id],
        )
        current = self.env.cr.fetchone()[0] or 0
        next_value = current + 1
        if next_value > 999999:
            raise UserError(_("Se alcanzo el maximo de consecutivo 999999 para %s-%s-%s.") % (yy, aa, pppp))

        control.with_context(real_user_id=self.env.user.id).write({"ultimo_consecutivo": next_value})
        return f"{next_value:06d}"

    def action_asignar_numero_pedimento(self):
        for rec in self:
            yy, aa, pppp, d = rec._get_pedimento_number_parts()
            nnnnnn = rec._next_pedimento_consecutivo(yy, aa, pppp)
            # El numero visible del pedimento debe conservar solo el bloque final (7 digitos).
            rec.pedimento_numero = f"{d}{nnnnnn}"
        return True

    # ==========================
    # Cargar registros desde Lead
    # ==========================
    def _extract_value(self, value):
        if value is False:
            return ""
        if hasattr(value, "id"):
            if not value:
                return ""
            if hasattr(value, "code") and value.code:
                return value.code
            if hasattr(value, "name") and value.name:
                return value.name
            return value.id
        return value

    def _record_value_for_field(self, record, field_name):
        if not record:
            return None
        if field_name in record._fields:
            return self._extract_value(getattr(record, field_name))
        if not field_name.startswith("x_"):
            pref = f"x_{field_name}"
            if pref in record._fields:
                return self._extract_value(getattr(record, pref))
        return None

    def _lead_value_for_field_name(self, field_name, source_field=None, source_model=None):
        self.ensure_one()
        lead = self.lead_id

        def _norm(name):
            return (name or "").lower().replace(" ", "").replace("_", "")

        aliases = {
            "aduana": "aduana_clave",
            "patente": "patente",
            "clave_pedimento": "clave_pedimento",
            "tipo_operacion": "tipo_operacion",
            "tipo_movimiento": "tipo_movimiento",
            "regimen": "regimen",
            "incoterm": "incoterm",
            "moneda": "currency_id",
            "pais_origen": "x_pais_origen_id",
            "pais_destino": "x_pais_destino_id",
            "bultos": "total_packages_line",
            "bultos_totales": "total_packages_line",
            "numero_total_de_bultos": "total_packages_line",
            "peso_bruto": "total_gross_weight",
            "peso_bruto_total": "total_gross_weight",
            "peso_bruto_total_de_la_mercancia": "total_gross_weight",
            "peso_neto": "total_net_weight",
            "peso_neto_total": "total_net_weight",
            "peso_neto_total_de_la_mercancia": "total_net_weight",
            "valor_factura": "x_valor_factura",
            "valor_aduana": "x_valor_aduana_estimado",
            "folio_operacion": "x_folio_operacion",
            "referencia_cliente": "x_referencia_cliente",
            "aduana_seccion_entrada_salida": "aduana_seccion_entrada_salida",
            "medio_transporte_salida": "x_medio_transporte_salida",
            "tipo_contenedor": "x_tipo_contenedor_id",
            "clave_tipo_contenedor": "x_tipo_contenedor_id",
            "acuse_validacion": "acuse_validacion",
            "curp_agente": "curp_agente",
            "rfc_importador_exportador": "participante_rfc",
            "curp_importador_exportador": "participante_curp",
            "nombre_importador_exportador": "participante_nombre",
            "comprador": "x_comprador_id",
            "nombre_proveedor_comprador": "x_counterparty_name_505",
        }
        aliases_by_norm = {_norm(key): value for key, value in aliases.items()}

        source = source_field or aliases.get(field_name, aliases_by_norm.get(_norm(field_name), field_name))
        source_model = source_model or "lead"

        field_norm = _norm(field_name)
        source_norm_hint = _norm(source)
        if source == field_name:
            if "pesobruto" in field_norm:
                source = "total_gross_weight"
            elif "pesoneto" in field_norm:
                source = "total_net_weight"
            elif "bulto" in field_norm or "paquete" in field_norm:
                source = "total_packages_line"
        elif "pesobruto" in source_norm_hint:
            source = "total_gross_weight"
        elif "pesoneto" in source_norm_hint:
            source = "total_net_weight"
        elif "bulto" in source_norm_hint or "paquete" in source_norm_hint:
            source = "total_packages_line"

        # Normaliza tipo de operación a 1/2 aunque el layout use nombre "amigable"
        source_norm = _norm(source)
        if source_norm in ("tipooperacion", "xtipooperacion"):
            raw = self._record_value_for_field(lead, "x_tipo_operacion")
            raw = (str(raw or "")).strip().lower()
            if raw in ("importacion", "1", "01"):
                return "1"
            if raw in ("exportacion", "2", "02"):
                return "2"
            return ""
        if source_norm in ("tipomovimiento", "xtipomovimiento"):
            return self._get_tipo_movimiento_effective() or ""

        # Origen/destino: usa Many2one al catálogo de países → devuelve saai_m3 (2 dígitos)
        if source_norm in ("origendestino", "xorigendestino", "xorigendestinomercancia"):
            pais = getattr(lead, "x_origen_destino_id", False) if lead else False
            if pais:
                return (pais.saai_m3 or "").strip()
            # fallback al campo Char anterior para registros ya existentes
            return (getattr(lead, "x_origen_destino_mercancia", "") or "").strip()

        if source_model == "operacion":
            return self._record_value_for_field(self, source)
        if source in {"total_packages_line", "total_gross_weight", "total_net_weight"}:
            return self._record_value_for_field(self, source)
        if source_model == "partida":
            return None
        if source_model == "cliente":
            return self._record_value_for_field(lead.partner_id if lead else None, source)
        if source_model == "importador":
            return self._record_value_for_field(lead.x_importador_id if lead else None, source)
        if source_model == "exportador":
            return self._record_value_for_field(lead.x_exportador_id if lead else None, source)
        if source_model == "proveedor":
            if lead and lead.x_tipo_operacion == "exportacion":
                partner = lead.x_comprador_id or lead.x_proveedor_id
                return self._record_value_for_field(partner, source)
            return self._record_value_for_field(lead.x_proveedor_id if lead else None, source)
        if source_model == "comprador":
            return self._record_value_for_field(lead.x_comprador_id if lead else None, source)
        if source_model == "contraparte":
            if lead and lead.x_tipo_operacion == "exportacion":
                partner = lead.x_comprador_id or lead.x_proveedor_id
            else:
                partner = lead.x_proveedor_id or lead.x_comprador_id if lead else None
            return self._record_value_for_field(partner, source)
        if source_model == "transportista":
            t_line = lead.x_transportista_ids[:1] if lead else None
            return self._record_value_for_field(t_line.transportista_id if t_line else None, source)

        return self._record_value_for_field(lead, source)

    def _field_value_for_layout(self, campo, partida=None):
        self.ensure_one()
        source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
        if campo.source_model == "partida":
            source = source_name or campo.nombre
            val = self._record_value_for_field(partida, source)
            # fraccion_arancelaria es un snapshot que puede quedar vacío si la
            # línea del lead se creó programáticamente (sin disparar el onchange).
            # Fallback al code de fraccion_id para garantizar que nunca esté vacío.
            if not val and source == "fraccion_arancelaria" and partida and partida.fraccion_id:
                val = partida.fraccion_id.code or val
            # cantidad_comercial (UMC) puede ser 0.0 cuando el usuario no la ha llenado.
            # 0.0 == False en Python → el valor se descartaría en la guardia `not in (None, "", False)`.
            # Fallback a cantidad_tarifa y después a quantity (default=1.0) para que el
            # campo siempre lleve un valor positivo declarable en el TXT de SAAI.
            if not val and source == "cantidad_comercial" and partida:
                val = partida.cantidad_tarifa or partida.quantity or 0.0
            return val
        return self._lead_value_for_field_name(
            campo.nombre,
            source_field=source_name,
            source_model=campo.source_model,
        )

    def _document_value_for_505_field(self, campo, documento):
        self.ensure_one()
        source_name = (campo.source_field_id.name if campo.source_field_id else campo.source_field) or ""
        campo_name = self._norm_layout_token(campo.nombre)
        source_norm = self._norm_layout_token(source_name)
        token = f"{campo_name} {source_norm}".strip()
        document_field_map = {
            "fecha": documento.fecha or self.lead_id.x_cfdi_fecha or False,
            "folio": documento.folio or False,
            "cfdi_termino_facturacion": (documento.cfdi_termino_facturacion.code if documento.cfdi_termino_facturacion else None) or self.lead_id.x_incoterm or False,
            "x_incoterm": (documento.cfdi_termino_facturacion.code if documento.cfdi_termino_facturacion else None) or self.lead_id.x_incoterm or False,
            "cfdi_moneda_id": (
                documento.cfdi_moneda_id.code
                if documento.cfdi_moneda_id and hasattr(documento.cfdi_moneda_id, "code")
                else (documento.cfdi_moneda_id.name if documento.cfdi_moneda_id else False)
            ),
            "x_cfdi_moneda_id": (
                documento.cfdi_moneda_id.code
                if documento.cfdi_moneda_id and hasattr(documento.cfdi_moneda_id, "code")
                else (documento.cfdi_moneda_id.name if documento.cfdi_moneda_id else False)
            ),
            "cfdi_valor_usd": documento.cfdi_valor_usd or False,
            "x_cfdi_valor_usd": documento.cfdi_valor_usd or False,
            "cfdi_valor_moneda": documento.cfdi_valor_moneda or False,
            "x_cfdi_valor_moneda": documento.cfdi_valor_moneda or False,
            "cfdi_pais_id": (
                documento.cfdi_pais_id.code
                if documento.cfdi_pais_id and hasattr(documento.cfdi_pais_id, "code")
                else (documento.cfdi_pais_id.name if documento.cfdi_pais_id else False)
            ),
            "x_cfdi_pais_id": (
                documento.cfdi_pais_id.code
                if documento.cfdi_pais_id and hasattr(documento.cfdi_pais_id, "code")
                else (documento.cfdi_pais_id.name if documento.cfdi_pais_id else False)
            ),
            "cfdi_estado_id": (
                documento.cfdi_estado_id.code
                if documento.cfdi_estado_id and hasattr(documento.cfdi_estado_id, "code")
                else (documento.cfdi_estado_id.name if documento.cfdi_estado_id else False)
            ),
            "x_cfdi_estado_id": (
                documento.cfdi_estado_id.code
                if documento.cfdi_estado_id and hasattr(documento.cfdi_estado_id, "code")
                else (documento.cfdi_estado_id.name if documento.cfdi_estado_id else False)
            ),
            "cfdi_id_fiscal": documento.cfdi_id_fiscal or False,
            "x_cfdi_id_fiscal": documento.cfdi_id_fiscal or False,
            "counterparty_name_505": documento.counterparty_name_505 or False,
            "name": documento.counterparty_name_505 or False,
            "counterparty_street_505": documento.counterparty_street_505 or False,
            "x_street_name": documento.counterparty_street_505 or False,
            "street": documento.counterparty_street_505 or False,
            "counterparty_num_int_505": documento.counterparty_num_int_505 or False,
            "x_street_number_int": documento.counterparty_num_int_505 or False,
            "counterparty_num_ext_505": documento.counterparty_num_ext_505 or False,
            "x_street_number_ext": documento.counterparty_num_ext_505 or False,
            "counterparty_zip_505": documento.counterparty_zip_505 or False,
            "zip": documento.counterparty_zip_505 or False,
            "counterparty_city_505": documento.counterparty_city_505 or False,
            "city": documento.counterparty_city_505 or False,
            "x_municipio": documento.counterparty_city_505 or False,
            "vat": documento.cfdi_id_fiscal or False,
        }

        if source_name and source_name in document_field_map:
            return document_field_map[source_name]

        if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro"):
            return "505"
        if "pedimento" in token and ("numero" in token or "num" in token or token == "pedimento"):
            return self.pedimento_numero or ""
        if "fecha" in token and ("cfdi" in token or "documento" in token or "acuse" in token):
            return documento.fecha or self.lead_id.x_cfdi_fecha or False
        if any(key in token for key in ["acuse de valor", "acuse valor", "numero del acuse", "numero acuse", "numero cfdi", "numero documento", "folio"]):
            return documento.folio or False
        if "termino" in token and "facturacion" in token:
            return (documento.cfdi_termino_facturacion.code if documento.cfdi_termino_facturacion else None) or self.lead_id.x_incoterm or False
        if "moneda" in token and ("cfdi" in token or "documento" in token):
            return documento.cfdi_moneda_id.code if documento.cfdi_moneda_id and hasattr(documento.cfdi_moneda_id, "code") else (documento.cfdi_moneda_id.name if documento.cfdi_moneda_id else False)
        if "valor" in token and "dolar" in token:
            return documento.cfdi_valor_usd or False
        if "valor" in token and "moneda" in token:
            return documento.cfdi_valor_moneda or False
        if "pais" in token and ("cfdi" in token or "documento" in token):
            return documento.cfdi_pais_id.code if documento.cfdi_pais_id and hasattr(documento.cfdi_pais_id, "code") else (documento.cfdi_pais_id.name if documento.cfdi_pais_id else False)
        if ("entidad" in token or "estado" in token) and ("cfdi" in token or "documento" in token):
            return documento.cfdi_estado_id.code if documento.cfdi_estado_id and hasattr(documento.cfdi_estado_id, "code") else (documento.cfdi_estado_id.name if documento.cfdi_estado_id else False)
        if "identificacion fiscal" in token or "id fiscal" in token:
            return documento.cfdi_id_fiscal or False
        if "proveedor" in token or "comprador" in token:
            return documento.counterparty_name_505 or False
        if "calle" in token:
            return documento.counterparty_street_505 or False
        if "numero interior" in token or "num interior" in token:
            return documento.counterparty_num_int_505 or False
        if "numero exterior" in token or "num exterior" in token:
            return documento.counterparty_num_ext_505 or False
        if "codigo postal" in token or token.endswith("cp") or token == "cp":
            return documento.counterparty_zip_505 or False
        if "municipio" in token or "ciudad" in token:
            return documento.counterparty_city_505 or False

        # Fallback a source_field tecnico si coincide con documento.
        source = source_name or campo.nombre
        if source in documento._fields:
            return self._record_value_for_field(documento, source)
        if campo.source_model in ("contraparte", "proveedor", "comprador"):
            if source_name in document_field_map:
                return document_field_map[source_name]
            return False
        return self._field_value_for_layout(campo, partida=False)

    def _is_505_export_a1_mode(self):
        self.ensure_one()
        return self.tipo_operacion == "exportacion" and (self.clave_pedimento or "").strip().upper() == "A1"

    def _is_505_contingency_mode(self):
        self.ensure_one()
        return bool(self.send_505_contingency or self.env.context.get("force_505_contingency"))

    def _should_blank_505_field(self, token):
        self.ensure_one()
        if self._is_505_contingency_mode():
            return False

        export_a1 = self._is_505_export_a1_mode()

        if "fecha" in token and ("cfdi" in token or "documento" in token or "acuse" in token):
            return not export_a1
        if "moneda" in token and ("cfdi" in token or "documento" in token):
            return not export_a1
        if "valor" in token and ("dolar" in token or "usd" in token):
            return not export_a1
        if "valor" in token and "moneda" in token:
            return not export_a1
        if "pais" in token and ("cfdi" in token or "documento" in token):
            return not export_a1
        if ("entidad" in token or "estado" in token) and ("cfdi" in token or "documento" in token):
            return not export_a1
        if "calle" in token:
            return True
        if "numero interior" in token or "num interior" in token:
            return True
        if "numero exterior" in token or "num exterior" in token:
            return True
        if "codigo postal" in token or token.endswith("cp") or token == "cp":
            return True
        if "municipio" in token or "ciudad" in token:
            return True
        return False

    @staticmethod
    def _json_safe_layout_value(value):
        if isinstance(value, datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, date):
            return fields.Date.to_string(value)
        return value

    @staticmethod
    def _format_layout_date_8(value):
        if not value:
            return ""
        dt = fields.Date.to_date(value)
        return dt.strftime("%d%m%Y") if dt else ""

    def _build_505_valores(self, layout_reg, documento):
        self.ensure_one()
        valores = {}
        for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0):
            source_name = (campo.source_field_id.name if campo.source_field_id else campo.source_field) or ""
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            if self._should_blank_505_field(token):
                valores[campo.nombre] = self._LAYOUT_EMPTY
                continue
            val = self._document_value_for_505_field(campo, documento)
            if val not in (None, "", False) and "fecha" in token and ("cfdi" in token or "documento" in token or "acuse" in token):
                val = self._format_layout_date_8(val)
            if val in (None, "", False) and campo.default:
                val = campo.default
            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    @staticmethod
    def _format_506_date(value):
        if not value:
            return ""
        dt = fields.Date.to_date(value)
        return dt.strftime("%d%m%Y") if dt else ""

    def _build_506_valores(self, layout_reg, fecha_line):
        self.ensure_one()
        valores = {}
        tipo_code = (fecha_line.tipo_fecha_code or "").strip()
        fecha_txt = self._format_506_date(fecha_line.fecha)

        for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = (campo.nombre or "").strip().lower()
            source_norm = (source_name or "").strip().lower()
            token = f"{campo_name} {source_norm}".strip()

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro"):
                val = "506"
            elif "pedimento" in token and ("numero" in token or "num" in token or token == "pedimento"):
                val = self.pedimento_numero or ""
            elif "tipo" in token and "fecha" in token:
                val = tipo_code
            elif "fecha" in token and "tipo" not in token and "registro" not in token:
                val = fecha_txt
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = val
        return valores

    def _build_507_valores(self, layout_reg, identificador_line):
        self.ensure_one()
        valores = {}
        code = ((identificador_line.code if identificador_line else "") or "").strip()
        comp1 = ((identificador_line.complemento1 if identificador_line else "") or "").strip() or "NULO"
        comp2 = ((identificador_line.complemento2 if identificador_line else "") or "").strip() or "NULO"
        comp3 = ((identificador_line.complemento3 if identificador_line else "") or "").strip() or "NULO"

        for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = (campo.nombre or "").strip().lower()
            source_norm = (source_name or "").strip().lower()
            token = f"{campo_name} {source_norm}".strip()

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro"):
                val = "507"
            elif "pedimento" in token and ("numero" in token or "num" in token or token == "pedimento"):
                val = self.pedimento_numero or ""
            elif ("identificador" in token and "clave" in token) or token in ("identificador", "idf"):
                val = code
            elif "complemento 1" in token or "complemento1" in token:
                val = comp1
            elif "complemento 2" in token or "complemento2" in token:
                val = comp2
            elif "complemento 3" in token or "complemento3" in token:
                val = comp3
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = val
        return valores

    @staticmethod
    def _format_508_date(value):
        if not value:
            return ""
        dt = fields.Date.to_date(value)
        return dt.strftime("%d%m%Y") if dt else ""

    @staticmethod
    def _norm_layout_token(value):
        txt = (value or "").strip().lower()
        if not txt:
            return ""
        txt = unicodedata.normalize("NFKD", txt)
        txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
        return txt

    def _build_508_valores(self, layout_reg, cuenta_line):
        self.ensure_one()
        valores = {}
        fecha_txt = self._format_508_date(cuenta_line.fecha_constancia)
        for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro"):
                val = "508"
            elif "pedimento" in token and ("numero" in token or "num" in token or token == "pedimento"):
                val = self.pedimento_numero or ""
            elif ("institucion" in token and "emisora" in token) or "institucion_emisora" in token:
                val = cuenta_line.institucion_emisora or ""
            elif ("numero" in token and "contrato" in token) or "numero_contrato" in token:
                val = cuenta_line.numero_contrato or ""
            elif ("folio" in token and "constancia" in token) or "folio_constancia" in token:
                val = cuenta_line.folio_constancia or ""
            elif "fecha" in token and "constancia" in token:
                val = fecha_txt
            elif ("tipo" in token and "cuenta" in token) or "tipo_cuenta" in token:
                val = cuenta_line.tipo_cuenta or ""
            elif ("tipo" in token and "garantia" in token) or "tipo_garantia" in token:
                val = cuenta_line.tipo_garantia or ""
            elif ("valor" in token and "unitario" in token and "titulo" in token) or "valor_unitario_titulo" in token:
                val = cuenta_line.valor_unitario_titulo
            elif ("total" in token and "garantia" in token) or "total_garantia" in token:
                val = cuenta_line.total_garantia
            elif ("cantidad" in token and ("unidad" in token or "um" in token)) or "cantidad_um" in token:
                val = cuenta_line.cantidad_um
            elif ("titulos" in token and "asignados" in token) or "titulos_asignados" in token:
                val = cuenta_line.titulos_asignados
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = val
        return valores

    def _build_501_valores(self, layout_reg):
        self.ensure_one()
        valores = {}
        for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0):
            source_name = (campo.source_field_id.name if campo.source_field_id else campo.source_field) or ""
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            token_compact = token.replace(" ", "").replace("_", "")
            source_compact = source_norm.replace(" ", "").replace("_", "")

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro"):
                val = "501"
            elif "pedimento" in token and ("numero" in token or "num" in token or token == "pedimento"):
                val = self.pedimento_numero or ""
            elif source_compact == "totalgrossweight" or "pesobruto" in token_compact:
                val = self.total_gross_weight
            elif source_compact == "totalnetweight" or "pesoneto" in token_compact:
                val = self.total_net_weight
            elif source_compact == "totalpackagesline" or "bulto" in token_compact or "paquete" in token_compact:
                val = self.total_packages_line
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _build_511_valores(self, layout_reg, observation_line):
        self.ensure_one()
        valores = {}
        sequence_txt = str(observation_line.get("sequence") or "").zfill(3)
        clean_text = self._sanitize_511_text(observation_line.get("texto"))

        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro"):
                val = "511"
            elif "pedimento" in token and ("numero" in token or "num" in token or token == "pedimento"):
                val = self.pedimento_numero or ""
            elif (
                "secuencia" in token
                or source_norm in {"sequence", "secuencia"}
                or idx == 3
                or orden == 3
                or pos_ini == 11
            ):
                val = sequence_txt
            elif (
                "observ" in token
                or source_norm in {"texto", "observaciones", "observacion"}
                or idx == 4
                or orden == 4
                or pos_ini == 14
            ):
                val = clean_text
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _build_512_valores(self, layout_reg, descargo_line):
        self.ensure_one()
        valores = {}
        fecha_original = ""
        if descargo_line.get("fecha_operacion_original"):
            fecha_original = fields.Date.from_string(descargo_line["fecha_operacion_original"]).strftime("%d%m%Y")

        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "512"
            elif "pedimento" in token and ("numero" in token or "num" in token) and "original" not in token:
                val = self.pedimento_numero or ""
            elif ("patente" in token or "autorizacion" in token) and "original" in token:
                val = descargo_line.get("patente_original") or ""
            elif "pedimento" in token and "original" in token:
                val = descargo_line.get("pedimento_original") or ""
            elif ("aduana" in token and "original" in token) or source_norm in {"aduana_seccion_original", "aduana_original"}:
                val = descargo_line.get("aduana_seccion_original") or ""
            elif ("clave" in token and "documento" in token and "original" in token) or source_norm in {"clave_documento_original", "documento_original"}:
                val = descargo_line.get("clave_documento_original") or ""
            elif ("fecha" in token and "original" in token) or source_norm in {"fecha_operacion_original", "fecha_original"}:
                val = fecha_original
            elif ("fraccion" in token and "original" in token) or source_norm in {"fraccion_original"}:
                val = descargo_line.get("fraccion_original") or ""
            elif ("unidad" in token and "original" in token) or source_norm in {"unidad_medida_original", "um_original"}:
                val = descargo_line.get("unidad_medida_original") or ""
            elif ("cantidad" in token and ("umt" in token or "mercancia" in token)) or source_norm in {"cantidad_umt_original", "cantidad_original"}:
                val = descargo_line.get("cantidad_umt_original")
            else:
                if idx == 2 or orden == 2 or pos_ini == 4:
                    val = self.pedimento_numero or ""
                elif idx == 3 or orden == 3 or pos_ini == 11:
                    val = descargo_line.get("patente_original") or ""
                elif idx == 4 or orden == 4 or pos_ini == 15:
                    val = descargo_line.get("pedimento_original") or ""
                elif idx == 5 or orden == 5 or pos_ini == 22:
                    val = descargo_line.get("aduana_seccion_original") or ""
                elif idx == 6 or orden == 6 or pos_ini == 25:
                    val = descargo_line.get("clave_documento_original") or ""
                elif idx == 7 or orden == 7 or pos_ini == 27:
                    val = fecha_original
                elif idx == 8 or orden == 8 or pos_ini == 35:
                    val = descargo_line.get("fraccion_original") or ""
                elif idx == 9 or orden == 9 or pos_ini == 43:
                    val = descargo_line.get("unidad_medida_original") or ""
                elif idx == 10 or orden == 10 or pos_ini == 45:
                    val = descargo_line.get("cantidad_umt_original")
                else:
                    val = self._field_value_for_layout(campo, partida=False)
                    if val in (None, "", False) and campo.default:
                        val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _build_513_valores(self, layout_reg, compensacion_line):
        self.ensure_one()
        valores = {}
        fecha_original = ""
        if compensacion_line.get("fecha_pago_original"):
            fecha_original = fields.Date.from_string(compensacion_line["fecha_pago_original"]).strftime("%d%m%Y")

        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "513"
            elif "pedimento" in token and ("numero" in token or "num" in token) and "original" not in token:
                val = self.pedimento_numero or ""
            elif ("patente" in token or "autorizacion" in token) and "original" in token:
                val = compensacion_line.get("patente_original") or ""
            elif "pedimento" in token and "original" in token:
                val = compensacion_line.get("pedimento_original") or ""
            elif ("aduana" in token and "original" in token) or source_norm in {"aduana_seccion_original", "aduana_original"}:
                val = compensacion_line.get("aduana_seccion_original") or ""
            elif "fecha" in token and ("pago" in token or "original" in token):
                val = fecha_original
            elif ("contribucion" in token and "compens" in token) or ("gravamen" in token and "compens" in token):
                val = compensacion_line.get("contribucion_compensada") or ""
            elif ("importe" in token and "compens" in token) or source_norm == "importe_compensado":
                val = compensacion_line.get("importe_compensado")
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _build_514_valores(self, layout_reg, documento):
        self.ensure_one()
        valores = {}
        fecha_txt = ""
        if documento.fecha:
            fecha_txt = fields.Date.to_date(documento.fecha).strftime("%d%m%Y")
        forma_pago_code = (documento.forma_pago_code or "").strip()
        institucion_emisora = (documento.institucion_emisora_514 or "").strip()
        if not institucion_emisora:
            if forma_pago_code == "12":
                institucion_emisora = "Aduanas"
            elif documento.institucion_financiera_514_id:
                institucion_emisora = documento.institucion_financiera_514_id.name or ""
            elif forma_pago_code in {"4", "15"}:
                cuenta = self.cuenta_aduanera_ids.sorted(lambda l: (l.sequence or 0, l.id))[:1]
                if cuenta and cuenta.institucion_financiera_id:
                    institucion_emisora = cuenta.institucion_financiera_id.name or ""

        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "514"
            elif ("pedimento" in token and ("numero" in token or "num" in token)) or idx == 2 or orden == 2 or pos_ini == 4:
                val = self.pedimento_numero or ""
            elif ("forma" in token and "pago" in token) or idx == 3 or orden == 3 or pos_ini == 11:
                val = forma_pago_code or ""
            elif (
                (("dependencia" in token or "institucion" in token) and ("emisora" in token or "emisor" in token))
                or idx == 4
                or orden == 4
                or pos_ini == 14
            ):
                val = institucion_emisora or ""
            elif (("numero" in token and "documento" in token) or "folio" in token) or idx == 5 or orden == 5:
                val = documento.folio or ""
            elif ("fecha" in token and ("exped" in token or "emision" in token or "expedicion" in token)) or idx == 6 or orden == 6:
                val = fecha_txt
            elif (("importe" in token and "ampar" in token) or source_norm == "importe_total_amparado_514") or idx == 7 or orden == 7:
                val = documento.importe_total_amparado_514
            elif ("saldo" in token and "disponible" in token) or idx == 8 or orden == 8:
                val = documento.saldo_disponible_514
            elif (("importe" in token and "pagar" in token) or source_norm == "importe_total_pagar_514") or idx == 9 or orden == 9:
                val = documento.importe_total_pagar_514
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _get_520_destinatario_lines(self):
        self.ensure_one()
        lead = self.lead_id
        if not lead or not lead.x_send_520_contingency:
            return []

        lines = []
        for line in lead.x_destinatario_520_ids.sorted(lambda l: l.id):
            if not ((line.nombre or "").strip() and (line.calle or "").strip() and (line.num_exterior or "").strip()):
                continue
            lines.append({
                "identificacion_fiscal": (line.identificacion_fiscal or "").strip(),
                "nombre": (line.nombre or "").strip(),
                "calle": (line.calle or "").strip(),
                "num_interior": (line.num_interior or "").strip(),
                "num_exterior": (line.num_exterior or "").strip(),
                "codigo_postal": (line.codigo_postal or "").strip(),
                "municipio_ciudad": (line.municipio_ciudad or "").strip(),
                "pais": (line.pais_id.code or "").strip() if line.pais_id else "",
                "__source_id": line.id,
            })
        return lines

    def _build_520_valores(self, layout_reg, destinatario_line):
        self.ensure_one()
        valores = {}

        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "520"
            elif ("pedimento" in token and ("numero" in token or "num" in token)) or idx == 2 or orden == 2 or pos_ini == 4:
                val = self.pedimento_numero or ""
            elif ("identificacion" in token and "fiscal" in token) or source_norm in {"identificacion_fiscal", "id_fiscal"} or idx == 3 or orden == 3:
                val = destinatario_line.get("identificacion_fiscal") or ""
            elif ("nombre" in token and "destinat" in token) or source_norm in {"nombre", "nombre_destinatario"} or idx == 4 or orden == 4:
                val = destinatario_line.get("nombre") or ""
            elif "calle" in token or source_norm == "calle" or idx == 5 or orden == 5:
                val = destinatario_line.get("calle") or ""
            elif (("numero" in token and "interior" in token) or source_norm in {"num_interior", "numero_interior"}) or idx == 6 or orden == 6:
                val = destinatario_line.get("num_interior") or ""
            elif (("numero" in token and "exterior" in token) or source_norm in {"num_exterior", "numero_exterior"}) or idx == 7 or orden == 7:
                val = destinatario_line.get("num_exterior") or ""
            elif ("codigo" in token and "postal" in token) or source_norm in {"codigo_postal", "cp"} or idx == 8 or orden == 8:
                val = destinatario_line.get("codigo_postal") or ""
            elif ("municipio" in token or "ciudad" in token) or source_norm in {"municipio_ciudad", "municipio", "ciudad"} or idx == 9 or orden == 9:
                val = destinatario_line.get("municipio_ciudad") or ""
            elif "pais" in token or source_norm in {"pais", "pais_destinatario"} or idx == 10 or orden == 10:
                val = destinatario_line.get("pais") or ""
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _sanitize_516_transport_identificador(self, value):
        clean = (value or "").strip()
        for ch in ("'", '"', "´", "*", "-", "_"):
            clean = clean.replace(ch, "")
        return clean.strip()

    def _get_516_candado_lines(self):
        self.ensure_one()
        lead = self.lead_id
        if not lead:
            return []

        lines = []
        for line in lead.x_candado_ids.sorted(lambda l: l.id):
            transporte_identificador = self._sanitize_516_transport_identificador(line.transporte_identificador)
            num_candado = (line.num_candado or "").strip()
            if not transporte_identificador or not num_candado:
                continue
            lines.append({
                "transporte_identificador": transporte_identificador,
                "num_candado": num_candado,
                "__source_id": line.id,
            })

        return lines

    def _build_516_valores(self, layout_reg, candado_line):
        self.ensure_one()
        valores = {}
        transporte_identificador = candado_line.get("transporte_identificador") or ""
        num_candado = candado_line.get("num_candado") or ""

        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "516"
            elif ("pedimento" in token and ("numero" in token or "num" in token)) or idx == 2 or orden == 2 or pos_ini == 4:
                val = self.pedimento_numero or ""
            elif (
                ("transporte" in token and ("identificador" in token or "medio" in token))
                or source_norm in {"transporte_identificador", "identificador_transporte"}
                or idx == 3
                or orden == 3
                or pos_ini == 11
            ):
                val = transporte_identificador
            elif (
                ("candado" in token or "precinto" in token)
                or source_norm in {"num_candado", "numero_candado", "candado", "precinto"}
                or idx == 4
                or orden == 4
                or pos_ini == 28
            ):
                val = num_candado
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    @staticmethod
    def _sanitize_502_text(value, max_len=120):
        """Quita caracteres especiales no permitidos en campos alfanuméricos del 502."""
        txt = (value or "").strip()
        for ch in ("'", '"', "´", "*", "-", "_"):
            txt = txt.replace(ch, " ")
        txt = " ".join(txt.split())
        return txt[:max_len].strip()

    def _resolve_saai_pais_code(self, country):
        """Dado un res.country, devuelve el código SAAI M3 (Apéndice 4).
        Busca en aduana.catalogo.pais por country_id; si no está configurado, usa res.country.code como fallback.
        """
        if not country:
            return ""
        catalogo = self.env["aduana.catalogo.pais"].search(
            [("country_id", "=", country.id), ("active", "=", True)],
            limit=1,
        )
        if catalogo:
            return (catalogo.saai_m3 or "").strip()
        return (country.code or "").strip().upper()

    def _get_502_transporte_lines(self):
        """Devuelve una lista de dicts, uno por transportista capturado (registro 502).

        El contenido del dict varía según el modo de transporte:
        - Terrestre: RFC, CURP, placas, domicilio (carrier mexicano)
        - Aéreo: nombre aerolínea, país, número de vuelo como identificador; sin RFC/CURP si es extranjero
        - Marítimo: nombre naviera, país, nombre del buque/voyage; sin RFC/CURP si es extranjero
        - Ferroviario: nombre empresa, RFC si es nacional, número de furgón
        """
        self.ensure_one()
        lead = self.lead_id
        if not lead or not lead.x_transportista_ids:
            return []
        modo = lead.x_modo_transporte or "terrestre"
        lines = []
        for t in lead.x_transportista_ids.sorted(lambda l: (l.sequence or 0, l.id)):
            if not t.transportista_id:
                continue
            pais_code = self._resolve_saai_pais_code(t.transporte_pais_id)
            es_nacional = t.es_carrier_nacional

            # RFC y CURP solo para carriers nacionales (terrestres y ferroviarios mexicanos)
            rfc_val = (t.rfc or "").strip()[:13] if es_nacional else ""
            curp_val = (t.curp or "").strip()[:18] if (es_nacional and modo == "terrestre") else ""
            domicilio_val = self._sanitize_502_text(t.domicilio or "", 150) if es_nacional else ""

            # Identificador del vehículo según modo
            if modo == "aereo":
                # Para aéreo preferimos el número de vuelo; fallback a matrícula aeronave
                identificador = self._sanitize_502_text(
                    t.numero_vuelo or t.transporte_identificador or "", 30
                )[:30]
            elif modo == "maritimo":
                # Para marítimo: nombre del buque + voyage si disponible
                buque = (t.nombre_buque or t.transporte_identificador or "").strip()
                voyage = (t.numero_viaje or "").strip()
                identificador = self._sanitize_502_text(
                    ("%s/%s" % (buque, voyage)) if buque and voyage else buque, 30
                )[:30]
            else:
                # Terrestre y ferroviario: placas o número de furgón
                identificador = self._sanitize_502_text(t.transporte_identificador or "", 30)[:30]

            lines.append({
                "rfc": rfc_val,
                "curp": curp_val,
                "nombre": self._sanitize_502_text(t.transportista_id.name or "", 120),
                "pais": pais_code[:3],
                "identificador": identificador,
                "bultos": lead.x_bultos or 0,
                "domicilio": domicilio_val,
                "__source_id": t.id,
            })
        return lines

    def _get_503_guia_lines(self):
        """Devuelve lista de dicts para el registro 503 desde x_guia_ids."""
        self.ensure_one()
        lead = self.lead_id
        if not lead:
            return []
        return [
            {
                "numero": (g.numero or "").strip()[:20],
                "identificador": (g.identificador or "M")[:1],
                "__source_id": g.id,
            }
            for g in lead.x_guia_ids.sorted(lambda g: (g.sequence or 0, g.id))
            if (g.numero or "").strip()
        ]

    def _get_504_contenedor_lines(self):
        """Devuelve lista de dicts para el registro 504 desde x_contenedor_ids."""
        self.ensure_one()
        lead = self.lead_id
        if not lead:
            return []
        return [
            {
                "numero": (c.numero or "").strip()[:12],
                "tipo": str(c.tipo_contenedor_id.code or "").zfill(2) if c.tipo_contenedor_id else "",
                "__source_id": c.id,
            }
            for c in lead.x_contenedor_ids.sorted(lambda c: (c.sequence or 0, c.id))
            if (c.numero or "").strip()
        ]

    def _build_502_valores(self, layout_reg, transporte_line):
        self.ensure_one()
        valores = {}
        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "502"
            elif ("pedimento" in token and ("numero" in token or "num" in token)) or idx == 2 or orden == 2 or pos_ini == 4:
                val = self.pedimento_numero or ""
            elif ("rfc" in token and "transport" in token) or source_norm == "rfc_transportista" or idx == 3 or orden == 3:
                val = transporte_line.get("rfc") or ""
            elif ("curp" in token and "transport" in token) or source_norm == "curp_transportista" or idx == 4 or orden == 4:
                val = transporte_line.get("curp") or ""
            elif ("nombre" in token and "transport" in token) or source_norm in {"nombre_transportista", "nombre_transport"} or idx == 5 or orden == 5:
                val = transporte_line.get("nombre") or ""
            elif "pais" in token or source_norm in {"pais", "pais_transporte", "pais_medio_transporte"} or idx == 6 or orden == 6:
                val = transporte_line.get("pais") or ""
            elif ("identificad" in token and "transport" in token) or source_norm in {"identificador_transporte", "id_transporte", "identificacion_transporte"} or idx == 7 or orden == 7:
                val = transporte_line.get("identificador") or ""
            elif "bulto" in token or source_norm in {"total_bultos", "bultos"} or idx == 8 or orden == 8:
                bultos = transporte_line.get("bultos") or 0
                val = str(int(bultos)) if bultos else ""
            elif "domicilio" in token or source_norm in {"domicilio_transportista", "domicilio_fiscal_transportista", "domicilio"} or idx == 9 or orden == 9:
                val = transporte_line.get("domicilio") or ""
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _build_503_valores(self, layout_reg, guia_line):
        self.ensure_one()
        valores = {}
        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if source_norm in {"identificador_guia", "tipo_guia", "id_guia"}:
                val = guia_line.get("identificador") or ""
            elif source_norm in {"guia", "numero_guia", "guia_manifiesto", "num_guia", "conocimiento_embarque"}:
                val = guia_line.get("numero") or ""
            elif ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "503"
            elif ("pedimento" in token and ("numero" in token or "num" in token)) or idx == 2 or orden == 2 or pos_ini == 4:
                val = self.pedimento_numero or ""
            elif ("identificad" in token and ("guia" in token or "tipo" in token)) or idx == 4 or orden == 4:
                val = guia_line.get("identificador") or ""
            elif "guia" in token or "manifiesto" in token or "conocimiento" in token or idx == 3 or orden == 3:
                val = guia_line.get("numero") or ""
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def _build_504_valores(self, layout_reg, contenedor_line):
        self.ensure_one()
        valores = {}
        ordered_campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)
        for idx, campo in enumerate(ordered_campos, start=1):
            source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
            campo_name = self._norm_layout_token(campo.nombre)
            source_norm = self._norm_layout_token(source_name)
            token = f"{campo_name} {source_norm}".strip()
            pos_ini = campo.pos_ini or 0
            orden = campo.orden or 0

            val = None
            if ("tipo" in token and "registro" in token) or token in ("registro", "clave_registro") or idx == 1 or orden == 1 or pos_ini == 1:
                val = "504"
            elif ("pedimento" in token and ("numero" in token or "num" in token)) or idx == 2 or orden == 2 or pos_ini == 4:
                val = self.pedimento_numero or ""
            elif ("contenedor" in token and ("numero" in token or "num" in token)) or source_norm in {"num_contenedor", "numero_contenedor", "contenedor"} or idx == 3 or orden == 3:
                val = contenedor_line.get("numero") or ""
            elif ("tipo" in token and "contenedor" in token) or source_norm in {"tipo_contenedor", "clave_tipo_contenedor"} or idx == 4 or orden == 4:
                val = contenedor_line.get("tipo") or ""
            else:
                val = self._field_value_for_layout(campo, partida=False)
                if val in (None, "", False) and campo.default:
                    val = campo.default

            if val not in (None, "", False):
                valores[campo.nombre] = self._json_safe_layout_value(val)
        return valores

    def action_cargar_desde_lead(self):
        self.ensure_one()
        if not self.layout_id:
            self.layout_id = self._get_latest_layout().id or False
        if not self.layout_id:
            raise UserError(_("No hay layout activo configurado para la operación."))
        if not self.lead_id:
            raise UserError(_("La operación no tiene Lead asociado."))

        def _allowed_codes():
            from_rule = self._get_allowed_codes_from_regla()
            from_stage = self._get_stage_allowed_codes("load_from_lead")
            if from_rule is None:
                return from_stage
            if from_stage is None:
                return from_rule
            return from_rule & from_stage

        allowed = _allowed_codes()
        repeat_codes_by_partida = {"551", "552", "553", "554", "555", "556", "557", "558"}
        registros = []
        order_map = self._get_record_order_map()
        for layout_reg in self.layout_id.registro_ids.sorted(lambda r: self._layout_registro_sort_key(r, order_map=order_map)):
            if allowed is not None and layout_reg.codigo not in allowed:
                continue
            code = (layout_reg.codigo or "").strip()
            # Estos registros se generan/sincronizan desde modelos técnicos dedicados
            # o tienen condiciones propias (auto_single / auto_multi).
            # NO deben procesarse por el loop de layout para evitar que se generen
            # incondicionalmente (ej. 800 apareciendo en pedimentos normales).
            if code in {"509", "510", "557", "514"}:
                continue
            # 505 se inyecta por su propio bloque (una línea por documento).
            if code == "505":
                continue
            # Registros condicionales de escenario: solo via auto_single con guardia propia.
            if code in {"800", "801", "701", "702", "301", "302"}:
                continue
            campos = layout_reg.campo_ids.sorted(lambda c: c.pos_ini or c.orden or 0)

            if code == "506":
                fecha_lines = self.lead_id.x_fecha_506_ids.sorted(lambda l: (l.sequence or 0, l.id))
                if not fecha_lines:
                    continue
                for secuencia, fecha_line in enumerate(fecha_lines, start=1):
                    _vals = self._build_506_valores(layout_reg, fecha_line)
                    _vals["__source_id"] = fecha_line.id
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "507":
                id_lines = self.identificador_pedimento_ids.filtered(
                    lambda l: l.identificador_id or ((l.code or "").strip())
                ).sorted(lambda l: (l.sequence or 0, l.id))
                if not id_lines:
                    continue
                for secuencia, ident_line in enumerate(id_lines, start=1):
                    _vals = self._build_507_valores(layout_reg, ident_line)
                    _vals["__source_id"] = ident_line.id
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "508":
                cuenta_lines = self.cuenta_aduanera_ids.sorted(lambda l: (l.sequence or 0, l.id))
                if not cuenta_lines:
                    continue
                for secuencia, cuenta_line in enumerate(cuenta_lines, start=1):
                    _vals = self._build_508_valores(layout_reg, cuenta_line)
                    _vals["__source_id"] = cuenta_line.id
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "502":
                transporte_lines = self._get_502_transporte_lines()
                if not transporte_lines:
                    continue
                for secuencia, transporte_line in enumerate(transporte_lines, start=1):
                    _vals = self._build_502_valores(layout_reg, transporte_line)
                    if "__source_id" in transporte_line:
                        _vals["__source_id"] = transporte_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "503":
                guia_lines = self._get_503_guia_lines()
                if not guia_lines:
                    continue
                for secuencia, guia_line in enumerate(guia_lines, start=1):
                    _vals = self._build_503_valores(layout_reg, guia_line)
                    if "__source_id" in guia_line:
                        _vals["__source_id"] = guia_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "504":
                contenedor_lines = self._get_504_contenedor_lines()
                if not contenedor_lines:
                    continue
                for secuencia, contenedor_line in enumerate(contenedor_lines, start=1):
                    _vals = self._build_504_valores(layout_reg, contenedor_line)
                    if "__source_id" in contenedor_line:
                        _vals["__source_id"] = contenedor_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "516":
                candado_lines = self._get_516_candado_lines()
                if not candado_lines:
                    continue
                for secuencia, candado_line in enumerate(candado_lines, start=1):
                    _vals = self._build_516_valores(layout_reg, candado_line)
                    if "__source_id" in candado_line:
                        _vals["__source_id"] = candado_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "520":
                destinatario_lines = self._get_520_destinatario_lines()
                if self.lead_id.x_send_520_contingency and not destinatario_lines:
                    raise UserError(_("Activas 520 de contingencia pero no capturaste destinatarios en el lead."))
                if not destinatario_lines:
                    continue
                for secuencia, destinatario_line in enumerate(destinatario_lines, start=1):
                    _vals = self._build_520_valores(layout_reg, destinatario_line)
                    if "__source_id" in destinatario_line:
                        _vals["__source_id"] = destinatario_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "511":
                observation_lines = self._get_511_observation_lines()
                if not observation_lines:
                    continue
                for secuencia, observation_line in enumerate(observation_lines, start=1):
                    _vals = self._build_511_valores(layout_reg, observation_line)
                    if "__source_id" in observation_line:
                        _vals["__source_id"] = observation_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "512":
                descargo_lines = self._get_512_descargo_lines()
                if not descargo_lines:
                    continue
                for secuencia, descargo_line in enumerate(descargo_lines, start=1):
                    _vals = self._build_512_valores(layout_reg, descargo_line)
                    if "__source_id" in descargo_line:
                        _vals["__source_id"] = descargo_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "513":
                compensacion_lines = self._get_513_compensacion_lines()
                if not compensacion_lines:
                    continue
                for secuencia, compensacion_line in enumerate(compensacion_lines, start=1):
                    _vals = self._build_513_valores(layout_reg, compensacion_line)
                    if "__source_id" in compensacion_line:
                        _vals["__source_id"] = compensacion_line["__source_id"]
                    registros.append((0, 0, {"codigo": layout_reg.codigo, "secuencia": secuencia, "valores": _vals}))
                continue

            if code == "505":
                # El 505 se maneja siempre desde código (ver bloque post-loop).
                continue

            if code == "501":
                registros.append((0, 0, {
                    "codigo": layout_reg.codigo,
                    "secuencia": 1,
                    "valores": self._build_501_valores(layout_reg),
                }))
                continue

            has_partida_source = any(c.source_model == "partida" for c in campos)
            repeat_by_partida = has_partida_source or code in repeat_codes_by_partida

            target_partidas = self.partida_ids.sorted(lambda p: (p.numero_partida or 0, p.id)) if repeat_by_partida else [False]
            if repeat_by_partida and not target_partidas:
                continue

            # Registros opcionales a nivel partida: solo se incluyen si tienen
            # datos más allá de los 4 campos de identificación básicos.
            # Sin esta guardia se generarían p.ej. 552 (vehículos) para
            # partidas que no son automotrices, 553 sin permisos, etc.
            _OPTIONAL_PARTIDA_CODES = {
                "552", "553", "554", "558",   # rectificación opcionales
                "555", "556",                  # cuentas garantía / tasas partida
                "560",                         # partidas industria automotriz
                "351", "352", "353", "355", "358",  # T-MEC complementario
            }
            _PARTIDA_ID_KEYS = {
                "clave_registro", "numero_pedimento",
                "fraccion_arancelaria", "numero_partida",
                "subdivision",
            }

            for secuencia, partida in enumerate(target_partidas, start=1):
                valores = {}
                for campo in campos:
                    val = self._field_value_for_layout(campo, partida=partida)
                    if val is None or val == "" or val is False:
                        if campo.default:
                            val = campo.default
                    val = self._json_safe_layout_value(val)
                    if val not in (None, "", False):
                        valores[campo.nombre] = val

                # Registros 553 y 556 se manejan en auto_multi (una línea por
                # permiso/contribución por partida). Si se dejaran en el loop
                # genérico, los campos de importe siempre harían pasar la guardia
                # opcional aunque no haya datos reales → campos clave vacíos.
                if code in {"553", "556"}:
                    continue

                # Saltar registros opcionales de partida que no tienen datos
                # propios (solo tienen los campos de identificación básicos).
                if code in _OPTIONAL_PARTIDA_CODES:
                    meaningful_keys = set(valores.keys()) - _PARTIDA_ID_KEYS
                    if not meaningful_keys:
                        continue

                if partida:
                    valores["__partida_id"] = partida.id

                registros.append((0, 0, {
                    "codigo": layout_reg.codigo,
                    "secuencia": secuencia,
                    "valores": valores,
                }))

        # ── 505: se inyecta siempre que existan documentos de tipo factura/cove/otro ──
        # (obligatorio para importaciones normales; no se limita a modo contingencia)
        layout_reg_505 = self.layout_id.registro_ids.filtered(
            lambda r: (r.codigo or "").strip() == "505"
        )
        if layout_reg_505:
            layout_reg_505 = layout_reg_505.sorted(lambda r: r.orden or 0)[0]
            docs_505 = self.documento_ids.filtered(
                lambda d: d.tipo in ("factura", "cove", "otro")
                and (d.registro_codigo or "").strip() not in {"514", "510", "557"}
            ).sorted(lambda d: (d.es_documento_principal is not True, d.id))
            for secuencia, documento in enumerate(docs_505, start=1):
                _vals_505 = self._build_505_valores(layout_reg_505, documento)
                _vals_505["__source_id"] = documento.id
                registros.append((0, 0, {
                    "codigo": "505",
                    "secuencia": secuencia,
                    "valores": _vals_505,
                }))

        # Auto-inyección de registros con estructura fija (no dependen del layout).
        is_rectificacion = bool(self.es_rectificacion)
        is_complementario = (self.clave_pedimento or "").strip().upper() == "CT"

        generated_codes = {r[2]["codigo"] for r in registros}

        # Registros con datos múltiples (listas) ─ se inyectan por línea
        auto_multi = [
            ("502", self._get_502_transporte_lines(), self._build_502_valores_direct, True),
            ("503", self._get_503_guia_lines(),       self._build_503_valores_direct, True),
            ("504", self._get_504_contenedor_lines(), self._build_504_valores_direct, True),
            ("553", self._get_553_permiso_lines(),       self._build_553_valores_direct, True),
            ("556", self._get_556_contribucion_lines(),  self._build_556_valores_direct, True),
            ("702", self._get_702_contribucion_lines() if is_rectificacion else [], self._build_702_valores_direct, True),
            ("302", self._get_302_prueba_lines() if is_complementario else [],       self._build_302_valores_direct, True),
        ]
        for auto_code, auto_lines, auto_builder, _multi in auto_multi:
            if auto_code in generated_codes:
                continue
            if allowed is not None and auto_code not in allowed:
                continue
            if not auto_lines:
                continue
            for secuencia, line in enumerate(auto_lines, start=1):
                _vals_multi = auto_builder(line)
                if isinstance(line, dict) and "__source_id" in line:
                    _vals_multi["__source_id"] = line["__source_id"]
                if isinstance(line, dict) and "__partida_id" in line:
                    _vals_multi["__partida_id"] = line["__partida_id"]
                registros.append((0, 0, {
                    "codigo": auto_code,
                    "secuencia": secuencia,
                    "valores": _vals_multi,
                }))

        # Registros de encabezado único (1 por pedimento, condicionados al escenario)
        mov = self._get_tipo_movimiento_effective()
        # 800 (Firma Electrónica) es obligatorio en todos los tipos EXCEPTO:
        #   7 = Despacho Anticipado  (aún no hay firma definitiva)
        #   8 = Confirmación de Pago (el pago confirma sin firma adicional)
        is_despacho_anticipado = mov == "7"
        is_confirmacion_pago = mov == "8"

        auto_single = []
        if is_rectificacion and "701" not in generated_codes:
            if allowed is None or "701" in allowed:
                auto_single.append(("701", self._build_701_valores_direct()))
        if is_complementario and "301" not in generated_codes:
            if allowed is None or "301" in allowed:
                auto_single.append(("301", self._build_301_valores_direct()))
        if not is_despacho_anticipado and not is_confirmacion_pago and "800" not in generated_codes:
            if allowed is None or "800" in allowed:
                auto_single.append(("800", self._build_800_valores_direct()))
        if "801" not in generated_codes:
            if allowed is None or "801" in allowed:
                auto_single.append(("801", self._build_801_valores_direct()))
        for auto_code, valores in auto_single:
            registros.append((0, 0, {
                "codigo": auto_code,
                "secuencia": 1,
                "valores": valores,
            }))

        # ── Post-procesamiento: asignar __sync_key / __sync_origin a cada registro ──
        # Las claves se construyen a partir de metadata temporal (__source_id,
        # __partida_id) inyectada en los valores durante el loop de arriba.
        # Los registros de tipo "tecnico" (509/510/557/514) los maneja
        # _sync_registro_ids_from_tecnicos con su propio sistema de keys.
        TECNICO_CODES = {"509", "510", "557", "514"}
        desired = []
        for cmd in registros:
            # cmd es (0, 0, {codigo, secuencia, valores})
            rec_data = cmd[2]
            code = rec_data["codigo"]
            seq = rec_data["secuencia"]
            vals = dict(rec_data.get("valores") or {})

            if code in TECNICO_CODES:
                # Los técnicos los maneja su propio sync — los excluimos del diff general.
                continue

            source_id = vals.pop("__source_id", None)
            partida_id = vals.pop("__partida_id", None)

            # Construir la sync_key más estable posible:
            if source_id is not None and partida_id is not None:
                # Registro de partida con fuente identificada (ej: 553, 702, 302)
                sync_key = f"{code}:p{partida_id}:id{source_id}"
            elif source_id is not None:
                # Registro de encabezado con fuente identificada (ej: 502, 503, 505)
                sync_key = f"{code}:id{source_id}"
            elif partida_id is not None:
                # Registro de partida sin fuente específica (loop genérico del layout)
                sync_key = f"{code}:p{partida_id}:seq{seq}"
            else:
                # Registro único de encabezado (800, 801, 701, 301, etc.)
                sync_key = f"{code}:seq{seq}"

            vals["__sync_origin"] = "auto"
            vals["__sync_key"] = sync_key

            desired.append({
                "codigo": code,
                "secuencia": seq,
                "key": sync_key,
                "valores": vals,
            })

        self._apply_registro_diff(desired)
        # Auto-poblar contribuciones (Reg. 557) desde tasas de fracciones arancelarias.
        self.with_context(skip_auto_generated_refresh=True).action_generar_contribuciones_557()
        return True

    def _build_502_valores_direct(self, line):
        """Genera el dict de valores para el registro 502 sin depender del layout."""
        return {
            "clave_registro":         "502",
            "numero_pedimento":       self.pedimento_numero or "",
            "rfc_transportista":      line.get("rfc") or "",
            "curp_transportista":     line.get("curp") or "",
            "nombre_transportista":   line.get("nombre") or "",
            "pais_transporte":        line.get("pais") or "",
            "identificador_transporte": line.get("identificador") or "",
            "total_bultos":           str(int(line.get("bultos") or 0)) if (line.get("bultos") or 0) else "",
            "domicilio_transportista": line.get("domicilio") or "",
        }

    def _build_503_valores_direct(self, line):
        """Genera el dict de valores para el registro 503 sin depender del layout."""
        return {
            "clave_registro":   "503",
            "numero_pedimento": self.pedimento_numero or "",
            "guia_manifiesto":  line.get("numero") or "",
            "identificador_guia": line.get("identificador") or "",
        }

    def _build_504_valores_direct(self, line):
        """Genera el dict de valores para el registro 504 sin depender del layout."""
        return {
            "clave_registro":  "504",
            "numero_pedimento": self.pedimento_numero or "",
            "numero_contenedor": line.get("numero") or "",
            "tipo_contenedor":  line.get("tipo") or "",
        }

    # ============================================================
    # 553 – Permisos por partida
    # ============================================================

    def _get_553_permiso_lines(self):
        """Un dict por cada (partida, permiso) — el SAT requiere un 553 por permiso."""
        self.ensure_one()
        lines = []
        for partida in self.partida_ids.sorted(lambda p: (p.numero_partida or 0, p.id)):
            fraccion = (partida.fraccion_arancelaria or "").strip()
            numero_partida = partida.numero_partida or 0
            valor = partida.value_usd or 0.0
            cantidad = partida.cantidad_tarifa or 0.0
            for permiso in partida.permiso_ids:
                lines.append({
                    "fraccion": fraccion,
                    "numero_partida": numero_partida,
                    "clave_permiso": (permiso.code or "").strip(),
                    "valor": valor,
                    "cantidad": cantidad,
                    "__source_id": f"{partida.id}_{permiso.id}",
                })
        return lines

    def _build_553_valores_direct(self, line):
        """Genera el dict de valores para el registro 553 (un permiso por línea)."""
        valor = line.get("valor") or 0.0
        cantidad = line.get("cantidad") or 0.0
        return {
            "clave_registro":             "553",
            "numero_pedimento":           self.pedimento_numero or "",
            "fraccion_arancelaria":       line.get("fraccion") or "",
            "numero_partida":             str(int(line.get("numero_partida") or 0)) if line.get("numero_partida") else "",
            "clave_permiso":              line.get("clave_permiso") or "",
            "valor_comercial_permiso":    str(round(valor, 2)) if valor else "",
            "cantidad_mercancia_permiso": str(round(cantidad, 5)) if cantidad else "",
        }

    # ============================================================
    # 556 – Tasas por Partida
    # ============================================================

    def _get_556_contribucion_lines(self):
        """Un 556 por contribucion por partida, derivado de partida_contribucion_ids (557).
        El 556 es un subconjunto del 557: misma clave y tasa, sin base ni importe.
        Se agrupa por (partida, contribucion) para evitar duplicados si hay varias
        líneas de la misma contribución en una partida.
        """
        self.ensure_one()
        seen = set()
        lines = []
        sorted_contribs = self.partida_contribucion_ids.sorted(
            lambda l: ((l.partida_id.numero_partida or 0) if l.partida_id else 0, l.sequence or 0, l.id)
        )
        for contrib in sorted_contribs:
            partida = contrib.partida_id
            if not partida:
                continue
            fraccion = (partida.fraccion_arancelaria or partida.fraccion_id.code or "").strip()
            numero_partida = partida.numero_partida or 0
            clave = contrib.contribucion_id.code or 0
            key = (numero_partida, clave)
            if key in seen:
                continue
            seen.add(key)
            lines.append({
                "fraccion": fraccion,
                "numero_partida": numero_partida,
                "clave_contribucion": str(clave) if clave else "",
                "tasa": contrib.tasa or 0.0,
                "tipo_tasa": contrib.tipo_tasa or "AD",
            })
        return lines

    def _build_556_valores_direct(self, line):
        """Genera el dict de valores para el registro 556 (una tasa por línea)."""
        tasa = line.get("tasa") or 0.0
        return {
            "clave_registro":    "556",
            "numero_pedimento":  self.pedimento_numero or "",
            "fraccion_arancelaria": line.get("fraccion") or "",
            "numero_partida":    str(int(line.get("numero_partida") or 0)) if line.get("numero_partida") else "",
            "clave_contribucion": line.get("clave_contribucion") or "",
            "tasa":              str(round(tasa, 6)) if tasa is not None else "",
            "tipo_tasa":         line.get("tipo_tasa") or "AD",
        }

    # ============================================================
    # 701 – Rectificación
    # ============================================================

    def _build_701_valores_direct(self, _line=None):
        """Registro 701: encabezado de rectificación. Solo 1 por pedimento."""
        aduana = (
            self.aduana_seccion_despacho_id.code
            or self.aduana_clave
            or ""
        ).strip().upper()[:3]
        aduana_orig = (
            self.rect_aduana_original
            or ""
        ).strip().upper()[:3]
        fecha_pago_str = self.fecha_pago.strftime("%Y%m%d") if self.fecha_pago else ""
        fecha_orig_str = self.rect_fecha_pago_original.strftime("%Y%m%d") if self.rect_fecha_pago_original else ""
        patente = (self.patente or "").strip().zfill(4)[:4]
        patente_orig = (self.rect_patente_original or "").strip().zfill(4)[:4]
        num_ped = (self.pedimento_numero or "").strip()[:7]
        num_ped_orig = (self.rect_pedimento_original or "").strip()[:7]
        clave_rect = (self.clave_pedimento or "").strip().upper()[:2]
        clave_orig = (self.rect_clave_pedimento_original or "").strip().upper()[:2]
        return {
            "clave_registro":            "701",
            "patente":                   patente,
            "numero_pedimento":          num_ped,
            "aduana_despacho":           aduana,
            "clave_pedimento_rectificar": clave_rect,
            "fecha_pago":                fecha_pago_str,
            "pedimento_original":        num_ped_orig,
            "patente_original":          patente_orig,
            "aduana_original":           aduana_orig,
            "clave_pedimento_original":  clave_orig,
            "fecha_operacion_original":  fecha_orig_str,
        }

    # ============================================================
    # 702 – Diferencias de Contribuciones
    # ============================================================

    def _get_702_contribucion_lines(self):
        """Devuelve lista de dicts para los registros 702."""
        return [
            {
                "clave_contribucion": (line.clave_contribucion or "").strip(),
                "clave_forma_pago":   (line.clave_forma_pago or "").strip(),
                "importe_pago":       line.importe_pago or 0.0,
                "__source_id":        line.id,
            }
            for line in self.contribucion_702_ids
            if line.clave_contribucion and line.clave_forma_pago
        ]

    def _build_702_valores_direct(self, line):
        """Registro 702: diferencias de contribución por línea."""
        importe = line.get("importe_pago") or 0.0
        importe_str = "{:.2f}".format(importe).replace(".", "").lstrip("0") or "0"
        return {
            "clave_registro":     "702",
            "numero_pedimento":   (self.pedimento_numero or "").strip()[:7],
            "clave_contribucion": str(line.get("clave_contribucion") or ""),
            "clave_forma_pago":   str(line.get("clave_forma_pago") or ""),
            "importe_pago":       importe_str,
        }

    # ============================================================
    # 301 – Complementario
    # ============================================================

    def _build_301_valores_direct(self, _line=None):
        """Registro 301: encabezado complementario CT. Solo 1 por pedimento."""
        aduana = (
            self.aduana_seccion_despacho_id.code
            or self.aduana_clave
            or ""
        ).strip().upper()[:3]
        exportador = self.exportador_id
        agente = self.lead_id.x_agente_aduanal_id if self.lead_id else False
        tipo_cambio = self.lead_id.x_tipo_cambio if self.lead_id else 0.0
        tipo_cambio_str = "{:.5f}".format(tipo_cambio or 0.0)
        rfc_exp   = ((exportador.vat or "") if exportador else "").strip()[:13]
        curp_exp  = ((exportador.x_curp or "") if exportador else "").strip()[:18]
        nombre_exp = ((exportador.name or "") if exportador else "").strip()[:120]
        curp_age  = (self.curp_agente or "").strip()[:18]
        rfc_agente = ((agente.vat or "") if agente else "").strip()[:13]
        return {
            "clave_registro":   "301",
            "patente":          (self.patente or "").strip().zfill(4)[:4],
            "numero_pedimento": (self.pedimento_numero or "").strip()[:7],
            "aduana_despacho":  aduana,
            "clave_pedimento":  "CT",
            "tipo_cambio":      tipo_cambio_str,
            "rfc_exportador":   rfc_exp,
            "curp_exportador":  curp_exp,
            "nombre_exportador": nombre_exp,
            "curp_agente":      curp_age,
            "rfc_agente_cfdi":  rfc_agente,
        }

    # ============================================================
    # 302 – Prueba Suficiente
    # ============================================================

    def _get_302_prueba_lines(self):
        """Devuelve lista de dicts para los registros 302."""
        lines = []
        for ps in self.prueba_suficiente_302_ids:
            pais_code = ""
            if ps.pais_destino_id:
                pais_code = self._resolve_saai_pais_code(ps.pais_destino_id.country_id) if ps.pais_destino_id.country_id else (ps.pais_destino_id.code or "")
            pais_code = (pais_code or ps.pais_destino or "").strip().upper()[:3]
            fecha_str = ps.fecha_documento.strftime("%Y%m%d") if ps.fecha_documento else ""
            lines.append({
                "pais_destino":    pais_code,
                "pedimento_eua_can": (ps.pedimento_eua_can or "").strip()[:14],
                "prueba_suficiente": ps.prueba_suficiente or "",
                "fecha_documento":  fecha_str,
                "__source_id":      ps.id,
            })
        return lines

    def _build_302_valores_direct(self, line):
        """Registro 302: prueba suficiente por línea."""
        return {
            "clave_registro":     "302",
            "numero_pedimento":   (self.pedimento_numero or "").strip()[:7],
            "pais_destino":       line.get("pais_destino") or "",
            "pedimento_eua_can":  line.get("pedimento_eua_can") or "",
            "prueba_suficiente":  str(line.get("prueba_suficiente") or ""),
            "fecha_documento":    line.get("fecha_documento") or "",
        }

    # ============================================================
    # 800 – Cancelación / Desistimiento
    # ============================================================

    def _build_800_valores_direct(self, _line=None):
        """Registro 800: datos de cancelación o desistimiento (movimientos 2/3)."""
        aduana = (
            self.aduana_seccion_despacho_id.code
            or self.aduana_clave
            or ""
        ).strip().upper()[:3]
        fecha_op_str = self.fecha_operacion.strftime("%Y%m%d") if self.fecha_operacion else ""
        motivo = (self.motivo_cancelacion or "").strip()[:500]
        return {
            "clave_registro":   "800",
            "patente":          (self.patente or "").strip().zfill(4)[:4],
            "numero_pedimento": (self.pedimento_numero or "").strip()[:7],
            "aduana_despacho":  aduana,
            "clave_pedimento":  (self.clave_pedimento or "").strip().upper()[:2],
            "fecha_operacion":  fecha_op_str,
            "motivo":           motivo,
        }

    # ============================================================
    # 801 – Fin de pedimento
    # ============================================================

    def _build_801_valores_direct(self, _line=None):
        """Registro 801: marcador de fin de pedimento (siempre presente)."""
        return {"clave_registro": "801"}

    # ============================================================
    # Wizard Eliminación / Desistimiento
    # ============================================================

    def action_generar_desistimiento(self):
        """Abre el wizard para generar un pedimento de Eliminación (mov. 2)
        o Desistimiento (mov. 3) a partir de este pedimento."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Generar Eliminación / Desistimiento"),
            "res_model": "mx.ped.desistimiento.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_operacion_id": self.id},
        }


class MxPedOperacionObservacion(models.Model):
    _name = "mx.ped.operacion.observacion"
    _description = "Operacion - Observacion 511"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    texto = fields.Char(string="Observacion", required=True, size=120)

    @api.constrains("texto")
    def _check_texto(self):
        for rec in self:
            clean = rec.operacion_id._sanitize_511_text(rec.texto)
            if not clean:
                raise ValidationError(_("La observacion 511 no puede quedar vacia."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res


class MxPedOperacionDescargo(models.Model):
    _name = "mx.ped.operacion.descargo"
    _description = "Operacion - Descargo 512"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    patente_original = fields.Char(string="Patente original", required=True, size=4)
    pedimento_original = fields.Char(string="Pedimento original", required=True, size=7)
    aduana_seccion_original_id = fields.Many2one("mx.ped.aduana.seccion", string="Aduana-seccion original", required=True)
    aduana_seccion_original = fields.Char(string="Aduana-seccion original (codigo)", related="aduana_seccion_original_id.code", store=True, readonly=True)
    clave_documento_original_id = fields.Many2one("mx.ped.clave", string="Clave documento original", required=True)
    clave_documento_original = fields.Char(string="Clave documento original (codigo)", related="clave_documento_original_id.code", store=True, readonly=True)
    fecha_operacion_original = fields.Date(string="Fecha operacion original", required=True)
    fraccion_original_id = fields.Many2one("mx.tigie.maestra", string="Fraccion original")
    fraccion_original = fields.Char(string="Fraccion original (codigo)", related="fraccion_original_id.code", store=True, readonly=True)
    unidad_medida_original_id = fields.Many2one("mx.ped.um", string="Unidad medida original")
    unidad_medida_original_code = fields.Char(string="Unidad medida original (codigo)", related="unidad_medida_original_id.code", store=True, readonly=True)
    cantidad_umt_original = fields.Float(string="Cantidad UMT original", digits=(16, 5), required=True)

    @api.constrains(
        "patente_original",
        "pedimento_original",
        "aduana_seccion_original_id",
        "clave_documento_original_id",
        "fecha_operacion_original",
        "cantidad_umt_original",
    )
    def _check_required_512_fields(self):
        for rec in self:
            if not rec.operacion_id.show_descargo_ui:
                continue
            patente = rec.operacion_id._sanitize_512_patente(rec.patente_original)
            pedimento = rec.operacion_id._sanitize_512_pedimento(rec.pedimento_original)
            if len(patente) != 4:
                raise ValidationError(_("La patente original del 512 debe tener 4 digitos."))
            if len(pedimento) != 7:
                raise ValidationError(_("El pedimento original del 512 debe tener 7 digitos."))
            if not rec.fecha_operacion_original:
                raise ValidationError(_("La fecha de la operacion original del 512 es obligatoria."))
            if rec.cantidad_umt_original in (False, None):
                raise ValidationError(_("La cantidad UMT original del 512 es obligatoria."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res


class MxPedOperacionCompensacion(models.Model):
    _name = "mx.ped.operacion.compensacion"
    _description = "Operacion - Compensacion 513"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    patente_original = fields.Char(string="Patente original", required=True, size=4)
    pedimento_original = fields.Char(string="Pedimento original", required=True, size=7)
    aduana_seccion_original_id = fields.Many2one("mx.ped.aduana.seccion", string="Aduana-seccion original", required=True)
    aduana_seccion_original = fields.Char(string="Aduana-seccion original (codigo)", related="aduana_seccion_original_id.code", store=True, readonly=True)
    fecha_pago_original = fields.Date(string="Fecha de pago original", required=True)
    contribucion_compensada_id = fields.Many2one(
        "aduana.catalogo.contribucion",
        string="Contribucion compensada",
        required=True,
        ondelete="restrict",
    )
    importe_compensado = fields.Float(string="Importe compensado", digits=(16, 2), required=True)

    @api.constrains(
        "patente_original",
        "pedimento_original",
        "aduana_seccion_original_id",
        "fecha_pago_original",
        "contribucion_compensada_id",
        "importe_compensado",
    )
    def _check_required_fields_compensacion(self):
        for rec in self:
            if not rec.operacion_id._has_forma_pago_code("12"):
                raise ValidationError(_("513 solo aplica cuando existe forma de pago 12 en la operacion."))
            if not rec.patente_original or len(re.sub(r"\D+", "", rec.patente_original)) != 4:
                raise ValidationError(_("513: la patente original debe tener 4 digitos."))
            if not rec.pedimento_original or len(re.sub(r"\D+", "", rec.pedimento_original)) != 7:
                raise ValidationError(_("513: el pedimento original debe tener 7 digitos."))
            if not rec.aduana_seccion_original_id:
                raise ValidationError(_("513: la aduana-seccion original es obligatoria."))
            if not rec.fecha_pago_original:
                raise ValidationError(_("513: la fecha de pago original es obligatoria."))
            if not rec.contribucion_compensada_id:
                raise ValidationError(_("513: la contribucion compensada es obligatoria."))
            if not rec.importe_compensado or rec.importe_compensado <= 0:
                raise ValidationError(_("513: el importe compensado debe ser mayor a cero."))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res


class MxPedOperacionContribucion(models.Model):
    """Diferencias de contribuciones – Registro 702 (Rectificación)."""

    _name = "mx.ped.operacion.contribucion"
    _description = "Operacion - Diferencias contribuciones 702"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    contribucion_id = fields.Many2one(
        "aduana.catalogo.contribucion",
        string="Contribución",
        ondelete="restrict",
    )
    clave_contribucion = fields.Char(
        string="Clave contribución",
        size=2,
        required=True,
        help="Clave numérica 2 dígitos (ej. 1=IGI/IGE, 2=IVA, 3=IEPS).",
    )
    clave_forma_pago = fields.Char(
        string="Clave forma de pago",
        size=3,
        required=True,
        help="Clave numérica 3 dígitos según Apéndice 13 Anexo 22.",
    )
    importe_pago = fields.Float(string="Importe de pago", digits=(16, 2), required=True)

    @api.onchange("contribucion_id")
    def _onchange_contribucion_id(self):
        for rec in self:
            if rec.contribucion_id and rec.contribucion_id.contribucion:
                rec.clave_contribucion = rec.contribucion_id.contribucion

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res


class MxPedOperacionPruebaSuficiente(models.Model):
    """Prueba Suficiente – Registro 302 (Complementario CT)."""

    _name = "mx.ped.operacion.prueba.suficiente"
    _description = "Operacion - Prueba suficiente 302"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(string="Secuencia", default=10)
    pais_destino_id = fields.Many2one(
        "aduana.catalogo.pais",
        string="País destino",
        ondelete="restrict",
        help="País destino según Apéndice 4 Anexo 22.",
    )
    pais_destino = fields.Char(
        string="Clave país destino (3 dig.)",
        size=3,
        help="Se llena automáticamente desde el catálogo, o se captura manualmente.",
    )
    pedimento_eua_can = fields.Char(
        string="Pedimento EUA/CAN",
        size=14,
        help="Número de pedimento de importación en EUA o Canadá.",
    )
    prueba_suficiente = fields.Selection(
        selection=[
            ("1", "1 – Factura comercial"),
            ("2", "2 – Factura certificada"),
            ("3", "3 – Carta declaración"),
            ("4", "4 – Otros documentos"),
            ("5", "5 – Factura partes interrelacionadas"),
        ],
        string="Prueba suficiente",
        required=True,
    )
    fecha_documento = fields.Date(string="Fecha del documento", required=True)

    @api.onchange("pais_destino_id")
    def _onchange_pais_destino_id(self):
        for rec in self:
            if rec.pais_destino_id:
                rec.pais_destino = rec.pais_destino_id.code or ""

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res

