# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MxPedIdentificador(models.Model):
    _name = "mx.ped.identificador"
    _description = "Catalogo de identificadores (Apendice 8)"
    _order = "code, id"

    code = fields.Char(string="Clave", required=True, size=2, index=True)
    name = fields.Char(string="Descripcion", required=True)
    nivel = fields.Selection(
        [("G", "Global / Pedimento"), ("P", "Partida")],
        string="Nivel",
        default="G",
        required=True,
        index=True,
    )
    req_comp1 = fields.Boolean(string="Requiere complemento 1")
    req_comp2 = fields.Boolean(string="Requiere complemento 2")
    req_comp3 = fields.Boolean(string="Requiere complemento 3")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("mx_ped_identificador_code_nivel_uniq", "unique(code, nivel)", "La clave/nivel del identificador ya existe."),
    ]


class MxPedOperacionIdentificador(models.Model):
    _name = "mx.ped.operacion.identificador"
    _description = "Operacion - Identificador a nivel pedimento"
    _order = "sequence, id"

    operacion_id = fields.Many2one("mx.ped.operacion", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    identificador_id = fields.Many2one(
        "mx.ped.identificador",
        string="Identificador",
        required=True,
        domain="[('nivel','=','G'), ('active','=',True)]",
        ondelete="restrict",
    )
    code = fields.Char(string="Clave", related="identificador_id.code", store=True, readonly=True)
    complemento1 = fields.Char(string="Complemento 1", size=20)
    complemento2 = fields.Char(string="Complemento 2", size=30)
    complemento3 = fields.Char(string="Complemento 3", size=40)
    notes = fields.Char(string="Notas")

    @api.constrains("identificador_id", "complemento1", "complemento2", "complemento3")
    def _check_required_complements(self):
        for rec in self:
            ident = rec.identificador_id
            if not ident:
                continue
            if ident.req_comp1 and not (rec.complemento1 or "").strip():
                raise ValidationError("El identificador requiere complemento 1.")
            if ident.req_comp2 and not (rec.complemento2 or "").strip():
                raise ValidationError("El identificador requiere complemento 2.")
            if ident.req_comp3 and not (rec.complemento3 or "").strip():
                raise ValidationError("El identificador requiere complemento 3.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_auto_generated_refresh"):
            records.mapped("operacion_id")._auto_refresh_generated_registros()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_auto_generated_refresh"):
            self.mapped("operacion_id")._auto_refresh_generated_registros()
        return res

    def unlink(self):
        ops = self.mapped("operacion_id")
        res = super().unlink()
        if not self.env.context.get("skip_auto_generated_refresh"):
            ops._auto_refresh_generated_registros()
        return res
