# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedClave(models.Model):
    _name = "mx.ped.clave"
    _description = "Catalogo Claves de Pedimento (Anexo 22)"
    _rec_name = "display_name"
    _order = "code"

    code = fields.Char(string="Clave", required=True, index=True)  # A1, A4, V1...
    name = fields.Char(string="Descripcion", required=True)

    tipo_operacion = fields.Selection(
        selection=[
            ("importacion", "Importacion"),
            ("exportacion", "Exportacion"),
            ("ambas", "Ambas"),
        ],
        string="Tipo de operacion",
        default="ambas",
        required=True,
    )

    regimen = fields.Selection(
        selection=[
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Deposito fiscal"),
            ("transito", "Transito"),
            ("cualquiera", "Cualquiera"),
        ],
        string="Regimen",
        default="cualquiera",
        required=True,
    )

    requiere_immex = fields.Boolean(string="Requiere IMMEX", default=False)
    requires_series = fields.Boolean(
        string="Requiere series",
        help="Marca si la clave requiere registros de series/mercancias en su estructura.",
    )
    is_virtual = fields.Boolean(
        string="Operacion virtual",
        help="Marca si la clave se opera como movimiento virtual.",
    )
    saai_structure_type = fields.Selection(
        selection=[
            ("auto", "Auto (por tipo de movimiento)"),
            ("normal", "Pedimento normal"),
            ("transito", "Transito"),
            ("rectificacion", "Rectificacion"),
            ("eliminacion_desistimiento", "Eliminacion / Desistimiento"),
            ("industria_automotriz", "Industria automotriz"),
            ("complementario", "Complementario"),
            ("despacho_anticipado", "Despacho anticipado"),
            ("confirmacion_pago", "Confirmacion de pago"),
            ("global_complementario", "Global complementario"),
        ],
        string="Tipo de estructura SAAI",
        default="auto",
        required=True,
        help="Permite forzar el escenario de estructura sin hardcodear por clave.",
    )
    tipo_movimiento_id = fields.Many2one(
        "mx.ped.tipo.movimiento",
        string="Tipo de movimiento default",
        ondelete="restrict",
        help="Cuando se selecciona esta clave, este tipo de movimiento se propone para registro 500.",
    )

    # Banderas de compatibilidad para transicion.
    requires_reg_552 = fields.Boolean(
        string="Exige registro 552",
        help="Compatibilidad: fuerza presencia del registro 552.",
    )
    omits_reg_502 = fields.Boolean(
        string="Omite registro 502",
        help="Compatibilidad: prohibe el registro 502 para esta clave.",
    )
    requires_identificador_re = fields.Boolean(
        string="Exige identificador RE",
        help="Compatibilidad: valida identificador RE en registro 507.",
    )

    registro_policy_ids = fields.One2many(
        "mx.ped.clave.regla.registro",
        "clave_id",
        string="Politica de registros",
        help="Reglas por codigo de registro para esta clave.",
    )

    active = fields.Boolean(default=True)
    vigente_desde = fields.Date(string="Vigente desde")
    vigente_hasta = fields.Date(string="Vigente hasta")
    note = fields.Text(string="Notas")

    display_name = fields.Char(compute="_compute_display_name", store=False)

    _sql_constraints = [
        ("mx_ped_clave_code_uniq", "unique(code)", "La clave de pedimento debe ser unica."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            code = (vals.get("code") or "").strip().upper()
            if code:
                vals["code"] = code
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("code") is not None:
            vals["code"] = (vals.get("code") or "").strip().upper()
        return super().write(vals)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.code} - {rec.name}"

    @api.constrains("code")
    def _check_code(self):
        for rec in self:
            code = (rec.code or "").strip().upper()
            if not code:
                raise ValidationError(_("La clave de pedimento es obligatoria."))
            if len(code) > 3:
                raise ValidationError(_("La clave de pedimento no debe exceder 3 caracteres."))


class MxPedClaveReglaRegistro(models.Model):
    _name = "mx.ped.clave.regla.registro"
    _description = "Clave de pedimento - politica de registros"
    _order = "sequence, id"

    clave_id = fields.Many2one(
        "mx.ped.clave",
        string="Clave de pedimento",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    registro_codigo = fields.Char(string="Codigo de registro", required=True, size=3)
    policy = fields.Selection(
        [
            ("required", "Obligatorio"),
            ("optional", "Opcional"),
            ("forbidden", "Prohibido"),
        ],
        string="Politica",
        default="required",
        required=True,
    )
    min_occurs = fields.Integer(string="Min ocurrencias", default=1)
    max_occurs = fields.Integer(
        string="Max ocurrencias",
        default=1,
        help="Usa 0 para ilimitado.",
    )
    required_identifier_code = fields.Char(
        string="Identificador requerido",
        size=3,
        help="Opcional. Para registro 507 valida que exista esta clave de identificador.",
    )
    notes = fields.Char(string="Notas")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            code = (vals.get("registro_codigo") or "").strip()
            if code:
                vals["registro_codigo"] = code.zfill(3)
            ident = (vals.get("required_identifier_code") or "").strip().upper()
            if ident:
                vals["required_identifier_code"] = ident
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("registro_codigo") is not None:
            vals["registro_codigo"] = (vals.get("registro_codigo") or "").strip().zfill(3)
        if vals.get("required_identifier_code") is not None:
            vals["required_identifier_code"] = (vals.get("required_identifier_code") or "").strip().upper()
        return super().write(vals)

    @api.constrains("registro_codigo", "min_occurs", "max_occurs")
    def _check_line(self):
        for rec in self:
            code = (rec.registro_codigo or "").strip()
            if not (code.isdigit() and len(code) == 3):
                raise ValidationError(_("El codigo de registro debe ser numerico de 3 digitos."))
            if rec.min_occurs < 0:
                raise ValidationError(_("Min ocurrencias no puede ser negativo."))
            if rec.max_occurs < 0:
                raise ValidationError(_("Max ocurrencias no puede ser negativo."))
            if rec.max_occurs and rec.max_occurs < rec.min_occurs:
                raise ValidationError(_("Max ocurrencias no puede ser menor que Min ocurrencias."))
