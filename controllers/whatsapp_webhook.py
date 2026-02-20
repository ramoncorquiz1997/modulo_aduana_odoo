# -*- coding: utf-8 -*-
import base64
import json
import logging
import re
import requests
from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppWebhookController(http.Controller):
    def _param(self, key):
        return request.env["ir.config_parameter"].sudo().get_param(key)

    def _normalize_phone(self, value):
        return re.sub(r"\D+", "", value or "")

    def _find_partner_by_wa_id(self, wa_id):
        digits = self._normalize_phone(wa_id)
        if not digits:
            return request.env["res.partner"]
        # Match by suffix to support local/international formatting differences.
        domain = ["|", ("mobile", "ilike", digits[-10:]), ("phone", "ilike", digits[-10:])]
        return request.env["res.partner"].sudo().search(domain, limit=1)

    def _session_for_sender(self, wa_id):
        session_model = request.env["mx.wa.session"].sudo()
        session = session_model.search([("wa_id", "=", wa_id)], limit=1)
        if not session:
            partner = self._find_partner_by_wa_id(wa_id)
            session = session_model.create({
                "wa_id": wa_id,
                "partner_id": partner.id or False,
            })
        elif not session.partner_id:
            partner = self._find_partner_by_wa_id(wa_id)
            if partner:
                session.partner_id = partner.id
        return session

    def _send_whatsapp_message(self, to, payload):
        token = self._param("modulo_aduana_odoo.whatsapp_token")
        phone_number_id = self._param("modulo_aduana_odoo.whatsapp_phone_number_id")
        if not token or not phone_number_id:
            _logger.warning("WhatsApp config incompleta (token/phone_number_id).")
            return
        url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {"messaging_product": "whatsapp", "to": to}
        body.update(payload)
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
            if resp.status_code >= 300:
                _logger.warning("WhatsApp send failed %s: %s", resp.status_code, resp.text)
        except Exception:
            _logger.exception("Error enviando mensaje de WhatsApp")

    def _send_doc_menu(self, wa_id):
        payload = {
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "Selecciona el documento que quieres enviar:"},
                "action": {
                    "button": "Seleccionar",
                    "sections": [
                        {
                            "title": "Documentos",
                            "rows": [
                                {"id": "send_csf", "title": "Enviar CSF"},
                                {"id": "send_ine", "title": "Enviar INE"},
                            ],
                        }
                    ],
                },
            },
        }
        self._send_whatsapp_message(wa_id, payload)

    def _download_media(self, media_id):
        token = self._param("modulo_aduana_odoo.whatsapp_token")
        if not token:
            raise ValueError("Falta token de WhatsApp.")
        headers = {"Authorization": f"Bearer {token}"}
        meta_url = f"https://graph.facebook.com/v21.0/{media_id}"
        meta_resp = requests.get(meta_url, headers=headers, timeout=20)
        meta_resp.raise_for_status()
        media_url = meta_resp.json().get("url")
        if not media_url:
            raise ValueError("No llego URL de media.")
        bin_resp = requests.get(media_url, headers=headers, timeout=20)
        bin_resp.raise_for_status()
        mime_type = (meta_resp.json().get("mime_type") or "").lower()
        return bin_resp.content, mime_type

    def _process_document_message(self, session, wa_id, msg):
        doc = msg.get("document") or {}
        media_id = doc.get("id")
        filename = doc.get("filename") or "documento"
        if not media_id:
            self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "No pude leer el archivo. Intenta de nuevo."}})
            return

        if session.expected_doc_type != "csf":
            self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "Primero selecciona el tipo de documento (ej. Enviar CSF)."}})
            return

        partner = session.partner_id or self._find_partner_by_wa_id(wa_id)
        if not partner:
            self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "No encontre tu contacto. Pide a soporte vincular tu numero."}})
            return

        try:
            content, mime_type = self._download_media(media_id)
            partner.sudo().write({
                "x_csf_file": base64.b64encode(content),
                "x_csf_filename": filename,
            })
            # Guarda adjunto también para trazabilidad.
            request.env["ir.attachment"].sudo().create({
                "name": filename,
                "datas": base64.b64encode(content),
                "mimetype": mime_type or "application/octet-stream",
                "res_model": "res.partner",
                "res_id": partner.id,
            })
            session.sudo().write({
                "expected_doc_type": False,
                "last_message_id": msg.get("id"),
                "last_event_at": fields.Datetime.now(),
                "partner_id": partner.id,
            })
            self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "CSF recibido y cargado correctamente."}})
        except Exception:
            _logger.exception("Error procesando documento WhatsApp para partner %s", partner.id)
            self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "No pude procesar el archivo. Verifica que sea PDF y vuelve a intentar."}})

    @http.route("/whatsapp/webhook", type="http", auth="public", methods=["GET"], csrf=False)
    def whatsapp_verify(self, **kwargs):
        verify_token = self._param("modulo_aduana_odoo.whatsapp_verify_token")
        mode = kwargs.get("hub.mode")
        token = kwargs.get("hub.verify_token")
        challenge = kwargs.get("hub.challenge")
        if mode == "subscribe" and token and verify_token and token == verify_token:
            return request.make_response(challenge or "", headers=[("Content-Type", "text/plain")])
        return request.make_response("forbidden", status=403)

    @http.route("/whatsapp/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def whatsapp_incoming(self):
        payload = {}
        try:
            payload = json.loads(request.httprequest.data or b"{}")
        except Exception:
            _logger.warning("Webhook WhatsApp recibio payload invalido.")
            return request.make_json_response({"status": "invalid_json"}, status=400)
        try:
            entries = payload.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    for msg in value.get("messages", []) or []:
                        wa_id = msg.get("from")
                        if not wa_id:
                            continue
                        session = self._session_for_sender(wa_id)
                        msg_type = msg.get("type")
                        if msg_type == "interactive":
                            reply = ((msg.get("interactive") or {}).get("list_reply") or {})
                            reply_id = reply.get("id")
                            if reply_id == "send_csf":
                                session.sudo().write({
                                    "expected_doc_type": "csf",
                                    "last_message_id": msg.get("id"),
                                    "last_event_at": fields.Datetime.now(),
                                })
                                self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "Perfecto. Adjunta tu archivo CSF en PDF."}})
                            elif reply_id == "send_ine":
                                self._send_whatsapp_message(wa_id, {"type": "text", "text": {"body": "INE aun no esta habilitado. Por ahora usa Enviar CSF."}})
                        elif msg_type == "text":
                            body = ((msg.get("text") or {}).get("body") or "").strip().lower()
                            if body in ("menu", "documentos", "docs", "hola"):
                                self._send_doc_menu(wa_id)
                        elif msg_type == "document":
                            self._process_document_message(session, wa_id, msg)
            return request.make_json_response({"status": "ok"})
        except Exception:
            _logger.exception("Error en webhook de WhatsApp")
            return request.make_json_response({"status": "error"}, status=500)
