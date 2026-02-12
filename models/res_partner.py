# -*- coding: utf-8 -*-
from odoo import fields, models

class ResPartner(models.Model):
    _inherit = "res.partner"

    x_curp = fields.Char(string="CURP")
    x_identificacion_fiscal = fields.Char(string="Identificación fiscal (extranjero)")
