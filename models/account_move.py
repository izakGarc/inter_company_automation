# -*- coding: utf-8 -*-

from odoo import models

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super(AccountMove, self).action_post()
        
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            partner_company = move.partner_id.commercial_partner_id.company_id
            if partner_company and partner_company != self.env.company:
                move._create_inter_company_bill(partner_company)
        
        return res

    def _create_inter_company_bill(self, partner_company):
        pass