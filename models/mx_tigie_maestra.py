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
    sql_constraint UNIQUE.  Los campos 'fraccion_8' y 'nico' se auto-derivan
    de 'llave_10' en create/write si no se proporcionan explicitamente.
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
        index=True,
        help="Fraccion arancelaria de 8 digitos segun la TIGIE. "
             "Se auto-deriva de llave_10[:8] si no se proporciona.",
    )
    nico = fields.Char(
        string="NICO",
        size=2,
        help="Numero de identificacion comercial (NICO). "
             "Se auto-deriva de llave_10[8:] si no se proporciona.",
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
        help="Tasa advalorem de IGI en porcentaje. "
             "0.0 cuando la fraccion es exenta o tiene cuota especial (ver nota).",
    )
    nota_importacion = fields.Char(
        string="Nota arancel importacion",
        help="Texto del arancel cuando no es advalorem puro: 'Ex.' (exento), "
             "'AMX (...)' (cuota mixta), 'AE (...)' (arancel especifico), etc.",
    )
    arancel_exportacion = fields.Float(
        string="Arancel exportacion (%)",
        digits=(16, 6),
        help="Tasa advalorem de IGE en porcentaje. "
             "0.0 cuando la fraccion es exenta o esta prohibida (ver nota).",
    )
    nota_exportacion = fields.Char(
        string="Nota arancel exportacion",
        help="Texto del arancel cuando no es advalorem puro: 'Ex.' (exento), "
             "'Prohibida', etc.",
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

    # ── ORM create / write ───────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._auto_fill_from_llave(vals)
        return super().create(vals_list)

    def write(self, vals):
        if "llave_10" in vals and "fraccion_8" not in vals:
            self._auto_fill_from_llave(vals)
        return super().write(vals)

    @staticmethod
    def _auto_fill_from_llave(vals):
        """Deriva fraccion_8 y nico de llave_10 cuando no se proporcionan."""
        llave = (vals.get("llave_10") or "").strip()
        if len(llave) == 10:
            if not vals.get("fraccion_8"):
                vals["fraccion_8"] = llave[:8]
            if "nico" not in vals:
                vals["nico"] = llave[8:]

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
