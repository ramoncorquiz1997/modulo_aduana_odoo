# -*- coding: utf-8 -*-
"""
Manifestación de Valor (MV) — Formato E2 (2025/2026)

Estructura de modelos:
  mx.ped.mv                  — Cabecera de la MV (1 por pedimento de importación)
  mx.ped.mv.persona.consulta — Personas autorizadas a consultar la MV en VUCEM
  mx.ped.mv.cove             — Puente MV ↔ mx.cove; contiene datos de valoración del COVE
  mx.ped.mv.precio.pagado    — Precio efectivamente pagado (≥0 por COVE)
  mx.ped.mv.precio.por.pagar — Precio por pagar / a crédito (≥0 por COVE)
  mx.ped.mv.compenso.pago    — Compensación de pago (≥0 por COVE)
  mx.ped.mv.incrementable    — Incrementables al valor en aduana (≥0 por COVE)
  mx.ped.mv.decrementable    — Decrementables al valor en aduana (≥0 por COVE)

Referencia normativa:
  IngresoManifestacionService.xsd (VUCEM 2025)
  ConsultaManifestacionService.xsd (VUCEM 2025)
  Diccionario_de_datos_MV_2025.pdf
  Catálogos_Manifestación de Valor 2025.xlsx

Webservices de producción:
  Registro : https://privados.ventanillaunica.gob.mx:8106/IngresoManifestacionImpl/IngresoManifestacionService
  Consulta : https://privados.ventanillaunica.gob.mx/ConsultaManifestacionImpl/ConsultaManifestacionService
"""
import base64
import logging
from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ── Catálogos inline (fuente: Catálogos MV 2025.xlsx) ────────────────────────

FORMAS_PAGO = [
    ("FORPAG.TE",  "Transferencia electrónica"),
    ("FORPAG.LC",  "Letra de crédito"),
    ("FORPAG.CO",  "Compensación"),
    ("FORPAG.OT",  "Otra forma de pago"),
]

METODOS_VALORACION = [
    ("VALADU.VPV",  "Valor de transacción de las mercancías importadas"),
    ("VALADU.VTM",  "Valor de transacción de mercancías idénticas"),
    ("VALADU.VTS",  "Valor de transacción de mercancías similares"),
    ("VALADU.VDR",  "Valor deductivo"),
    ("VALADU.VRC",  "Valor reconstruido"),
    ("VALADU.VUA",  "Último recurso"),
]

TIPOS_INCREMENTABLE = [
    ("INCRE.CG",  "Comisiones y gastos de corretaje"),
    ("INCRE.EN",  "Envases y embalajes"),
    ("INCRE.MA",  "Materiales, componentes, herramientas e insumos"),
    ("INCRE.CG2", "Cánones y derechos de licencia"),
    ("INCRE.RP",  "Reversa de procedencia de la reventa"),
    ("INCRE.FG",  "Fletes y gastos de carga y descarga"),
    ("INCRE.SE",  "Seguros"),
    ("INCRE.OT",  "Otros gastos de transporte"),
    ("INCRE.AS",  "Asistencia técnica"),
    ("INCRE.MA2", "Materiales de embalaje o envase"),
]

TIPOS_DECREMENTABLE = [
    ("DECRE.GT",  "Gastos de transporte después de la importación"),
    ("DECRE.DE",  "Derechos de importación"),
    ("DECRE.GC",  "Gastos de construcción, instalación, montaje, mantenimiento o asistencia técnica"),
    ("DECRE.UT",  "Utilidades y gastos generales"),
    ("DECRE.IC",  "Intereses y costos financieros"),
    ("DECRE.SB",  "Subvenciones"),
]

TIPOS_FIGURA = [
    ("TIPFIG.IMP", "Importador"),
    ("TIPFIG.AGE", "Agente aduanal"),
    ("TIPFIG.APD", "Apoderado aduanal"),
    ("TIPFIG.REP", "Representante legal"),
]

INCOTERMS = [
    ("TIPINC.EXW", "EXW — Ex Works"),
    ("TIPINC.FCA", "FCA — Free Carrier"),
    ("TIPINC.FAS", "FAS — Free Alongside Ship"),
    ("TIPINC.FOB", "FOB — Free On Board"),
    ("TIPINC.CFR", "CFR — Cost and Freight"),
    ("TIPINC.CIF", "CIF — Cost, Insurance and Freight"),
    ("TIPINC.CPT", "CPT — Carriage Paid To"),
    ("TIPINC.CIP", "CIP — Carriage and Insurance Paid To"),
    ("TIPINC.DPU", "DPU — Delivered at Place Unloaded"),
    ("TIPINC.DAP", "DAP — Delivered at Place"),
    ("TIPINC.DDP", "DDP — Delivered Duty Paid"),
    ("TIPINC.DAT", "DAT — Delivered at Terminal"),
    ("TIPINC.DAF", "DAF — Delivered at Frontier"),
    ("TIPINC.DES", "DES — Delivered Ex Ship"),
    ("TIPINC.DEQ", "DEQ — Delivered Ex Quay"),
    ("TIPINC.DDU", "DDU — Delivered Duty Unpaid"),
]


# Mapeo incoterm operación/COVE (ej. "FOB") → clave VUCEM MV (ej. "TIPINC.FOB")
_INCOTERM_MAP = {
    "EXW": "TIPINC.EXW",
    "FCA": "TIPINC.FCA",
    "FAS": "TIPINC.FAS",
    "FOB": "TIPINC.FOB",
    "CFR": "TIPINC.CFR",
    "CIF": "TIPINC.CIF",
    "CPT": "TIPINC.CPT",
    "CIP": "TIPINC.CIP",
    "DPU": "TIPINC.DPU",
    "DAP": "TIPINC.DAP",
    "DDP": "TIPINC.DDP",
    "DAT": "TIPINC.DAT",
    "DAF": "TIPINC.DAF",
    "DES": "TIPINC.DES",
    "DEQ": "TIPINC.DEQ",
    "DDU": "TIPINC.DDU",
}


def _to_tipinc(plain_code):
    """Convierte 'FOB' → 'TIPINC.FOB'. Devuelve False si no hay mapeo."""
    return _INCOTERM_MAP.get((plain_code or "").upper(), False)


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv  —  Cabecera de la Manifestación de Valor
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMv(models.Model):
    """Manifestación de Valor (MV) ligada a una operación de importación."""

    _name = "mx.ped.mv"
    _description = "Manifestación de Valor"
    _inherit = ["mx.firma.digital"]
    _order = "operacion_id desc, id desc"
    _rec_name = "numero_mv"

    # ── Relación con la operación ─────────────────────────────────────────────
    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Operación",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="operacion_id.company_id",
        store=True,
        index=True,
    )

    # ── Identificadores VUCEM ─────────────────────────────────────────────────
    numero_mv = fields.Char(
        string="Número MV (VUCEM)",
        readonly=True,
        copy=False,
        index=True,
        help="Número de operación devuelto por VUCEM al registrar la MV (Long → Char).",
    )
    e_document_mv = fields.Char(
        string="e-Document MV",
        readonly=True,
        copy=False,
        help="Folio asignado por VUCEM (ej. MNVA250002S37).",
    )

    # ── Importador / exportador ───────────────────────────────────────────────
    rfc_importador = fields.Char(
        string="RFC Importador",
        required=True,
        size=13,
        help="RFC de la empresa importadora / exportadora.",
    )

    # ── Estatus local ─────────────────────────────────────────────────────────
    estatus = fields.Selection(
        [
            ("borrador",   "Borrador"),
            ("firmada",    "Firmada (pendiente envío)"),
            ("enviada",    "Enviada a VUCEM"),
            ("registrada", "Registrada en VUCEM"),
            ("error",      "Error VUCEM"),
        ],
        string="Estatus",
        default="borrador",
        required=True,
        copy=False,
        index=True,
    )
    estatus_vucem = fields.Char(
        string="Estatus VUCEM",
        readonly=True,
        copy=False,
        help="Valor textual devuelto por ConsultaManifestacion.",
    )

    # ── Totales (valor en aduana) — calculados automáticamente desde las líneas ─
    # [AUTO #4] Computed desde precio_pagado_ids / incrementable_ids de todos los COVEs.
    # store=True para que queden guardados y sean exportables al XML sin recalcular.
    # El usuario puede corregirlos manualmente si hay conversiones de moneda pendientes.
    total_precio_pagado = fields.Float(
        string="Total precio pagado",
        digits=(19, 3),
        compute="_compute_totales",
        store=True,
        readonly=False,
        help="Suma automática de todos los Precios Pagados de los COVEs de esta MV.",
    )
    total_precio_por_pagar = fields.Float(
        string="Total precio por pagar",
        digits=(19, 3),
        compute="_compute_totales",
        store=True,
        readonly=False,
        help="Suma automática de todos los Precios por Pagar de los COVEs.",
    )
    total_incrementables = fields.Float(
        string="Total incrementables",
        digits=(19, 3),
        compute="_compute_totales",
        store=True,
        readonly=False,
        help="Suma automática de todos los importes Incrementables de los COVEs.",
    )
    total_decrementables = fields.Float(
        string="Total decrementables",
        digits=(19, 3),
        compute="_compute_totales",
        store=True,
        readonly=False,
        help="Suma automática de todos los importes Decrementables de los COVEs.",
    )
    total_valor_aduana = fields.Float(
        string="Total valor en aduana",
        digits=(19, 3),
        compute="_compute_totales",
        store=True,
        readonly=False,
        help="PP + PPP + Incrementables − Decrementables. Editable si hay conversión de moneda.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="operacion_id.currency_id",
        store=True,
    )
    aviso_multicurrency = fields.Char(
        string="Aviso monedas",
        compute="_compute_totales",
        store=False,
        readonly=True,
        help="Se muestra cuando los COVEs tienen precios en más de una moneda.",
    )

    # ── Firma electrónica (SHA256withRSA) ─────────────────────────────────────
    certificado_b64 = fields.Text(
        string="Certificado (base64)",
        readonly=True,
        copy=False,
        groups="base.group_system",
    )
    cadena_original = fields.Text(
        string="Cadena original",
        readonly=True,
        copy=False,
    )
    firma_b64 = fields.Text(
        string="Firma (base64)",
        readonly=True,
        copy=False,
        groups="base.group_system",
    )

    # ── Credencial y logs ─────────────────────────────────────────────────────
    credencial_id = fields.Many2one(
        "mx.ped.credencial.ws",
        string="Credencial WS",
        ondelete="set null",
    )
    log_ids = fields.One2many(
        "mx.vucem.log",
        "mv_id",
        string="Logs VUCEM",
        copy=False,
    )

    # ── Personas consulta y COVEs ─────────────────────────────────────────────
    persona_consulta_ids = fields.One2many(
        "mx.ped.mv.persona.consulta",
        "mv_id",
        string="Personas consulta",
        copy=True,
    )
    cove_line_ids = fields.One2many(
        "mx.ped.mv.cove",
        "mv_id",
        string="COVEs",
        copy=True,
    )

    # ── Metadatos ─────────────────────────────────────────────────────────────
    fecha_envio = fields.Datetime(string="Fecha envío", readonly=True, copy=False)
    fecha_registro = fields.Datetime(string="Fecha registro VUCEM", readonly=True, copy=False)
    notes = fields.Text(string="Notas")

    # ── Cómputos auxiliares ───────────────────────────────────────────────────
    cove_count = fields.Integer(
        string="# COVEs",
        compute="_compute_cove_count",
    )
    log_count = fields.Integer(
        string="# Logs",
        compute="_compute_log_count",
    )

    @api.depends("cove_line_ids")
    def _compute_cove_count(self):
        for rec in self:
            rec.cove_count = len(rec.cove_line_ids)

    @api.depends("log_ids")
    def _compute_log_count(self):
        for rec in self:
            rec.log_count = len(rec.log_ids)

    # [AUTO #4] Totales computados desde las líneas hijas
    # Cada importe se convierte a MXN usando su tipo_cambio:
    #   MXN = importe × tipo_cambio  (estándar SAT: tipo_cambio = MXN por 1 unidad extranjera)
    # Si todos los registros son en MXN (tipo_cambio = 1.0) el resultado es idéntico al anterior.
    @api.depends(
        "cove_line_ids.precio_pagado_ids.total",
        "cove_line_ids.precio_pagado_ids.tipo_cambio",
        "cove_line_ids.precio_pagado_ids.tipo_moneda",
        "cove_line_ids.precio_por_pagar_ids.total",
        "cove_line_ids.precio_por_pagar_ids.tipo_cambio",
        "cove_line_ids.precio_por_pagar_ids.tipo_moneda",
        "cove_line_ids.incrementable_ids.importe",
        "cove_line_ids.incrementable_ids.tipo_cambio",
        "cove_line_ids.incrementable_ids.tipo_moneda",
        "cove_line_ids.decrementable_ids.importe",
        "cove_line_ids.decrementable_ids.tipo_cambio",
        "cove_line_ids.decrementable_ids.tipo_moneda",
    )
    def _compute_totales(self):
        for rec in self:
            monedas = set()

            def _to_mxn(importe, linea):
                """Convierte importe a MXN usando tipo_cambio de la línea."""
                tc = getattr(linea, "tipo_cambio", 1.0) or 1.0
                mon = getattr(linea, "tipo_moneda", "MXN") or "MXN"
                monedas.add(mon)
                return importe * tc

            pp  = sum(_to_mxn(p.total,   p) for cl in rec.cove_line_ids for p in cl.precio_pagado_ids)
            ppp = sum(_to_mxn(p.total,   p) for cl in rec.cove_line_ids for p in cl.precio_por_pagar_ids)
            inc = sum(_to_mxn(i.importe, i) for cl in rec.cove_line_ids for i in cl.incrementable_ids)
            dec = sum(_to_mxn(d.importe, d) for cl in rec.cove_line_ids for d in cl.decrementable_ids)

            rec.total_precio_pagado    = pp
            rec.total_precio_por_pagar = ppp
            rec.total_incrementables   = inc
            rec.total_decrementables   = dec
            rec.total_valor_aduana     = pp + ppp + inc - dec

            # Aviso si hay más de una moneda extranjera (excluyendo MXN puro)
            monedas_ext = monedas - {"MXN"}
            if len(monedas_ext) > 1:
                rec.aviso_multicurrency = (
                    f"⚠️ Múltiples monedas detectadas: {', '.join(sorted(monedas_ext))}. "
                    "Verifica los tipos de cambio antes de firmar."
                )
            else:
                rec.aviso_multicurrency = False

    # [AUTO #1 #2 #3] onchange de operacion_id — pre-llena RFC, credencial y COVEs
    @api.onchange("operacion_id")
    def _onchange_operacion_id(self):
        if not self.operacion_id:
            return
        op = self.operacion_id

        # AUTO #1 — RFC importador desde el partner importador de la operación
        if not self.rfc_importador:
            rfc = (
                op.participante_rfc
                or (op.importador_id.vat if op.importador_id else "")
            )
            self.rfc_importador = (rfc or "").upper().strip()

        # AUTO #2 — Credencial WS desde la operación
        if not self.credencial_id and op.ws_credencial_id:
            self.credencial_id = op.ws_credencial_id

        # AUTO #3 — Pre-cargar líneas COVE desde la operación
        # Solo si la MV no tiene COVEs aún (evitar sobreescribir si ya capturó algo)
        if not self.cove_line_ids:
            self._cargar_coves_desde_operacion()

    def _cargar_coves_desde_operacion(self):
        """Crea las líneas mx.ped.mv.cove a partir de los COVEs de la operación."""
        if not self.operacion_id:
            return
        # Fallback: incoterm a nivel operación (por si el COVE no tiene uno propio)
        op_incoterm_mv = _to_tipinc(self.operacion_id.incoterm)

        nuevas_lineas = []
        for cove in self.operacion_id.cove_ids:
            # Usar el incoterm propio del COVE; si no tiene, heredar de la operación
            incoterm_mv = _to_tipinc(cove.incoterm) or op_incoterm_mv or False
            nuevas_lineas.append((0, 0, {
                "cove_id": cove.id,
                "incoterm": incoterm_mv,            # AUTO #5 — por COVE
                "existe_vinculacion": False,
                "metodo_valoracion": "VALADU.VPV",  # default más común
            }))
        if nuevas_lineas:
            self.cove_line_ids = nuevas_lineas

    def action_cargar_coves(self):
        """Botón manual: recarga las líneas COVE desde la operación (descarta las existentes)."""
        self.ensure_one()
        if self.estatus != "borrador":
            raise UserError("Solo se pueden recargar los COVEs en estado Borrador.")
        self.cove_line_ids = [(5, 0, 0)]  # borrar existentes
        self._cargar_coves_desde_operacion()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "COVEs cargados",
                "message": f"Se pre-cargaron {len(self.cove_line_ids)} COVE(s) desde la operación.",
                "type": "success",
            },
        }

    # ── Acciones de botón ─────────────────────────────────────────────────────

    def action_firmar(self):
        """Genera cadena original y firma la MV con la e.firma del importador."""
        self.ensure_one()
        if self.estatus != "borrador":
            raise UserError("Solo se puede firmar una MV en estado Borrador.")
        if not self.credencial_id:
            raise UserError("Selecciona una Credencial WS antes de firmar.")
        if not self.cove_line_ids:
            raise UserError("Agrega al menos un COVE a la MV antes de firmar.")

        resultado = self._firmar_mv(self, self.credencial_id)
        self.write({
            "certificado_b64": resultado["certificado_b64"],
            "cadena_original": resultado["cadena_original"],
            "firma_b64": resultado["firma_b64"],
            "estatus": "firmada",
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "MV firmada",
                "message": "La cadena original y firma se generaron correctamente.",
                "type": "success",
            },
        }

    def action_enviar_vucem(self):
        """Transmite la MV al webservice de VUCEM (registroManifestacion)."""
        self.ensure_one()
        if self.estatus not in ("firmada", "error"):
            raise UserError("La MV debe estar Firmada para poder enviarse.")
        self._ws_registrar_mv()

    def action_consultar_vucem(self):
        """Consulta el estatus de la MV en VUCEM (consultaManifestacion)."""
        self.ensure_one()
        if not self.numero_mv:
            raise UserError("La MV aún no tiene Número de Operación VUCEM.")
        self._ws_consultar_mv()

    def action_actualizar_mv(self):
        """Permite agregar e-Documents / RFCs consulta a una MV ya registrada."""
        self.ensure_one()
        if not self.numero_mv:
            raise UserError("La MV aún no tiene Número de Operación VUCEM.")
        self._ws_actualizar_mv()

    def action_view_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Logs VUCEM — MV",
            "res_model": "mx.vucem.log",
            "view_mode": "list,form",
            "domain": [("mv_id", "=", self.id)],
            "context": {"default_mv_id": self.id},
        }

    # ── Webservices VUCEM ─────────────────────────────────────────────────────

    def _get_ws_credencial(self):
        """Devuelve la credencial WS activa para esta MV."""
        self.ensure_one()
        cred = self.credencial_id
        if not cred:
            raise UserError("Configura una Credencial WS en la MV antes de transmitir.")
        return cred

    def _build_soap_registro(self):
        """Construye el XML SOAP para registroManifestacion."""
        self.ensure_one()
        cred = self._get_ws_credencial()

        from xml.etree.ElementTree import Element, SubElement, tostring
        import xml.etree.ElementTree as ET

        NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
        NS_WS   = "http://ws.ingresomanifestacion.manifestacion.www.ventanillaunica.gob.mx"
        NS_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
        NS_WSU  = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
        PW_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText"

        ET.register_namespace("soapenv", NS_SOAP)
        ET.register_namespace("ws", NS_WS)
        ET.register_namespace("wsse", NS_WSSE)
        ET.register_namespace("wsu", NS_WSU)

        now_utc = datetime.now(timezone.utc)
        created = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        expires = now_utc.strftime("%Y-%m-%dT23:59:59Z")

        envelope = Element(f"{{{NS_SOAP}}}Envelope")

        # ── Header / WS-Security ─────────────────────────────────────────────
        header = SubElement(envelope, f"{{{NS_SOAP}}}Header")
        security = SubElement(header, f"{{{NS_WSSE}}}Security")
        token = SubElement(security, f"{{{NS_WSSE}}}UsernameToken")
        SubElement(token, f"{{{NS_WSSE}}}Username").text = cred.ws_username or ""
        pw_el = SubElement(token, f"{{{NS_WSSE}}}Password")
        pw_el.set("Type", PW_TYPE)
        pw_el.text = cred.ws_password or ""
        ts = SubElement(security, f"{{{NS_WSU}}}Timestamp")
        SubElement(ts, f"{{{NS_WSU}}}Created").text = created
        SubElement(ts, f"{{{NS_WSU}}}Expires").text = expires

        # ── Body ─────────────────────────────────────────────────────────────
        body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
        reg = SubElement(body, f"{{{NS_WS}}}registroManifestacion")
        info = SubElement(reg, "informacionManifestacion")

        # firmaElectronica
        firma_el = SubElement(info, "firmaElectronica")
        SubElement(firma_el, "certificado").text = self.certificado_b64 or ""
        SubElement(firma_el, "cadenaOriginal").text = self.cadena_original or ""
        SubElement(firma_el, "firma").text = self.firma_b64 or ""

        # importador-exportador
        imp = SubElement(info, "importador-exportador")
        SubElement(imp, "rfc").text = self.rfc_importador or ""

        # datosManifestacionValor
        datos = SubElement(info, "datosManifestacionValor")

        # personasConsulta
        for pc in self.persona_consulta_ids:
            pc_el = SubElement(datos, "personaConsulta")
            SubElement(pc_el, "rfc").text = pc.rfc or ""
            SubElement(pc_el, "tipoFigura").text = pc.tipo_figura or ""

        # documentos (e-Documents de todos los COVEs)
        for cove_line in self.cove_line_ids:
            if cove_line.cove_id and cove_line.cove_id.e_document:
                doc_el = SubElement(datos, "documentos")
                SubElement(doc_el, "eDocument").text = cove_line.cove_id.e_document

        # informacionCove (uno por línea)
        for cove_line in self.cove_line_ids:
            self._xml_info_cove(datos, cove_line)

        # valorEnAduana
        vea = SubElement(datos, "valorEnAduana")
        SubElement(vea, "totalPrecioPagado").text = self._fmt_decimal(self.total_precio_pagado)
        SubElement(vea, "totalPrecioPorPagar").text = self._fmt_decimal(self.total_precio_por_pagar)
        SubElement(vea, "totalIncrementables").text = self._fmt_decimal(self.total_incrementables)
        SubElement(vea, "totalDecrementables").text = self._fmt_decimal(self.total_decrementables)
        SubElement(vea, "totalValorAduana").text = self._fmt_decimal(self.total_valor_aduana)

        xml_bytes = tostring(envelope, encoding="unicode", xml_declaration=False)
        return '<?xml version="1.0" encoding="utf-8"?>' + xml_bytes

    @staticmethod
    def _fmt_decimal(value):
        """Formatea decimal con 3 decimales mínimos para el XML."""
        if value is None or value is False:
            return "0.000"
        return f"{float(value):.3f}"

    @staticmethod
    def _fmt_datetime(dt_value):
        """Convierte un campo Datetime de Odoo a formato xsd:dateTime UTC."""
        if not dt_value:
            return ""
        if isinstance(dt_value, str):
            return dt_value
        return dt_value.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _xml_info_cove(self, parent, cove_line):
        """Agrega un nodo <informacionCove> al elemento parent."""
        from xml.etree.ElementTree import SubElement

        ic = SubElement(parent, "informacionCove")
        SubElement(ic, "cove").text = cove_line.cove_id.e_document if cove_line.cove_id else ""
        SubElement(ic, "incoterm").text = cove_line.incoterm or ""
        SubElement(ic, "existeVinculacion").text = "1" if cove_line.existe_vinculacion else "0"

        # pedimentos
        for ped in cove_line.pedimento_ids:
            ped_el = SubElement(ic, "pedimento")
            SubElement(ped_el, "pedimento").text = ped.numero_pedimento or ""
            SubElement(ped_el, "patente").text = ped.patente or ""
            SubElement(ped_el, "aduana").text = ped.aduana or ""

        # precioPagado
        for pp in cove_line.precio_pagado_ids:
            pp_el = SubElement(ic, "precioPagado")
            SubElement(pp_el, "fechaPago").text = self._fmt_datetime(pp.fecha_pago)
            SubElement(pp_el, "total").text = self._fmt_decimal(pp.total)
            SubElement(pp_el, "tipoPago").text = pp.tipo_pago or ""
            if pp.especifique:
                SubElement(pp_el, "especifique").text = pp.especifique
            SubElement(pp_el, "tipoMoneda").text = pp.tipo_moneda or ""
            SubElement(pp_el, "tipoCambio").text = self._fmt_decimal(pp.tipo_cambio)

        # precioPorPagar
        for ppp in cove_line.precio_por_pagar_ids:
            ppp_el = SubElement(ic, "precioPorPagar")
            SubElement(ppp_el, "fechaPago").text = self._fmt_datetime(ppp.fecha_pago)
            SubElement(ppp_el, "total").text = self._fmt_decimal(ppp.total)
            if ppp.situacion_no_fecha_pago:
                SubElement(ppp_el, "situacionNofechaPago").text = ppp.situacion_no_fecha_pago
            SubElement(ppp_el, "tipoPago").text = ppp.tipo_pago or ""
            if ppp.especifique:
                SubElement(ppp_el, "especifique").text = ppp.especifique
            SubElement(ppp_el, "tipoMoneda").text = ppp.tipo_moneda or ""
            SubElement(ppp_el, "tipoCambio").text = self._fmt_decimal(ppp.tipo_cambio)

        # compensoPago
        for cp in cove_line.compenso_pago_ids:
            cp_el = SubElement(ic, "compensoPago")
            SubElement(cp_el, "tipoPago").text = cp.tipo_pago or ""
            SubElement(cp_el, "fecha").text = self._fmt_datetime(cp.fecha)
            SubElement(cp_el, "motivo").text = cp.motivo or ""
            SubElement(cp_el, "prestacionMercancia").text = cp.prestacion_mercancia or ""
            if cp.especifique:
                SubElement(cp_el, "especifique").text = cp.especifique

        SubElement(ic, "metodoValoracion").text = cove_line.metodo_valoracion or ""

        # incrementables
        for inc in cove_line.incrementable_ids:
            inc_el = SubElement(ic, "incrementables")
            SubElement(inc_el, "tipoIncrementable").text = inc.tipo_incrementable or ""
            SubElement(inc_el, "fechaErogacion").text = self._fmt_datetime(inc.fecha_erogacion)
            SubElement(inc_el, "importe").text = self._fmt_decimal(inc.importe)
            SubElement(inc_el, "tipoMoneda").text = inc.tipo_moneda or ""
            SubElement(inc_el, "tipoCambio").text = self._fmt_decimal(inc.tipo_cambio)
            SubElement(inc_el, "aCargoImportador").text = "1" if inc.a_cargo_importador else "0"

        # decrementables
        for dec in cove_line.decrementable_ids:
            dec_el = SubElement(ic, "decrementables")
            SubElement(dec_el, "tipoDecrementable").text = dec.tipo_decrementable or ""
            SubElement(dec_el, "fechaErogacion").text = self._fmt_datetime(dec.fecha_erogacion)
            SubElement(dec_el, "importe").text = self._fmt_decimal(dec.importe)
            SubElement(dec_el, "tipoMoneda").text = dec.tipo_moneda or ""
            SubElement(dec_el, "tipoCambio").text = self._fmt_decimal(dec.tipo_cambio)

    def _ws_registrar_mv(self):
        """Llama al WS registroManifestacion y procesa la respuesta."""
        self.ensure_one()
        import time
        try:
            import requests as req_lib
        except ImportError as exc:
            raise UserError("La librería 'requests' no está disponible.") from exc

        cred = self._get_ws_credencial()
        endpoint = (
            cred.endpoint_mv_registro
            or "https://privados.ventanillaunica.gob.mx:8106/IngresoManifestacionImpl/IngresoManifestacionService"
        )
        xml_body = self._build_soap_registro()

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '""',
        }

        t0 = time.time()
        try:
            resp = req_lib.post(endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=60)
            duracion_ms = int((time.time() - t0) * 1000)
        except Exception as exc:
            self._log_mv_error("error_red", str(exc), xml_body, "")
            raise UserError(f"Error de red al conectar con VUCEM: {exc}") from exc

        xml_resp = resp.text or ""
        duracion_ms = int((time.time() - t0) * 1000)

        if resp.status_code >= 400:
            self._log_mv_error("error_vucem", f"HTTP {resp.status_code}", xml_body, xml_resp, duracion_ms)
            raise UserError(f"VUCEM devolvió HTTP {resp.status_code}:\n{xml_resp[:500]}")

        # Parsear respuesta para extraer numeroOperacion / mensajes de error
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_resp)
            num_op = self._xml_find_text(root, "numeroOperacion")
            errores = self._xml_find_errores(root)
        except Exception as exc:
            self._log_mv_error("error_xsd", str(exc), xml_body, xml_resp, duracion_ms)
            raise UserError(f"Error al parsear respuesta VUCEM: {exc}") from exc

        if errores:
            desc = "; ".join(f"{e['codigo']}: {e['desc']}" for e in errores)
            self._log_mv_error("error_vucem", desc, xml_body, xml_resp, duracion_ms)
            self.write({"estatus": "error"})
            raise UserError(f"VUCEM devolvió errores:\n{desc}")

        if num_op:
            self.write({
                "numero_mv": str(num_op),
                "estatus": "registrada",
                "fecha_envio": fields.Datetime.now(),
                "fecha_registro": fields.Datetime.now(),
            })
            self.env["mx.vucem.log"].create({
                "mv_id": self.id,
                "tipo_operacion": "registrar_mv",
                "ambiente": cred.ambiente,
                "cadena_original": self.cadena_original,
                "xml_enviado": xml_body,
                "xml_recibido": xml_resp,
                "estatus": "exitoso",
                "numero_operacion": str(num_op),
                "credencial_id": cred.id,
                "duracion_ms": duracion_ms,
            })
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "MV registrada",
                    "message": f"Número de operación VUCEM: {num_op}",
                    "type": "success",
                },
            }

        self._log_mv_error("error_vucem", "Respuesta sin numeroOperacion", xml_body, xml_resp, duracion_ms)
        raise UserError("VUCEM no devolvió número de operación. Revisa los logs.")

    def _ws_consultar_mv(self):
        """Llama al WS consultaManifestacion por numeroOperacion."""
        self.ensure_one()
        import time
        try:
            import requests as req_lib
        except ImportError as exc:
            raise UserError("La librería 'requests' no está disponible.") from exc

        cred = self._get_ws_credencial()
        endpoint = (
            cred.endpoint_mv_consulta
            or "https://privados.ventanillaunica.gob.mx/ConsultaManifestacionImpl/ConsultaManifestacionService"
        )

        xml_body = self._build_soap_consulta()
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}

        t0 = time.time()
        try:
            resp = req_lib.post(endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=60)
        except Exception as exc:
            self._log_mv_error("error_red", str(exc), xml_body, "")
            raise UserError(f"Error de red: {exc}") from exc

        duracion_ms = int((time.time() - t0) * 1000)
        xml_resp = resp.text or ""

        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_resp)
            estatus_txt = self._xml_find_text(root, "estatus") or ""
            e_doc = self._xml_find_text(root, "eDocument") or self.e_document_mv or ""
        except Exception:
            estatus_txt = ""
            e_doc = self.e_document_mv or ""

        self.env["mx.vucem.log"].create({
            "mv_id": self.id,
            "tipo_operacion": "consultar_mv",
            "ambiente": cred.ambiente,
            "xml_enviado": xml_body,
            "xml_recibido": xml_resp,
            "estatus": "exitoso",
            "credencial_id": cred.id,
            "duracion_ms": duracion_ms,
        })
        write_vals = {"estatus_vucem": estatus_txt}
        if e_doc and not self.e_document_mv:
            write_vals["e_document_mv"] = e_doc
        self.write(write_vals)

    def _ws_actualizar_mv(self):
        """Llama al WS actualizarManifestacion (agrega eDocuments / RFCs consulta)."""
        self.ensure_one()
        import time
        try:
            import requests as req_lib
        except ImportError as exc:
            raise UserError("La librería 'requests' no está disponible.") from exc

        cred = self._get_ws_credencial()
        endpoint = (
            cred.endpoint_mv_registro
            or "https://privados.ventanillaunica.gob.mx:8106/IngresoManifestacionImpl/IngresoManifestacionService"
        )
        xml_body = self._build_soap_actualizar()
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'}

        t0 = time.time()
        try:
            resp = req_lib.post(endpoint, data=xml_body.encode("utf-8"), headers=headers, timeout=60)
        except Exception as exc:
            raise UserError(f"Error de red: {exc}") from exc

        duracion_ms = int((time.time() - t0) * 1000)
        xml_resp = resp.text or ""

        self.env["mx.vucem.log"].create({
            "mv_id": self.id,
            "tipo_operacion": "actualizar_mv",
            "ambiente": cred.ambiente,
            "xml_enviado": xml_body,
            "xml_recibido": xml_resp,
            "estatus": "exitoso",
            "credencial_id": cred.id,
            "duracion_ms": duracion_ms,
        })

    def _build_soap_consulta(self):
        """Construye el XML SOAP para consultaManifestacion."""
        from xml.etree.ElementTree import Element, SubElement, tostring
        import xml.etree.ElementTree as ET

        NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
        NS_WS   = "http://ws.consultamanifestacion.manifestacion.www.ventanillaunica.gob.mx"
        ET.register_namespace("soapenv", NS_SOAP)
        ET.register_namespace("ws", NS_WS)

        envelope = Element(f"{{{NS_SOAP}}}Envelope")
        body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
        cons = SubElement(body, f"{{{NS_WS}}}consultaManifestacion")
        datos = SubElement(cons, "datosManifestacion")
        if self.numero_mv:
            SubElement(datos, "numeroOperacion").text = self.numero_mv
        elif self.e_document_mv:
            SubElement(datos, "eDocument").text = self.e_document_mv

        xml_bytes = tostring(envelope, encoding="unicode")
        return '<?xml version="1.0" encoding="utf-8"?>' + xml_bytes

    def _build_soap_actualizar(self):
        """Construye el XML SOAP para actualizarManifestacion."""
        from xml.etree.ElementTree import Element, SubElement, tostring
        import xml.etree.ElementTree as ET

        NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
        NS_WS   = "http://ws.ingresomanifestacion.manifestacion.www.ventanillaunica.gob.mx"
        NS_WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
        NS_WSU  = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
        PW_TYPE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText"

        ET.register_namespace("soapenv", NS_SOAP)
        ET.register_namespace("ws", NS_WS)

        cred = self._get_ws_credencial()
        now_utc = datetime.now(timezone.utc)

        envelope = Element(f"{{{NS_SOAP}}}Envelope")
        header = SubElement(envelope, f"{{{NS_SOAP}}}Header")
        security = SubElement(header, f"{{{NS_WSSE}}}Security")
        token = SubElement(security, f"{{{NS_WSSE}}}UsernameToken")
        SubElement(token, f"{{{NS_WSSE}}}Username").text = cred.ws_username or ""
        pw_el = SubElement(token, f"{{{NS_WSSE}}}Password")
        pw_el.set("Type", PW_TYPE)
        pw_el.text = cred.ws_password or ""
        ts = SubElement(security, f"{{{NS_WSU}}}Timestamp")
        SubElement(ts, f"{{{NS_WSU}}}Created").text = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        SubElement(ts, f"{{{NS_WSU}}}Expires").text = now_utc.strftime("%Y-%m-%dT23:59:59Z")

        # Cadena original actualizar: |MNVA...|eDocument|rfc|tipoFigura|
        cadena_act = self._build_cadena_actualizar()
        resultado = self._firmar_mv_cadena(cadena_act, cred)

        body = SubElement(envelope, f"{{{NS_SOAP}}}Body")
        act = SubElement(body, f"{{{NS_WS}}}actualizarManifestacion")
        info = SubElement(act, "informacionActualizarManifestacion")

        firma_el = SubElement(info, "firmaElectronica")
        SubElement(firma_el, "certificado").text = resultado["certificado_b64"]
        SubElement(firma_el, "cadenaOriginal").text = cadena_act
        SubElement(firma_el, "firma").text = resultado["firma_b64"]

        datos = SubElement(info, "datosActualizarManifestacion")
        SubElement(datos, "numeroMV").text = self.numero_mv or ""

        docs = SubElement(datos, "documentos")
        for cl in self.cove_line_ids:
            if cl.cove_id and cl.cove_id.e_document:
                SubElement(docs, "eDocument").text = cl.cove_id.e_document

        personas = SubElement(datos, "personasConsulta")
        for pc in self.persona_consulta_ids:
            pc_el = SubElement(personas, "personaConsulta")
            SubElement(pc_el, "rfc").text = pc.rfc or ""
            SubElement(pc_el, "tipoFigura").text = pc.tipo_figura or ""

        xml_bytes = tostring(envelope, encoding="unicode")
        return '<?xml version="1.0" encoding="utf-8"?>' + xml_bytes

    def _build_cadena_actualizar(self):
        """Cadena original para actualizarManifestacion.
        Formato (Ejemplo Agregar ED-RFC consulta MV):
        |numeroMV|eDocument|rfc|tipoFigura|
        """
        partes = [self.numero_mv or ""]
        for cl in self.cove_line_ids:
            if cl.cove_id and cl.cove_id.e_document:
                partes.append(cl.cove_id.e_document)
        for pc in self.persona_consulta_ids:
            partes.append(pc.rfc or "")
            partes.append(pc.tipo_figura or "")
        return "|" + "|".join(partes) + "|"

    # ── Helpers de parseo XML ─────────────────────────────────────────────────

    @staticmethod
    def _xml_find_text(root, tag):
        """Busca el texto del primer elemento con ese tag local (namespace-agnostic)."""
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == tag:
                return (el.text or "").strip() or None
        return None

    @staticmethod
    def _xml_find_errores(root):
        """Extrae todos los MensajeRespuesta con codigoError != '0'."""
        errores = []
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == "mensaje":
                codigo = ""
                desc = ""
                for child in el:
                    cl = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if cl == "codigoError":
                        codigo = (child.text or "").strip()
                    elif cl == "descripcionError":
                        desc = (child.text or "").strip()
                if codigo and codigo != "0":
                    errores.append({"codigo": codigo, "desc": desc})
        return errores

    def _log_mv_error(self, estatus, desc, xml_env="", xml_resp="", duracion_ms=0):
        """Crea un log VUCEM de error para esta MV."""
        cred = self.credencial_id
        self.env["mx.vucem.log"].create({
            "mv_id": self.id,
            "tipo_operacion": "registrar_mv",
            "ambiente": cred.ambiente if cred else "produccion",
            "xml_enviado": xml_env,
            "xml_recibido": xml_resp,
            "estatus": estatus,
            "error_descripcion": desc,
            "credencial_id": cred.id if cred else False,
            "duracion_ms": duracion_ms,
        })
        self.write({"estatus": "error"})


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.persona.consulta  —  RFC autorizado para consultar la MV
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvPersonaConsulta(models.Model):
    _name = "mx.ped.mv.persona.consulta"
    _description = "Persona consulta MV"
    _order = "mv_id, id"

    mv_id = fields.Many2one(
        "mx.ped.mv",
        string="MV",
        required=True,
        ondelete="cascade",
        index=True,
    )
    rfc = fields.Char(string="RFC", required=True, size=13)
    tipo_figura = fields.Selection(
        TIPOS_FIGURA,
        string="Tipo de figura",
        required=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.cove  —  Línea de COVE dentro de la MV (puente MV ↔ mx.cove)
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvCove(models.Model):
    _name = "mx.ped.mv.cove"
    _description = "COVE en Manifestación de Valor"
    _order = "mv_id, sequence, id"
    _rec_name = "display_name_computed"

    mv_id = fields.Many2one(
        "mx.ped.mv",
        string="MV",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    cove_id = fields.Many2one(
        "mx.cove",
        string="COVE",
        required=True,
        ondelete="restrict",
        domain="[('operacion_id','=',parent.operacion_id)]",
    )
    e_document_cove = fields.Char(
        related="cove_id.e_document",
        string="e-Document COVE",
        readonly=True,
    )

    # ── Datos de valoración propios del COVE en esta MV ──────────────────────
    incoterm = fields.Selection(
        INCOTERMS,
        string="Incoterm",
        required=True,
    )
    existe_vinculacion = fields.Boolean(
        string="¿Existe vinculación?",
        default=False,
        help="1 = SÍ hay vinculación entre comprador y vendedor.",
    )
    metodo_valoracion = fields.Selection(
        METODOS_VALORACION,
        string="Método de valoración",
        required=True,
    )

    # ── Líneas hijas ──────────────────────────────────────────────────────────
    pedimento_ids = fields.One2many(
        "mx.ped.mv.pedimento",
        "cove_line_id",
        string="Pedimentos relacionados",
        copy=True,
    )
    precio_pagado_ids = fields.One2many(
        "mx.ped.mv.precio.pagado",
        "cove_line_id",
        string="Precios pagados",
        copy=True,
    )
    precio_por_pagar_ids = fields.One2many(
        "mx.ped.mv.precio.por.pagar",
        "cove_line_id",
        string="Precios por pagar",
        copy=True,
    )
    compenso_pago_ids = fields.One2many(
        "mx.ped.mv.compenso.pago",
        "cove_line_id",
        string="Compensaciones de pago",
        copy=True,
    )
    incrementable_ids = fields.One2many(
        "mx.ped.mv.incrementable",
        "cove_line_id",
        string="Incrementables",
        copy=True,
    )
    decrementable_ids = fields.One2many(
        "mx.ped.mv.decrementable",
        "cove_line_id",
        string="Decrementables",
        copy=True,
    )

    display_name_computed = fields.Char(
        compute="_compute_display_name_computed",
        store=False,
    )

    def _compute_display_name_computed(self):
        for rec in self:
            cove_ref = rec.e_document_cove or (rec.cove_id.numero_factura_original if rec.cove_id else "")
            rec.display_name_computed = f"COVE {cove_ref}" if cove_ref else f"COVE #{rec.id}"

    # [AUTO #5] Al seleccionar el COVE, pre-llena el incoterm desde el COVE
    #           (fallback: incoterm de la operación padre)
    @api.onchange("cove_id")
    def _onchange_cove_id(self):
        if not self.incoterm and self.cove_id:
            # Primero intenta el incoterm del propio COVE
            incoterm_mv = _to_tipinc(self.cove_id.incoterm)
            # Si el COVE no tiene uno, usa el de la operación
            if not incoterm_mv and self.mv_id and self.mv_id.operacion_id:
                incoterm_mv = _to_tipinc(self.mv_id.operacion_id.incoterm)
            if incoterm_mv:
                self.incoterm = incoterm_mv


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.pedimento  —  Pedimento relacionado dentro de un informacionCove
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvPedimento(models.Model):
    _name = "mx.ped.mv.pedimento"
    _description = "Pedimento relacionado en MV"
    _order = "cove_line_id, id"

    cove_line_id = fields.Many2one(
        "mx.ped.mv.cove",
        string="Línea COVE",
        required=True,
        ondelete="cascade",
        index=True,
    )
    numero_pedimento = fields.Char(string="Pedimento", size=15)
    patente = fields.Char(string="Patente", size=4)
    aduana = fields.Char(string="Aduana", size=3)


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.precio.pagado
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvPrecioPagado(models.Model):
    _name = "mx.ped.mv.precio.pagado"
    _description = "Precio pagado en MV"
    _order = "cove_line_id, id"

    cove_line_id = fields.Many2one(
        "mx.ped.mv.cove",
        string="Línea COVE",
        required=True,
        ondelete="cascade",
        index=True,
    )
    fecha_pago = fields.Datetime(
        string="Fecha de pago",
        required=True,
    )
    total = fields.Float(
        string="Total",
        required=True,
        digits=(19, 3),
    )
    tipo_pago = fields.Selection(
        FORMAS_PAGO,
        string="Tipo de pago",
        required=True,
    )
    especifique = fields.Char(
        string="Especifique",
        size=70,
        help="Obligatorio cuando tipo_pago = FORPAG.OT.",
    )
    tipo_moneda = fields.Char(
        string="Tipo de moneda",
        size=3,
        required=True,
        help="ISO 4217 — 3 caracteres (USD, EUR, MXN…).",
    )
    tipo_cambio = fields.Float(
        string="Tipo de cambio",
        required=True,
        digits=(16, 3),
    )

    @api.constrains("tipo_pago", "especifique")
    def _check_especifique(self):
        for rec in self:
            if rec.tipo_pago == "FORPAG.OT" and not (rec.especifique or "").strip():
                raise ValidationError(
                    "Cuando el tipo de pago es 'Otra forma de pago', "
                    "el campo 'Especifique' es obligatorio."
                )


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.precio.por.pagar
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvPrecioPorPagar(models.Model):
    _name = "mx.ped.mv.precio.por.pagar"
    _description = "Precio por pagar en MV"
    _order = "cove_line_id, id"

    cove_line_id = fields.Many2one(
        "mx.ped.mv.cove",
        string="Línea COVE",
        required=True,
        ondelete="cascade",
        index=True,
    )
    fecha_pago = fields.Datetime(
        string="Fecha de pago estimada",
        required=True,
    )
    total = fields.Float(
        string="Total",
        required=True,
        digits=(19, 3),
    )
    situacion_no_fecha_pago = fields.Char(
        string="Situación (sin fecha exacta)",
        help="Descripción cuando no se conoce la fecha exacta de pago.",
    )
    tipo_pago = fields.Selection(
        FORMAS_PAGO,
        string="Tipo de pago",
        required=True,
    )
    especifique = fields.Char(
        string="Especifique",
        size=70,
    )
    tipo_moneda = fields.Char(
        string="Tipo de moneda",
        size=3,
        required=True,
    )
    tipo_cambio = fields.Float(
        string="Tipo de cambio",
        required=True,
        digits=(16, 3),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.compenso.pago
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvCompensoPago(models.Model):
    _name = "mx.ped.mv.compenso.pago"
    _description = "Compensación de pago en MV"
    _order = "cove_line_id, id"

    cove_line_id = fields.Many2one(
        "mx.ped.mv.cove",
        string="Línea COVE",
        required=True,
        ondelete="cascade",
        index=True,
    )
    tipo_pago = fields.Selection(
        FORMAS_PAGO,
        string="Tipo de pago",
        required=True,
    )
    especifique = fields.Char(
        string="Especifique",
        size=70,
    )
    fecha = fields.Datetime(
        string="Fecha",
        required=True,
    )
    motivo = fields.Text(
        string="Motivo",
        required=True,
        help="Máximo 1000 caracteres.",
    )
    prestacion_mercancia = fields.Text(
        string="Prestación / Mercancía",
        required=True,
        help="Descripción de la mercancía o prestación. Máximo 1000 caracteres.",
    )

    @api.constrains("motivo", "prestacion_mercancia")
    def _check_longitud(self):
        for rec in self:
            if rec.motivo and len(rec.motivo) > 1000:
                raise ValidationError("El campo 'Motivo' no puede exceder 1000 caracteres.")
            if rec.prestacion_mercancia and len(rec.prestacion_mercancia) > 1000:
                raise ValidationError("El campo 'Prestación / Mercancía' no puede exceder 1000 caracteres.")


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.incrementable
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvIncrementable(models.Model):
    _name = "mx.ped.mv.incrementable"
    _description = "Incrementable en MV"
    _order = "cove_line_id, id"

    cove_line_id = fields.Many2one(
        "mx.ped.mv.cove",
        string="Línea COVE",
        required=True,
        ondelete="cascade",
        index=True,
    )
    tipo_incrementable = fields.Selection(
        TIPOS_INCREMENTABLE,
        string="Tipo",
        required=True,
    )
    fecha_erogacion = fields.Datetime(
        string="Fecha de erogación",
        required=True,
    )
    importe = fields.Float(
        string="Importe",
        required=True,
        digits=(19, 3),
    )
    tipo_moneda = fields.Char(
        string="Tipo de moneda",
        size=3,
        required=True,
    )
    tipo_cambio = fields.Float(
        string="Tipo de cambio",
        required=True,
        digits=(16, 3),
    )
    a_cargo_importador = fields.Boolean(
        string="¿A cargo del importador?",
        default=True,
        help="1 = SÍ está a cargo del importador.",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  mx.ped.mv.decrementable
# ─────────────────────────────────────────────────────────────────────────────

class MxPedMvDecrementable(models.Model):
    _name = "mx.ped.mv.decrementable"
    _description = "Decrementable en MV"
    _order = "cove_line_id, id"

    cove_line_id = fields.Many2one(
        "mx.ped.mv.cove",
        string="Línea COVE",
        required=True,
        ondelete="cascade",
        index=True,
    )
    tipo_decrementable = fields.Selection(
        TIPOS_DECREMENTABLE,
        string="Tipo",
        required=True,
    )
    fecha_erogacion = fields.Datetime(
        string="Fecha de erogación",
        required=True,
    )
    importe = fields.Float(
        string="Importe",
        required=True,
        digits=(19, 3),
    )
    tipo_moneda = fields.Char(
        string="Tipo de moneda",
        size=3,
        required=True,
    )
    tipo_cambio = fields.Float(
        string="Tipo de cambio",
        required=True,
        digits=(16, 3),
    )
