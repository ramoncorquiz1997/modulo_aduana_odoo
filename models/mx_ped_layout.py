# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedLayout(models.Model):
    _name = "mx.ped.layout"
    _description = "Layout de Pedimento"
    _order = "name asc, id asc"

    name = fields.Char(string="Nombre", required=True)
    version = fields.Char(string="Versión")
    active = fields.Boolean(default=True)
    export_format = fields.Selection(
        [
            ("positional", "Posicional (por posiciones)"),
            ("pipe", "Separado por | (pipes)"),
        ],
        string="Formato de exportación",
        default="positional",
        required=True,
    )
    field_separator = fields.Char(
        string="Separador de campos",
        default="|",
        help="Usado cuando el formato es separado por pipes.",
    )
    record_separator = fields.Char(
        string="Separador de registros",
        default="\n",
        help="Usado para separar registros en el TXT.",
    )
    file_name_pattern = fields.Char(
        string="Patrón de nombre de archivo",
        help="Ej: m{patente}{seq:03d}.{julian_day:03d}",
    )

    registro_ids = fields.One2many(
        comodel_name="mx.ped.layout.registro",
        inverse_name="layout_id",
        string="Registros",
        copy=True,
    )


class MxPedLayoutRegistro(models.Model):
    _name = "mx.ped.layout.registro"
    _description = "Layout - Registro"
    _order = "orden asc, codigo asc, id asc"
    _rec_name = "codigo"

    layout_id = fields.Many2one(
        "mx.ped.layout",
        string="Layout",
        required=True,
        ondelete="cascade",
        index=True,
    )
    codigo = fields.Char(string="Código", required=True)
    nombre = fields.Char(string="Nombre")
    orden = fields.Integer(default=10)
    requerido = fields.Boolean(default=False)

    campo_ids = fields.One2many(
        comodel_name="mx.ped.layout.campo",
        inverse_name="registro_id",
        string="Campos",
        copy=True,
    )

    def name_get(self):
        result = []
        for rec in self:
            if rec.nombre:
                result.append((rec.id, f"{rec.codigo} - {rec.nombre}"))
            else:
                result.append((rec.id, rec.codigo or str(rec.id)))
        return result


class MxPedLayoutCampo(models.Model):
    _name = "mx.ped.layout.campo"
    _description = "Layout - Campo"
    _order = "pos_ini asc, id asc"

    registro_id = fields.Many2one(
        "mx.ped.layout.registro",
        string="Registro",
        required=True,
        ondelete="cascade",
        index=True,
    )
    layout_export_format = fields.Selection(
        related="registro_id.layout_id.export_format",
        string="Formato layout",
        readonly=True,
    )
    source_model = fields.Selection(
        [
            ("lead", "Operación (Lead)"),
            ("operacion", "Pedimento (Operación)"),
            ("cliente", "Contacto / Cliente"),
            ("importador", "Importador (Contacto)"),
            ("exportador", "Exportador (Contacto)"),
            ("proveedor", "Proveedor (Contacto)"),
        ],
        string="Fuente de datos",
        default="lead",
    )
    source_model_name = fields.Char(
        string="Modelo fuente",
        compute="_compute_source_model_name",
        store=False,
    )
    orden = fields.Integer(string="Orden", default=10)
    nombre = fields.Char(string="Nombre", required=True)
    pos_ini = fields.Integer(string="Posición inicial")
    pos_fin = fields.Integer(string="Posición final")
    longitud = fields.Integer(
        string="Longitud",
        compute="_compute_longitud",
        store=True,
        readonly=True,
    )
    tipo = fields.Selection(
        [
            ("A", "Alfabético"),
            ("N", "Numérico"),
            ("AN", "Alfanumérico"),
            ("F", "Fecha"),
        ],
        string="Tipo",
        default="AN",
        required=True,
    )
    requerido = fields.Boolean(default=False)
    default = fields.Char(string="Valor por defecto")
    formato = fields.Char(string="Formato")
    source_field_id = fields.Many2one(
        "ir.model.fields",
        string="Campo origen (Lead)",
        domain="[('model', '=', source_model_name)]",
        help="Selecciona el campo del Lead que alimenta este campo del layout.",
    )
    source_field = fields.Char(
        string="Campo origen (técnico)",
        help="Nombre técnico del campo en Lead/Pedimento (opcional si usas el selector).",
    )

    @api.depends("source_model")
    def _compute_source_model_name(self):
        for rec in self:
            if rec.source_model in ("cliente", "importador", "exportador", "proveedor"):
                rec.source_model_name = "res.partner"
            elif rec.source_model == "operacion":
                rec.source_model_name = "mx.ped.operacion"
            else:
                rec.source_model_name = "crm.lead"

    @api.depends("pos_ini", "pos_fin")
    def _compute_longitud(self):
        for rec in self:
            if rec.pos_ini and rec.pos_fin and rec.pos_fin >= rec.pos_ini:
                rec.longitud = rec.pos_fin - rec.pos_ini + 1
            else:
                rec.longitud = 0

    @api.constrains("pos_ini", "pos_fin", "layout_export_format")
    def _check_positions(self):
        for rec in self:
            if rec.layout_export_format == "pipe":
                continue
            if rec.pos_ini < 1 or rec.pos_fin < 1:
                raise ValidationError("Las posiciones deben ser mayores o iguales a 1.")
            if rec.pos_fin < rec.pos_ini:
                raise ValidationError("La posición final debe ser >= a la inicial.")
