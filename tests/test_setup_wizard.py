# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestSetupWizard(TransactionCase):
    """Smoke tests para el wizard de configuracion inicial."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Wizard = cls.env["aduana.setup.wizard"]

    def _new_wizard(self):
        return self.Wizard.create({})

    def test_wizard_starts_at_agencia(self):
        w = self._new_wizard()
        self.assertEqual(w.step, "agencia")
        self.assertEqual(w.step_number, 1)

    def test_wizard_next_without_agent_raises(self):
        w = self._new_wizard()
        with self.assertRaises(UserError):
            w.action_next()

    def test_wizard_next_with_new_agent_data_advances(self):
        w = self._new_wizard()
        w.agente_nombre = "Agente Demo"
        w.agente_rfc = "AGDM010101AAA"
        w.patente = "1234"
        w.action_next()
        self.assertEqual(w.step, "vucem")

    def test_wizard_creates_agent_partner(self):
        w = self._new_wizard()
        w.agente_nombre = "Agente Nuevo SA"
        w.agente_rfc = "ANSA010101BBB"
        w.patente = "5678"
        w.action_next()
        partner = self.env["res.partner"].search([("vat", "=", "ANSA010101BBB")], limit=1)
        self.assertTrue(partner)
        self.assertEqual(partner.x_contact_role, "agente_aduanal")
        self.assertEqual(partner.x_patente_aduanal, "5678")

    def test_wizard_selects_existing_agent(self):
        agent = self.env["res.partner"].create({
            "name": "Agente Existente SA",
            "vat": "AESA010101CCC",
            "x_contact_role": "agente_aduanal",
            "is_company": True,
        })
        w = self._new_wizard()
        w.agente_id = agent.id
        w.patente = "9999"
        w.action_next()
        self.assertEqual(w.step, "vucem")
        agent.refresh()
        self.assertEqual(agent.x_patente_aduanal, "9999")

    def test_wizard_prev_stays_at_first_step(self):
        w = self._new_wizard()
        w.action_prev()
        self.assertEqual(w.step, "agencia")

    def test_wizard_completes_to_listo(self):
        w = self._new_wizard()
        w.agente_nombre = "Agente Final"
        w.agente_rfc = "AGFI010101DDD"
        w.patente = "1111"
        w.action_next()   # agencia -> vucem
        w.action_next()   # vucem -> catalogo
        w.action_next()   # catalogo -> listo
        self.assertEqual(w.step, "listo")
        self.assertTrue(w.is_last_step)

    def test_wizard_finish_returns_notification(self):
        w = self._new_wizard()
        w.step = "listo"
        result = w.action_finish()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
