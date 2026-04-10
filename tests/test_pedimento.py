# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestPedimento(TransactionCase):
    """Smoke tests para el modelo aduana.pedimento y exportacion TXT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env["crm.lead"]
        cls.Pedimento = cls.env["aduana.pedimento"]
        cls.Partner = cls.env["res.partner"]

        cls.partner = cls.Partner.create({
            "name": "Importador Test SA",
            "vat": "IMP010101AAA",
            "x_contact_role": "cliente",
            "is_company": True,
        })
        cls.lead = cls.Lead.create({
            "name": "Expediente Prueba 001",
            "partner_id": cls.partner.id,
            "x_tipo_operacion": "importacion",
        })

    def _make_pedimento(self):
        return self.Pedimento.create({
            "name": "PED-TEST-001",
            "lead_id": self.lead.id,
            "patente": "1234",
            "rfc_importador_exportador": "IMP010101AAA",
        })

    # ── Creacion ─────────────────────────────────────────────────────────

    def test_pedimento_created_linked_to_lead(self):
        ped = self._make_pedimento()
        self.assertEqual(ped.lead_id, self.lead)

    def test_pedimento_unique_per_lead(self):
        self._make_pedimento()
        with self.assertRaises(Exception):
            # Segundo pedimento en el mismo lead debe fallar por constraint unique
            self.Pedimento.create({
                "name": "PED-TEST-DUP",
                "lead_id": self.lead.id,
            })

    # ── Exportacion TXT ──────────────────────────────────────────────────

    def test_export_txt_raises_without_registros(self):
        ped = self._make_pedimento()
        with self.assertRaises(UserError):
            ped.action_export_txt()

    def test_prepare_txt_payload_returns_empty_without_registros(self):
        ped = self._make_pedimento()
        payload = ped.action_prepare_txt_payload()
        self.assertEqual(payload, [], "Sin registros tecnicos el payload debe ser lista vacia")

    def test_resolve_path_returns_none_for_missing_field(self):
        ped = self._make_pedimento()
        result = ped._resolve_path(ped, "campo_que_no_existe")
        self.assertIsNone(result)

    def test_resolve_path_returns_scalar(self):
        ped = self._make_pedimento()
        result = ped._resolve_path(ped, "patente")
        self.assertEqual(result, "1234")

    def test_format_txt_value_pads_char(self):
        ped = self._make_pedimento()
        campo = type("Campo", (), {"tipo_dato": "char", "longitud": 10})()
        result = ped._format_txt_value("HOLA", campo)
        self.assertEqual(len(result), 10)
        self.assertTrue(result.startswith("HOLA"))

    def test_format_txt_value_pads_number_right(self):
        ped = self._make_pedimento()
        campo = type("Campo", (), {"tipo_dato": "int", "longitud": 6})()
        result = ped._format_txt_value(42, campo)
        self.assertEqual(len(result), 6)
        self.assertEqual(result, "    42")

    def test_format_txt_value_none_returns_empty(self):
        ped = self._make_pedimento()
        campo = type("Campo", (), {"tipo_dato": "char", "longitud": 0})()
        result = ped._format_txt_value(None, campo)
        self.assertEqual(result, "")


class TestCrmLeadAduanal(TransactionCase):
    """Smoke tests para campos aduanales en crm.lead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env["crm.lead"]
        cls.Partner = cls.env["res.partner"]
        cls.partner = cls.Partner.create({
            "name": "Empresa Exportadora SA",
            "is_company": True,
        })

    def test_lead_with_tipo_operacion(self):
        lead = self.Lead.create({
            "name": "Exportacion 001",
            "partner_id": self.partner.id,
            "x_tipo_operacion": "exportacion",
            "x_regimen": "definitivo",
        })
        self.assertEqual(lead.x_tipo_operacion, "exportacion")
        self.assertEqual(lead.x_regimen, "definitivo")

    def test_lead_pedimento_status_default_draft(self):
        lead = self.Lead.create({
            "name": "Importacion 002",
            "partner_id": self.partner.id,
        })
        self.assertEqual(lead.x_pedimento_status, "draft")
