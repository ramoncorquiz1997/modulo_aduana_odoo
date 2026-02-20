# -*- coding: utf-8 -*-
from odoo import fields, models


class MxWaSession(models.Model):
    _name = "mx.wa.session"
    _description = "Sesion de WhatsApp por remitente"

    wa_id = fields.Char(string="WhatsApp ID", required=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Contacto")
    expected_doc_type = fields.Selection(
        [
            ("csf", "CSF"),
            ("ine", "INE"),
        ],
        string="Documento esperado",
    )
    last_message_id = fields.Char(string="Ultimo mensaje")
    last_event_at = fields.Datetime(string="Ultimo evento")

    _sql_constraints = [
        ("mx_wa_session_wa_id_uniq", "unique(wa_id)", "Ya existe una sesion para este remitente."),
    ]
