# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MxPedAduanaSeccion(models.Model):
    _name = "mx.ped.aduana.seccion"
    _description = "Catalogo de Aduana-Seccion"
    _rec_name = "display_name"
    _order = "aduana, seccion"

    aduana = fields.Char(string="Aduana", required=True, size=2, index=True)
    seccion = fields.Char(string="Seccion", required=False, size=1, index=True, default="0")
    denominacion = fields.Char(string="Denominacion", required=True)
    active = fields.Boolean(default=True)

    code = fields.Char(string="Clave", compute="_compute_code", store=True)
    display_name = fields.Char(compute="_compute_display_name", store=False)

    _sql_constraints = [
        (
            "mx_ped_aduana_seccion_code_uniq",
            "unique(aduana, seccion)",
            "La combinacion Aduana-Seccion debe ser unica.",
        ),
    ]

    @staticmethod
    def _normalize_seccion(value):
        return (value or "0").strip() or "0"

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals = []
        for vals in vals_list:
            row = dict(vals)
            row["aduana"] = (row.get("aduana") or "").strip()
            row["seccion"] = self._normalize_seccion(row.get("seccion"))
            normalized_vals.append(row)

        # Evita errores de importacion cuando el CSV trae varias filas con
        # la misma combinacion aduana-seccion.
        unique_rows = {}
        order = []
        for row in normalized_vals:
            key = (row.get("aduana"), row.get("seccion"))
            if key not in unique_rows:
                unique_rows[key] = row
                order.append(key)
                continue
            # Conserva datos utiles de filas repetidas sin crear duplicados.
            if (not unique_rows[key].get("denominacion")) and row.get("denominacion"):
                unique_rows[key]["denominacion"] = row.get("denominacion")
            if "active" in row:
                unique_rows[key]["active"] = row.get("active")

        aduanas = sorted({k[0] for k in order if k[0]})
        secciones = sorted({k[1] for k in order if k[1]})
        existing_map = {}
        if aduanas and secciones:
            existing = self.search([
                ("aduana", "in", aduanas),
                ("seccion", "in", secciones),
            ])
            existing_map = {(rec.aduana, rec.seccion): rec for rec in existing}

        to_create = []
        result = self.browse()
        for key in order:
            row = unique_rows[key]
            existing_rec = existing_map.get(key)
            if existing_rec:
                write_vals = {}
                if row.get("denominacion") and row.get("denominacion") != existing_rec.denominacion:
                    write_vals["denominacion"] = row.get("denominacion")
                if "active" in row and row.get("active") != existing_rec.active:
                    write_vals["active"] = row.get("active")
                if write_vals:
                    existing_rec.write(write_vals)
                result |= existing_rec
            else:
                to_create.append(row)

        if to_create:
            result |= super().create(to_create)
        return result

    def write(self, vals):
        if "seccion" in vals:
            vals["seccion"] = self._normalize_seccion(vals.get("seccion"))
        return super().write(vals)


    @api.depends("aduana", "seccion")
    def _compute_code(self):
        for rec in self:
            rec.aduana = (rec.aduana or "").strip()
            rec.seccion = self._normalize_seccion(rec.seccion)
            rec.code = f"{rec.aduana}{rec.seccion}" if rec.aduana and rec.seccion else False

    @api.depends("aduana", "seccion", "denominacion")
    def _compute_display_name(self):
        for rec in self:
            if rec.aduana and rec.seccion:
                rec.display_name = f"{rec.aduana}-{rec.seccion} {rec.denominacion or ''}".strip()
            else:
                rec.display_name = rec.denominacion or ""
