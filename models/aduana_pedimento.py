# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AduanaPedimento(models.Model):
    _name = "aduana.pedimento"
    _description = "Aduana - Pedimento"
    _order = "id desc"

    name = fields.Char(string="Referencia", required=True, default=lambda self: _("Nuevo"))
    lead_id = fields.Many2one("crm.lead", required=True, index=True, ondelete="cascade")

    clave_pedimento_id = fields.Many2one(
        "aduana.catalogo.clave_pedimento",
        string="Clave de pedimento",
        ondelete="set null",
    )
    tipo_operacion_id = fields.Many2one(
        "aduana.catalogo.tipo_operacion",
        string="Tipo de operacion",
        ondelete="set null",
    )
    regimen_id = fields.Many2one(
        "aduana.catalogo.regimen",
        string="Regimen",
        ondelete="set null",
    )
    aduana_despacho_id = fields.Many2one(
        "aduana.catalogo.aduana",
        string="Aduana despacho",
        ondelete="set null",
    )

    patente = fields.Char()
    agente_id = fields.Many2one("res.partner", string="Agente")
    participante_id = fields.Many2one("res.partner", string="Importador/Exportador")
    rfc_importador_exportador = fields.Char()
    fecha_pedimento = fields.Date()

    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    total_pedimento = fields.Monetary(currency_field="currency_id")

    partida_ids = fields.One2many("aduana.partida", "pedimento_id")
    factura_ids = fields.One2many("aduana.factura", "pedimento_id")
    documento_ids = fields.One2many("aduana.documento", "pedimento_id")
    contenedor_ids = fields.One2many("aduana.contenedor", "pedimento_id")
    contribucion_global_ids = fields.One2many("aduana.contribucion.global", "pedimento_id")
    registro_tecnico_ids = fields.One2many("aduana.pedimento.registro_tecnico", "pedimento_id")

    _sql_constraints = [
        ("aduana_pedimento_lead_uniq", "unique(lead_id)", "Solo puede existir un pedimento por lead."),
    ]

    def _resolve_path(self, model_record, path):
        value = model_record
        for part in (path or "").split("."):
            if not value or not hasattr(value, "_fields") or part not in value._fields:
                return None
            value = value[part]
            if hasattr(value, "__len__") and hasattr(value, "_name") and value._name != "ir.attachment":
                value = value[:1]
        if hasattr(value, "id"):
            if hasattr(value, "code") and value.code:
                return value.code
            if hasattr(value, "name") and value.name:
                return value.name
            return value.id
        return value

    def action_prepare_txt_payload(self):
        """Esqueleto para futura exportacion TXT segun layout tecnico."""
        self.ensure_one()
        lines = []
        for reg in self.registro_tecnico_ids.sorted(lambda r: (r.registro_tipo_id.orden, r.id)):
            line_values = {}
            for field_def in reg.registro_tipo_id.campo_ids.sorted("secuencia"):
                if field_def.origen_modelo == "aduana.pedimento":
                    value = self._resolve_path(self, field_def.origen_campo)
                else:
                    value = reg.payload.get(field_def.nombre_tecnico) if reg.payload else None
                if value in (None, "") and field_def.default:
                    value = field_def.default
                line_values[field_def.nombre_tecnico] = value
            lines.append({"registro": reg.registro_tipo_id.codigo, "values": line_values})
        return lines


class AduanaPartida(models.Model):
    _name = "aduana.partida"
    _description = "Aduana - Partida"
    _order = "sequence, id"

    pedimento_id = fields.Many2one("aduana.pedimento", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    fraccion_arancelaria = fields.Char(required=True)
    descripcion = fields.Char(required=True)
    cantidad = fields.Float(default=1.0)
    umc = fields.Char(string="UMC")
    valor_unitario = fields.Monetary(currency_field="currency_id")
    valor_aduana = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="pedimento_id.currency_id", store=True, readonly=True)

    identificador_ids = fields.One2many("aduana.partida.identificador", "partida_id")
    contribucion_ids = fields.One2many("aduana.partida.contribucion", "partida_id")


class AduanaPartidaIdentificador(models.Model):
    _name = "aduana.partida.identificador"
    _description = "Aduana - Partida Identificador"
    _order = "id"

    partida_id = fields.Many2one("aduana.partida", required=True, ondelete="cascade", index=True)
    clave = fields.Char(required=True)
    complemento1 = fields.Char()
    complemento2 = fields.Char()
    complemento3 = fields.Char()


class AduanaPartidaContribucion(models.Model):
    _name = "aduana.partida.contribucion"
    _description = "Aduana - Partida Contribucion"
    _order = "id"

    partida_id = fields.Many2one("aduana.partida", required=True, ondelete="cascade", index=True)
    tipo_contribucion = fields.Char(required=True)
    tasa = fields.Float()
    base = fields.Monetary(currency_field="currency_id")
    importe = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="partida_id.currency_id", store=True, readonly=True)


class AduanaFactura(models.Model):
    _name = "aduana.factura"
    _description = "Aduana - Factura"
    _order = "fecha desc, id desc"

    pedimento_id = fields.Many2one("aduana.pedimento", required=True, ondelete="cascade", index=True)
    numero = fields.Char(required=True)
    fecha = fields.Date()
    moneda_id = fields.Many2one("res.currency", required=True, default=lambda self: self.env.company.currency_id)
    proveedor_id = fields.Many2one("res.partner")
    valor = fields.Monetary(currency_field="moneda_id")


class AduanaDocumento(models.Model):
    _name = "aduana.documento"
    _description = "Aduana - Documento"
    _order = "fecha desc, id desc"

    pedimento_id = fields.Many2one("aduana.pedimento", ondelete="cascade", index=True)
    partida_id = fields.Many2one("aduana.partida", ondelete="cascade", index=True)
    tipo_doc = fields.Char(required=True)
    folio = fields.Char()
    fecha = fields.Date()

    @api.constrains("pedimento_id", "partida_id")
    def _check_scope(self):
        for rec in self:
            if not rec.pedimento_id and not rec.partida_id:
                raise ValidationError(_("El documento debe estar ligado a pedimento o partida."))


class AduanaContenedor(models.Model):
    _name = "aduana.contenedor"
    _description = "Aduana - Contenedor"

    pedimento_id = fields.Many2one("aduana.pedimento", required=True, ondelete="cascade", index=True)
    numero = fields.Char(required=True)
    tipo = fields.Char()


class AduanaContribucionGlobal(models.Model):
    _name = "aduana.contribucion.global"
    _description = "Aduana - Contribucion Global"

    pedimento_id = fields.Many2one("aduana.pedimento", required=True, ondelete="cascade", index=True)
    tipo_contribucion = fields.Char(required=True)
    base = fields.Monetary(currency_field="currency_id")
    importe = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(related="pedimento_id.currency_id", store=True, readonly=True)


class AduanaPedimentoRegistroTecnico(models.Model):
    _name = "aduana.pedimento.registro_tecnico"
    _description = "Aduana - Registro Tecnico Capturado"
    _order = "registro_tipo_id, id"

    pedimento_id = fields.Many2one("aduana.pedimento", required=True, ondelete="cascade", index=True)
    registro_tipo_id = fields.Many2one("aduana.layout_registro_tipo", required=True, ondelete="restrict")
    payload = fields.Json(default=dict)
