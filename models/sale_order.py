# -*- coding: utf-8 -*-
from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super(SaleOrder, self)._create_invoices(grouped=grouped, final=final, date=date)
        
        for invoice in invoices:
            sale = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
            if sale and not sale.auto_generated:
                company = self.env['res.company']._find_company_from_partner(sale.partner_id.id)
                if company and company != self.env.company:
                    sale._create_intercompany_bill(company)
        
        return invoices

    def _create_intercompany_bill(self, company):
        PurchaseOrder = self.env['purchase.order'].sudo()
        
        po = PurchaseOrder.search([
            ('partner_ref', '=', self.name),
            ('company_id', '=', company.id),
            ('state', 'in', ['purchase', 'done'])
        ], limit=1)
        
        if po:
            bill_vals = {
                'move_type': 'in_invoice',
                'partner_id': po.partner_id.id,
                'invoice_date': fields.Date.today(),
                'currency_id': po.currency_id.id,
                'company_id': company.id,
                'ref': self.name,
                'invoice_line_ids': [],
            }
            
            for line in po.order_line:
                bill_vals['invoice_line_ids'].append((0, 0, {
                    'name': line.name,
                    'product_id': line.product_id.id,
                    'quantity': line.product_qty,
                    'product_uom_id': line.product_uom.id,
                    'price_unit': line.price_unit,
                    'tax_ids': [(6, 0, line.taxes_id.ids)],
                    'purchase_line_id': line.id,
                }))
            
            self.env['account.move'].sudo().with_company(company.id).create(bill_vals)

    def action_cancel(self):
        res = super(SaleOrder, self).action_cancel()
        
        for order in self:
            if not order.auto_generated:
                company = self.env['res.company']._find_company_from_partner(order.partner_id.id)
                if company and company != self.env.company:
                    order._cancel_intercompany_po(company)
        
        return res

    def _cancel_intercompany_po(self, company):
        po = self.env['purchase.order'].sudo().search([
            ('partner_ref', '=', self.name),
            ('company_id', '=', company.id),
            ('state', '!=', 'cancel')
        ], limit=1)
        
        if po:
            po.with_company(company.id).button_cancel()