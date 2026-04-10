# -*- coding: utf-8 -*-
import base64
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PortalRegistrationController(http.Controller):

    @http.route(
        "/portal/extract-csf",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def extract_csf(self, file_b64, **kwargs):
        """
        Recibe un PDF de CSF codificado en base64 y retorna los valores extraídos
        (RFC, CURP, domicilio, etc.) usando la lógica existente de _extract_csf_values.
        """
        if not file_b64:
            return {"error": "No se recibió archivo"}

        try:
            partner_model = request.env["res.partner"].sudo()
            extracted = partner_model._extract_csf_values(file_b64)
            if not extracted:
                return {"error": "No se pudo extraer información del CSF. Verifica que el PDF tenga código QR válido."}
            return {"success": True, "data": extracted}
        except Exception:
            _logger.exception("Error en extract_csf endpoint")
            return {"error": "Error procesando el CSF en el servidor"}

    @http.route(
        "/portal/register",
        type="json",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def register_client(self, name, email, phone, password, rfc, csf_b64, csf_filename, **kwargs):
        """
        Crea un nuevo res.partner con estado portal 'pending'.
        El RFC viene extraído del CSF.
        La agencia debe aprobar antes de que el cliente pueda iniciar sesión.
        """
        if not all([name, email, phone, password, rfc, csf_b64]):
            return {"error": "Todos los campos son requeridos"}

        try:
            Partner = request.env["res.partner"].sudo()

            # Verificar que el RFC no esté ya registrado
            existing = Partner.search([("vat", "=", rfc.strip().upper())], limit=1)
            if existing:
                return {"error": "Este RFC ya está registrado. Si ya tienes cuenta, inicia sesión."}

            # Verificar que el email no esté ya en uso como login
            existing_email = Partner.search([("email", "=ilike", email.strip())], limit=1)
            if existing_email:
                return {"error": "Este correo electrónico ya está registrado."}

            vals = {
                "name": name.strip(),
                "email": email.strip().lower(),
                "phone": phone.strip(),
                "vat": rfc.strip().upper(),
                "x_contact_role": "cliente",
                "x_portal_status": "pending",
                "x_portal_registration_date": fields.Datetime.now(),
                "x_portal_password": password,
                "x_csf_file": csf_b64,
                "x_csf_filename": (csf_filename or "csf.pdf"),
                "is_company": False,
                "customer_rank": 1,
            }

            partner = Partner.create(vals)
            _logger.info("Portal: nuevo registro pendiente partner_id=%s rfc=%s email=%s", partner.id, rfc, email)

            return {
                "success": True,
                "message": "Solicitud enviada. La agencia revisará tu información y recibirás confirmación por correo.",
            }

        except Exception:
            _logger.exception("Error en register_client endpoint")
            return {"error": "Error interno al procesar el registro. Inténtalo de nuevo."}


class PortalClienteController(http.Controller):
    """Vistas de portal para clientes aprobados."""

    _STATUS_LABELS = {
        "draft": ("Borrador", "bg-secondary"),
        "ready": ("Listo", "bg-info"),
        "generated": ("Generado", "bg-success"),
        "error": ("Error", "bg-danger"),
    }
    _TIPO_LABELS = {
        "importacion": "Importación",
        "exportacion": "Exportación",
    }
    _REGIMEN_LABELS = {
        "definitivo": "Definitivo",
        "temporal": "Temporal",
        "deposito_fiscal": "Depósito fiscal",
        "transito": "Tránsito",
    }

    @http.route(
        "/mis-pedimentos",
        type="http",
        auth="user",
        methods=["GET"],
        website=False,
    )
    def mis_pedimentos(self, **kwargs):
        partner = request.env.user.partner_id
        # Solo clientes aprobados
        if partner.x_portal_status != "approved":
            return request.render(
                "modulo_aduana_odoo.portal_mis_pedimentos_error",
                {"partner": partner},
            )

        leads = request.env["crm.lead"].sudo().search([
            ("partner_id", "=", partner.id),
        ], order="create_date desc", limit=100)

        rows = []
        for lead in leads:
            status = lead.x_pedimento_status or "draft"
            label, badge = self._STATUS_LABELS.get(status, (status, "bg-secondary"))
            rows.append({
                "name": lead.name or f"#{lead.id}",
                "tipo_operacion": self._TIPO_LABELS.get(lead.x_tipo_operacion or "", lead.x_tipo_operacion or "-"),
                "regimen": self._REGIMEN_LABELS.get(lead.x_regimen or "", lead.x_regimen or "-"),
                "aduana": lead.x_aduana or "-",
                "status_label": label,
                "status_badge": badge,
                "docs_completos": bool(lead.x_docs_completos) if hasattr(lead, "x_docs_completos") else False,
                "fecha": str(lead.create_date.date()) if lead.create_date else "-",
            })

        return request.render(
            "modulo_aduana_odoo.portal_mis_pedimentos",
            {"partner": partner, "leads": rows},
        )
