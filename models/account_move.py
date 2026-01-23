# -*- coding: utf-8 -*-
from odoo import models

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super(AccountMove, self).action_post()
        
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            sale = move.invoice_line_ids.mapped('sale_line_ids.order_id')
            if sale and not sale.auto_generated:
                company = self.env['res.company']._find_company_from_partner(sale.partner_id.id)
                if company and company != self.env.company:
                    move._validate_intercompany_bill(company, sale)
        
        return res

    def _validate_intercompany_bill(self, company, sale):
        bill = self.sudo().search([
            ('move_type', '=', 'in_invoice'),
            ('company_id', '=', company.id),
            ('state', '=', 'draft'),
            ('ref', '=', sale.name)
        ], limit=1)
        
        if bill:
            bill.with_company(company.id).action_post()