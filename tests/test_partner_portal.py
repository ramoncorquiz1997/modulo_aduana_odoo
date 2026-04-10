# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestPartnerPortal(TransactionCase):
    """Smoke tests para el flujo de registro y aprobacion de portal."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    def _make_pending_partner(self, suffix="01"):
        return self.Partner.create({
            "name": f"Cliente Test {suffix}",
            "email": f"cliente{suffix}@test.com",
            "vat": f"TEST{suffix}0101AAA",
            "x_contact_role": "cliente",
            "x_portal_status": "pending",
            "x_portal_password": "clave_temporal_123",
            "customer_rank": 1,
            "is_company": False,
        })

    # ── Creacion ─────────────────────────────────────────────────────────

    def test_pending_partner_created_with_role_cliente(self):
        partner = self._make_pending_partner("02")
        self.assertEqual(partner.x_portal_status, "pending")
        self.assertEqual(partner.x_contact_role, "cliente")

    def test_pending_partner_appears_in_solicitudes_domain(self):
        partner = self._make_pending_partner("03")
        pending = self.Partner.search([("x_portal_status", "=", "pending")])
        self.assertIn(partner, pending)

    # ── Aprobacion ───────────────────────────────────────────────────────

    def test_approve_creates_portal_user(self):
        partner = self._make_pending_partner("04")
        partner.action_approve_portal_user()
        self.assertEqual(partner.x_portal_status, "approved")
        user = self.env["res.users"].search([("partner_id", "=", partner.id)], limit=1)
        self.assertTrue(user, "Debe crearse un res.users al aprobar")

    def test_approve_clears_plain_password(self):
        partner = self._make_pending_partner("05")
        partner.action_approve_portal_user()
        self.assertFalse(
            partner.x_portal_password,
            "La contraseña en texto plano debe borrarse tras la aprobacion",
        )

    def test_approve_twice_does_not_raise(self):
        partner = self._make_pending_partner("06")
        partner.action_approve_portal_user()
        # Segunda aprobacion: ya existe usuario, debe actualizar estado sin error
        partner.x_portal_status = "pending"
        result = partner.action_approve_portal_user()
        self.assertEqual(result["params"]["type"], "warning")

    # ── Rechazo ──────────────────────────────────────────────────────────

    def test_reject_sets_rejected_status(self):
        partner = self._make_pending_partner("07")
        partner.action_reject_portal_user()
        self.assertEqual(partner.x_portal_status, "rejected")

    # ── Token de invitacion ──────────────────────────────────────────────

    def test_send_invite_generates_token(self):
        partner = self._make_pending_partner("08")
        partner.action_send_portal_invite()
        self.assertTrue(partner.x_portal_invite_token, "Debe generarse un token de invitacion")
        self.assertTrue(partner.x_portal_invite_expiry, "Debe establecerse una fecha de expiracion")

    def test_validate_token_returns_partner_data(self):
        partner = self._make_pending_partner("09")
        partner.action_send_portal_invite()
        result = self.Partner.portal_validate_token(partner.x_portal_invite_token)
        self.assertTrue(result.get("valid"))
        self.assertEqual(result["partner_id"], partner.id)

    def test_validate_invalid_token_returns_error(self):
        result = self.Partner.portal_validate_token("token_invalido_xyz")
        self.assertIn("error", result)

    # ── Freight Forwarder ────────────────────────────────────────────────

    def test_ff_client_creation(self):
        ff = self.Partner.create({
            "name": "FF Test",
            "x_contact_role": "freight_forwarder",
            "is_company": True,
        })
        result = self.Partner.portal_ff_add_client(
            ff.id, "Cliente FF", "FFCL000101AAA", "clienteff@test.com", "5512345678",
            False, False,
        )
        self.assertTrue(result.get("success"))
        client = self.Partner.browse(result["client_id"])
        self.assertEqual(client.x_freight_forwarder_id, ff)
