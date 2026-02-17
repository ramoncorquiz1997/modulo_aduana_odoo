# custom-addons/mi_modulo/models/account_move.py

from odoo import models, fields

class AccountMove(models.Model):
    _inherit = "account.move"

    x_ped_operacion_id = fields.Many2one(
        "mx.ped.operacion",
        string="Pedimento"
    )
