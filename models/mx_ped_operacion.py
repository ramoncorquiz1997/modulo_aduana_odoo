# -*- coding: utf-8 -*-
import base64
import io
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
        string="Aduana-seccion entrada/salida",
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
        string="Facturas",
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
        help="Define qué registros debe contener la operación según tipo de movimiento.",
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
            if rec.tipo_movimiento not in ("2", "3", "8"):
                rec.acuse_validacion = False
            if rec.tipo_movimiento != "1":
                rec.es_rectificacion = False
            if rec.tipo_movimiento != "8":
                rec.formas_pago_claves = False
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.onchange("clave_pedimento_id", "tipo_operacion", "regimen")
    def _onchange_estructura_regla_context(self):
        for rec in self:
            if rec.clave_pedimento_id and rec.clave_pedimento_id.tipo_movimiento_id:
                rec.tipo_movimiento = rec.clave_pedimento_id.tipo_movimiento_id.code
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.onchange("es_rectificacion", "formas_pago_claves")
    def _onchange_estructura_regla_flags(self):
        for rec in self:
            rec.estructura_regla_id = rec._resolve_estructura_regla()

    @api.depends("tipo_movimiento", "clave_pedimento_id", "es_rectificacion")
    def _compute_estructura_escenario(self):
        for rec in self:
            rec.estructura_escenario = rec._detect_escenario_estructura()

    @api.constrains("tipo_movimiento", "acuse_validacion", "clave_pedimento_id")
    def _check_acuse_validacion(self):
        for rec in self:
            mov = rec._get_tipo_movimiento_effective()
            if mov in ("2", "3", "8"):
                acuse = (rec.acuse_validacion or "").strip()
                if not acuse:
                    raise ValidationError(
                        _("El acuse de validacion es obligatorio para eliminacion, desistimiento y confirmacion de pago.")
                    )
                if len(acuse) != 8:
                    raise ValidationError(_("El acuse de validacion debe tener exactamente 8 caracteres."))
                if acuse == "0" * 8:
                    raise ValidationError(_("El acuse de validacion no puede ser 00000000."))

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
        policy_map = {}
        clave = self.clave_pedimento_id
        if not clave:
            return policy_map

        for line in clave.registro_policy_ids:
            code = (line.registro_codigo or "").strip()
            if not code:
                continue
            policy_map[code] = {
                "policy": line.policy,
                "min": max(line.min_occurs or 0, 0),
                "max": max(line.max_occurs or 0, 0),
                "identifier": (line.required_identifier_code or "").strip().upper(),
            }

        # Compatibilidad con banderas antiguas para transicion.
        if clave.requires_reg_552:
            rule = policy_map.get("552", {"policy": "required", "min": 1, "max": 0, "identifier": ""})
            rule["policy"] = "required"
            rule["min"] = max(rule.get("min", 0), 1)
            policy_map["552"] = rule
        if clave.omits_reg_502:
            policy_map["502"] = {"policy": "forbidden", "min": 0, "max": 0, "identifier": ""}
        if clave.requires_identificador_re:
            rule = policy_map.get("507", {"policy": "required", "min": 1, "max": 0, "identifier": ""})
            if not rule.get("identifier"):
                rule["identifier"] = "RE"
            policy_map["507"] = rule

        return policy_map

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

    def _resolve_estructura_regla(self):
        self.ensure_one()
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
        clave_structure = (self.clave_pedimento_id.saai_structure_type or "auto") if self.clave_pedimento_id else "auto"
        if clave_structure and clave_structure != "auto":
            return clave_structure

        mov = self._get_tipo_movimiento_effective()
        if mov == "1":
            if self._is_rectificacion():
                return "rectificacion"
            if self._is_transito():
                return "transito"
            return "normal"
        if mov in ("2", "3"):
            return "eliminacion_desistimiento"
        if mov == "5":
            return "industria_automotriz"
        if mov == "6":
            return "complementario"
        if mov == "7":
            return "despacho_anticipado"
        if mov == "8":
            return "confirmacion_pago"
        if mov == "9":
            return "global_complementario"
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

    def _validate_confirmacion_pago_formas(self):
        self.ensure_one()
        if self._get_tipo_movimiento_effective() != "8":
            return
        allowed = {"5", "6", "8", "9", "13", "14", "16", "18", "21"}
        current = self._parse_formas_pago_claves()
        if not current:
            raise ValidationError(
                _("Para tipo de movimiento 8, captura las formas de pago (claves).")
            )
        invalid = sorted(current - allowed, key=lambda x: int(x))
        if invalid:
            raise ValidationError(
                _("Tipo de movimiento 8 solo permite formas de pago %s. No permitidas: %s")
                % (", ".join(sorted(allowed, key=lambda x: int(x))), ", ".join(invalid))
            )

    def _build_record_plan(self):
        """Construye el plan de registros aplicable y una traza de decisiones."""
        self.ensure_one()
        rule = self.estructura_regla_id or self._resolve_estructura_regla()
        clave_policy = self._get_clave_policy_map()

        states = {}
        trace = []

        if rule:
            for line in rule.line_ids:
                code = (line.registro_codigo or "").strip()
                if not code:
                    continue
                min_occ = max(line.min_occurs or 0, 0)
                max_occ = max(line.max_occurs or 0, 0)
                req_min = max(min_occ, 1) if line.required else min_occ
                state = states.setdefault(code, {
                    "min": 0,
                    "max": 0,
                    "required": False,
                    "forbidden": False,
                    "identifier": "",
                    "contributors": [],
                })
                state["required"] = state["required"] or bool(req_min)
                state["min"] = max(state["min"], req_min)
                if max_occ:
                    state["max"] = max_occ if not state["max"] else min(state["max"], max_occ)
                state["contributors"].append(f"estructura:{rule.id}")
                trace.append({
                    "source": "estructura",
                    "rule_id": rule.id,
                    "record_code": code,
                    "required": line.required,
                    "min": req_min,
                    "max": max_occ,
                })

        for code, policy in clave_policy.items():
            state = states.setdefault(code, {
                "min": 0,
                "max": 0,
                "required": False,
                "forbidden": False,
                "identifier": "",
                "contributors": [],
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
                req_min = max(min_occ, 1)
                state["required"] = True
                state["min"] = max(state["min"], req_min)
            elif policy_type == "optional" and not state["forbidden"]:
                state["min"] = max(state["min"], min_occ)

            if max_occ and not state["forbidden"]:
                state["max"] = max_occ if not state["max"] else min(state["max"], max_occ)
            if identifier:
                state["identifier"] = identifier

            state["contributors"].append(f"clave:{self.clave_pedimento_id.id}")
            trace.append({
                "source": "clave",
                "clave_id": self.clave_pedimento_id.id,
                "record_code": code,
                "policy": policy_type,
                "min": min_occ,
                "max": max_occ,
                "identifier": identifier,
            })

        # Precedencia explicita: forbidden siempre gana sobre required.
        for state in states.values():
            if state["forbidden"]:
                state["required"] = False
                state["min"] = 0
                state["max"] = 0

        return {
            "rule": rule,
            "states": states,
            "trace": trace,
        }

    def _get_allowed_codes_from_regla(self):
        self.ensure_one()
        plan = self._build_record_plan()
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

        if errors:
            raise UserError("\n".join(errors))

    def action_preparar_estructura(self):
        for rec in self:
            rule = rec.estructura_regla_id or rec._resolve_estructura_regla()
            if not rule:
                raise UserError(_("No existe una regla de estructura para este contexto."))
            rec.estructura_regla_id = rule
            counts = Counter((r.codigo or "") for r in rec.registro_ids)
            new_lines = []
            for line in rule.line_ids.sorted(lambda l: (l.sequence, l.id)):
                needed = max(line.min_occurs or 0, 0) - counts.get(line.registro_codigo, 0)
                seq_base = counts.get(line.registro_codigo, 0)
                for i in range(max(needed, 0)):
                    new_lines.append((0, 0, {
                        "codigo": line.registro_codigo,
                        "secuencia": seq_base + i + 1,
                        "valores": {},
                    }))
                counts[line.registro_codigo] = counts.get(line.registro_codigo, 0) + max(needed, 0)
            if new_lines:
                rec.write({"registro_ids": new_lines})
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

        # Normaliza tipo de operación (1/2). Si el layout pide 2 dígitos, se rellena.
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
        return txt

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
            rec.pedimento_numero = f"{yy}{aa}{pppp}{d}{nnnnnn}"
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
            "fraccion_arancelaria": "x_fraccion_arancelaria_principal",
            "descripcion_mercancia": "x_descripcion_mercancia",
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
        if source_norm in ("acusevalidacion", "xacusevalidacion"):
            if self._get_tipo_movimiento_effective() not in ("2", "3", "8"):
                return "NULO"

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

        return self._record_value_for_field(lead, source)

    def action_cargar_desde_lead(self):
        self.ensure_one()
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.lead_id:
            raise UserError(_("La operación no tiene Lead asociado."))

        def _allowed_codes():
            from_rule = self._get_allowed_codes_from_regla()
            if from_rule is not None:
                return from_rule
            mov = self._get_tipo_movimiento_effective()
            if mov in ("2", "3"):
                return {"500", "800", "801"}
            if mov == "8":
                return {"500", "801"}
            return None

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
