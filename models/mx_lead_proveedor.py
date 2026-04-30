# -*- coding: utf-8 -*-
"""
mx.lead.proveedor — Línea de proveedor/factura para operaciones con múltiples proveedores.

Cada línea representa un proveedor distinto dentro de una misma operación de CE.
Al hacer clic en "Generar COVE" se abre el formulario de mx.cove pre-llenado con
los datos de ese proveedor y vinculado a la operación correspondiente.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

# Mismo catálogo que mx.cove para consistencia
TIPO_IDENTIFICADOR = [
    ("0", "TAX ID"),
    ("1", "RFC"),
    ("2", "CURP"),
    ("3", "Sin Tax ID"),
]

INCOTERM_COVE = [
    ("EXW", "EXW — Ex Works"),
    ("FCA", "FCA — Free Carrier"),
    ("FAS", "FAS — Free Alongside Ship"),
    ("FOB", "FOB — Free On Board"),
    ("CFR", "CFR — Cost and Freight"),
    ("CIF", "CIF — Cost, Insurance and Freight"),
    ("CPT", "CPT — Carriage Paid To"),
    ("CIP", "CIP — Carriage and Insurance Paid To"),
    ("DPU", "DPU — Delivered at Place Unloaded"),
    ("DAP", "DAP — Delivered at Place"),
    ("DDP", "DDP — Delivered Duty Paid"),
    ("DAT", "DAT — Delivered at Terminal"),
    ("DAF", "DAF — Delivered at Frontier"),
    ("DES", "DES — Delivered Ex Ship"),
    ("DEQ", "DEQ — Delivered Ex Quay"),
    ("DDU", "DDU — Delivered Duty Unpaid"),
]


class MxLeadProveedor(models.Model):
    _name = "mx.lead.proveedor"
    _description = "Proveedor / factura para operación de CE"
    _order = "sequence, id"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Oportunidad",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)

    # ── Identificación del proveedor ──────────────────────────────────────────
    nombre = fields.Char(string="Nombre / razón social", required=True)
    tipo_identificador = fields.Selection(
        TIPO_IDENTIFICADOR,
        string="Tipo ID fiscal",
        default="0",
        required=True,
    )
    identificacion = fields.Char(string="ID fiscal / RFC")
    pais_id = fields.Many2one("res.country", string="País")

    # ── Domicilio (pre-llena el COVE) ─────────────────────────────────────────
    calle = fields.Char(string="Calle")
    numero_exterior = fields.Char(string="Núm. ext.")
    numero_interior = fields.Char(string="Núm. int.")
    codigo_postal = fields.Char(string="C.P.")
    ciudad = fields.Char(string="Ciudad / municipio")

    # ── Factura ───────────────────────────────────────────────────────────────
    numero_factura = fields.Char(string="Núm. de factura", required=True)
    incoterm = fields.Selection(INCOTERM_COVE, string="Incoterm")

    # ── Vínculo al COVE generado ─────────────────────────────────────────────
    cove_ids = fields.One2many(
        "mx.cove",
        "proveedor_lead_id",
        string="COVEs",
        readonly=True,
    )
    cove_count = fields.Integer(
        string="# COVEs",
        compute="_compute_cove_count",
    )
    cove_estado = fields.Char(
        string="Estado COVE",
        compute="_compute_cove_estado",
    )

    @api.depends("cove_ids")
    def _compute_cove_count(self):
        for rec in self:
            rec.cove_count = len(rec.cove_ids)

    @api.depends("cove_ids.estado")
    def _compute_cove_estado(self):
        for rec in self:
            if not rec.cove_ids:
                rec.cove_estado = "sin COVE"
            else:
                estados = rec.cove_ids.mapped("estado")
                if "con_edocument" in estados:
                    rec.cove_estado = "con e-Document"
                elif "enviado" in estados:
                    rec.cove_estado = "enviado"
                elif "rechazado" in estados:
                    rec.cove_estado = "rechazado"
                else:
                    rec.cove_estado = "borrador"

    # ── Acción principal ──────────────────────────────────────────────────────
    def action_generar_cove(self):
        """
        Abre el formulario de mx.cove pre-llenado con los datos de este proveedor.
        Si hay operación en contexto se usa esa; si no, se busca la más reciente del lead.
        """
        self.ensure_one()

        # Resolver operación
        operacion_id = self.env.context.get("operacion_id")
        if operacion_id:
            operacion = self.env["mx.ped.operacion"].browse(operacion_id)
        else:
            operacion = self.env["mx.ped.operacion"].search(
                [("lead_id", "=", self.lead_id.id)],
                order="id desc",
                limit=1,
            )

        if not operacion:
            raise UserError(
                "No hay operación (pedimento) asociada a este lead. "
                "Genera el pedimento primero desde el botón 'Crear/Actualizar pedimento'."
            )

        # Tipo de operación VUCEM
        mov = (operacion.tipo_movimiento or "").strip()
        tipo_op = "TOCE.IMP" if mov in ("1", "2", "3", "4", "5", "6") else "TOCE.EXP"

        ctx = {
            "default_operacion_id": operacion.id,
            "default_tipo_operacion": tipo_op,
            "default_proveedor_lead_id": self.id,
            # Emisor
            "default_emisor_tipo_identificador": self.tipo_identificador or "0",
            "default_emisor_identificacion": self.identificacion or "",
            "default_emisor_nombre": self.nombre or "",
            "default_emisor_calle": self.calle or "",
            "default_emisor_numero_exterior": self.numero_exterior or "",
            "default_emisor_numero_interior": self.numero_interior or "",
            "default_emisor_codigo_postal": self.codigo_postal or "",
            "default_emisor_municipio": self.ciudad or "",
            "default_emisor_pais": self.pais_id.code if self.pais_id else "",
            # Factura
            "default_numero_factura_original": self.numero_factura or "",
            "default_incoterm": self.incoterm or operacion.incoterm or "",
        }

        # Destinatario desde el importador de la operación
        if operacion.importador_id:
            imp = operacion.importador_id
            ctx.update({
                "default_dest_tipo_identificador": "1",  # RFC
                "default_dest_identificacion": imp.vat or "",
                "default_dest_nombre": imp.name or "",
                "default_dest_calle": imp.x_street_name or imp.street or "",
                "default_dest_numero_exterior": imp.x_street_number_ext or "",
                "default_dest_numero_interior": imp.x_street_number_int or "",
                "default_dest_codigo_postal": imp.zip or "",
                "default_dest_municipio": imp.x_municipio or imp.city or "",
                "default_dest_pais": imp.country_id.code if imp.country_id else "MEX",
            })

        return {
            "type": "ir.actions.act_window",
            "name": f"COVE — {self.nombre}",
            "res_model": "mx.cove",
            "view_mode": "form",
            "target": "current",
            "context": ctx,
        }

    def action_ver_coves(self):
        """Abre los COVEs asociados a este proveedor."""
        self.ensure_one()
        if self.cove_count == 1:
            return {
                "type": "ir.actions.act_window",
                "res_model": "mx.cove",
                "view_mode": "form",
                "res_id": self.cove_ids[0].id,
            }
        return {
            "type": "ir.actions.act_window",
            "name": f"COVEs — {self.nombre}",
            "res_model": "mx.cove",
            "view_mode": "list,form",
            "domain": [("proveedor_lead_id", "=", self.id)],
        }
