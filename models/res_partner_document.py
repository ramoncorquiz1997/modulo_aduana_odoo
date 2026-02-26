# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartnerDocument(models.Model):
    _name = "res.partner.document"
    _description = "Documento de expediente de contacto"
    _order = "sequence, id"

    _DOC_SPECS = {
        "csf": {"label": "Constancia de Situacion Fiscal (PDF)", "applies_to": "all", "is_monthly": True},
        "programa_fomento": {"label": "Programa de fomento / certificacion", "applies_to": "all", "is_monthly": False},
        "fotos_instalaciones": {"label": "Fotografias instalaciones", "applies_to": "all", "is_monthly": False},
        "sellos_vucem": {"label": "Sellos VUCEM", "applies_to": "all", "is_monthly": False},
        "contrato_servicios": {"label": "Contrato de prestacion de servicios", "applies_to": "all", "is_monthly": False},
        "carta_69b": {"label": "Carta juramentada 69-B/49 Bis", "applies_to": "all", "is_monthly": False},
        "cuestionario_oea_ctpat": {"label": "Cuestionarios OEA / CTPAT", "applies_to": "all", "is_monthly": False},
        "autorizacion_shipper_export": {"label": "Autorizacion firmada Shipper Export", "applies_to": "all", "is_monthly": False},
        "convenio_confidencialidad": {"label": "Convenio de confidencialidad", "applies_to": "all", "is_monthly": False},
        "info_atencion_ce": {"label": "Informacion para atencion de Comercio Exterior", "applies_to": "person", "is_monthly": False},
        "opinion_cumplimiento_mensual": {"label": "Opinion de cumplimiento mensual", "applies_to": "person", "is_monthly": True},
        "pantalla_domicilio_localizado": {"label": "Pantalla de domicilio localizado", "applies_to": "person", "is_monthly": True},
        "acta_constitutiva": {"label": "Acta Constitutiva", "applies_to": "company", "is_monthly": False},
        "poder_representante": {"label": "Poder del Representante Legal", "applies_to": "company", "is_monthly": False},
        "doc_propiedad_posesion": {"label": "Documento de propiedad o posesion", "applies_to": "company", "is_monthly": False},
        "rep_identificacion": {"label": "Identificacion oficial del representante", "applies_to": "company", "is_monthly": False},
        "rep_rfc_csf": {"label": "RFC personal del representante (CSF)", "applies_to": "company", "is_monthly": False},
        "rep_opinion_cumplimiento": {"label": "Opinion cumplimiento del representante", "applies_to": "company", "is_monthly": False},
        "acta_verificacion_domicilio": {"label": "Acta de verificacion de domicilio", "applies_to": "company", "is_monthly": False},
        "comprobante_domicilio": {"label": "Comprobante de domicilio", "applies_to": "company", "is_monthly": False},
        "opinion_32d": {"label": "Opinion de cumplimiento 32-D", "applies_to": "company", "is_monthly": False},
        "carta_encomienda": {"label": "Carta encomienda", "applies_to": "company", "is_monthly": False},
        "acuse_encargo_conferido": {"label": "Acuse de encargo conferido", "applies_to": "company", "is_monthly": False},
    }

    @api.model
    def _selection_code(self):
        return [(code, spec["label"]) for code, spec in self._DOC_SPECS.items()]

    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    code = fields.Selection(selection=_selection_code, required=True, index=True)
    doc_name = fields.Char(string="Documento", compute="_compute_doc_meta", store=True)
    applies_to = fields.Selection(
        [("all", "Todos"), ("person", "Persona"), ("company", "Compania")],
        string="Aplica a",
        compute="_compute_doc_meta",
        store=True,
    )
    is_monthly = fields.Boolean(string="Mensual", compute="_compute_doc_meta", store=True)
    file_data = fields.Binary(string="Archivo")
    filename = fields.Char(string="Nombre archivo")
    status = fields.Selection(
        [("missing", "Pendiente"), ("received", "Cargado")],
        string="Estado",
        compute="_compute_status",
        store=True,
    )
    notes = fields.Char(string="Notas")

    _sql_constraints = [
        ("res_partner_document_code_unique", "unique(partner_id, code)", "Documento duplicado para el contacto."),
    ]

    @api.depends("code")
    def _compute_doc_meta(self):
        for rec in self:
            spec = self._DOC_SPECS.get(rec.code or "", {})
            rec.doc_name = spec.get("label", "")
            rec.applies_to = spec.get("applies_to", "all")
            rec.is_monthly = bool(spec.get("is_monthly"))

    @api.depends("file_data")
    def _compute_status(self):
        for rec in self:
            rec.status = "received" if rec.file_data else "missing"

