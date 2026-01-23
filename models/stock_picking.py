# -*- coding: utf-8 -*-
from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.sale_id:
                sale = picking.sale_id
                if not sale.auto_generated:
                    company = self.env['res.company']._find_company_from_partner(sale.partner_id.id)
                    if company and company != self.env.company:
                        picking._validate_intercompany_receipt(company, sale)
        
        return res

    def _validate_intercompany_receipt(self, company, sale):
        pickings = self.sudo().search([
            ('purchase_id.partner_ref', '=', sale.name),
            ('company_id', '=', company.id),
            ('state', 'not in', ['done', 'cancel'])
        ])
        
        for pick in pickings:
            if pick.state == 'assigned':
                for move in pick.move_ids:
                    move.quantity_done = move.product_uom_qty
                pick.with_company(company.id).button_validate()