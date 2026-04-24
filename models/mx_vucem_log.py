# -*- coding: utf-8 -*-
"""
Log de transmisiones VUCEM.

Registra cada intento de comunicación con el webservice de VUCEM:
XML enviado, respuesta recibida, errores, tiempos y credencial usada.
Sirve como trazabilidad y para diagnóstico de errores.
"""
from odoo import fields, models


class MxVucemLog(models.Model):
    _name = "mx.vucem.log"
    _description = "Log de transmisión VUCEM"
    _order = "timestamp desc, id desc"
    _rec_name = "display_name_computed"

    # ── Referencia al documento origen ───────────────────────────────────────
    cove_id = fields.Many2one(
        "mx.cove",
        string="COVE",
        ondelete="set null",
        index=True,
    )

    # ── Tipo de operación ─────────────────────────────────────────────────────
    tipo_operacion = fields.Selection(
        [
            ("registrar_cove", "Registrar COVE"),
            ("consultar_resultado", "Consultar resultado"),
            ("registrar_relacion_ia", "Registrar Relación IA"),
            ("registrar_relacion_no_ia", "Registrar Relación No IA"),
        ],
        string="Operación",
        required=True,
    )
    ambiente = fields.Selection(
        [("pruebas", "Pruebas"), ("produccion", "Producción")],
        string="Ambiente",
        required=True,
    )

    # ── Payload ───────────────────────────────────────────────────────────────
    cadena_original = fields.Text(
        string="Cadena original",
        help="Cadena pipe-separated enviada para firma.",
    )
    xml_enviado = fields.Text(
        string="XML enviado",
        help="XML / payload SOAP completo enviado a VUCEM.",
    )
    xml_recibido = fields.Text(
        string="XML / respuesta recibida",
        help="Respuesta SOAP cruda devuelta por VUCEM.",
    )

    # ── Resultado ─────────────────────────────────────────────────────────────
    estatus = fields.Selection(
        [
            ("exitoso", "Exitoso"),
            ("error_vucem", "Error VUCEM"),
            ("error_firma", "Error de firma"),
            ("error_xsd", "Error XSD / validación"),
            ("timeout", "Timeout"),
            ("error_red", "Error de red"),
            ("error_config", "Error de configuración"),
        ],
        string="Estatus",
        required=True,
    )
    numero_operacion = fields.Char(
        string="Núm. operación VUCEM",
        help="Número devuelto por VUCEM en el Acuse. Usar para consultar resultado.",
    )
    e_document = fields.Char(
        string="e-Document",
        help="Folio COVE asignado por VUCEM (disponible tras consultar resultado).",
    )
    error_code = fields.Char(string="Código de error", size=50)
    error_descripcion = fields.Text(string="Descripción del error")

    # ── Metadatos ─────────────────────────────────────────────────────────────
    timestamp = fields.Datetime(
        string="Fecha / hora",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )
    duracion_ms = fields.Integer(
        string="Duración (ms)",
        help="Tiempo de respuesta del webservice en milisegundos.",
    )
    credencial_id = fields.Many2one(
        "mx.ped.credencial.ws",
        string="Credencial usada",
        ondelete="set null",
    )

    display_name_computed = fields.Char(
        string="Nombre",
        compute="_compute_display_name_computed",
        store=False,
    )

    def _compute_display_name_computed(self):
        for rec in self:
            tipo = dict(self._fields["tipo_operacion"].selection).get(
                rec.tipo_operacion, rec.tipo_operacion or ""
            )
            ts = rec.timestamp.strftime("%Y-%m-%d %H:%M") if rec.timestamp else ""
            rec.display_name_computed = f"{tipo} — {ts}"
