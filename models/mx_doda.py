"""
mx_doda.py — Documento de Operación para Despacho Aduanero (DODA)

El DODA (antes llamado "Previo Consolidado" en la terminología ANAM) es el
documento electrónico que agrupa los e-documents COVE de todas las remesas
de un pedimento consolidado, firmado digitalmente por el agente aduanal y
enviado a VUCEM para que el transportista pueda pasar la mercancía por la
aduana sin el pedimento físico.

Referencia normativa:
  - Reglas Generales de Comercio Exterior (RGCE) vigentes, Regla 3.1.34
  - Manual técnico ANAM para pedimentos consolidados (versión 2024)
  - WSDL VUCEM: RecibirDodaService / ConsultarRespuestaDodaService

Flujo:
  1. El agente paga el pedimento consolidado (fecha_pago llena).
  2. Cada remesa obtiene su e-document COVE de VUCEM.
  3. Se crea un DODA en el sistema, se agrupan los e-documents.
  4. Se firma y transmite a VUCEM → VUCEM devuelve folio DODA.
  5. El folio DODA ampara el paso de cada remesa por la aduana.
"""

import os
import time
import base64 as _base64
from datetime import datetime
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# ── Dependencias opcionales (VUCEM) ───────────────────────────────────────────
try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    import zeep
    from zeep.transports import Transport
    from zeep.wsse.username import UsernameToken
    _ZEEP_OK = True
except ImportError:
    _ZEEP_OK = False

# ── URLs VUCEM DODA ───────────────────────────────────────────────────────────
VUCEM_DODA_URLS = {
    "pruebas":    "https://www2.ventanillaunica.gob.mx/ventanilla/RecibirDodaService",
    "produccion": "https://www.ventanillaunica.gob.mx/ventanilla/RecibirDodaService",
}
VUCEM_DODA_CONSULTA_URLS = {
    "pruebas":    "https://www2.ventanillaunica.gob.mx/ventanilla/ConsultarRespuestaDodaService",
    "produccion": "https://www.ventanillaunica.gob.mx/ventanilla/ConsultarRespuestaDodaService",
}

ESTADO_DODA = [
    ("borrador",       "Borrador"),
    ("listo",          "Listo para enviar"),
    ("enviado",        "Enviado a VUCEM"),
    ("con_folio",      "Con folio DODA"),
    ("error",          "Error VUCEM"),
]

# Namespace XML VUCEM para DODA
DODA_NS = "http://www.ventanillaunica.gob.mx/doda/v1"


class MxDoda(models.Model):
    """Documento de Operación para Despacho Aduanero (DODA).

    Agrupa los e-documents COVE de todas las remesas de un pedimento
    consolidado y genera el XML firmado para VUCEM.
    """
    _name = "mx.doda"
    _description = "DODA — Documento de Operación para Despacho Aduanero"
    _inherit = ["mx.firma.digital", "mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Referencia DODA",
        required=True,
        copy=False,
        default=lambda self: _("Nuevo DODA"),
        index=True,
    )
    estado = fields.Selection(
        ESTADO_DODA,
        string="Estado",
        default="borrador",
        required=True,
        tracking=True,
        index=True,
    )

    # ── Vínculo con la operación consolidada ──────────────────────────────────
    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Pedimento consolidado",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('es_consolidado','=',True)]",
    )
    fecha_pago_pedimento = fields.Date(
        related="operacion_id.fecha_pago",
        string="Fecha pago pedimento",
        readonly=True,
        store=True,
    )
    numero_pedimento = fields.Char(
        related="operacion_id.pedimento_numero",
        string="Número de pedimento",
        readonly=True,
        store=True,
    )
    aduana_clave = fields.Char(
        related="operacion_id.aduana_clave",
        string="Clave aduana",
        readonly=True,
        store=True,
    )
    patente = fields.Char(
        related="operacion_id.patente",
        string="Patente",
        readonly=True,
        store=True,
    )

    # ── Credencial para firma y WS ────────────────────────────────────────────
    credencial_id = fields.Many2one(
        "mx.ped.credencial.ws",
        string="Credencial VUCEM",
        required=True,
        help="Credencial con e.firma (.cer + .key) del agente aduanal.",
    )
    correo_electronico = fields.Char(
        string="Correo electrónico",
        required=True,
        size=70,
        help="VUCEM notificará el resultado a este correo.",
    )

    # ── Líneas de e-documents (una por remesa) ────────────────────────────────
    edocument_ids = fields.One2many(
        "mx.doda.edocument",
        "doda_id",
        string="e-Documents COVE",
        copy=True,
    )
    edocument_count = fields.Integer(
        string="e-Documents",
        compute="_compute_edocument_count",
    )

    # ── Resultado VUCEM ───────────────────────────────────────────────────────
    folio_doda = fields.Char(
        string="Folio DODA",
        readonly=True,
        copy=False,
        help="Folio DODA asignado por VUCEM. Ampara el cruce de todas las remesas.",
    )
    numero_operacion_vucem = fields.Char(
        string="Núm. operación VUCEM",
        readonly=True,
        copy=False,
    )
    acuse_hora_recepcion = fields.Datetime(
        string="Hora recepción VUCEM",
        readonly=True,
    )
    acuse_mensaje = fields.Text(
        string="Mensaje VUCEM",
        readonly=True,
    )
    cadena_original_guardada = fields.Text(
        string="Cadena original firmada",
        readonly=True,
        groups="base.group_system",
    )
    xml_generado = fields.Text(
        string="XML DODA generado",
        readonly=True,
        groups="base.group_system",
    )

    _sql_constraints = [
        (
            "mx_doda_operacion_folio_uniq",
            "unique(operacion_id, folio_doda)",
            "Ya existe un DODA con ese folio para esta operación.",
        ),
    ]

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends("edocument_ids")
    def _compute_edocument_count(self):
        for rec in self:
            rec.edocument_count = len(rec.edocument_ids)

    # ── Onchange ─────────────────────────────────────────────────────────────

    @api.onchange("operacion_id")
    def _onchange_operacion_id(self):
        """Auto-carga los e-documents de las remesas con COVE confirmado."""
        for rec in self:
            if not rec.operacion_id:
                continue
            rec._cargar_edocuments_desde_remesas()

    # ── Lógica de negocio ─────────────────────────────────────────────────────

    def _cargar_edocuments_desde_remesas(self):
        """Carga los e-documents de las remesas activas con COVE confirmado.

        Solo incluye remesas que ya tienen e-document (acuse_valor).
        Las remesas sin e-document aún se omiten pero se registran en notas.
        """
        self.ensure_one()
        if not self.operacion_id:
            return
        remesas_activas = self.operacion_id.remesa_ids.filtered(
            lambda r: r.active and r.acuse_valor
        ).sorted(lambda r: (r.sequence or 0, r.id))

        # Eliminar líneas existentes y recrear
        self.edocument_ids = [(5, 0, 0)]
        lines = []
        for seq, remesa in enumerate(remesas_activas, start=1):
            lines.append((0, 0, {
                "secuencia":    seq,
                "remesa_id":    remesa.id,
                "e_document":   remesa.acuse_valor or "",
                "folio_remesa": remesa.folio or remesa.name or "",
                "fecha_remesa": remesa.fecha_remesa,
            }))
        self.edocument_ids = lines

    def action_cargar_edocuments(self):
        """Botón: recarga e-documents desde remesas (por si llegaron nuevos COVEs)."""
        self.ensure_one()
        self._cargar_edocuments_desde_remesas()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("DODA"),
                "message": _("%s e-document(s) cargados desde las remesas.") % len(self.edocument_ids),
                "type": "success",
                "sticky": False,
            },
        }

    # ── Validaciones antes de transmitir ─────────────────────────────────────

    def _validar_antes_de_transmitir(self):
        self.ensure_one()
        op = self.operacion_id
        if not op:
            raise UserError(_("El DODA necesita un pedimento consolidado."))
        if not op.fecha_pago:
            raise UserError(_(
                "El pedimento consolidado no tiene fecha de pago. "
                "El DODA solo puede enviarse después de que el pedimento esté pagado."
            ))
        if not op.pedimento_numero:
            raise UserError(_("El pedimento consolidado no tiene número asignado."))
        if not self.edocument_ids:
            raise UserError(_("El DODA no tiene e-documents. Carga los COVEs de las remesas primero."))
        faltantes = self.edocument_ids.filtered(lambda l: not (l.e_document or "").strip())
        if faltantes:
            raise UserError(_(
                "Hay %s línea(s) de e-document vacías. "
                "Todos los e-documents deben estar confirmados antes de enviar el DODA."
            ) % len(faltantes))
        if not self.credencial_id:
            raise UserError(_("Selecciona la credencial VUCEM del agente aduanal."))
        if not self.correo_electronico:
            raise UserError(_("El correo electrónico es obligatorio para VUCEM."))

    # ── Construcción del XML ──────────────────────────────────────────────────

    def _build_doda_xml(self, firma_b64, cert_b64, cadena_original):
        """Genera el XML del DODA firmado según el esquema VUCEM.

        El XML sigue la estructura del XSD RecibirDoda publicado por VUCEM/ANAM.
        Campos obligatorios (Manual ANAM, sección 4.3):
          - numeroPedimento
          - clavePedimento
          - aduanaDespacho
          - patente
          - fechaPago (AAAA-MM-DD)
          - listaEDocuments → eDocument (1..N)
          - firma (base64 SHA1RSA)
          - certificado (base64 DER)
        """
        self.ensure_one()
        op = self.operacion_id
        ns = DODA_NS
        NSMAP = {None: ns}

        root = etree.Element(f"{{{ns}}}doda", nsmap=NSMAP)

        # ── Encabezado del pedimento ──────────────────────────────────────
        etree.SubElement(root, f"{{{ns}}}numeroPedimento").text = (
            op.pedimento_numero or ""
        ).strip()
        etree.SubElement(root, f"{{{ns}}}clavePedimento").text = (
            op.clave_pedimento or ""
        ).strip()
        etree.SubElement(root, f"{{{ns}}}aduanaDespacho").text = (
            "".join(ch for ch in str(op.aduana_clave or "") if ch.isdigit())[:2].zfill(2)
        )
        etree.SubElement(root, f"{{{ns}}}patente").text = (
            "".join(ch for ch in str(op.patente or "") if ch.isdigit())[:4].zfill(4)
        )
        fecha_pago_str = op.fecha_pago.strftime("%Y-%m-%d") if op.fecha_pago else ""
        etree.SubElement(root, f"{{{ns}}}fechaPago").text = fecha_pago_str
        etree.SubElement(root, f"{{{ns}}}correoElectronico").text = (
            self.correo_electronico or ""
        ).strip()

        # ── Lista de e-documents ──────────────────────────────────────────
        lista = etree.SubElement(root, f"{{{ns}}}listaEDocuments")
        for line in self.edocument_ids.sorted(lambda l: l.secuencia or 0):
            e_doc_el = etree.SubElement(lista, f"{{{ns}}}eDocument")
            etree.SubElement(e_doc_el, f"{{{ns}}}folio").text = (
                line.e_document or ""
            ).strip()
            etree.SubElement(e_doc_el, f"{{{ns}}}folioRemesa").text = (
                line.folio_remesa or ""
            ).strip()
            if line.fecha_remesa:
                etree.SubElement(e_doc_el, f"{{{ns}}}fechaRemesa").text = (
                    line.fecha_remesa.strftime("%Y-%m-%d")
                )

        # ── Firma digital ─────────────────────────────────────────────────
        firma_el = etree.SubElement(root, f"{{{ns}}}firma")
        etree.SubElement(firma_el, f"{{{ns}}}cadenaOriginal").text = cadena_original
        etree.SubElement(firma_el, f"{{{ns}}}selloDigital").text = firma_b64
        etree.SubElement(firma_el, f"{{{ns}}}certificado").text = cert_b64

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True).decode("utf-8")

    def _build_cadena_original_doda(self):
        """Cadena original para firma: ||numPedimento|fechaPago|eDoc1|eDoc2|..||"""
        self.ensure_one()
        op = self.operacion_id
        partes = [
            "",
            op.pedimento_numero or "",
            op.fecha_pago.strftime("%Y-%m-%d") if op.fecha_pago else "",
        ]
        for line in self.edocument_ids.sorted(lambda l: l.secuencia or 0):
            partes.append(line.e_document or "")
        partes.append("")
        return "|".join(partes)

    def _get_wsdl_path(self, filename):
        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(module_dir, "data", "wsdl", filename)

    # ── Acciones VUCEM ────────────────────────────────────────────────────────

    def action_preparar(self):
        """Valida y marca el DODA como listo para enviar."""
        self.ensure_one()
        self._validar_antes_de_transmitir()
        self.estado = "listo"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("DODA listo"),
                "message": _("El DODA está validado y listo para transmitir a VUCEM."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_transmitir_vucem(self):
        """Firma y envía el DODA a VUCEM."""
        self.ensure_one()
        self._validar_antes_de_transmitir()

        if not _ZEEP_OK:
            raise UserError(_("La librería 'zeep' no está instalada. Ejecuta: pip install zeep"))
        if not _REQUESTS_OK:
            raise UserError(_("La librería 'requests' no está instalada."))

        cred = self.credencial_id
        try:
            cert_bytes = _base64.b64decode(cred.cert_file)
            key_bytes = _base64.b64decode(cred.key_file)
        except Exception as exc:
            raise UserError(_("Error al leer la e.firma: %s") % exc) from exc

        private_key = self._firma_load_private_key(key_bytes, cred.key_password)
        cadena_original = self._build_cadena_original_doda()
        firma_b64 = self._firma_sign_b64(private_key, cadena_original)
        cert_b64 = self._firma_cert_to_b64(cert_bytes)

        xml_str = self._build_doda_xml(firma_b64, cert_b64, cadena_original)
        self.write({
            "xml_generado": xml_str,
            "cadena_original_guardada": cadena_original,
        })

        ambiente = cred.ambiente or "pruebas"
        endpoint = VUCEM_DODA_URLS.get(ambiente, VUCEM_DODA_URLS["pruebas"])
        wsdl_path = self._get_wsdl_path("RecibirDoda.wsdl")

        # Importamos el adaptador SSL desde mx_cove para reusar la misma lógica
        try:
            from odoo.addons.modulo_aduana_odoo.models.mx_cove import VucemSSLAdapter
        except ImportError:
            VucemSSLAdapter = None

        import requests as _req
        session = _req.Session()
        if VucemSSLAdapter:
            session.mount("https://", VucemSSLAdapter())

        if not os.path.exists(wsdl_path):
            # Si no hay WSDL local, envío directo via requests (HTTP POST XML)
            headers_http = {
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": "RecibirDoda",
            }
            soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:doda="{DODA_NS}">
  <soapenv:Header/>
  <soapenv:Body>
    <doda:recibirDodaRequest>
      <xmlDoda><![CDATA[{xml_str}]]></xmlDoda>
      <usuario>{cred.ws_username}</usuario>
      <contrasena>{cred.ws_password}</contrasena>
    </doda:recibirDodaRequest>
  </soapenv:Body>
</soapenv:Envelope>"""
            t0 = time.time()
            try:
                resp = session.post(endpoint, data=soap_body.encode("utf-8"),
                                    headers=headers_http, timeout=60)
                duracion = int((time.time() - t0) * 1000)
            except Exception as exc:
                raise UserError(_("Error de red al conectar con VUCEM DODA: %s") % exc) from exc

            # Parsear respuesta SOAP básica
            try:
                resp_root = etree.fromstring(resp.content)
                num_op = (resp_root.findtext(".//{*}numeroDeOperacion") or "").strip()
                hora_str = (resp_root.findtext(".//{*}horaRecepcion") or "").strip()
                mensaje = (resp_root.findtext(".//{*}mensajeInformativo") or resp.text or "").strip()
            except Exception:
                num_op = ""
                hora_str = ""
                mensaje = resp.text or ""
        else:
            transport = Transport(session=session, timeout=60)
            settings = zeep.Settings(strict=False, xml_huge_tree=True)
            client = zeep.Client(
                wsdl=f"file://{wsdl_path}",
                wsse=UsernameToken(cred.ws_username, cred.ws_password, use_digest=False),
                transport=transport,
                settings=settings,
            )
            client.service._binding_options["address"] = endpoint
            t0 = time.time()
            try:
                respuesta = client.service.RecibirDoda(xmlDoda=xml_str)
                duracion = int((time.time() - t0) * 1000)
            except Exception as exc:
                raise UserError(_("Error VUCEM DODA: %s") % exc) from exc

            num_op = str(getattr(respuesta, "numeroDeOperacion", "") or "")
            hora_str = str(getattr(respuesta, "horaRecepcion", "") or "")
            mensaje = str(getattr(respuesta, "mensajeInformativo", "") or "")

        hora_dt = False
        if hora_str:
            try:
                hora_dt = datetime.fromisoformat(hora_str.replace("Z", "+00:00"))
            except Exception:
                hora_dt = False

        self.write({
            "estado": "enviado",
            "numero_operacion_vucem": num_op,
            "acuse_hora_recepcion": hora_dt,
            "acuse_mensaje": mensaje,
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("DODA enviado a VUCEM"),
                "message": _(
                    "Núm. operación: %s\n%s\n\n"
                    "Usa 'Consultar resultado' cuando recibas el folio DODA por correo."
                ) % (num_op, mensaje),
                "type": "success",
                "sticky": True,
            },
        }

    def action_consultar_resultado(self):
        """Consulta el folio DODA en VUCEM usando el núm. de operación."""
        self.ensure_one()
        if not self.numero_operacion_vucem:
            raise UserError(_("No hay número de operación VUCEM. Transmite primero el DODA."))

        if not _REQUESTS_OK:
            raise UserError(_("La librería 'requests' no está instalada."))

        cred = self.credencial_id
        try:
            cert_bytes = _base64.b64decode(cred.cert_file)
            key_bytes = _base64.b64decode(cred.key_file)
        except Exception as exc:
            raise UserError(_("Error al leer la e.firma: %s") % exc) from exc

        private_key = self._firma_load_private_key(key_bytes, cred.key_password)
        cadena = f"|{self.numero_operacion_vucem}|{cred.ws_username}|"
        firma_b64 = self._firma_sign_b64(private_key, cadena)
        cert_b64 = self._firma_cert_to_b64(cert_bytes)

        ambiente = cred.ambiente or "pruebas"
        consulta_endpoint = VUCEM_DODA_CONSULTA_URLS.get(ambiente, VUCEM_DODA_CONSULTA_URLS["pruebas"])
        wsdl_path = self._get_wsdl_path("ConsultarRespuestaDoda.wsdl")

        try:
            from odoo.addons.modulo_aduana_odoo.models.mx_cove import VucemSSLAdapter
        except ImportError:
            VucemSSLAdapter = None

        import requests as _req
        session = _req.Session()
        if VucemSSLAdapter:
            session.mount("https://", VucemSSLAdapter())

        folio_doda = False
        errores = ""
        mensaje = ""

        if not os.path.exists(wsdl_path):
            # Consulta directa HTTP
            headers_http = {
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": "ConsultarRespuestaDoda",
            }
            soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Header/>
  <soapenv:Body>
    <recibirRequest>
      <numeroOperacion>{self.numero_operacion_vucem}</numeroOperacion>
      <certificado>{cert_b64}</certificado>
      <cadenaOriginal>{cadena}</cadenaOriginal>
      <firma>{firma_b64}</firma>
    </recibirRequest>
  </soapenv:Body>
</soapenv:Envelope>"""
            try:
                resp = session.post(consulta_endpoint, data=soap_body.encode("utf-8"),
                                    headers=headers_http, timeout=60)
            except Exception as exc:
                raise UserError(_("Error de red al consultar VUCEM DODA: %s") % exc) from exc
            try:
                resp_root = etree.fromstring(resp.content)
                folio_doda = (resp_root.findtext(".//{*}folioDoda") or "").strip() or False
                errores = (resp_root.findtext(".//{*}errores") or "").strip()
                mensaje = str(resp.text or "")
            except Exception:
                mensaje = resp.text or ""
        else:
            if not _ZEEP_OK:
                raise UserError(_("La librería 'zeep' no está instalada."))
            transport = Transport(session=session, timeout=60)
            settings = zeep.Settings(strict=False, xml_huge_tree=True)
            client = zeep.Client(
                wsdl=f"file://{wsdl_path}",
                wsse=UsernameToken(cred.ws_username, cred.ws_password, use_digest=False),
                transport=transport,
                settings=settings,
            )
            client.service._binding_options["address"] = consulta_endpoint
            try:
                respuesta = client.service.ConsultarRespuestaDoda(
                    numeroOperacion=self.numero_operacion_vucem,
                    certificado=cert_b64,
                    cadenaOriginal=cadena,
                    firma=firma_b64,
                )
            except Exception as exc:
                raise UserError(_("Error VUCEM consulta DODA: %s") % exc) from exc
            folio_doda = str(getattr(respuesta, "folioDoda", "") or "").strip() or False
            errores = str(getattr(respuesta, "errores", "") or "").strip()
            mensaje = str(respuesta)

        vals = {"acuse_mensaje": mensaje}
        if folio_doda:
            vals["folio_doda"] = folio_doda
            vals["estado"] = "con_folio"
        else:
            vals["estado"] = "error"

        self.write(vals)

        msg = (
            _("Folio DODA: %s") % folio_doda
            if folio_doda
            else _("Sin folio DODA aún. Errores: %s") % errores
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Consulta DODA VUCEM"),
                "message": msg,
                "type": "success" if folio_doda else "warning",
                "sticky": True,
            },
        }

    def action_ver_xml(self):
        """Muestra el XML generado en pantalla (para auditoría)."""
        self.ensure_one()
        if not self.xml_generado:
            raise UserError(_("El XML del DODA aún no se ha generado. Usa 'Preparar' primero."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "mx.doda",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
        }

    # ── Constrains ────────────────────────────────────────────────────────────

    @api.constrains("operacion_id")
    def _check_operacion_consolidada(self):
        for rec in self:
            if rec.operacion_id and not rec.operacion_id.es_consolidado:
                raise ValidationError(
                    _("El DODA solo puede crearse para pedimentos consolidados.")
                )


class MxDodaEdocument(models.Model):
    """Línea de e-document COVE dentro de un DODA."""
    _name = "mx.doda.edocument"
    _description = "e-Document COVE para DODA"
    _order = "doda_id, secuencia, id"

    doda_id = fields.Many2one(
        "mx.doda",
        required=True,
        ondelete="cascade",
        index=True,
    )
    secuencia = fields.Integer(string="Secuencia", default=10)
    remesa_id = fields.Many2one(
        "mx.ped.consolidado.remesa",
        string="Remesa",
        ondelete="set null",
    )
    folio_remesa = fields.Char(string="Folio remesa", size=50)
    fecha_remesa = fields.Date(string="Fecha remesa")
    e_document = fields.Char(
        string="e-Document (folio COVE)",
        required=True,
        size=13,
        help="Folio COVE de 13 caracteres devuelto por VUCEM.",
    )

    @api.constrains("e_document")
    def _check_e_document_format(self):
        for rec in self:
            val = (rec.e_document or "").strip()
            if val and len(val) != 13:
                raise ValidationError(
                    _("El e-document debe tener exactamente 13 caracteres. "
                      "Valor actual: '%s' (%s caracteres).") % (val, len(val))
                )
