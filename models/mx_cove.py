# -*- coding: utf-8 -*-
"""
Comprobante de Valor Electrónico (COVE) — integración VUCEM.

Webservice: RecibirCoveService
WSDL:  https://www.ventanillaunica.gob.mx:8110/ventanilla/RecibirCoveService?wsdl
XSD:   https://www.ventanillaunica.gob.mx:443/ventanilla/RecibirCoveService?xsd=1

Referencias:
  - XSD oficial: namespace http://www.ventanillaunica.gob.mx/cove/ws/oxml/
  - Autenticación: WS-Security UsernameToken (usuario + contraseña VUCEM)
  - Firma: SHA1 + RSA PKCS1v15
  - Certificado y firma: Base64 (xsd:base64Binary — el manual decía hex, el XSD manda)
  - Cadena original: ISO-8859-1, campo tipoMoneda va ANTES de cantidad en mercancías
"""
import logging
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# ── Importaciones opcionales ──────────────────────────────────────────────────
try:
    import zeep
    from zeep.wsse.username import UsernameToken
    from zeep.transports import Transport
    import requests as _requests
    _ZEEP_OK = True
except ImportError:
    _ZEEP_OK = False
    _logger.warning("librería 'zeep' no disponible — transmisión VUCEM deshabilitada")

# ── Catálogos de enumeraciones XSD ────────────────────────────────────────────
TIPO_IDENTIFICADOR = [
    ("0", "TAX ID"),
    ("1", "RFC"),
    ("2", "CURP"),
    ("3", "Sin Tax ID"),
]

TIPO_OPERACION = [
    ("TOCE.IMP", "Importación"),
    ("TOCE.EXP", "Exportación"),
]

TIPO_FIGURA = [
    ("1", "Agente Aduanal"),
    ("2", "Apoderado Aduanal"),
    ("4", "Exportador"),
    ("5", "Importador"),
]

SUBDIVISION = [
    ("0", "Sin subdivisión"),
    ("1", "Con subdivisión"),
]

CERTIFICADO_ORIGEN = [
    ("0", "No funge como certificado de origen"),
    ("1", "Sí funge como certificado de origen"),
]

ESTADO_COVE = [
    ("borrador", "Borrador"),
    ("enviado", "Enviado — pendiente e-document"),
    ("con_edocument", "Con e-document"),
    ("rechazado", "Rechazado"),
    ("adenda", "Adenda"),
]

# URLs de endpoints por ambiente
VUCEM_URLS = {
    "pruebas": "https://www2.ventanillaunica.gob.mx/ventanilla/RecibirCoveService",
    "produccion": "https://www.ventanillaunica.gob.mx:8110/ventanilla/RecibirCoveService",
}
VUCEM_CONSULTA_URLS = {
    "pruebas": "https://www2.ventanillaunica.gob.mx/ventanilla/ConsultarRespuestaCoveService",
    "produccion": "https://www.ventanillaunica.gob.mx:8110/ventanilla/ConsultarRespuestaCoveService",
}


class MxCoveRfcConsulta(models.Model):
    """RFCs adicionales que pueden consultar el COVE en VUCEM."""
    _name = "mx.cove.rfc.consulta"
    _description = "RFC de consulta COVE"
    _order = "id"

    cove_id = fields.Many2one("mx.cove", required=True, ondelete="cascade")
    rfc = fields.Char(string="RFC", required=True, size=13)


class MxCovePatenteAduanal(models.Model):
    """Patentes aduanales asociadas al COVE."""
    _name = "mx.cove.patente.aduanal"
    _description = "Patente aduanal COVE"
    _order = "id"

    cove_id = fields.Many2one("mx.cove", required=True, ondelete="cascade")
    patente = fields.Char(string="Patente", required=True, size=4)


class MxCoveMercancia(models.Model):
    """Mercancía declarada en el COVE (elemento <mercancias> del XSD)."""
    _name = "mx.cove.mercancia"
    _description = "Mercancía COVE"
    _order = "sequence, id"

    cove_id = fields.Many2one("mx.cove", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)

    # ── Campos obligatorios XSD ───────────────────────────────────────────────
    descripcion_generica = fields.Char(
        string="Descripción genérica",
        required=True,
        size=256,
        help="Descripción comercial de la mercancía (máx. 256 chars).",
    )
    clave_unidad_medida = fields.Char(
        string="Clave UM",
        required=True,
        size=10,
        help="Clave de la unidad de medida según catálogo VUCEM/OMA.",
    )
    tipo_moneda = fields.Char(
        string="Moneda",
        required=True,
        size=3,
        help="Código ISO 4217, ej: USD, EUR, MXN.",
    )

    # Decimales exactos según formato VUCEM (pág. 62 manual)
    cantidad = fields.Float(
        string="Cantidad",
        required=True,
        digits=(15, 3),
        help="Cantidad UM comercialización. Formato: ###########0.000 (3 decimales).",
    )
    valor_unitario = fields.Float(
        string="Valor unitario",
        required=True,
        digits=(23, 6),
        help="Valor por unidad en la moneda de la factura. Formato: 6 decimales.",
    )
    valor_total = fields.Float(
        string="Valor total",
        required=True,
        digits=(23, 6),
        help="Valor total en la moneda de la factura. Formato: 6 decimales.",
    )
    valor_dolares = fields.Float(
        string="Valor dólares",
        required=True,
        digits=(16, 4),
        help="Valor en USD. Formato: ###########0.0000 (4 decimales). Mín: 0.01.",
    )

    # ── DescripcionMercancia (opcional) ───────────────────────────────────────
    marca = fields.Char(string="Marca", size=100)
    modelo = fields.Char(string="Modelo", size=50)
    sub_modelo = fields.Char(string="Sub-modelo", size=50)
    numero_serie = fields.Char(string="Número de serie", size=25)

    @api.constrains("cantidad")
    def _check_cantidad(self):
        for rec in self:
            if rec.cantidad < 0.001:
                raise ValidationError("La cantidad debe ser mayor o igual a 0.001.")

    @api.constrains("valor_dolares")
    def _check_valor_dolares(self):
        for rec in self:
            if rec.valor_dolares < 0.01:
                raise ValidationError("Valor dólares debe ser mayor o igual a 0.01.")

    @api.constrains("valor_unitario", "valor_total")
    def _check_valores(self):
        for rec in self:
            if rec.valor_unitario < 0.000001:
                raise ValidationError("Valor unitario debe ser > 0.")
            if rec.valor_total < 0.000001:
                raise ValidationError("Valor total debe ser > 0.")


class MxCove(models.Model):
    """Comprobante de Valor Electrónico (COVE).

    Un COVE corresponde a una factura (RecibirCove) o puede agrupar
    múltiples facturas (RecibirRelacionFacturasNoIA).
    Para el piloto se implementa la operación de factura única.
    """
    _name = "mx.cove"
    _description = "Comprobante de Valor Electrónico (COVE)"
    _inherit = ["mx.firma.digital"]
    _order = "id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        default=lambda self: _("Nuevo COVE"),
        index=True,
    )
    estado = fields.Selection(
        ESTADO_COVE,
        string="Estado",
        default="borrador",
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    # ── Vínculos con el módulo aduanal ────────────────────────────────────────
    operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Operación aduanal",
        ondelete="set null",
        index=True,
    )
    credencial_id = fields.Many2one(
        "mx.ped.credencial.ws",
        string="Credencial VUCEM",
        required=True,
        help="Credencial con e.firma (.cer + .key) para firmar y usuario/contraseña para VUCEM.",
    )

    # ── e-document (para adendas) ─────────────────────────────────────────────
    e_document_adenda = fields.Char(
        string="e-Document original (adenda)",
        size=13,
        help="Si se llena, este COVE se enviará como adenda del e-document indicado.",
    )

    # ── Datos del comprobante (ComprobanteValorElectronicoBase) ───────────────
    tipo_operacion = fields.Selection(
        TIPO_OPERACION,
        string="Tipo de operación",
        required=True,
        default="TOCE.IMP",
    )
    tipo_figura = fields.Selection(
        TIPO_FIGURA,
        string="Tipo de figura",
        required=True,
        default="1",
        help="Quién firma el COVE: 1=Agente, 2=Apoderado, 4=Exportador, 5=Importador.",
    )
    fecha_expedicion = fields.Date(
        string="Fecha de expedición",
        required=True,
        default=fields.Date.context_today,
        help="Fecha en que fue expedida la factura (AAAA-MM-DD).",
    )
    observaciones = fields.Text(
        string="Observaciones",
        help="Observaciones adicionales, leyendas de TLC, etc. Máx. 300 chars.",
    )
    correo_electronico = fields.Char(
        string="Correo electrónico",
        required=True,
        size=70,
        help="VUCEM enviará el resultado de la operación a este correo.",
    )

    patente_aduanal_ids = fields.One2many(
        "mx.cove.patente.aduanal",
        "cove_id",
        string="Patentes aduanales",
    )
    rfc_consulta_ids = fields.One2many(
        "mx.cove.rfc.consulta",
        "cove_id",
        string="RFCs de consulta",
        help="RFCs adicionales que podrán consultar este COVE en VUCEM.",
    )

    # ── Datos de la factura (FacturaCove) ─────────────────────────────────────
    numero_factura_original = fields.Char(
        string="Número de factura",
        required=True,
        size=25,
        help="Folio de la factura comercial.",
    )
    certificado_origen = fields.Selection(
        CERTIFICADO_ORIGEN,
        string="Certificado de origen",
        required=True,
        default="0",
    )
    numero_exportador_autorizado = fields.Char(
        string="Núm. exportador autorizado",
        size=50,
        help="Número de exportador confiable (TLC con UE, etc.). Opcional.",
    )
    subdivision = fields.Selection(
        SUBDIVISION,
        string="Subdivisión",
        required=True,
        default="0",
        help="Indica si la factura tiene subdivisión.",
    )

    # ── Emisor ────────────────────────────────────────────────────────────────
    emisor_tipo_identificador = fields.Selection(
        TIPO_IDENTIFICADOR,
        string="Tipo identificador emisor",
        required=True,
        default="0",
    )
    emisor_identificacion = fields.Char(
        string="Identificación emisor",
        required=True,
        size=50,
        help="Tax ID, RFC, CURP o vacío si es Sin Tax ID.",
    )
    emisor_nombre = fields.Char(
        string="Nombre / razón social emisor",
        required=True,
        size=200,
    )
    emisor_apellido_paterno = fields.Char(string="Apellido paterno emisor", size=200)
    emisor_apellido_materno = fields.Char(string="Apellido materno emisor", size=200)
    # Domicilio emisor
    emisor_calle = fields.Char(string="Calle emisor", required=True, size=100)
    emisor_numero_exterior = fields.Char(string="Núm. exterior emisor", size=55)
    emisor_numero_interior = fields.Char(string="Núm. interior emisor", size=55)
    emisor_colonia = fields.Char(string="Colonia emisor", size=120)
    emisor_localidad = fields.Char(string="Localidad emisor", size=120)
    emisor_municipio = fields.Char(string="Municipio emisor", size=120)
    emisor_entidad_federativa = fields.Char(string="Entidad federativa emisor", size=30)
    emisor_pais = fields.Char(
        string="País emisor",
        required=True,
        size=120,
        help="Clave OMA del país, ej: MEX, USA, CHN.",
    )
    emisor_codigo_postal = fields.Char(string="CP emisor", size=12)

    # ── Destinatario ──────────────────────────────────────────────────────────
    dest_tipo_identificador = fields.Selection(
        TIPO_IDENTIFICADOR,
        string="Tipo identificador destinatario",
        required=True,
        default="1",
    )
    dest_identificacion = fields.Char(
        string="Identificación destinatario",
        required=True,
        size=50,
    )
    dest_nombre = fields.Char(
        string="Nombre / razón social destinatario",
        required=True,
        size=200,
    )
    dest_apellido_paterno = fields.Char(string="Apellido paterno destinatario", size=200)
    dest_apellido_materno = fields.Char(string="Apellido materno destinatario", size=200)
    # Domicilio destinatario
    dest_calle = fields.Char(string="Calle destinatario", required=True, size=100)
    dest_numero_exterior = fields.Char(string="Núm. exterior destinatario", size=55)
    dest_numero_interior = fields.Char(string="Núm. interior destinatario", size=55)
    dest_colonia = fields.Char(string="Colonia destinatario", size=120)
    dest_localidad = fields.Char(string="Localidad destinatario", size=120)
    dest_municipio = fields.Char(string="Municipio destinatario", size=120)
    dest_entidad_federativa = fields.Char(string="Entidad federativa destinatario", size=30)
    dest_pais = fields.Char(
        string="País destinatario",
        required=True,
        size=120,
    )
    dest_codigo_postal = fields.Char(string="CP destinatario", size=12)

    # ── Mercancías ────────────────────────────────────────────────────────────
    mercancia_ids = fields.One2many(
        "mx.cove.mercancia",
        "cove_id",
        string="Mercancías",
    )

    # ── Resultado VUCEM ───────────────────────────────────────────────────────
    e_document = fields.Char(
        string="e-Document (folio COVE)",
        size=13,
        readonly=True,
        help="Folio COVE asignado por VUCEM. Llega por correo y/o consulta de resultado.",
    )
    numero_operacion_vucem = fields.Char(
        string="Núm. operación VUCEM",
        readonly=True,
        help="Número devuelto en el Acuse. Usar para consultar resultado.",
    )
    acuse_hora_recepcion = fields.Datetime(string="Hora recepción VUCEM", readonly=True)
    acuse_mensaje = fields.Text(string="Mensaje VUCEM", readonly=True)
    cadena_original_guardada = fields.Text(
        string="Cadena original (auditoría)",
        readonly=True,
        groups="base.group_system",
    )

    # ── Logs ──────────────────────────────────────────────────────────────────
    log_ids = fields.One2many("mx.vucem.log", "cove_id", string="Logs VUCEM")
    log_count = fields.Integer(compute="_compute_log_count", string="Logs")

    def _compute_log_count(self):
        for rec in self:
            rec.log_count = self.env["mx.vucem.log"].search_count(
                [("cove_id", "=", rec.id)]
            )

    # ── Secuencia ─────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("Nuevo COVE")) == _("Nuevo COVE"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mx.cove") or _("Nuevo COVE")
        return super().create(vals_list)

    # ── Validaciones ──────────────────────────────────────────────────────────
    @api.constrains("observaciones")
    def _check_observaciones(self):
        for rec in self:
            if rec.observaciones and len(rec.observaciones) > 300:
                raise ValidationError("Observaciones no puede superar 300 caracteres.")

    def _validar_campos_requeridos(self):
        """Valida campos mínimos antes de transmitir."""
        self.ensure_one()
        if not self.mercancia_ids:
            raise UserError("El COVE debe tener al menos una mercancía.")
        if not self.correo_electronico:
            raise UserError("El correo electrónico es obligatorio para VUCEM.")
        if not self.credencial_id:
            raise UserError("Selecciona una credencial VUCEM antes de transmitir.")
        if not self.credencial_id.cert_file:
            raise UserError("La credencial no tiene certificado (.cer) cargado.")
        if not self.credencial_id.key_file:
            raise UserError("La credencial no tiene llave privada (.key) cargada.")
        if not self.credencial_id.ws_username or not self.credencial_id.ws_password:
            raise UserError("La credencial no tiene usuario/contraseña VUCEM configurados.")

    # ── Constructor del payload SOAP ─────────────────────────────────────────

    def _build_soap_payload(self, firma_data):
        """Construye el diccionario Python para zeep (ComprobanteValorElectronico)."""
        self.ensure_one()

        def _opt(val):
            """Devuelve None si el valor está vacío/False, para omitir el tag XML.
            Odoo devuelve False (no None) para campos de texto vacíos."""
            if not val:  # maneja None, False, "", 0
                return None
            v = str(val).strip()
            return v if v else None

        mercancias = []
        for m in self.mercancia_ids:
            mercancia = {
                "descripcionGenerica": m.descripcion_generica,
                "claveUnidadMedida": m.clave_unidad_medida,
                "tipoMoneda": m.tipo_moneda,
                "cantidad": round(m.cantidad, 3),
                "valorUnitario": round(m.valor_unitario, 6),
                "valorTotal": round(m.valor_total, 6),
                "valorDolares": round(m.valor_dolares, 4),
            }
            # DescripcionMercancia — solo si hay algún campo
            desc_especificas = []
            if any([m.marca, m.modelo, m.sub_modelo, m.numero_serie]):
                desc_especificas.append({
                    "marca": _opt(m.marca),
                    "modelo": _opt(m.modelo),
                    "subModelo": _opt(m.sub_modelo),
                    "numeroSerie": _opt(m.numero_serie),
                })
            if desc_especificas:
                mercancia["descripcionesEspecificas"] = desc_especificas
            mercancias.append(mercancia)

        comprobante = {
            "tipoOperacion": self.tipo_operacion,
            "fechaExpedicion": self.fecha_expedicion,
            "tipoFigura": int(self.tipo_figura),
            "correoElectronico": self.correo_electronico,
            "numeroFacturaOriginal": self.numero_factura_original,
            "factura": {
                "certificadoOrigen": int(self.certificado_origen),
                "subdivision": int(self.subdivision),
                "numeroExportadorAutorizado": _opt(self.numero_exportador_autorizado),
            },
            "emisor": {
                "tipoIdentificador": int(self.emisor_tipo_identificador),
                "identificacion": self.emisor_identificacion,
                "nombre": self.emisor_nombre,
                "apellidoPaterno": _opt(self.emisor_apellido_paterno),
                "apellidoMaterno": _opt(self.emisor_apellido_materno),
                "domicilio": {
                    "calle": self.emisor_calle,
                    "pais": self.emisor_pais,
                    "numeroExterior": _opt(self.emisor_numero_exterior),
                    "numeroInterior": _opt(self.emisor_numero_interior),
                    "colonia": _opt(self.emisor_colonia),
                    "localidad": _opt(self.emisor_localidad),
                    "municipio": _opt(self.emisor_municipio),
                    "entidadFederativa": _opt(self.emisor_entidad_federativa),
                    "codigoPostal": _opt(self.emisor_codigo_postal),
                },
            },
            "destinatario": {
                "tipoIdentificador": int(self.dest_tipo_identificador),
                "identificacion": self.dest_identificacion,
                "nombre": self.dest_nombre,
                "apellidoPaterno": _opt(self.dest_apellido_paterno),
                "apellidoMaterno": _opt(self.dest_apellido_materno),
                "domicilio": {
                    "calle": self.dest_calle,
                    "pais": self.dest_pais,
                    "numeroExterior": _opt(self.dest_numero_exterior),
                    "numeroInterior": _opt(self.dest_numero_interior),
                    "colonia": _opt(self.dest_colonia),
                    "localidad": _opt(self.dest_localidad),
                    "municipio": _opt(self.dest_municipio),
                    "entidadFederativa": _opt(self.dest_entidad_federativa),
                    "codigoPostal": _opt(self.dest_codigo_postal),
                },
            },
            "mercancias": mercancias,
            "firmaElectronica": {
                "certificado": firma_data["certificado_b64"],   # xsd:base64Binary
                "cadenaOriginal": firma_data["cadena_original"],
                "firma": firma_data["firma_b64"],               # xsd:base64Binary
            },
        }

        # Campos opcionales del base
        obs = _opt(self.observaciones)
        if obs:
            comprobante["observaciones"] = obs
        if self.e_document_adenda:
            comprobante["e-document"] = self.e_document_adenda
        if self.patente_aduanal_ids:
            comprobante["patenteAduanal"] = [p.patente for p in self.patente_aduanal_ids]
        if self.rfc_consulta_ids:
            comprobante["rfcConsulta"] = [r.rfc for r in self.rfc_consulta_ids]

        return {"comprobantes": comprobante}

    # ── Transmisión a VUCEM ───────────────────────────────────────────────────

    def _get_zeep_client(self):
        """Crea y devuelve un cliente zeep configurado para este COVE."""
        if not _ZEEP_OK:
            raise UserError(
                "La librería 'zeep' no está instalada.\n"
                "Ejecuta: pip install zeep --break-system-packages"
            )
        cred = self.credencial_id
        ambiente = cred.ambiente or "pruebas"
        wsdl_url = VUCEM_URLS.get(ambiente, VUCEM_URLS["pruebas"]) + "?wsdl"

        session = _requests.Session()
        session.verify = True
        transport = Transport(session=session, timeout=40)

        client = zeep.Client(
            wsdl=wsdl_url,
            wsse=UsernameToken(
                username=cred.ws_username,
                password=cred.ws_password,
                use_digest=False,
            ),
            transport=transport,
        )
        return client, ambiente

    def _registrar_log(self, tipo, ambiente, estatus, cadena=None,
                       xml_enviado=None, xml_recibido=None,
                       numero_operacion=None, e_document=None,
                       error_code=None, error_desc=None, duracion_ms=None):
        self.ensure_one()
        self.env["mx.vucem.log"].create({
            "cove_id": self.id,
            "tipo_operacion": tipo,
            "ambiente": ambiente,
            "estatus": estatus,
            "cadena_original": cadena,
            "xml_enviado": xml_enviado,
            "xml_recibido": str(xml_recibido) if xml_recibido else None,
            "numero_operacion": numero_operacion,
            "e_document": e_document,
            "error_code": error_code,
            "error_descripcion": error_desc,
            "duracion_ms": duracion_ms,
            "credencial_id": self.credencial_id.id,
        })

    def action_transmitir_cove(self):
        """Acción principal: firmar y transmitir el COVE a VUCEM."""
        self.ensure_one()
        self._validar_campos_requeridos()

        # 1. Generar firma
        try:
            firma_data = self._firmar_cove(self, self.credencial_id)
        except (UserError, Exception) as exc:
            self._registrar_log(
                "registrar_cove",
                self.credencial_id.ambiente or "pruebas",
                "error_firma",
                error_desc=str(exc),
            )
            raise

        # 2. Construir payload
        payload = self._build_soap_payload(firma_data)

        # 3. Transmitir
        client, ambiente = self._get_zeep_client()
        t0 = time.time()
        try:
            respuesta = client.service.RecibirCove(**payload)
            duracion = int((time.time() - t0) * 1000)
        except Exception as exc:
            duracion = int((time.time() - t0) * 1000)
            estatus = "timeout" if "timeout" in str(exc).lower() else "error_red"
            self._registrar_log(
                "registrar_cove", ambiente, estatus,
                cadena=firma_data["cadena_original"],
                xml_recibido=str(exc),
                duracion_ms=duracion,
                error_desc=str(exc),
            )
            raise UserError(
                f"Error al conectar con VUCEM: {exc}\n\n"
                "Verifica la URL del webservice y que el puerto 8110 esté abierto."
            ) from exc

        # 4. Procesar respuesta (Acuse)
        num_op = str(getattr(respuesta, "numeroDeOperacion", "") or "")
        hora = getattr(respuesta, "horaRecepcion", None)
        mensaje = str(getattr(respuesta, "mensajeInformativo", "") or "")

        self.write({
            "estado": "enviado",
            "numero_operacion_vucem": num_op,
            "acuse_hora_recepcion": hora,
            "acuse_mensaje": mensaje,
            "cadena_original_guardada": firma_data["cadena_original"],
        })

        self._registrar_log(
            "registrar_cove", ambiente, "exitoso",
            cadena=firma_data["cadena_original"],
            xml_recibido=str(respuesta),
            numero_operacion=num_op,
            duracion_ms=duracion,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("COVE enviado"),
                "message": _(
                    "Núm. operación: %s\n%s\n\n"
                    "El e-document llegará al correo indicado. "
                    "Usa 'Consultar resultado' cuando lo recibas."
                ) % (num_op, mensaje),
                "type": "success",
                "sticky": True,
            },
        }

    def action_consultar_resultado(self):
        """Consulta el resultado de la transmisión en VUCEM usando el núm. de operación."""
        self.ensure_one()
        if not self.numero_operacion_vucem:
            raise UserError("No hay número de operación VUCEM. Transmite primero el COVE.")
        if not _ZEEP_OK:
            raise UserError("La librería 'zeep' no está instalada.")

        import base64 as _base64
        cred = self.credencial_id
        cert_bytes = _base64.b64decode(cred.cert_file)
        key_bytes = _base64.b64decode(cred.key_file)
        private_key = self._firma_load_private_key(key_bytes, cred.key_password)

        # Cadena original para consulta: |numOperacion|RFC|
        rfc = cred.ws_username  # El RFC es el usuario VUCEM
        cadena = self._build_cadena_consulta(self.numero_operacion_vucem, rfc)
        firma_b64 = self._firma_sign_b64(private_key, cadena)
        cert_b64 = self._firma_cert_to_b64(cert_bytes)

        ambiente = cred.ambiente or "pruebas"
        consulta_wsdl = VUCEM_CONSULTA_URLS.get(ambiente) + "?wsdl"

        session = _requests.Session()
        transport = Transport(session=session, timeout=40)
        client = zeep.Client(
            wsdl=consulta_wsdl,
            wsse=UsernameToken(cred.ws_username, cred.ws_password, use_digest=False),
            transport=transport,
        )

        t0 = time.time()
        try:
            respuesta = client.service.ConsultarRespuestaCove(
                numeroOperacion=self.numero_operacion_vucem,
                certificado=cert_b64,
                cadenaOriginal=cadena,
                firma=firma_b64,
            )
            duracion = int((time.time() - t0) * 1000)
        except Exception as exc:
            duracion = int((time.time() - t0) * 1000)
            self._registrar_log(
                "consultar_resultado", ambiente, "error_red",
                cadena=cadena, error_desc=str(exc), duracion_ms=duracion,
            )
            raise UserError(f"Error al consultar VUCEM: {exc}") from exc

        # Extraer e-document de la respuesta
        e_doc = str(getattr(respuesta, "eDocument", "") or "").strip() or False
        errores = str(getattr(respuesta, "errores", "") or "").strip()

        vals = {"acuse_mensaje": str(respuesta)}
        if e_doc:
            vals["e_document"] = e_doc
            vals["estado"] = "con_edocument"

        self.write(vals)
        self._registrar_log(
            "consultar_resultado", ambiente,
            "exitoso" if e_doc else "error_vucem",
            cadena=cadena,
            xml_recibido=str(respuesta),
            e_document=e_doc,
            error_desc=errores or None,
            duracion_ms=duracion,
        )

        msg = f"e-Document: {e_doc}" if e_doc else f"Sin e-document aún. Errores: {errores}"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Consulta VUCEM"),
                "message": msg,
                "type": "success" if e_doc else "warning",
                "sticky": bool(e_doc),
            },
        }

    def action_ver_logs(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Logs VUCEM"),
            "res_model": "mx.vucem.log",
            "view_mode": "list,form",
            "domain": [("cove_id", "=", self.id)],
            "context": {"default_cove_id": self.id},
        }
