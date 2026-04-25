# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MxTigieMaestra(models.Model):
    """
    Tabla Maestra Unificada de la TIGIE (Tarifa de la Ley de los Impuestos
    Generales de Importacion y Exportacion).

    Cada fila representa una combinacion unica fraccion + NICO, identificada
    por la clave 'llave_10' (8 digitos de fraccion + 2 de NICO, p. ej.
    "0101210001").  Es el modelo de referencia para el campo fraccion_id en
    las partidas de pedimento y en las lineas de cotizacion.

    Disenado para importacion masiva via CSV desde Odoo (import-compatible):
    la columna 'llave_10' actua como ID externo funcional gracias al
    sql_constraint UNIQUE.
    """

    _name = "mx.tigie.maestra"
    _description = "TIGIE - Tabla Maestra Unificada"
    _rec_name = "display_name"
    _order = "llave_10"

    # ── Identificadores ──────────────────────────────────────────────────────

    llave_10 = fields.Char(
        string="Llave (10 dig.)",
        required=True,
        size=10,
        index=True,
        help="Clave unica de 10 caracteres: 8 digitos de fraccion + 2 de NICO. "
             "Ejemplo: '0101210001' (fraccion 01012100, NICO 01). "
             "Actua como ID funcional para importaciones CSV.",
    )
    fraccion_8 = fields.Char(
        string="Fraccion (8)",
        size=8,
        required=True,
        index=True,
        help="Fraccion arancelaria de 8 digitos segun la TIGIE.",
    )
    nico = fields.Char(
        string="NICO",
        size=2,
        help="Numero de identificacion comercial (NICO). Vacio si no aplica.",
    )

    # ── Descripcion ──────────────────────────────────────────────────────────

    descripcion_completa = fields.Text(
        string="Descripcion",
        required=True,
        help="Descripcion oficial de la mercancia segun la TIGIE.",
    )

    # ── Unidad de medida ─────────────────────────────────────────────────────

    unidad_medida = fields.Char(
        string="UMT",
        size=10,
        help="Clave de Unidad de Medida de Tarifa (UMT) segun la TIGIE. "
             "Ejemplo: 'KG', 'PZ', 'MT'.",
    )

    # ── Aranceles ────────────────────────────────────────────────────────────

    arancel_importacion = fields.Float(
        string="Arancel importacion (%)",
        digits=(16, 6),
        help="Tasa advalorem de IGI (Impuesto General de Importacion) en porcentaje.",
    )
    arancel_exportacion = fields.Float(
        string="Arancel exportacion (%)",
        digits=(16, 6),
        help="Tasa advalorem de IGE (Impuesto General de Exportacion) en porcentaje.",
    )
    iva_importacion = fields.Float(
        string="IVA importacion (%)",
        digits=(16, 6),
        default=16.0,
        help="Tasa de IVA aplicable a la importacion. Por defecto 16%.",
    )

    # ── Regulaciones ─────────────────────────────────────────────────────────

    regulaciones_economia = fields.Text(
        string="Regulaciones SE / COFEPRIS",
        help="NOMs, RRNAs y permisos de la Secretaria de Economia y COFEPRIS "
             "aplicables segun la TIGIE. Texto libre separado por comas o saltos de linea.",
    )
    otras_dependencias = fields.Text(
        string="Otras dependencias",
        help="Requisitos regulatorios de otras dependencias (SADER, SENER, SAT, etc.).",
    )
    requires_labeling_default = fields.Boolean(
        string="Etiquetado requerido",
        help="Indica si esta fraccion requiere etiquetado NOM por defecto.",
    )

    active = fields.Boolean(default=True)

    # ── Campos calculados ────────────────────────────────────────────────────

    display_name = fields.Char(
        string="Nombre completo",
        compute="_compute_display_name",
        store=True,
        index=True,
    )

    # Campos de compatibilidad: mantienen la interfaz del antiguo mx.ped.fraccion
    # para que el resto del modulo no necesite cambios masivos.
    code = fields.Char(
        string="Codigo fraccion",
        compute="_compute_compat_fields",
        store=True,
        index=True,
        help="Alias de fraccion_8 — campo de compatibilidad con mx.ped.fraccion.",
    )
    capitulo = fields.Char(
        string="Capitulo",
        compute="_compute_compat_fields",
        store=True,
        size=2,
        help="Primeros 2 digitos de la fraccion (capitulo arancelario).",
    )

    # ── Restricciones SQL ────────────────────────────────────────────────────

    _sql_constraints = [
        (
            "mx_tigie_maestra_llave_10_uniq",
            "unique(llave_10)",
            "La llave_10 debe ser unica en la TIGIE maestra.",
        ),
    ]

    # ── Computes ─────────────────────────────────────────────────────────────

    @api.depends("llave_10", "fraccion_8", "nico", "descripcion_completa")
    def _compute_display_name(self):
        for rec in self:
            clave = rec.llave_10 or rec.fraccion_8 or ""
            if rec.descripcion_completa:
                snippet = (rec.descripcion_completa or "")[:80].replace("\n", " ")
                rec.display_name = f"{clave} {snippet}".strip()
            else:
                rec.display_name = clave

    @api.depends("fraccion_8")
    def _compute_compat_fields(self):
        for rec in self:
            rec.code = rec.fraccion_8 or ""
            raw = (rec.fraccion_8 or "")
            rec.capitulo = raw[:2] if len(raw) >= 2 else (raw or False)

    # ── Busqueda por nombre ──────────────────────────────────────────────────

    @api.model
    def _name_search(self, name, domain=None, operator="ilike", limit=100, order=None):
        domain = list(domain or [])
        if name:
            name_stripped = (name or "").strip()
            domain = [
                "|", "|", "|",
                ("llave_10", operator, name_stripped),
                ("fraccion_8", operator, name_stripped),
                ("nico", operator, name_stripped),
                ("descripcion_completa", operator, name_stripped),
            ] + domain
        return self._search(domain, limit=limit, order=order)
