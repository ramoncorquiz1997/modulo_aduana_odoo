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
    active = fields.Boolean(default=True)

    display_name = fields.Char(compute="_compute_display_name")

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
    note = fields.Char(string="Nota")

    _sql_constraints = [
        (
            "mx_ped_fraccion_tasa_uniq",
            "unique(fraccion_id, tipo_operacion, territorio)",
            "Ya existe una tasa para esa Fraccion / Tipo operacion / Territorio.",
        ),
    ]
