# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedUm(models.Model):
    _name = "mx.ped.um"
    _description = "Catalogo UM"
    _order = "code"

    code = fields.Char(string="Clave", required=True, size=10, index=True)
    name = fields.Char(string="Descripcion", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("mx_ped_um_code_uniq", "unique(code)", "La clave de UM debe ser unica."),
    ]


class MxPedFraccion(models.Model):
    _name = "mx.ped.fraccion"
    _description = "Catalogo de Fracciones Arancelarias"
    _rec_name = "display_name"
    _order = "code, nico"

    code = fields.Char(string="Fraccion", required=True, size=8, index=True)
    nico = fields.Char(string="NICO", size=2, index=True)
    name = fields.Text(string="Descripcion", required=True)

    seccion = fields.Char(string="Seccion")
    capitulo = fields.Char(string="Capitulo", size=2)
    partida = fields.Char(string="Partida", size=4)
    subpartida = fields.Char(string="Subpartida", size=6)

    um_id = fields.Many2one("mx.ped.um", string="Unidad de medida")
    tasa_ids = fields.One2many("mx.ped.fraccion.tasa", "fraccion_id", string="Tasas")
    nico_ids = fields.One2many("mx.nico", "fraccion_id", string="NICOs")
    nom_default_ids = fields.Many2many(
        "mx.nom",
        "mx_ped_fraccion_nom_default_rel",
        "fraccion_id",
        "nom_id",
        string="NOM sugeridas",
    )
    rrna_default_ids = fields.Many2many(
        "mx.rrna",
        "mx_ped_fraccion_rrna_default_rel",
        "fraccion_id",
        "rrna_id",
        string="RRNA sugeridas",
    )
    permiso_default_ids = fields.Many2many(
        "mx.permiso",
        "mx_ped_fraccion_permiso_default_rel",
        "fraccion_id",
        "permiso_id",
        string="Permisos sugeridos",
    )
    requires_labeling_default = fields.Boolean(string="Etiquetado sugerido")
    fraccion_anterior = fields.Char(string="Fraccion anterior", size=10, index=True)
    descripcion_especifica = fields.Text(string="Descripcion especifica")
    nota_especial = fields.Text(string="Nota especial")
    decretos_text = fields.Text(string="Decretos")
    historico_text = fields.Text(string="Historico")
    tlc_notes = fields.Text(string="Notas TLC")
    correlation_tigie = fields.Text(string="Correlacion TIGIE")
    correlation_tlc = fields.Text(string="Correlacion TLC")
    note_aladi = fields.Text(string="Notas ALADI")
    measure_code = fields.Char(string="Medida base", size=10)
    cuota_especial = fields.Float(string="Cuota especial", digits=(16, 6))
    cuota_um = fields.Char(string="Unidad cuota", size=10)
    sector_padron_code = fields.Char(string="Padron sectorial", size=32)
    note_annexes = fields.Text(string="Notas de anexos")
    precio_estimado_aplica = fields.Boolean(string="Precios estimados")
    padron_sectorial_aplica = fields.Boolean(string="Padron sectorial")
    avisos_automaticos_aplica = fields.Boolean(string="Avisos automaticos")
    prohibida = fields.Boolean(string="Fraccion prohibida")
    vulnerable = fields.Boolean(string="Mercancia vulnerable")
    decreto_aplica = fields.Boolean(string="Decretos")
    tlc_aplica = fields.Boolean(string="TLC")
    aladi_aplica = fields.Boolean(string="ALADI")
    aap_aplica = fields.Boolean(string="AAP")
    anexo_21_aplica = fields.Boolean(string="Anexo 21")
    anexo_23_aplica = fields.Boolean(string="Anexo 23")
    anexo_24_aplica = fields.Boolean(string="Anexo 24")
    anexo_29_aplica = fields.Boolean(string="Anexo 29")
    anexo_30_aplica = fields.Boolean(string="Anexo 30")
    active = fields.Boolean(default=True)

    display_name = fields.Char(compute="_compute_display_name")
    nom_aplica = fields.Boolean(compute="_compute_regulatory_flags", store=True)
    permiso_aplica = fields.Boolean(compute="_compute_regulatory_flags", store=True)
    rrna_aplica = fields.Boolean(compute="_compute_regulatory_flags", store=True)
    igi_importacion_general = fields.Float(
        string="Advalorem importacion",
        digits=(16, 6),
        compute="_compute_default_import_profile",
        store=True,
    )
    iva_importacion_general = fields.Float(
        string="IVA importacion",
        digits=(16, 6),
        compute="_compute_default_import_profile",
        store=True,
    )
    ieps_importacion_general = fields.Float(
        string="IEPS importacion",
        digits=(16, 6),
        compute="_compute_default_import_profile",
        store=True,
    )
    import_note = fields.Char(
        string="Nota importacion",
        compute="_compute_default_import_profile",
        store=True,
    )

    _sql_constraints = [
        (
            "mx_ped_fraccion_code_nico_uniq",
            "unique(code, nico)",
            "La combinacion Fraccion + NICO debe ser unica.",
        ),
    ]

    @api.depends("code", "nico", "name")
    def _compute_display_name(self):
        for rec in self:
            label = rec.code or ""
            if rec.nico:
                label = f"{label}-{rec.nico}"
            if rec.name:
                label = f"{label} {rec.name}"
            rec.display_name = label.strip()

    @api.depends("nom_default_ids", "permiso_default_ids", "rrna_default_ids")
    def _compute_regulatory_flags(self):
        for rec in self:
            rec.nom_aplica = bool(rec.nom_default_ids)
            rec.permiso_aplica = bool(rec.permiso_default_ids)
            rec.rrna_aplica = bool(rec.rrna_default_ids)

    @api.depends("tasa_ids", "tasa_ids.tipo_operacion", "tasa_ids.territorio", "tasa_ids.igi", "tasa_ids.iva", "tasa_ids.ieps", "tasa_ids.note")
    def _compute_default_import_profile(self):
        for rec in self:
            tasa = rec.tasa_ids.filtered(
                lambda t: t.tipo_operacion == "importacion" and t.territorio == "general"
            )[:1]
            if not tasa:
                tasa = rec.tasa_ids.filtered(lambda t: t.tipo_operacion == "importacion")[:1]
            rec.igi_importacion_general = tasa.igi if tasa else 0.0
            rec.iva_importacion_general = tasa.iva if tasa else 0.0
            rec.ieps_importacion_general = tasa.ieps if tasa else 0.0
            rec.import_note = tasa.note if tasa else False

    @api.constrains("code", "nico")
    def _check_numeric_lengths(self):
        for rec in self:
            code = (rec.code or "").strip()
            nico = (rec.nico or "").strip()
            if code and (not code.isdigit() or len(code) != 8):
                raise ValidationError("La fraccion debe tener exactamente 8 digitos numericos.")
            if nico and (not nico.isdigit() or len(nico) != 2):
                raise ValidationError("El NICO debe tener exactamente 2 digitos numericos.")


class MxPedFraccionTasa(models.Model):
    _name = "mx.ped.fraccion.tasa"
    _description = "Tasas por Fraccion"
    _order = "fraccion_id, tipo_operacion, territorio"

    fraccion_id = fields.Many2one("mx.ped.fraccion", required=True, ondelete="cascade", index=True)
    tipo_operacion = fields.Selection(
        [("importacion", "Importacion"), ("exportacion", "Exportacion")],
        required=True,
    )
    territorio = fields.Selection(
        [
            ("general", "General"),
            ("frontera", "Frontera"),
            ("franja", "Franja"),
            ("region", "Region"),
        ],
        required=True,
        default="general",
    )
    igi = fields.Float(string="IGI (%)", digits=(16, 6))
    iva = fields.Float(string="IVA (%)", digits=(16, 6))
    ieps = fields.Float(string="IEPS (%)", digits=(16, 6))
    note = fields.Char(string="Nota")

    _sql_constraints = [
        (
            "mx_ped_fraccion_tasa_uniq",
            "unique(fraccion_id, tipo_operacion, territorio)",
            "Ya existe una tasa para esa Fraccion / Tipo operacion / Territorio.",
        ),
    ]
