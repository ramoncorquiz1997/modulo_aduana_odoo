# -*- coding: utf-8 -*-
import base64
import xml.etree.ElementTree as ET

from odoo import api, fields, models, _
from odoo.exceptions import UserError


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

    aduana_clave = fields.Char(string="Aduana (clave)")  # ej 070
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

    # ==========================
    # Layout y registros (VOCE/SAAI)
    # ==========================
    layout_id = fields.Many2one(
        "mx.ped.layout",
        string="Layout",
        help="Define los registros y campos del archivo de validación.",
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
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))

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
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

    def action_export_xml(self):
        self.ensure_one()
        if not self.layout_id:
            raise UserError(_("Falta seleccionar un layout en la operación."))
        if not self.registro_ids:
            raise UserError(_("No hay registros capturados para exportar."))

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

    def _build_txt_filename(self):
        self.ensure_one()
        layout = self.layout_id
        if not layout or not layout.file_name_pattern:
            return f"PEDIMENTO_{self.name}.txt"

        from datetime import datetime

        patente = self.patente or (self.lead_id.x_patente_agente if self.lead_id else "")
        today = datetime.now()
        julian_day = int(today.strftime("%j"))
        seq = 1
        try:
            name = layout.file_name_pattern.format(
                patente=patente,
                julian_day=julian_day,
                seq=seq,
            )
        except Exception:
            name = f"PEDIMENTO_{self.name}.txt"
        if not name.lower().endswith(".txt"):
            name = f"{name}.txt"
        return name

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
        }

        source = source_field or aliases.get(field_name, field_name)
        source_model = source_model or "lead"

        # Normaliza tipo de operación a 1/2 aunque el layout use nombre "amigable"
        if _norm(source) in ("tipooperacion", "xtipooperacion"):
            raw = self._record_value_for_field(lead, "x_tipo_operacion")
            raw = (str(raw or "")).strip().lower()
            if raw in ("importacion", "1", "01"):
                return "1"
            if raw in ("exportacion", "2", "02"):
                return "2"
            return ""

        if source_model == "operacion":
            return self._record_value_for_field(self, source)
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
            if self.tipo_movimiento in ("2", "3"):
                return {"500", "800", "801"}
            if self.tipo_movimiento == "8":
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
