# -*- coding: utf-8 -*-
"""
Mixin de firma electrónica para VUCEM (COVE).

Especificaciones confirmadas contra XSD (RecibirCove.xsd) y XMLs de ejemplo oficiales:
  - Estándar de firma : PKCS7 / RSA con SHA1
  - Algoritmo digestión: SHA1  (NO SHA256)
  - Certificado (.cer) : leer bytes → Base64  (xsd:base64Binary — el manual decía hex, ESTÁ MAL)
  - Firma              : bytes RSA → Base64   (xsd:base64Binary — el manual decía hex, ESTÁ MAL)
  - Cadena original    : codificar como ISO-8859-1 antes de firmar

Orden de campos en la cadena para mercancías (confirmado en XMLs de ejemplo oficiales):
  descripcionGenerica | claveUnidadMedida | tipoMoneda | cantidad | valorUnitario | valorTotal | valorDolares
  (tipoMoneda va ANTES de cantidad, igual que el orden en el XSD)
"""
import base64
import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ── Importaciones opcionales ─────────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False
    _logger.warning("librería 'cryptography' no disponible — firma VUCEM deshabilitada")


class MxFirmaDigital(models.AbstractModel):
    """AbstractModel que provee utilidades de firma electrónica FIEL/e.firma
    para transmisión a VUCEM.  Incluir con _inherit en los modelos que
    necesiten firmar (mx.cove, mx.doda, etc.).
    """
    _name = "mx.firma.digital"
    _description = "Mixin — Firma Digital VUCEM"

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _firma_check_crypto(self):
        if not _CRYPTO_OK:
            raise UserError(
                "La librería 'cryptography' no está instalada en el servidor.\n"
                "Ejecuta: pip install cryptography --break-system-packages"
            )

    def _firma_load_private_key(self, key_bytes, key_password=None):
        """Carga la llave privada DER (.key del SAT).

        Args:
            key_bytes   : contenido binario del archivo .key
            key_password: contraseña de la llave (str o None)

        Returns:
            RSAPrivateKey
        """
        self._firma_check_crypto()
        pwd = key_password.encode("utf-8") if key_password else None
        try:
            return serialization.load_der_private_key(key_bytes, password=pwd)
        except Exception as exc:
            raise UserError(
                f"No se pudo cargar la llave privada (.key).\n"
                f"Verifica que el archivo y la contraseña sean correctos.\n"
                f"Detalle: {exc}"
            ) from exc

    @staticmethod
    def _firma_cert_to_b64(cert_bytes):
        """Convierte los bytes del certificado .cer a Base64.

        El XSD declara: <xsd:element name="certificado" type="xsd:base64Binary">
        Los XMLs de ejemplo oficiales confirman Base64 (NO hex como indicaba el manual).
        """
        return base64.b64encode(cert_bytes).decode("ascii")

    @staticmethod
    def _firma_sign_b64(private_key, cadena_str):
        """Firma la cadena original y devuelve la firma en Base64.

        Proceso:
          1. Codificar la cadena como ISO-8859-1 (requerido por VUCEM)
          2. Firmar con SHA1 + RSA PKCS1v15
          3. Convertir bytes resultado a Base64

        El XSD declara: <xsd:element name="firma" type="xsd:base64Binary">
        Los XMLs de ejemplo oficiales confirman Base64 (NO hex como indicaba el manual).

        Args:
            private_key : RSAPrivateKey cargado con _firma_load_private_key
            cadena_str  : cadena original (str) ya armada

        Returns:
            str  Base64 de la firma
        """
        try:
            cadena_bytes = cadena_str.encode("iso-8859-1")
        except UnicodeEncodeError as exc:
            raise UserError(
                "La cadena original contiene caracteres que no pueden "
                "codificarse en ISO-8859-1. Revisa los campos de texto "
                "(descripción, nombre, dirección).\n"
                f"Detalle: {exc}"
            ) from exc

        try:
            firma_bytes = private_key.sign(
                cadena_bytes,
                asym_padding.PKCS1v15(),
                hashes.SHA1(),  # noqa: S303 — VUCEM exige SHA1
            )
        except Exception as exc:
            raise UserError(
                f"Error al firmar con la llave privada: {exc}"
            ) from exc

        return base64.b64encode(firma_bytes).decode("ascii")

    # ── Constructor de cadena original COVE (RecibirCove) ────────────────────

    @staticmethod
    def _co_val(value, strip_zeros=True):
        """Normaliza un valor para la cadena original.
        Si es None / False / vacío → devuelve '' (campo omitido con pipe vacío).
        Odoo devuelve False (no None) para campos de texto vacíos.
        """
        if not value and value != 0:  # maneja None, False, ""
            return ""
        v = str(value).strip()
        return v

    @staticmethod
    def _co_decimal(value, decimals):
        """Formatea un número con exactamente N decimales para la cadena original.

        Formatos VUCEM (pág. 62 manual):
          cantidad      : ###########0.000   (3 dec)
          valorUnitario : ################0.000000  (6 dec)
          valorTotal    : ################0.000000  (6 dec)
          valorDolares  : ###########0.0000  (4 dec)

        Regla: el valor en el XML y en la cadena deben ser IDÉNTICOS
        (sin ceros al frente, sin espacios).
        """
        if value is None:
            return ""
        fmt = f"{{:.{decimals}f}}"
        return fmt.format(float(value))

    def _build_cadena_cove(self, cove):
        """Construye la cadena original pipe-separated para un mx.cove.

        Estructura (Manual VUCEM pág. 61):
          COVE sin Relación de facturas:
          Datos del comprobante | Factura COVE | Emisor | Dom. emisor |
          Destinatario | Dom. destinatario | [Mercancía]* |

        Returns:
            str — cadena original lista para firmar
        """
        p = self._co_val  # alias corto

        partes = []

        # ── Datos del comprobante ─────────────────────────────────────────
        # |tipoOperacion|numFactura|relacionFactura|fechaExpedicion|tipoFigura|observaciones|
        # Confirmado contra cadena oficial: simple COVE lleva "0", relación de facturas lleva "1"
        partes.append(p(cove.tipo_operacion))
        partes.append(p(cove.numero_factura_original))
        partes.append("0")  # relacionFactura: 0 = COVE simple (sin relación de facturas)
        fecha = cove.fecha_expedicion.strftime("%Y-%m-%d") if cove.fecha_expedicion else ""
        partes.append(fecha)
        partes.append(p(cove.tipo_figura))
        partes.append(p(cove.observaciones))

        # [RFC Consulta]*
        for rfc in (cove.rfc_consulta_ids or []):
            partes.append(p(rfc.rfc))

        # [Patente Aduanal]*
        for pat in (cove.patente_aduanal_ids or []):
            partes.append(p(pat.patente))

        # ── Factura COVE ──────────────────────────────────────────────────
        # |subdivision|certificadoOrigen|numExportadorConfiable
        partes.append(p(cove.subdivision))
        partes.append(p(cove.certificado_origen))
        partes.append(p(cove.numero_exportador_autorizado))

        # ── Emisor ────────────────────────────────────────────────────────
        partes.append(p(cove.emisor_tipo_identificador))
        partes.append(p(cove.emisor_identificacion))
        partes.append(p(cove.emisor_apellido_paterno))
        partes.append(p(cove.emisor_apellido_materno))
        partes.append(p(cove.emisor_nombre))

        # Domicilio emisor
        partes.append(p(cove.emisor_calle))
        partes.append(p(cove.emisor_numero_exterior))
        partes.append(p(cove.emisor_numero_interior))
        partes.append(p(cove.emisor_colonia))
        partes.append(p(cove.emisor_localidad))
        partes.append(p(cove.emisor_municipio))
        partes.append(p(cove.emisor_entidad_federativa))
        partes.append(p(cove.emisor_pais))
        partes.append(p(cove.emisor_codigo_postal))

        # ── Destinatario ──────────────────────────────────────────────────
        partes.append(p(cove.dest_tipo_identificador))
        partes.append(p(cove.dest_identificacion))
        partes.append(p(cove.dest_apellido_paterno))
        partes.append(p(cove.dest_apellido_materno))
        partes.append(p(cove.dest_nombre))

        # Domicilio destinatario
        partes.append(p(cove.dest_calle))
        partes.append(p(cove.dest_numero_exterior))
        partes.append(p(cove.dest_numero_interior))
        partes.append(p(cove.dest_colonia))
        partes.append(p(cove.dest_localidad))
        partes.append(p(cove.dest_municipio))
        partes.append(p(cove.dest_entidad_federativa))
        partes.append(p(cove.dest_pais))
        partes.append(p(cove.dest_codigo_postal))

        # ── Mercancías ────────────────────────────────────────────────────
        # Orden confirmado en XMLs oficiales y XSD:
        # descripcion | claveUM | tipoMoneda | cantidad | valorUnitario | valorTotal | valorDolares
        # (tipoMoneda va ANTES de cantidad)
        for m in cove.mercancia_ids:
            partes.append(p(m.descripcion_generica))
            partes.append(p(m.clave_unidad_medida))
            partes.append(p(m.tipo_moneda))                        # tipoMoneda primero
            partes.append(self._co_decimal(m.cantidad, 3))         # luego cantidad
            partes.append(self._co_decimal(m.valor_unitario, 6))
            partes.append(self._co_decimal(m.valor_total, 6))
            partes.append(self._co_decimal(m.valor_dolares, 4))

            # Descripciones específicas (marca/modelo/serie) — opcionales
            tiene_detalle = any([m.marca, m.modelo, m.sub_modelo, m.numero_serie])
            if tiene_detalle:
                partes.append(p(m.marca))
                partes.append(p(m.modelo))
                partes.append(p(m.sub_modelo))
                partes.append(p(m.numero_serie))

        # La cadena empieza y termina con pipe
        return "|" + "|".join(partes) + "|"

    def _build_cadena_consulta(self, numero_operacion, rfc):
        """Cadena original para ConsultarRespuestaCOVEService.

        Formato (pág. 74 manual): |numOperacion|RFC|
        Ejemplo: |110114|GWT921026L97|
        """
        return f"|{numero_operacion}|{rfc}|"

    # ── Método principal: firmar COVE completo ────────────────────────────────

    def _firmar_cove(self, cove, credencial):
        """Genera cadena original, firma y devuelve el dict para FirmaElectronica.

        Args:
            cove       : record mx.cove
            credencial : record mx.ped.credencial.ws (tiene cert_file, key_file, key_password)

        Returns:
            dict con claves: cadena_original, certificado_b64, firma_b64
            (certificado y firma en Base64 conforme xsd:base64Binary del XSD oficial)
        """
        self._firma_check_crypto()

        if not credencial.cert_file:
            raise UserError("La credencial no tiene certificado (.cer) cargado.")
        if not credencial.key_file:
            raise UserError("La credencial no tiene llave privada (.key) cargada.")

        cert_bytes = base64.b64decode(credencial.cert_file)
        key_bytes = base64.b64decode(credencial.key_file)

        private_key = self._firma_load_private_key(key_bytes, credencial.key_password)
        cadena = self._build_cadena_cove(cove)
        firma_b64 = self._firma_sign_b64(private_key, cadena)
        cert_b64 = self._firma_cert_to_b64(cert_bytes)

        return {
            "cadena_original": cadena,
            "certificado_b64": cert_b64,
            "firma_b64": firma_b64,
        }
