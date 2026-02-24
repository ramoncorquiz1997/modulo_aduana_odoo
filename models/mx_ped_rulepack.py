# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MxPedRulepack(models.Model):
    _name = "mx.ped.rulepack"
    _description = "Rulepack normativo de pedimentos"
    _order = "fecha_inicio desc, priority desc, id desc"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(default=100)
    weight_estructura = fields.Integer(default=10)
    weight_clave = fields.Integer(default=20)
    weight_condition = fields.Integer(default=30)
    state = fields.Selection(
        [("draft", "Borrador"), ("active", "Activo"), ("retired", "Retirado")],
        default="draft",
        required=True,
    )
    fecha_inicio = fields.Date(required=True)
    fecha_fin = fields.Date()
    note = fields.Text()

    scenario_ids = fields.One2many("mx.ped.rulepack.scenario", "rulepack_id", string="Escenarios")
    selector_ids = fields.One2many("mx.ped.rulepack.selector", "rulepack_id", string="Selectores de escenario")
    process_rule_ids = fields.One2many("mx.ped.rulepack.process.rule", "rulepack_id", string="Reglas de proceso")
    condition_rule_ids = fields.One2many("mx.ped.rulepack.condition.rule", "rulepack_id", string="Reglas de registros")

    _sql_constraints = [
        ("mx_ped_rulepack_code_uniq", "unique(code)", "El codigo del rulepack debe ser unico."),
    ]

    @api.constrains("fecha_inicio", "fecha_fin")
    def _check_dates(self):
        for rec in self:
            if rec.fecha_fin and rec.fecha_fin < rec.fecha_inicio:
                raise ValidationError(_("La fecha fin no puede ser menor que fecha inicio."))


class MxPedRulepackScenario(models.Model):
    _name = "mx.ped.rulepack.scenario"
    _description = "Escenario de estructura dentro de un rulepack"
    _order = "sequence, id"

    rulepack_id = fields.Many2one("mx.ped.rulepack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    code = fields.Selection(
        [
            ("normal", "Pedimento normal"),
            ("transito", "Transito"),
            ("rectificacion", "Rectificacion"),
            ("eliminacion_desistimiento", "Eliminacion / Desistimiento"),
            ("industria_automotriz", "Industria automotriz"),
            ("complementario", "Complementario"),
            ("despacho_anticipado", "Despacho anticipado"),
            ("confirmacion_pago", "Confirmacion de pago"),
            ("global_complementario", "Global complementario"),
            ("generico", "Generico"),
        ],
        required=True,
    )
    name = fields.Char(required=True)
    is_default = fields.Boolean(string="Escenario default", default=False)
    estructura_regla_id = fields.Many2one(
        "mx.ped.estructura.regla",
        string="Regla de estructura base",
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)


class MxPedRulepackSelector(models.Model):
    _name = "mx.ped.rulepack.selector"
    _description = "Selector de escenario (condicion -> escenario)"
    _order = "priority desc, sequence, id"

    rulepack_id = fields.Many2one("mx.ped.rulepack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    priority = fields.Integer(default=100)
    stop = fields.Boolean(default=True)
    active = fields.Boolean(default=True)

    tipo_movimiento_id = fields.Many2one("mx.ped.tipo.movimiento", string="Tipo movimiento", ondelete="restrict")
    tipo_operacion = fields.Selection(
        [("importacion", "Importacion"), ("exportacion", "Exportacion"), ("ambas", "Ambas")],
        default="ambas",
    )
    regimen = fields.Selection(
        [
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Deposito fiscal"),
            ("transito", "Transito"),
            ("cualquiera", "Cualquiera"),
        ],
        default="cualquiera",
    )
    clave_pedimento_id = fields.Many2one("mx.ped.clave", string="Clave pedimento", ondelete="restrict")
    is_virtual = fields.Selection(
        [("any", "Cualquiera"), ("yes", "Si"), ("no", "No")],
        default="any",
        required=True,
    )
    scenario_id = fields.Many2one("mx.ped.rulepack.scenario", required=True, ondelete="restrict")


class MxPedRulepackProcessRule(models.Model):
    _name = "mx.ped.rulepack.process.rule"
    _description = "Regla de proceso por etapa"
    _order = "priority desc, sequence, id"

    rulepack_id = fields.Many2one("mx.ped.rulepack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    priority = fields.Integer(default=100)
    stop = fields.Boolean(default=False)
    active = fields.Boolean(default=True)
    name = fields.Char(required=True)

    stage = fields.Selection(
        [
            ("load_from_lead", "Carga desde lead"),
            ("pre_validate", "Prevalidacion"),
            ("export", "Exportacion"),
        ],
        required=True,
    )
    action_type = fields.Selection(
        [
            ("allow_only_records", "Permitir solo registros"),
            ("require_field", "Campo obligatorio"),
            ("forbid_field", "Campo prohibido"),
            ("require_formas_pago", "Validar formas de pago"),
        ],
        required=True,
    )
    payload_json = fields.Json(string="Payload")

    tipo_movimiento_id = fields.Many2one("mx.ped.tipo.movimiento", string="Tipo movimiento", ondelete="restrict")
    tipo_operacion = fields.Selection(
        [("importacion", "Importacion"), ("exportacion", "Exportacion"), ("ambas", "Ambas")],
        default="ambas",
    )
    regimen = fields.Selection(
        [
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Deposito fiscal"),
            ("transito", "Transito"),
            ("cualquiera", "Cualquiera"),
        ],
        default="cualquiera",
    )
    clave_pedimento_id = fields.Many2one("mx.ped.clave", string="Clave pedimento", ondelete="restrict")
    is_virtual = fields.Selection(
        [("any", "Cualquiera"), ("yes", "Si"), ("no", "No")],
        default="any",
        required=True,
    )


class MxPedRulepackConditionRule(models.Model):
    _name = "mx.ped.rulepack.condition.rule"
    _description = "Regla de condiciones para incluir/omitir registros"
    _order = "priority desc, sequence, id"

    rulepack_id = fields.Many2one("mx.ped.rulepack", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    priority = fields.Integer(default=100)
    stop = fields.Boolean(default=False)
    active = fields.Boolean(default=True)
    name = fields.Char(required=True)

    scope = fields.Selection(
        [("pedimento", "Pedimento"), ("partida", "Partida")],
        default="pedimento",
        required=True,
    )
    target_type = fields.Selection(
        [("record", "Registro"), ("field", "Campo")],
        string="Target",
        default="record",
        required=True,
    )
    policy = fields.Selection(
        [
            ("required", "Obligatorio"),
            ("optional", "Opcional"),
            ("forbidden", "Prohibido"),
            ("require_field", "Campo obligatorio"),
            ("forbid_field", "Campo prohibido"),
            ("default_field", "Default campo"),
            ("warn_field", "Advertencia campo"),
        ],
        default="required",
        required=True,
    )
    registro_tipo_id = fields.Many2one(
        "mx.ped.layout.registro",
        string="Registro (catalogo)",
        ondelete="restrict",
        help="Selecciona el registro desde el catalogo de registros del layout.",
    )
    registro_codigo = fields.Char(required=True, size=3)
    field_id = fields.Many2one(
        "mx.ped.layout.campo",
        string="Campo objetivo",
        domain="[('registro_id', '=', registro_tipo_id)]",
        ondelete="restrict",
    )
    default_value = fields.Char(string="Valor default campo")
    min_occurs = fields.Integer(default=1)
    max_occurs = fields.Integer(default=1, help="Usa 0 para ilimitado.")
    required_identifier_code = fields.Char(size=3)

    tipo_movimiento_id = fields.Many2one("mx.ped.tipo.movimiento", string="Tipo movimiento", ondelete="restrict")
    tipo_operacion = fields.Selection(
        [("importacion", "Importacion"), ("exportacion", "Exportacion"), ("ambas", "Ambas")],
        default="ambas",
    )
    regimen = fields.Selection(
        [
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Deposito fiscal"),
            ("transito", "Transito"),
            ("cualquiera", "Cualquiera"),
        ],
        default="cualquiera",
    )
    clave_pedimento_id = fields.Many2one("mx.ped.clave", string="Clave pedimento", ondelete="restrict")
    is_virtual = fields.Selection(
        [("any", "Cualquiera"), ("yes", "Si"), ("no", "No")],
        default="any",
        required=True,
    )
    escenario_code = fields.Selection(
        [
            ("any", "Cualquiera"),
            ("normal", "Pedimento normal"),
            ("transito", "Transito"),
            ("rectificacion", "Rectificacion"),
            ("eliminacion_desistimiento", "Eliminacion / Desistimiento"),
            ("industria_automotriz", "Industria automotriz"),
            ("complementario", "Complementario"),
            ("despacho_anticipado", "Despacho anticipado"),
            ("confirmacion_pago", "Confirmacion de pago"),
            ("global_complementario", "Global complementario"),
            ("generico", "Generico"),
        ],
        default="any",
        required=True,
    )
    fraccion_id = fields.Many2one("mx.ped.fraccion", string="Fraccion (opcional)", ondelete="restrict")
    fraccion_capitulo = fields.Char(
        string="Capitulo (opcional)",
        size=2,
        help="Alternativa menos especifica a fraccion exacta.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        field_policies = {"require_field", "forbid_field", "default_field", "warn_field"}
        for vals in vals_list:
            if vals.get("policy") in field_policies:
                vals["target_type"] = "field"
            target_type = vals.get("target_type") or "record"
            field_id = vals.get("field_id")
            if target_type == "field" and field_id:
                field = self.env["mx.ped.layout.campo"].browse(field_id)
                if field and field.registro_id:
                    vals["registro_tipo_id"] = vals.get("registro_tipo_id") or field.registro_id.id
                    vals["registro_codigo"] = field.registro_id.codigo or ""
            registro_tipo_id = vals.get("registro_tipo_id")
            if registro_tipo_id and not vals.get("registro_codigo"):
                reg = self.env["mx.ped.layout.registro"].browse(registro_tipo_id)
                vals["registro_codigo"] = reg.codigo or ""
            if vals.get("registro_codigo"):
                vals["registro_codigo"] = (vals["registro_codigo"] or "").strip().zfill(3)
            if vals.get("required_identifier_code"):
                vals["required_identifier_code"] = (vals["required_identifier_code"] or "").strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        field_policies = {"require_field", "forbid_field", "default_field", "warn_field"}
        if vals.get("policy") in field_policies:
            vals["target_type"] = "field"
        target_type = vals.get("target_type")
        field_id = vals.get("field_id")
        if (target_type == "field" or (field_id and target_type is None)) and field_id:
            field = self.env["mx.ped.layout.campo"].browse(field_id)
            if field and field.registro_id:
                vals["registro_tipo_id"] = vals.get("registro_tipo_id") or field.registro_id.id
                vals["registro_codigo"] = field.registro_id.codigo or ""
        if vals.get("registro_tipo_id") and not vals.get("registro_codigo"):
            reg = self.env["mx.ped.layout.registro"].browse(vals["registro_tipo_id"])
            vals["registro_codigo"] = reg.codigo or ""
        if vals.get("registro_codigo") is not None:
            vals["registro_codigo"] = (vals["registro_codigo"] or "").strip().zfill(3)
        if vals.get("required_identifier_code") is not None:
            vals["required_identifier_code"] = (vals["required_identifier_code"] or "").strip().upper()
        return super().write(vals)

    @api.onchange("registro_tipo_id")
    def _onchange_registro_tipo_id(self):
        for rec in self:
            if rec.registro_tipo_id and rec.registro_tipo_id.codigo:
                rec.registro_codigo = rec.registro_tipo_id.codigo

    @api.onchange("field_id")
    def _onchange_field_id(self):
        for rec in self:
            if rec.field_id and rec.field_id.registro_id:
                rec.registro_tipo_id = rec.field_id.registro_id
                rec.registro_codigo = rec.field_id.registro_id.codigo or rec.registro_codigo

    @api.onchange("target_type")
    def _onchange_target_type(self):
        for rec in self:
            if rec.target_type == "record":
                rec.field_id = False
                rec.default_value = False
                if rec.policy in {"require_field", "forbid_field", "default_field", "warn_field"}:
                    rec.policy = "required"
            else:
                if rec.policy not in {"require_field", "forbid_field", "default_field", "warn_field"}:
                    rec.policy = "require_field"

    @api.onchange("policy")
    def _onchange_policy(self):
        field_policies = {"require_field", "forbid_field", "default_field", "warn_field"}
        for rec in self:
            if rec.policy in field_policies:
                rec.target_type = "field"

    @api.constrains("registro_codigo", "min_occurs", "max_occurs", "target_type", "policy", "field_id", "registro_tipo_id")
    def _check_rule(self):
        for rec in self:
            code = (rec.registro_codigo or rec.registro_tipo_id.codigo or "").strip()
            if not code.isdigit() or len(code) != 3:
                raise ValidationError(_("El codigo de registro debe ser numerico de 3 digitos."))
            if rec.min_occurs < 0 or rec.max_occurs < 0:
                raise ValidationError(_("Min/Max ocurrencias no pueden ser negativas."))
            if rec.max_occurs and rec.max_occurs < rec.min_occurs:
                raise ValidationError(_("Max ocurrencias no puede ser menor que Min ocurrencias."))
            if rec.target_type == "field":
                if not rec.field_id:
                    raise ValidationError(_("Para target Campo debes seleccionar Campo objetivo."))
                if rec.field_id.registro_id and (rec.field_id.registro_id.codigo or "").strip() != code:
                    raise ValidationError(_("El campo objetivo no pertenece al registro seleccionado en la regla."))
                if rec.policy not in {"require_field", "forbid_field", "default_field", "warn_field"}:
                    raise ValidationError(_("Policy invalida para target Campo."))
                if rec.policy == "default_field" and not (rec.default_value or "").strip():
                    raise ValidationError(_("Policy Default campo requiere Valor default campo."))
            elif rec.policy in {"require_field", "forbid_field", "default_field", "warn_field"}:
                raise ValidationError(_("Policies de campo solo aplican cuando Target = Campo."))
