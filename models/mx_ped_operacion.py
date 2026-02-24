# -*- coding: utf-8 -*-
import base64
import io
import json
import re
from collections import Counter
import xml.etree.ElementTree as ET

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

try:
    from PyPDF2 import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


class MxPedOperacion(models.Model):
    _name = "mx.ped.operacion"
    _description = "Pedimento / Operación Aduanera"
    _order = "create_date desc, id desc"

    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        string="Operación (Lead)",
        required=True,
        ondelete="cascade",
        index=True,
    )

    name = fields.Char(string="Referencia", required=True)

    # ==========================
    # Clasificación
    # ==========================
    tipo_operacion = fields.Selection(
        [("importacion", "Importación"), ("exportacion", "Exportación")],
        string="Tipo",
    )
    regimen = fields.Selection(
        [
            ("definitivo", "Definitivo"),
            ("temporal", "Temporal"),
            ("deposito_fiscal", "Depósito fiscal"),
            ("transito", "Tránsito"),
        ],
        string="Régimen",
    )
    incoterm = fields.Selection(
        [
            ("EXW", "EXW"),
            ("FCA", "FCA"),
            ("FOB", "FOB"),
            ("CFR", "CFR"),
            ("CIF", "CIF"),
            ("DAP", "DAP"),
            ("DDP", "DDP"),
        ],
        string="Incoterm",
    )

    aduana_seccion_despacho_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana-seccion de despacho",
    )
    aduana_clave = fields.Char(string="Aduana (clave)")  # ej 070
    agente_aduanal_id = fields.Many2one(
        "res.partner",
        string="Agente aduanal",
        domain="[('x_contact_role','=','agente_aduanal')]",
    )
    patente = fields.Char(string="Patente")
    clave_pedimento_id = fields.Many2one(
        "mx.ped.clave",
        string="Clave pedimento",
    )

    clave_pedimento = fields.Char(
        string="Clave pedimento (código)",
        related="clave_pedimento_id.code",
        store=True,
        readonly=True,
    )
    tipo_movimiento = fields.Selection(
        [
            ("1", "1 - Pedimento nuevo"),
            ("2", "2 - Eliminación"),
            ("3", "3 - Desistimiento"),
            ("5", "5 - Informe Industria Automotriz"),
            ("6", "6 - Pedimento complementario"),
            ("7", "7 - Despacho anticipado"),
            ("8", "8 - Confirmación de pago"),
            ("9", "9 - Global complementario"),
        ],
        string="Tipo de movimiento",
        default="1",
    )
    es_rectificacion = fields.Boolean(
        string="Rectificacion",
        help="Usa esta marca cuando el movimiento 1 corresponda a rectificacion.",
    )
    formas_pago_claves = fields.Char(
        string="Formas de pago (claves)",
        help="Solo para movimiento 8. Captura claves separadas por coma, ej. 5,6,8,9",
    )
    estructura_escenario = fields.Selection(
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
        string="Escenario de estructura",
        compute="_compute_estructura_escenario",
        store=False,
    )
    aduana_seccion_entrada_salida_id = fields.Many2one(
        "mx.ped.aduana.seccion",
        string="Aduana-seccion entrada/salida",
    )
    aduana_seccion_entrada_salida = fields.Char(
        string="Aduana-seccion entrada/salida (codigo)",
        related="aduana_seccion_entrada_salida_id.code",
        store=True,
        readonly=True,
    )
    acuse_validacion = fields.Char(string="Acuse electronico validacion")
    curp_agente = fields.Char(string="CURP agente/apoderado")

    cliente_id = fields.Many2one(
        "res.partner",
        string="Contacto / Cliente",
        related="lead_id.partner_id",
        store=True,
        readonly=True,
    )
    importador_id = fields.Many2one(
        "res.partner",
        string="Importador",
        related="lead_id.x_importador_id",
        store=True,
        readonly=True,
    )
    exportador_id = fields.Many2one(
        "res.partner",
        string="Exportador",
        related="lead_id.x_exportador_id",
        store=True,
        readonly=True,
    )
    proveedor_id = fields.Many2one(
        "res.partner",
        string="Proveedor",
        related="lead_id.x_proveedor_id",
        store=True,
        readonly=True,
    )
    participante_id = fields.Many2one(
        "res.partner",
        string="Importador/Exportador efectivo",
        compute="_compute_participante",
    )
    participante_rfc = fields.Char(
        string="RFC importador/exportador",
        compute="_compute_participante_data",
    )
    participante_curp = fields.Char(
        string="CURP importador/exportador",
        compute="_compute_participante_data",
    )
    participante_nombre = fields.Char(
        string="Nombre importador/exportador",
        compute="_compute_participante_data",
    )

    # ==========================
    # Resultado oficial/operativo
    # ==========================
    pedimento_numero = fields.Char(string="Número de pedimento")
    fecha_pago = fields.Date(string="Fecha de pago")
    fecha_liberacion = fields.Date(string="Fecha de liberación")
    semaforo = fields.Selection(
        [("verde", "Verde"), ("rojo", "Rojo")],
        string="Semáforo",
    )

    # Moneda
    currency_id = fields.Many2one(
        "res.currency",
        string="Moneda",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    observaciones = fields.Text(string="Observaciones")
    bl_file = fields.Binary(string="Archivo B/L (PDF)")
    bl_filename = fields.Char(string="Nombre archivo B/L")
    bl_last_read = fields.Datetime(string="Ultima lectura B/L", readonly=True)

    invoice_ids = fields.One2many(
        "account.move",
        "x_ped_operacion_id",
        string="Facturas",
    )
    invoice_count = fields.Integer(
        string="Conteo facturas",
        compute="_compute_invoice_count",
    )

    # ==========================
    # Layout y registros (VOCE/SAAI)
    # ==========================
    layout_id = fields.Many2one(
        "mx.ped.layout",
        string="Layout",
        help="Define los registros y campos del archivo de validación.",
    )
    estructura_regla_id = fields.Many2one(
        "mx.ped.estructura.regla",
        string="Regla de estructura",
        help="Define qu? registros debe contener la operaci?n seg?n tipo de movimiento.",
    )
    fecha_operacion = fields.Date(
        string="Fecha operacion",
        default=lambda self: fields.Date.context_today(self),
        required=True,
        help="Se usa para resolver automaticamente el rulepack normativo vigente.",
    )
    rulepack_id = fields.Many2one(
        "mx.ped.rulepack",
        string="Rulepack normativo",
        ondelete="restrict",
        help="Version normativa data-driven aplicada a esta operacion.",
    )
    strict_mode_policy = fields.Selection(
        [
            ("inherit", "Heredar"),
            ("strict", "Forzar STRICT"),
            ("relaxed", "Forzar no strict"),
        ],
        string="Modo STRICT",
        default="inherit",
    )
    strict_mode_effective = fields.Boolean(
        string="STRICT efectivo",
        compute="_compute_strict_mode_effective",
        store=False,
    )
    rule_trace_json = fields.Json(string="Trazabilidad de reglas", readonly=True, copy=False)
    rule_trace_at = fields.Datetime(string="Ultima evaluaci?n de reglas", readonly=True, copy=False)
    show_acuse_ui = fields.Boolean(
        string="Mostrar acuse",
        compute="_compute_process_ui_flags",
        store=False,
    )
    show_formas_pago_ui = fields.Boolean(
        string="Mostrar formas pago",
        compute="_compute_process_ui_flags",
        store=False,
    )

    registro_ids = fields.One2many(
        comodel_name="mx.ped.registro",
        inverse_name="operacion_id",
        string="Registros",
        copy=True,
    )

    # ==========================
    # Partidas / Mercancías
    # ==========================
    partida_ids = fields.One2many(
        comodel_name="mx.ped.partida",
        inverse_name="operacion_id",
        string="Partidas / Mercancías",
        copy=True,
    )

    partida_count = fields.Integer(
        string="Partidas",
        compute="_compute_partida_count",
    )

    @api.depends("partida_ids")
    def _compute_partida_count(self):
        for rec in self:
            rec.partida_count = len(rec.partida_ids)

    @api.depends("tipo_operacion", "importador_id", "exportador_id")
    def _compute_participante(self):
        for rec in self:
            if rec.tipo_operacion == "exportacion":
                rec.participante_id = rec.exportador_id
            else:
                rec.participante_id = rec.importador_id

    @api.depends(
        "tipo_operacion",
        "importador_id",
        "importador_id.vat",
        "importador_id.x_curp",
        "importador_id.name",
        "exportador_id",
        "exportador_id.vat",
        "exportador_id.x_curp",
        "exportador_id.name",
    )
    def _compute_participante_data(self):
        for rec in self:
            partner = rec.exportador_id if rec.tipo_operacion == "exportacion" else rec.importador_id
            rec.participante_rfc = partner.vat if partner else False
            rec.participante_curp = partner.x_curp if partner else False
            rec.participante_nombre = partner.name if partner else False

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids.filtered(lambda m: m.move_type == "out_invoice"))

    @api.depends("strict_mode_policy", "cliente_id.x_rule_engine_strict", "participante_id.x_rule_engine_strict")
    def _compute_strict_mode_effective(self):
        for rec in self:
            rec.strict_mode_effective = rec._is_strict_mode()

    @api.depends("tipo_movimiento", "clave_pedimento_id", "tipo_operacion", "regimen", "fecha_operacion", "rulepack_id")
    def _compute_process_ui_flags(self):
        for rec in self:
            show_acuse = False
            show_formas = False
            for rule in rec._get_process_stage_rules("pre_validate"):
                payload = rule.payload_json or {}
                if rule.action_type == "require_field" and payload.get("field") == "acuse_validacion":
                    show_acuse = True
                if rule.action_type == "require_formas_pago":
                    show_formas = True
                if rule.stop:
                    break
            rec.show_acuse_ui = show_acuse
            rec.show_formas_pago_ui = show_formas

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = {"fecha_operacion", "tipo_operacion", "regimen", "clave_pedimento_id", "tipo_movimiento"}
        if trigger_fields.intersection(vals.keys()):
            for rec in self:
                rec.rulepack_id = rec._resolve_rulepack()
                rec.estructura_regla_id = rec._resolve_estructura_regla()
        return res

    @api.onchange("lead_id")
    def _onchange_lead_id_fill_defaults(self):
        if not self.lead_id:
            return
        lead = self.lead_id
        defaults = {
            "tipo_operacion": lead.x_tipo_operacion or False,
            "regimen": lead.x_regimen or False,
            "incoterm": lead.x_incoterm or False,
            "aduana_seccion_despacho_id": lead.x_aduana_seccion_despacho_id or False,
            "aduana_clave": lead.x_aduana or False,
            "aduana_seccion_entrada_salida_id": lead.x_aduana_seccion_entrada_salida_id or False,
            "acuse_validacion": lead.x_acuse_validacion or False,
            "agente_aduanal_id": lead.x_agente_aduanal_id or False,
            "patente": (lead.x_agente_aduanal_id.x_patente_aduanal or lead.x_patente_agente or False),
            "curp_agente": lead.x_curp_agente or False,
            "clave_pedimento_id": lead.x_clave_pedimento_id or False,
            "currency_id": lead.x_currency_id or self.env.company.currency_id,
            "pedimento_numero": lead.x_num_pedimento or False,
            "fecha_pago": lead.x_fecha_pago_pedimento or False,
            "fecha_liberacion": lead.x_fecha_liberacion or False,
            "semaforo": lead.x_semaforo or False,
            "observaciones": lead.x_incidente_text or False,
        }
        for field_name, value in defaults.items():
            if not self[field_name]:
                self[field_name] = value

    @api.onchange("aduana_seccion_despacho_id")
    def _onchange_aduana_seccion_despacho_id(self):
        for rec in self:
            if rec.aduana_seccion_despacho_id:
                rec.aduana_clave = rec.aduana_seccion_despacho_id.code

    @api.onchange("agente_aduanal_id")
    def _onchange_agente_aduanal_id(self):
        for rec in self:
            agent = rec.agente_aduanal_id
            if not agent:
                continue
            rec.patente = agent.x_patente_aduanal or rec.patente
            rec.curp_agente = agent.x_curp or rec.curp_agente

    @api.onchange("tipo_movimiento")
    def _onchange_tipo_movimiento_clear_acuse(self):
        for rec in self:
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.onchange("clave_pedimento_id", "tipo_operacion", "regimen", "fecha_operacion")
    def _onchange_estructura_regla_context(self):
        for rec in self:
            if rec.clave_pedimento_id and rec.clave_pedimento_id.tipo_movimiento_id:
                rec.tipo_movimiento = rec.clave_pedimento_id.tipo_movimiento_id.code
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.onchange("es_rectificacion", "formas_pago_claves")
    def _onchange_estructura_regla_flags(self):
        for rec in self:
            rec.rulepack_id = rec._resolve_rulepack()
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.depends("tipo_movimiento", "clave_pedimento_id", "es_rectificacion")
    def _compute_estructura_escenario(self):
        for rec in self:
            rec.estructura_escenario = rec._detect_escenario_estructura()

    @api.constrains("tipo_movimiento", "acuse_validacion", "clave_pedimento_id")
    def _check_acuse_validacion(self):
        for rec in self:
            stage_rules = rec._get_process_stage_rules("pre_validate")
            for rule in stage_rules:
                payload = rule.payload_json or {}
                if rule.action_type != "require_field":
                    continue
                if payload.get("field") != "acuse_validacion":
                    continue
                acuse = (rec.acuse_validacion or "").strip()
                if not acuse:
                    raise ValidationError(_("Regla %s: el acuse de validacion es obligatorio.") % (rule.name,))
                expected_len = int(payload.get("length") or 0)
                if expected_len and len(acuse) != expected_len:
                    raise ValidationError(
                        _("Regla %s: el acuse de validacion debe tener %s caracteres.")
                        % (rule.name, expected_len)
                    )
                forbidden = str(payload.get("forbidden_value") or "").strip()
                if forbidden and acuse == forbidden:
                    raise ValidationError(
                        _("Regla %s: el acuse de validacion no puede ser %s.")
                        % (rule.name, forbidden)
                    )
                if rule.stop:
                    break

    def action_view_partidas(self):
        """Abre las partidas de esta operación (útil para smart button)."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Partidas"),
            "res_model": "mx.ped.partida",
            "view_mode": "list,form",
            "domain": [("operacion_id", "=", self.id)],
            "context": {"default_operacion_id": self.id},
            "target": "current",
        }

    def _get_tipo_movimiento_effective(self):
        self.ensure_one()
        if self.clave_pedimento_id and self.clave_pedimento_id.tipo_movimiento_id:
            return self.clave_pedimento_id.tipo_movimiento_id.code
        return self.tipo_movimiento

    def _get_clave_policy_map(self):
        self.ensure_one()
        policy_rules = []
        clave = self.clave_pedimento_id
        if not clave:
            return policy_rules

        for line in clave.registro_policy_ids.sorted(lambda l: (-l.priority, l.sequence, l.id)):
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            policy_rules.append({
                "code": code,
                "policy": line.policy,
                "scope": line.scope or "pedimento",
                "priority": line.priority,
                "stop": bool(line.stop),
                "min": max(line.min_occurs or 0, 0),
                "max": max(line.max_occurs or 0, 0),
                "identifier": (line.required_identifier_code or "").strip().upper(),
                "line_id": line.id,
            })

        policy_rules.sort(key=lambda r: (-r["priority"], r["code"], r["line_id"]))
        return policy_rules

    def _payload_has_token(self, payload, token):
        token = (token or "").strip().upper()
        if not token:
            return True
        payload = payload or {}
        for value in payload.values():
            if isinstance(value, str):
                tokens = {part.upper() for part in re.findall(r"[A-Za-z0-9]+", value)}
                if token in tokens:
                    return True
        return False

    def _extract_partida_number(self, payload):
        payload = payload or {}
        if not isinstance(payload, dict):
            return None

        candidates = {
            "partida",
            "numero_partida",
            "num_partida",
            "partida_numero",
            "secuencia_partida",
            "partida_seq",
        }
        for key, value in payload.items():
            key_norm = str(key or "").strip().lower()
            if key_norm not in candidates:
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                digits = "".join(ch for ch in value if ch.isdigit())
                if digits:
                    return int(digits)
        return None

    def _get_partida_numbers_for_validation(self):
        self.ensure_one()
        numbers = [p.numero_partida for p in self.partida_ids if p.numero_partida]
        if numbers:
            return sorted(set(numbers))

        inferred = []
        for reg in self.registro_ids:
            num = self._extract_partida_number(reg.valores)
            if num:
                inferred.append(num)
        return sorted(set(inferred))

    def _get_partida_meta_map(self):
        self.ensure_one()
        meta = {}
        for partida in self.partida_ids:
            if partida.numero_partida:
                meta[partida.numero_partida] = {
                    "fraccion_id": partida.fraccion_id.id if partida.fraccion_id else False,
                    "fraccion_capitulo": partida.fraccion_id.capitulo if partida.fraccion_id else False,
                }
        return meta

    def _resolve_rulepack(self):
        self.ensure_one()
        op_date = self.fecha_operacion or fields.Date.context_today(self)
        packs = self.env["mx.ped.rulepack"].search(
            [
                ("active", "=", True),
                ("state", "=", "active"),
                ("fecha_inicio", "<=", op_date),
                "|",
                ("fecha_fin", "=", False),
                ("fecha_fin", ">=", op_date),
            ],
            order="priority desc, fecha_inicio desc, id desc",
            limit=1,
        )
        return packs[:1]

    def _get_rulepack_effective(self):
        self.ensure_one()
        return self.rulepack_id or self._resolve_rulepack()

    def _is_strict_mode(self):
        self.ensure_one()
        if self.strict_mode_policy == "strict":
            return True
        if self.strict_mode_policy == "relaxed":
            return False

        partner_mode = (
            self.participante_id.x_rule_engine_strict
            or self.cliente_id.x_rule_engine_strict
            or "inherit"
        )
        if partner_mode == "strict":
            return True
        if partner_mode == "relaxed":
            return False

        raw = self.env["ir.config_parameter"].sudo().get_param("mx_ped.rule_engine.strict_mode", "false")
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    def _get_source_weights(self, rulepack):
        return {
            "estructura": int((rulepack.weight_estructura if rulepack else 10) or 10),
            "clave": int((rulepack.weight_clave if rulepack else 20) or 20),
            "condition": int((rulepack.weight_condition if rulepack else 30) or 30),
        }

    def _compute_specificity(self, rule, source):
        score = 0
        if source in ("selector", "condition", "process"):
            if getattr(rule, "tipo_movimiento_id", False):
                score += 30
            if getattr(rule, "clave_pedimento_id", False):
                score += 25
            if hasattr(rule, "escenario_code") and getattr(rule, "escenario_code", "") not in ("", "any"):
                score += 20
            if getattr(rule, "regimen", "") not in ("", "cualquiera"):
                score += 15
            if getattr(rule, "tipo_operacion", "") not in ("", "ambas"):
                score += 10
            if getattr(rule, "is_virtual", "") not in ("", "any"):
                score += 8
            if getattr(rule, "scope", "") == "partida":
                score += 5
            if getattr(rule, "fraccion_id", False):
                score += 22
            elif getattr(rule, "fraccion_capitulo", False):
                score += 12
        elif source == "clave":
            if getattr(rule, "scope", "") == "partida":
                score += 5
        return score

    def _build_rule_context(self, escenario_code=None):
        self.ensure_one()
        clave = self.clave_pedimento_id
        mov = self._get_tipo_movimiento_effective()
        fraccion_ids = {p.fraccion_id.id for p in self.partida_ids if p.fraccion_id}
        fraccion_capitulos = {p.fraccion_id.capitulo for p in self.partida_ids if p.fraccion_id and p.fraccion_id.capitulo}
        return {
            "tipo_movimiento": mov,
            "tipo_operacion": self.tipo_operacion or "",
            "regimen": self.regimen or "",
            "clave_id": clave.id if clave else False,
            "is_virtual": bool(clave and clave.is_virtual),
            "escenario": escenario_code or "",
            "fraccion_ids": fraccion_ids,
            "fraccion_capitulos": fraccion_capitulos,
        }

    def _rule_condition_match(self, rule, context):
        mov_code = rule.tipo_movimiento_id.code if getattr(rule, "tipo_movimiento_id", False) else False
        if mov_code and mov_code != context.get("tipo_movimiento"):
            return False
        if getattr(rule, "tipo_operacion", False) and rule.tipo_operacion not in ("", "ambas"):
            if rule.tipo_operacion != context.get("tipo_operacion"):
                return False
        if getattr(rule, "regimen", False) and rule.regimen not in ("", "cualquiera"):
            if rule.regimen != context.get("regimen"):
                return False
        if getattr(rule, "clave_pedimento_id", False) and rule.clave_pedimento_id.id != context.get("clave_id"):
            return False
        if getattr(rule, "is_virtual", False) and rule.is_virtual != "any":
            expected_virtual = (rule.is_virtual == "yes")
            if expected_virtual != bool(context.get("is_virtual")):
                return False
        if hasattr(rule, "escenario_code") and rule.escenario_code and rule.escenario_code != "any":
            if rule.escenario_code != context.get("escenario"):
                return False
        if hasattr(rule, "fraccion_id") and rule.fraccion_id:
            if rule.fraccion_id.id not in (context.get("fraccion_ids") or set()):
                return False
        if hasattr(rule, "fraccion_capitulo") and (rule.fraccion_capitulo or "").strip():
            cap = (rule.fraccion_capitulo or "").strip()
            if cap not in (context.get("fraccion_capitulos") or set()):
                return False
        return True

    def _select_rulepack_scenario(self):
        self.ensure_one()
        strict = self._is_strict_mode()
        rulepack = self._get_rulepack_effective()
        if not rulepack:
            if strict:
                raise UserError(_("Modo STRICT: no existe rulepack vigente para la fecha de operacion."))
            return {
                "scenario": self.env["mx.ped.rulepack.scenario"],
                "estructura_rule": self.env["mx.ped.estructura.regla"],
                "winner_selector": False,
                "selector_trace": {"candidates": [], "winner_selector_id": False},
            }

        context = self._build_rule_context()
        selectors = rulepack.selector_ids.filtered(lambda r: r.active).sorted(
            key=lambda r: (-r.priority, r.sequence, r.id)
        )
        selected = self.env["mx.ped.rulepack.scenario"]
        winner_selector = False
        selector_candidates = []
        for selector in selectors:
            matched = self._rule_condition_match(selector, context)
            selector_candidates.append({
                "selector_id": selector.id,
                "priority": selector.priority,
                "specificity_score": self._compute_specificity(selector, "selector"),
                "stop": bool(selector.stop),
                "matched": bool(matched),
                "scenario_id": selector.scenario_id.id if selector.scenario_id else False,
                "conditions": {
                    "tipo_movimiento_id": selector.tipo_movimiento_id.id if selector.tipo_movimiento_id else False,
                    "tipo_operacion": selector.tipo_operacion,
                    "regimen": selector.regimen,
                    "clave_pedimento_id": selector.clave_pedimento_id.id if selector.clave_pedimento_id else False,
                    "is_virtual": selector.is_virtual,
                },
            })
            if not matched:
                continue
            selected = selector.scenario_id
            winner_selector = selector
            if selector.stop:
                break

        if not selected:
            selected = rulepack.scenario_ids.filtered(lambda s: s.active and s.is_default)[:1]
        if not selected:
            selected = rulepack.scenario_ids.filtered(lambda s: s.active)[:1]
        if not selected and strict:
            raise UserError(_("Modo STRICT: no hay escenario seleccionable en el rulepack vigente."))
        if strict and selected and not selected.estructura_regla_id:
            raise UserError(_("Modo STRICT: el escenario seleccionado no tiene regla de estructura base."))

        return {
            "scenario": selected,
            "estructura_rule": selected.estructura_regla_id if selected else self.env["mx.ped.estructura.regla"],
            "winner_selector": winner_selector,
            "selector_trace": {
                "candidates": selector_candidates,
                "winner_selector_id": winner_selector.id if winner_selector else False,
            },
        }

    def _get_process_stage_rules(self, stage):
        self.ensure_one()
        rulepack = self._get_rulepack_effective()
        if not rulepack:
            return self.env["mx.ped.rulepack.process.rule"]
        context = self._build_rule_context()
        rules = rulepack.process_rule_ids.filtered(lambda r: r.active and r.stage == stage).sorted(
            key=lambda r: (-r.priority, -self._compute_specificity(r, "process"), r.sequence, r.id)
        )
        return rules.filtered(lambda r: self._rule_condition_match(r, context))

    def _resolve_estructura_regla(self):
        self.ensure_one()
        selected_data = self._select_rulepack_scenario()
        if selected_data.get("estructura_rule"):
            return selected_data["estructura_rule"]
        if self._is_strict_mode():
            raise UserError(_("Modo STRICT: no se pudo resolver una regla de estructura."))
        mov = self._get_tipo_movimiento_effective()
        if not mov:
            return self.env["mx.ped.estructura.regla"]
        detected_escenario = self._detect_escenario_estructura()
        rules = self.env["mx.ped.estructura.regla"].search(
            [
                ("active", "=", True),
                "|",
                ("tipo_movimiento_id.code", "=", mov),
                ("tipo_movimiento", "=", mov),
            ],
            order="priority desc, id desc",
        )
        best = self.env["mx.ped.estructura.regla"]
        best_score = -1
        for rule in rules:
            score = 0
            if rule.escenario and rule.escenario != "generico":
                if rule.escenario != detected_escenario:
                    continue
                score += 4
            if rule.clave_pedimento_id:
                if rule.clave_pedimento_id != self.clave_pedimento_id:
                    continue
                score += 3
            if rule.tipo_operacion and rule.tipo_operacion != "ambas":
                if rule.tipo_operacion != self.tipo_operacion:
                    continue
                score += 2
            if rule.regimen and rule.regimen != "cualquiera":
                if rule.regimen != self.regimen:
                    continue
                score += 1
            if score > best_score:
                best = rule
                best_score = score
        return best

    def _detect_escenario_estructura(self):
        self.ensure_one()
        selected_data = self._select_rulepack_scenario()
        selected_scenario = selected_data.get("scenario")
        if selected_scenario:
            return selected_scenario.code

        clave_structure = (self.clave_pedimento_id.saai_structure_type or "auto") if self.clave_pedimento_id else "auto"
        if clave_structure and clave_structure != "auto":
            return clave_structure
        if self._is_strict_mode():
            raise UserError(_("Modo STRICT: no se pudo determinar escenario de estructura."))
        return "generico"

    def _is_transito(self):
        self.ensure_one()
        code = (self.clave_pedimento_id.code or "").upper()
        return bool(code and (code.startswith("T") or code in {"TR"}))

    def _is_rectificacion(self):
        self.ensure_one()
        if self.es_rectificacion:
            return True
        return any((line.codigo or "") == "701" for line in self.registro_ids)

    def _parse_formas_pago_claves(self):
        self.ensure_one()
        raw = (self.formas_pago_claves or "").strip()
        if not raw:
            return set()
        return {token for token in re.findall(r"\d+", raw)}

    def _run_process_stage_checks(self, stage):
        self.ensure_one()
        stage_rules = self._get_process_stage_rules(stage)
        for rule in stage_rules:
            payload = rule.payload_json or {}
            action = rule.action_type
            if action == "require_formas_pago":
                allowed = set(str(v) for v in (payload.get("allowed") or []))
                current = self._parse_formas_pago_claves()
                if not current:
                    raise ValidationError(
                        _("Regla %s: captura formas de pago.") % (rule.name,)
                    )
                if allowed:
                    invalid = sorted(current - allowed, key=lambda x: int(x))
                    if invalid:
                        raise ValidationError(
                            _("Regla %s: formas permitidas %s. No permitidas: %s")
                            % (rule.name, ", ".join(sorted(allowed, key=lambda x: int(x))), ", ".join(invalid))
                        )
            elif action == "require_field":
                field_name = payload.get("field")
                if not field_name:
                    continue
                value = getattr(self, field_name, False)
                if not value:
                    raise ValidationError(_("Regla %s: el campo %s es obligatorio.") % (rule.name, field_name))
            elif action == "forbid_field":
                field_name = payload.get("field")
                if not field_name:
                    continue
                value = getattr(self, field_name, False)
                if value:
                    raise ValidationError(_("Regla %s: el campo %s debe estar vacio.") % (rule.name, field_name))
            if rule.stop:
                break

    def _validate_confirmacion_pago_formas(self):
        self.ensure_one()
        self._run_process_stage_checks("pre_validate")

    def _normalize_structure_rules(self, estructura_rule, source_weight):
        normalized = []
        if not estructura_rule:
            return normalized
        for line in estructura_rule.line_ids.sorted(lambda l: (l.sequence, l.id)):
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            min_occ = max(line.min_occurs or 0, 0)
            if line.required:
                min_occ = max(min_occ, 1)
            normalized.append({
                "rule_id": line.id,
                "source": "estructura",
                "source_weight": source_weight,
                "specificity_score": 0,
                "priority": 0,
                "scope": "pedimento",
                "record_code": code,
                "policy": "required" if line.required else "optional",
                "min": min_occ,
                "max": max(line.max_occurs or 0, 0),
                "identifier": "",
                "stop": False,
                "active": True,
                "applies": True,
                "extra": {"estructura_regla_id": estructura_rule.id},
            })
        return normalized

    def _normalize_clave_rules(self, source_weight):
        normalized = []
        clave = self.clave_pedimento_id
        if not clave:
            return normalized
        for line in clave.registro_policy_ids.sorted(lambda l: (-l.priority, l.sequence, l.id)):
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            normalized.append({
                "rule_id": line.id,
                "source": "clave",
                "source_weight": source_weight,
                "specificity_score": self._compute_specificity(line, "clave"),
                "priority": line.priority or 0,
                "scope": line.scope or "pedimento",
                "record_code": code,
                "policy": line.policy,
                "min": max(line.min_occurs or 0, 0),
                "max": max(line.max_occurs or 0, 0),
                "identifier": (line.required_identifier_code or "").strip().upper(),
                "stop": bool(line.stop),
                "active": True,
                "applies": True,
                "extra": {"clave_id": clave.id},
            })
        return normalized

    def _normalize_condition_rules(self, condition_rules, source_weight):
        normalized = []
        for rule in condition_rules:
            normalized.append({
                "rule_id": rule.id,
                "source": "condition",
                "source_weight": source_weight,
                "specificity_score": self._compute_specificity(rule, "condition"),
                "priority": rule.priority or 0,
                "scope": rule.scope or "pedimento",
                "record_code": (rule.registro_codigo or "").strip(),
                "policy": rule.policy,
                "min": max(rule.min_occurs or 0, 0),
                "max": max(rule.max_occurs or 0, 0),
                "identifier": (rule.required_identifier_code or "").strip().upper(),
                "stop": bool(rule.stop),
                "active": bool(rule.active),
                "applies": True,
                "extra": {
                    "fraccion_id": rule.fraccion_id.id if rule.fraccion_id else False,
                    "fraccion_capitulo": (rule.fraccion_capitulo or "").strip(),
                },
            })
        return normalized

    def _rule_sort_key(self, item):
        return (
            -(item.get("priority") or 0),
            -(item.get("specificity_score") or 0),
            -(item.get("source_weight") or 0),
            item.get("rule_id") or 0,
        )

    def _apply_rule_to_state(self, state, rule_item):
        policy = rule_item.get("policy")
        min_occ = max(rule_item.get("min") or 0, 0)
        max_occ = max(rule_item.get("max") or 0, 0)
        identifier = (rule_item.get("identifier") or "").strip().upper()

        if policy == "forbidden":
            state["forbidden"] = True
            state["required"] = False
            state["min"] = 0
            state["max"] = 0
        elif policy == "required" and not state.get("forbidden"):
            state["required"] = True
            state["min"] = max(state["min"], max(min_occ, 1))
        elif policy == "optional" and not state.get("forbidden"):
            state["min"] = max(state["min"], min_occ)

        if max_occ and not state.get("forbidden"):
            state["max"] = max_occ if not state["max"] else min(state["max"], max_occ)
        if identifier:
            state["identifier"] = identifier

    def _build_record_plan(self):
        """Construye plan determinista: normaliza reglas, aplica precedencias y guarda explicabilidad."""
        self.ensure_one()
        selected = self._select_rulepack_scenario()
        scenario = selected.get("scenario")
        estructura_rule = self.estructura_regla_id or selected.get("estructura_rule") or self._resolve_estructura_regla()
        rulepack = self._get_rulepack_effective()

        weights = self._get_source_weights(rulepack)
        condition_rules = self._get_dynamic_condition_rules()

        normalized = []
        normalized.extend(self._normalize_structure_rules(estructura_rule, weights["estructura"]))
        normalized.extend(self._normalize_clave_rules(weights["clave"]))
        normalized.extend(self._normalize_condition_rules(condition_rules, weights["condition"]))
        normalized = [n for n in normalized if n.get("record_code")]

        grouped = {}
        for item in normalized:
            key = (item.get("record_code"), item.get("scope") or "pedimento")
            grouped.setdefault(key, []).append(item)
        for key in list(grouped.keys()):
            grouped[key] = sorted(grouped[key], key=self._rule_sort_key)

        base_states = {}
        for item in normalized:
            if item.get("source") != "estructura" or (item.get("scope") or "pedimento") != "pedimento":
                continue
            code = item["record_code"]
            state = base_states.setdefault(code, {"required": False, "forbidden": False, "min": 0, "max": 0, "identifier": ""})
            self._apply_rule_to_state(state, item)

        states = {}
        record_resolution = {}
        trace_rows = []
        partida_policies = []

        for (code, scope), items in grouped.items():
            if scope == "partida":
                partida_policies.extend(items)
                continue
            state = dict(base_states.get(code, {"required": False, "forbidden": False, "min": 0, "max": 0, "identifier": ""}))
            winner = None
            blocked = False
            candidates = []
            for item in items:
                row = {
                    "rule_id": item["rule_id"],
                    "source": item["source"],
                    "record_code": code,
                    "scope": scope,
                    "policy": item["policy"],
                    "priority": item["priority"],
                    "source_weight": item["source_weight"],
                    "specificity_score": item["specificity_score"],
                    "min": item["min"],
                    "max": item["max"],
                    "identifier": item["identifier"],
                    "stop": item["stop"],
                    "matched": True,
                    "applied": False,
                    "blocked": False,
                }
                if blocked:
                    row["blocked"] = True
                    candidates.append(row)
                    continue
                self._apply_rule_to_state(state, item)
                row["applied"] = True
                candidates.append(row)
                if winner is None:
                    winner = row
                if item.get("stop"):
                    blocked = True

            if state.get("forbidden"):
                state["required"] = False
                state["min"] = 0
                state["max"] = 0
            states[code] = state
            record_resolution[f"{code}|{scope}"] = {
                "base_state": base_states.get(code, {"required": False, "forbidden": False, "min": 0, "max": 0, "identifier": ""}),
                "winner_rule_id": winner["rule_id"] if winner else False,
                "winner_source": winner["source"] if winner else False,
                "candidates": candidates,
                "final_state": state,
            }
            trace_rows.extend(candidates)

        diff = {"added_records": [], "removed_records": [], "changed_records": []}
        final_keys = set(states.keys())
        base_keys = set(base_states.keys())
        diff["added_records"] = sorted(list(final_keys - base_keys))
        diff["removed_records"] = sorted(list(base_keys - final_keys))
        for code in sorted(final_keys & base_keys):
            if states[code] != base_states[code]:
                diff["changed_records"].append({"key": f"{code}|pedimento", "from": base_states[code], "to": states[code]})

        return {
            "rulepack": rulepack,
            "scenario": scenario,
            "rule": estructura_rule,
            "states": states,
            "base_states": base_states,
            "trace": trace_rows,
            "record_resolution": record_resolution,
            "selector_trace": selected.get("selector_trace") or {"candidates": [], "winner_selector_id": False},
            "winner_selector_id": selected.get("winner_selector").id if selected.get("winner_selector") else False,
            "partida_policies": sorted(partida_policies, key=self._rule_sort_key),
            "normalized_rules": normalized,
            "diff_base_final": diff,
            "weights": weights,
        }

    def _store_rule_trace(self, plan):
        self.ensure_one()
        if not self.id or self.env.context.get("skip_rule_trace_write"):
            return
        plan = plan or {}
        trace_rows = plan.get("trace") or []
        truncated = False
        if len(trace_rows) > 500:
            trace_rows = trace_rows[:500]
            truncated = True
        trace_payload = {
            "meta": {
                "operation_id": self.id,
                "generated_at": fields.Datetime.now().isoformat(),
                "strict_mode": self._is_strict_mode(),
                "rulepack_id": plan.get("rulepack").id if plan.get("rulepack") else False,
                "rulepack_code": plan.get("rulepack").code if plan.get("rulepack") else False,
                "fecha_operacion": str(self.fecha_operacion or ""),
                "trace_truncated": truncated,
            },
            "selector_trace": plan.get("selector_trace") or {"candidates": [], "winner_selector_id": False},
            "winner_selector_id": plan.get("winner_selector_id") or False,
            "records": plan.get("record_resolution") or {},
            "diff_base_final": plan.get("diff_base_final") or {},
            "states": plan.get("states") or {},
            "trace": trace_rows,
            "errors": plan.get("errors") or [],
        }
        self.with_context(skip_rule_trace_write=True).write({
            "rule_trace_json": trace_payload,
            "rule_trace_at": fields.Datetime.now(),
        })

    def _get_stage_allowed_codes(self, stage):
        self.ensure_one()
        rules = self._get_process_stage_rules(stage)
        allowed = None
        for rule in rules:
            if rule.action_type != "allow_only_records":
                continue
            payload = rule.payload_json or {}
            rule_codes = {str(code).zfill(3) for code in (payload.get("codes") or []) if str(code).strip()}
            if allowed is None:
                allowed = rule_codes
            else:
                allowed &= rule_codes
            if rule.stop:
                break
        return allowed

    def _get_dynamic_condition_rules(self):
        self.ensure_one()
        rulepack = self._get_rulepack_effective()
        if not rulepack:
            return self.env["mx.ped.rulepack.condition.rule"]
        context = self._build_rule_context(self._detect_escenario_estructura())
        rules = rulepack.condition_rule_ids.filtered(lambda r: r.active).sorted(
            key=lambda r: (-r.priority, r.sequence, r.id)
        )
        return rules.filtered(lambda r: self._rule_condition_match(r, context))

    def _get_allowed_codes_from_regla(self):
        self.ensure_one()
        plan = self._build_record_plan()
        self._store_rule_trace(plan)
        states = plan["states"]

        # Sin regla base no restringimos layout para evitar omisiones no deseadas.
        if not plan["rule"]:
            return None

        allowed = {code for code, state in states.items() if not state.get("forbidden")}
        return allowed if allowed else None

    def _validate_registros_vs_estructura(self):
        self.ensure_one()
        counts = Counter((r.codigo or "") for r in self.registro_ids)
        errors = []

        plan = self._build_record_plan()
        self._store_rule_trace(plan)
        states = plan["states"]

        for code, state in states.items():
            present = counts.get(code, 0)
            min_occ = max(state.get("min") or 0, 0)
            max_occ = max(state.get("max") or 0, 0)

            if state.get("forbidden"):
                if present > 0:
                    errors.append(_("Registro %s esta prohibido para este contexto y se encontraron %s.") % (code, present))
                continue

            if state.get("required") and present < max(min_occ, 1):
                errors.append(_("Falta registro %s (min %s, actual %s).") % (code, max(min_occ, 1), present))
            elif min_occ and present < min_occ:
                errors.append(_("Falta registro %s (min %s, actual %s).") % (code, min_occ, present))

            if max_occ and present > max_occ:
                errors.append(_("Registro %s excede maximo (%s > %s).") % (code, present, max_occ))

            identifier = (state.get("identifier") or "").strip().upper()
            if identifier and present:
                has_identifier = any(
                    self._payload_has_token(reg.valores, identifier)
                    for reg in self.registro_ids
                    if (reg.codigo or "") == code
                )
                if not has_identifier:
                    errors.append(_("Registro %s exige identificador %s.") % (code, identifier))

        # Reglas con alcance partida: se validan por cada numero_partida.
        partida_policies = [p for p in (plan.get("partida_policies") or []) if (p.get("scope") or "pedimento") == "partida"]
        if partida_policies:
            partida_numbers = self._get_partida_numbers_for_validation()
            partida_meta = self._get_partida_meta_map()
            if not partida_numbers:
                errors.append(_(
                    "Existen reglas de alcance partida pero no hay numero_partida capturado en partidas o registros."
                ))
            else:
                per_partida_counts = {}
                per_partida_has_identifier = {}
                for reg in self.registro_ids:
                    code = (reg.codigo or "").strip()
                    partida_num = self._extract_partida_number(reg.valores)
                    if not partida_num:
                        continue
                    per_partida_counts[(partida_num, code)] = per_partida_counts.get((partida_num, code), 0) + 1
                    for policy in partida_policies:
                        if policy.get("record_code") != code:
                            continue
                        identifier = (policy.get("identifier") or "").strip().upper()
                        if identifier and self._payload_has_token(reg.valores, identifier):
                            per_partida_has_identifier[(partida_num, code)] = True

                for partida_num in partida_numbers:
                    partida_state = {}
                    blocked_codes = set()
                    meta = partida_meta.get(partida_num, {})
                    fraccion_id = meta.get("fraccion_id")
                    for policy in partida_policies:
                        code = policy.get("record_code")
                        if not code or code in blocked_codes:
                            continue
                        policy_fraccion = (policy.get("extra") or {}).get("fraccion_id")
                        policy_capitulo = ((policy.get("extra") or {}).get("fraccion_capitulo") or "").strip()
                        if policy_fraccion and policy_fraccion != fraccion_id:
                            continue
                        if policy_capitulo and not str(partida_meta.get(partida_num, {}).get("fraccion_capitulo", "")).strip() == policy_capitulo:
                            continue
                        state = partida_state.setdefault(code, {
                            "required": False,
                            "forbidden": False,
                            "min": 0,
                            "max": 0,
                            "identifier": "",
                        })
                        policy_type = policy.get("policy")
                        min_occ = max(policy.get("min") or 0, 0)
                        max_occ = max(policy.get("max") or 0, 0)
                        identifier = (policy.get("identifier") or "").strip().upper()

                        if policy_type == "forbidden":
                            state["forbidden"] = True
                            state["required"] = False
                            state["min"] = 0
                            state["max"] = 0
                        elif policy_type == "required" and not state["forbidden"]:
                            state["required"] = True
                            state["min"] = max(state["min"], max(min_occ, 1))
                        elif policy_type == "optional" and not state["forbidden"]:
                            state["min"] = max(state["min"], min_occ)

                        if max_occ and not state["forbidden"]:
                            state["max"] = max_occ if not state["max"] else min(state["max"], max_occ)
                        if identifier:
                            state["identifier"] = identifier
                        if policy.get("stop"):
                            blocked_codes.add(code)

                    for code, state in partida_state.items():
                        present = per_partida_counts.get((partida_num, code), 0)
                        min_occ = max(state.get("min") or 0, 0)
                        max_occ = max(state.get("max") or 0, 0)

                        if state.get("forbidden"):
                            if present > 0:
                                errors.append(_(
                                    "Partida %s: registro %s esta prohibido y se encontraron %s."
                                ) % (partida_num, code, present))
                            continue

                        if state.get("required") and present < max(min_occ, 1):
                            errors.append(_(
                                "Partida %s: falta registro %s (min %s, actual %s)."
                            ) % (partida_num, code, max(min_occ, 1), present))
                        elif min_occ and present < min_occ:
                            errors.append(_(
                                "Partida %s: falta registro %s (min %s, actual %s)."
                            ) % (partida_num, code, min_occ, present))

                        if max_occ and present > max_occ:
                            errors.append(_(
                                "Partida %s: registro %s excede maximo (%s > %s)."
                            ) % (partida_num, code, present, max_occ))

                        identifier = (state.get("identifier") or "").strip().upper()
                        if identifier and present and not per_partida_has_identifier.get((partida_num, code), False):
                            errors.append(_(
                                "Partida %s: registro %s exige identificador %s."
                            ) % (partida_num, code, identifier))

        if errors:
            plan["errors"] = errors
            self._store_rule_trace(plan)
            raise UserError("\n".join(errors))

    def action_preparar_estructura(self):
        for rec in self:
            plan = rec._build_record_plan()
            rule = plan.get("rule")
            if not rule and not plan.get("states"):
                raise UserError(_("No existe una regla de estructura para este contexto."))
            if rule:
                rec.estructura_regla_id = rule
            counts = Counter((r.codigo or "") for r in rec.registro_ids)
            new_lines = []
            states = plan.get("states") or {}
            line_order = {}
            if rule:
                for idx, line in enumerate(rule.line_ids.sorted(lambda l: (l.sequence, l.id)), start=1):
                    code = (line.registro_codigo or "").strip()
                    if code and code not in line_order:
                        line_order[code] = idx

            for code in sorted(states.keys(), key=lambda c: (line_order.get(c, 9999), c)):
                state = states[code]
                if state.get("forbidden"):
                    continue
                min_occurs = max(state.get("min") or 0, 0)
                if state.get("required"):
                    min_occurs = max(min_occurs, 1)
                needed = min_occurs - counts.get(code, 0)
                seq_base = counts.get(code, 0)
                for i in range(max(needed, 0)):
                    new_lines.append((0, 0, {
                        "codigo": code,
                        "secuencia": seq_base + i + 1,
                        "valores": {},
                    }))
                counts[code] = counts.get(code, 0) + max(needed, 0)
            if new_lines:
                rec.write({"registro_ids": new_lines})
            rec._store_rule_trace(plan)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Estructura preparada"),
                "message": _("Registros base agregados según regla de estructura."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_simular_estructura(self):
        self.ensure_one()
        plan = self._build_record_plan()
        states = plan.get("states") or {}
        counts = Counter((r.codigo or "") for r in self.registro_ids)

        missing = []
        forbidden = []
        for code, state in sorted(states.items()):
            present = counts.get(code, 0)
            min_occ = max(state.get("min") or 0, 0)
            if state.get("required"):
                min_occ = max(min_occ, 1)
            if state.get("forbidden"):
                if present:
                    forbidden.append(f"{code}({present})")
                continue
            if min_occ and present < min_occ:
                missing.append(f"{code}({present}/{min_occ})")

        summary = [
            _("Regla: %s") % (plan.get("rule").display_name if plan.get("rule") else _("sin regla")),
            _("Faltantes: %s") % (", ".join(missing) if missing else _("ninguno")),
            _("Prohibidos presentes: %s") % (", ".join(forbidden) if forbidden else _("ninguno")),
        ]
        plan["errors"] = []
        if missing:
            plan["errors"].append(_("Faltan registros obligatorios."))
        if forbidden:
            plan["errors"].append(_("Hay registros prohibidos capturados."))
        self._store_rule_trace(plan)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Simulacion de estructura"),
                "message": "\n".join(summary),
                "type": "warning" if (missing or forbidden) else "success",
                "sticky": bool(missing or forbidden),
            },
        }

    def action_explain_ruleplan(self):
        self.ensure_one()
        plan = self._build_record_plan()
        self._store_rule_trace(plan)
        payload = self.rule_trace_json or {}
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        attachment = self.env["ir.attachment"].create({
            "name": f"RULEPLAN_{self.name or self.id}.json",
            "type": "binary",
            "datas": base64.b64encode(data),
            "mimetype": "application/json",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _get_invoice_partner(self):
        self.ensure_one()
        lead = self.lead_id
        partner = lead.partner_id or lead.x_importador_id or lead.x_exportador_id
        if not partner:
            raise UserError(
                _("La operación no tiene cliente para facturar. Define Cliente/Importador/Exportador en el Lead.")
            )
        return partner

    def _get_invoice_origin(self):
        self.ensure_one()
        parts = [self.name or ""]
        if self.pedimento_numero:
            parts.append(f"PED-{self.pedimento_numero}")
        return " / ".join([p for p in parts if p])

    def _prepare_optional_invoice_lines(self):
        self.ensure_one()
        lead = self.lead_id
        concepts = [
            (_("Honorarios aduanales"), lead.x_costo_estimado),
            (_("DTA estimado"), lead.x_dta_estimado),
            (_("PRV estimado"), lead.x_prv_estimado),
            (_("IGI estimado"), lead.x_igi_estimado),
            (_("IVA estimado"), lead.x_iva_estimado),
        ]
        lines = []
        for name, amount in concepts:
            if amount and amount > 0:
                lines.append((0, 0, {
                    "name": name,
                    "quantity": 1.0,
                    "price_unit": amount,
                }))
        return lines

    def action_crear_factura(self):
        self.ensure_one()
        partner = self._get_invoice_partner()
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "currency_id": self.currency_id.id,
            "invoice_origin": self._get_invoice_origin(),
            "x_ped_operacion_id": self.id,
        })

        line_vals = self._prepare_optional_invoice_lines()
        if line_vals:
            try:
                move.write({"invoice_line_ids": line_vals})
            except Exception:
                # Fallback: keep invoice linked even if product/account setup is incomplete.
                move.write({
                    "invoice_line_ids": [(0, 0, {
                        "display_type": "line_note",
                        "name": _("No se pudieron crear líneas automáticas. Revisa cuentas/productos de facturación."),
                    })]
                })

        if self.lead_id:
            self.lead_id.write({
                "x_factura_emitida": True,
                "x_factura_ref": move.name or str(move.id),
            })

        return {
            "type": "ir.actions.act_window",
            "name": _("Factura"),
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_facturas(self):
        self.ensure_one()
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        action["domain"] = [("x_ped_operacion_id", "=", self.id), ("move_type", "=", "out_invoice")]
        action["context"] = {
            "default_move_type": "out_invoice",
            "default_partner_id": self._get_invoice_partner().id,
            "default_currency_id": self.currency_id.id,
            "default_x_ped_operacion_id": self.id,
            "default_invoice_origin": self._get_invoice_origin(),
        }
        return action

    # ==========================
    # Exportación TXT / XML
    # ==========================
    def _get_layout_registro(self, codigo):
        self.ensure_one()
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        matches = self.layout_id.registro_ids.filtered(lambda r: r.codigo == codigo)
        if not matches:
            raise UserError(_("No existe layout para el registro %s.") % codigo)
        return matches.sorted(lambda r: r.orden or 0)[0]

    def _format_txt_value(self, campo, val):
        txt = str(val)

        # Sanea caracteres de control para no romper el TXT por renglones/columnas.
        txt = txt.replace("\r", " ").replace("\n", " ").replace("\t", " ")
        txt = txt.replace("|", " ")
        txt = " ".join(txt.split())

        # Normaliza tipo de operaci?n (1/2). Si el layout pide 2 d?gitos, se rellena.
        source_name = (
            campo.source_field_id.name
            if getattr(campo, "source_field_id", False)
            else campo.source_field
        ) or campo.nombre
        if source_name in ("tipo_operacion", "x_tipo_operacion"):
            normalized = txt.strip().lower()
            if normalized in ("importacion", "1", "01"):
                txt = "1"
            elif normalized in ("exportacion", "2", "02"):
                txt = "2"
            if campo.longitud == 2:
                txt = txt.zfill(2)

        if campo.tipo == "N":
            txt = "".join(ch for ch in txt if ch.isdigit())
        # Normaliza paises a clave corta cuando el campo es de pais y longitud pequena.
        # Evita errores tipo "excede longitud 3" por valores como "MEXICO".
        source_norm = (source_name or "").strip().lower()
        if (
            campo.tipo in ("A", "AN")
            and campo.longitud
            and campo.longitud <= 3
            and ("pais" in source_norm or "country" in source_norm)
        ):
            txt = self._normalize_country_token(txt, campo.longitud)
        return txt

    def _normalize_country_token(self, raw_value, max_len):
        token = (raw_value or "").strip()
        if not token:
            return ""

        # Si ya cabe, no tocar.
        if len(token) <= max_len:
            return token

        upper = token.upper()
        country_model = self.env["res.country"].sudo()

        country = country_model.search([("code", "=", upper)], limit=1)
        if not country:
            country = country_model.search([("name", "=ilike", token)], limit=1)
        if not country:
            country = country_model.search([("name", "ilike", token)], limit=1)

        if country and country.code:
            code = country.code.strip().upper()
            if len(code) <= max_len:
                return code

        # Ultimo recurso: truncar para no romper exportacion.
        return token[:max_len]

    def _build_txt_line(self, layout_registro, valores):
        layout = layout_registro.layout_id
        campos = layout_registro.campo_ids.sorted(lambda c: c.orden or c.pos_ini or 0)

        if layout.export_format == "pipe":
            parts = []
            for campo in campos:
                val = (valores or {}).get(campo.nombre)
                if val in (None, ""):
                    if campo.default:
                        val = campo.default
                    elif campo.requerido:
                        raise UserError(
                            _("Falta el campo requerido %s en registro %s.")
                            % (campo.nombre, layout_registro.codigo)
                        )
                    else:
                        val = ""

                txt = self._format_txt_value(campo, val)
                if campo.longitud and len(txt) > campo.longitud:
                    raise UserError(
                        _("El campo %s excede la longitud %s.")
                        % (campo.nombre, campo.longitud)
                    )
                parts.append(txt)

            return (layout.field_separator or "|").join(parts)

        line = [" "] * 2000
        max_pos = 0
        for campo in campos:
            if not campo.pos_ini or not campo.pos_fin:
                raise UserError(
                    _("El campo %s del registro %s no tiene posiciones válidas.")
                    % (campo.nombre, layout_registro.codigo)
                )
            length = campo.longitud or (campo.pos_fin - campo.pos_ini + 1)

            val = (valores or {}).get(campo.nombre)
            if val in (None, ""):
                if campo.default:
                    val = campo.default
                elif campo.requerido:
                    raise UserError(
                        _("Falta el campo requerido %s en registro %s.")
                        % (campo.nombre, layout_registro.codigo)
                    )
                else:
                    val = ""

            txt = self._format_txt_value(campo, val)

            if len(txt) > length:
                raise UserError(
                    _("El campo %s excede la longitud %s.")
                    % (campo.nombre, length)
                )

            if campo.tipo in ("A", "AN", "F"):
                txt = txt.ljust(length)
            else:
                txt = txt.rjust(length, "0")

            pos_ini = campo.pos_ini - 1
            pos_fin = pos_ini + length
            if pos_fin > len(line):
                line.extend([" "] * (pos_fin - len(line)))
            line[pos_ini:pos_fin] = list(txt)
            max_pos = max(max_pos, pos_fin)

        return "".join(line[:max_pos])

    def action_export_txt(self):
        self.ensure_one()
        self._validate_confirmacion_pago_formas()
        self._run_process_stage_checks("export")
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))
        self._validate_registros_vs_estructura()

        lines = []
        for reg in self.registro_ids.sorted(lambda r: (r.codigo, r.secuencia or 0)):
            layout_reg = self._get_layout_registro(reg.codigo)
            lines.append(self._build_txt_line(layout_reg, reg.valores))

        sep = self.layout_id.record_separator or "\n"
        txt_data = sep.join(lines)
        attachment = self.env["ir.attachment"].create({
            "name": self._build_txt_filename(),
            "type": "binary",
            "datas": base64.b64encode(txt_data.encode("utf-8")),
            "mimetype": "text/plain",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_export_xml(self):
        self.ensure_one()
        self._validate_confirmacion_pago_formas()
        self._run_process_stage_checks("export")
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))
        self._validate_registros_vs_estructura()

        root = ET.Element("pedimento", layout=(self.layout_id.name or ""))
        for reg in self.registro_ids.sorted(lambda r: (r.codigo, r.secuencia or 0)):
            reg_el = ET.SubElement(
                root,
                "registro",
                codigo=str(reg.codigo or ""),
                secuencia=str(reg.secuencia or 1),
            )
            layout_reg = self._get_layout_registro(reg.codigo)
            for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or 0):
                val = (reg.valores or {}).get(campo.nombre)
                if val in (None, ""):
                    val = campo.default or ""
                campo_el = ET.SubElement(reg_el, "campo", nombre=campo.nombre or "")
                campo_el.text = str(val)

        xml_data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        attachment = self.env["ir.attachment"].create({
            "name": f"PEDIMENTO_{self.name}.xml",
            "type": "binary",
            "datas": base64.b64encode(xml_data),
            "mimetype": "application/xml",
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def _extract_bl_pdf_text(self, pdf_bytes):
        if not PdfReader:
            raise UserError(_("Falta dependencia PyPDF2 en el servidor para leer PDF de B/L."))
        reader = PdfReader(io.BytesIO(pdf_bytes))
        chunks = []
        for page in reader.pages[:3]:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks)

    def _parse_bl_text(self, text):
        clean = re.sub(r"[ \t]+", " ", text or "")

        def _pick(patterns):
            for pat in patterns:
                m = re.search(pat, clean, re.IGNORECASE | re.MULTILINE)
                if m:
                    return (m.group(1) or "").strip()
            return False

        bl_no = _pick([
            r"\bB/?L\s*(?:NO\.?|NUMBER)?\s*[:#]?\s*([A-Z0-9\-]+)",
            r"\bMBL\s*[:#]?\s*([A-Z0-9\-]+)",
            r"\bMASTER\s*B/?L\s*[:#]?\s*([A-Z0-9\-]+)",
        ])
        container = _pick([r"\b([A-Z]{4}\d{7})\b"])
        seal = _pick([r"\b(?:SEAL\s*NO\.?\s*[:#]?\s*|/)([A-Z0-9]{6,})\b"])
        kgs = _pick([r"(\d+(?:\.\d+)?)\s*KGS\b"])
        cbm = _pick([r"(\d+(?:\.\d+)?)\s*CBM\b"])
        bultos = _pick([
            r"/\s*(\d+)\s+[A-Z ]{2,20}/",
            r"\b(\d+)\s+(?:WOODEN\s+CASES?|PACKAGES?|PKGS?)\b",
        ])
        loading = _pick([r"Port of Loading\s*([A-Z0-9 ,\-\(\)]+)"])
        discharge = _pick([r"Port of discharge:\s*Place of delivery\s*([A-Z0-9 ,\-\(\)\/]+)"])
        vessel_line = _pick([r"Ocean Vessel\s+Voy\.?No\.\s+Port of Loading\s*([A-Z0-9 .,\-\(\)]+)"])

        return {
            "bl_no": bl_no,
            "container": container,
            "seal": seal,
            "kgs": kgs,
            "cbm": cbm,
            "bultos": bultos,
            "loading": loading,
            "discharge": discharge,
            "vessel": vessel_line,
        }

    def action_read_bl(self):
        self.ensure_one()
        if not self.bl_file:
            raise UserError(_("Sube primero el archivo B/L en PDF."))
        if not self.lead_id:
            raise UserError(_("La operacion requiere un Lead asociado para cargar datos del B/L."))

        pdf_bytes = base64.b64decode(self.bl_file)
        text = self._extract_bl_pdf_text(pdf_bytes)
        parsed = self._parse_bl_text(text)
        if not any(parsed.values()):
            raise UserError(_("No se detectaron datos utiles en el B/L. Revisa calidad del PDF."))

        lead_vals = {}
        if parsed.get("bl_no"):
            lead_vals["x_guia_manifiesto"] = parsed["bl_no"]
            lead_vals["x_tipo_guia"] = "M"
        if parsed.get("container"):
            lead_vals["x_num_contenedor"] = parsed["container"]
        if parsed.get("seal"):
            lead_vals["x_num_sello"] = parsed["seal"]
        if parsed.get("bultos"):
            try:
                lead_vals["x_bultos"] = int(float(parsed["bultos"]))
            except Exception:
                pass
        if parsed.get("kgs"):
            try:
                lead_vals["x_peso_bruto"] = float(parsed["kgs"])
            except Exception:
                pass
        if parsed.get("cbm"):
            try:
                lead_vals["x_volumen_cbm"] = float(parsed["cbm"])
            except Exception:
                pass
        if parsed.get("loading"):
            lead_vals["x_lugar_carga"] = parsed["loading"]
        if parsed.get("discharge"):
            lead_vals["x_lugar_descarga"] = parsed["discharge"]

        if lead_vals:
            self.lead_id.write(lead_vals)
        if parsed.get("vessel"):
            note = f"B/L vessel/voy: {parsed['vessel']}"
            self.observaciones = f"{(self.observaciones or '').strip()}\n{note}".strip()
        self.bl_last_read = fields.Datetime.now()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("B/L procesado"),
                "message": _("Datos cargados al lead vinculado."),
                "type": "success",
                "sticky": False,
            },
        }

    def _build_txt_filename(self):
        self.ensure_one()
        patente_raw = (
            self.patente
            or (self.agente_aduanal_id.x_patente_aduanal if self.agente_aduanal_id else "")
            or (self.lead_id.x_agente_aduanal_id.x_patente_aduanal if self.lead_id and self.lead_id.x_agente_aduanal_id else "")
            or (self.lead_id.x_patente_agente if self.lead_id else "")
        )
        patente = "".join(ch for ch in str(patente_raw or "") if ch.isdigit())
        if not patente:
            raise UserError(_("Falta la patente para construir el nombre SAAI (mppppnnn.ddd)."))
        if len(patente) > 4:
            raise UserError(_("La patente debe tener maximo 4 digitos para el nombre SAAI."))
        patente = patente.zfill(4)

        today = fields.Date.context_today(self)
        julian_day = today.timetuple().tm_yday
        ddd = f"{julian_day:03d}"
        prefix = f"m{patente}"
        regex = re.compile(rf"^{prefix}(\d{{3}})\.{ddd}$")

        existing = self.env["ir.attachment"].search([
            ("name", "=like", f"{prefix}%.{ddd}"),
            ("mimetype", "=", "text/plain"),
        ])
        seq = 0
        for att in existing:
            m = regex.match(att.name or "")
            if m:
                seq = max(seq, int(m.group(1)))
        seq += 1
        if seq > 999:
            raise UserError(_("Se alcanzo el consecutivo diario maximo (999) para la patente %s.") % patente)

        # Formato obligatorio SAAI M3: mppppnnn.ddd
        return f"{prefix}{seq:03d}.{ddd}"

    def _get_pedimento_number_parts(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        yy = f"{today.year % 100:02d}"
        year_last_digit = str(today.year)[-1]

        aduana_digits = "".join(ch for ch in str(self.aduana_clave or "") if ch.isdigit())
        if len(aduana_digits) < 2:
            raise UserError(_("La aduana debe tener al menos 2 digitos para generar el numero de pedimento."))
        aa = aduana_digits[:2]

        patente_raw = (
            self.patente
            or (self.agente_aduanal_id.x_patente_aduanal if self.agente_aduanal_id else "")
            or (self.lead_id.x_agente_aduanal_id.x_patente_aduanal if self.lead_id and self.lead_id.x_agente_aduanal_id else "")
            or (self.lead_id.x_patente_agente if self.lead_id else "")
        )
        patente_digits = "".join(ch for ch in str(patente_raw or "") if ch.isdigit())
        if not patente_digits:
            raise UserError(_("Falta la patente para generar el numero de pedimento."))
        if len(patente_digits) > 4:
            raise UserError(_("La patente debe tener maximo 4 digitos."))
        pppp = patente_digits.zfill(4)
        return yy, aa, pppp, year_last_digit

    def _next_pedimento_consecutivo(self, yy, aa, pppp):
        self.ensure_one()
        control_model = self.env["mx.ped.numero.control"].sudo()
        control = control_model.search([
            ("year_two", "=", yy),
            ("aduana_clave", "=", aa),
            ("patente", "=", pppp),
        ], limit=1)
        if not control:
            control = control_model.with_context(real_user_id=self.env.user.id).create({
                "year_two": yy,
                "aduana_clave": aa,
                "patente": pppp,
                "ultimo_consecutivo": 0,
            })

        self.env.cr.execute(
            "SELECT ultimo_consecutivo FROM mx_ped_numero_control WHERE id = %s FOR UPDATE",
            [control.id],
        )
        current = self.env.cr.fetchone()[0] or 0
        next_value = current + 1
        if next_value > 999999:
            raise UserError(_("Se alcanzo el maximo de consecutivo 999999 para %s-%s-%s.") % (yy, aa, pppp))

        control.with_context(real_user_id=self.env.user.id).write({"ultimo_consecutivo": next_value})
        return f"{next_value:06d}"

    def action_asignar_numero_pedimento(self):
        for rec in self:
            yy, aa, pppp, d = rec._get_pedimento_number_parts()
            nnnnnn = rec._next_pedimento_consecutivo(yy, aa, pppp)
            # El numero visible del pedimento debe conservar solo el bloque final (7 digitos).
            rec.pedimento_numero = f"{d}{nnnnnn}"
        return True

    # ==========================
    # Cargar registros desde Lead
    # ==========================
    def _extract_value(self, value):
        if value is False:
            return ""
        if hasattr(value, "id"):
            if not value:
                return ""
            if hasattr(value, "code") and value.code:
                return value.code
            if hasattr(value, "name") and value.name:
                return value.name
            return value.id
        return value

    def _record_value_for_field(self, record, field_name):
        if not record:
            return None
        if field_name in record._fields:
            return self._extract_value(getattr(record, field_name))
        if not field_name.startswith("x_"):
            pref = f"x_{field_name}"
            if pref in record._fields:
                return self._extract_value(getattr(record, pref))
        return None

    def _lead_value_for_field_name(self, field_name, source_field=None, source_model=None):
        self.ensure_one()
        lead = self.lead_id

        def _norm(name):
            return (name or "").lower().replace(" ", "").replace("_", "")

        aliases = {
            "aduana": "aduana_clave",
            "patente": "patente",
            "clave_pedimento": "clave_pedimento",
            "tipo_operacion": "tipo_operacion",
            "tipo_movimiento": "tipo_movimiento",
            "regimen": "regimen",
            "incoterm": "incoterm",
            "moneda": "currency_id",
            "pais_origen": "x_pais_origen_id",
            "pais_destino": "x_pais_destino_id",
            "bultos": "x_bultos",
            "peso_bruto": "x_peso_bruto",
            "peso_neto": "x_peso_neto",
            "valor_factura": "x_valor_factura",
            "valor_aduana": "x_valor_aduana_estimado",
            "folio_operacion": "x_folio_operacion",
            "referencia_cliente": "x_referencia_cliente",
            "aduana_seccion_entrada_salida": "aduana_seccion_entrada_salida",
            "medio_transporte_salida": "x_medio_transporte_salida",
            "tipo_contenedor": "x_tipo_contenedor_id",
            "clave_tipo_contenedor": "x_tipo_contenedor_id",
            "identificador_guia": "x_tipo_guia",
            "guia_manifiesto": "x_guia_manifiesto",
            "acuse_validacion": "acuse_validacion",
            "curp_agente": "curp_agente",
            "rfc_importador_exportador": "participante_rfc",
            "curp_importador_exportador": "participante_curp",
            "nombre_importador_exportador": "participante_nombre",
            "transportista_rfc": "x_transportista_rfc",
            "transportista_curp": "x_transportista_curp",
            "transportista_domicilio": "x_transportista_domicilio",
            "transportista_calle": "x_transportista_calle",
            "transportista_num_ext": "x_transportista_num_ext",
            "transportista_num_int": "x_transportista_num_int",
            "transportista_colonia": "x_transportista_colonia",
            "transportista_municipio": "x_transportista_municipio",
            "transportista_localidad": "x_transportista_localidad",
            "transportista_estado": "x_transportista_estado_id",
            "transportista_cp": "x_transportista_cp",
        }

        source = source_field or aliases.get(field_name, field_name)
        source_model = source_model or "lead"

        # Normaliza tipo de operación a 1/2 aunque el layout use nombre "amigable"
        source_norm = _norm(source)
        if source_norm in ("tipooperacion", "xtipooperacion"):
            raw = self._record_value_for_field(lead, "x_tipo_operacion")
            raw = (str(raw or "")).strip().lower()
            if raw in ("importacion", "1", "01"):
                return "1"
            if raw in ("exportacion", "2", "02"):
                return "2"
            return ""
        if source_norm in ("tipomovimiento", "xtipomovimiento"):
            return self._get_tipo_movimiento_effective() or ""

        if source_model == "operacion":
            return self._record_value_for_field(self, source)
        if source_model == "cliente":
            return self._record_value_for_field(lead.partner_id if lead else None, source)
        if source_model == "importador":
            return self._record_value_for_field(lead.x_importador_id if lead else None, source)
        if source_model == "exportador":
            return self._record_value_for_field(lead.x_exportador_id if lead else None, source)
        if source_model == "proveedor":
            return self._record_value_for_field(lead.x_proveedor_id if lead else None, source)
        if source_model == "transportista":
            return self._record_value_for_field(lead.x_transportista_id if lead else None, source)

        return self._record_value_for_field(lead, source)

    def action_cargar_desde_lead(self):
        self.ensure_one()
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.lead_id:
            raise UserError(_("La operación no tiene Lead asociado."))

        def _allowed_codes():
            from_rule = self._get_allowed_codes_from_regla()
            from_stage = self._get_stage_allowed_codes("load_from_lead")
            if from_rule is None:
                return from_stage
            if from_stage is None:
                return from_rule
            return from_rule & from_stage

        allowed = _allowed_codes()
        registros = []
        for layout_reg in self.layout_id.registro_ids.sorted(lambda r: r.orden or 0):
            if allowed is not None and layout_reg.codigo not in allowed:
                continue
            valores = {}
            for campo in layout_reg.campo_ids.sorted(lambda c: c.pos_ini or 0):
                source_name = campo.source_field_id.name if campo.source_field_id else campo.source_field
                val = self._lead_value_for_field_name(
                    campo.nombre,
                    source_field=source_name,
                    source_model=campo.source_model,
                )
                if val is None or val == "" or val is False:
                    if campo.default:
                        val = campo.default
                if val not in (None, "", False):
                    valores[campo.nombre] = val
            registros.append((0, 0, {
                "codigo": layout_reg.codigo,
                "secuencia": 1,
                "valores": valores,
            }))

        self.registro_ids = [(5, 0, 0)] + registros
        return True
