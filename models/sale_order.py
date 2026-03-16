# -*- coding: utf-8 -*-
from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_confirm(self):
        res = super(SaleOrder, self)._action_confirm()
        
        for order in self:
            if order.company_id.id != 1 and not order.auto_generated:
                base_company = self.env['res.company'].sudo().browse(1)
                if base_company:
                    order._create_supply_sale_order(base_company)
                    order._validate_supply_chain()
        
        return res

    def _create_supply_sale_order(self, base_company):
        # Buscar el contacto que representa a Empresa B dentro de Empresa A
        outlet_partner = self.env['res.partner'].sudo().search([
            ('name', '=', self.company_id.name),
            ('company_id', 'in', [False, base_company.id])
        ], limit=1)

        if not outlet_partner:
            outlet_partner = self.company_id.partner_id

        # Buscar la lista de precios asignada al partner en Empresa A
        pricelist = outlet_partner.with_company(base_company.id).property_product_pricelist

        so_vals = {
            'partner_id': outlet_partner.id,
            'company_id': base_company.id,
            'client_order_ref': self.name,
            'date_order': self.date_order,
            'pricelist_id': pricelist.id if pricelist else False,
            'order_line': [],
        }

        for line in self.order_line:
            if not line.display_type:
                price_unit = line.price_unit  # fallback
                if pricelist:
                    price_unit = pricelist.with_company(base_company.id)._get_product_price(
                        line.product_id,
                        line.product_uom_qty,
                        uom=line.product_uom,
                    )

                so_vals['order_line'].append((0, 0, {
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom': line.product_uom.id,
                    'price_unit': price_unit,
                }))

        supply_so = self.env['sale.order'].sudo().with_company(base_company.id).create(so_vals)
        supply_so.action_confirm()

    def _validate_supply_chain(self):
        supply_so = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', self.name),
            ('company_id', '=', 1)
        ], limit=1)
        
        if supply_so:
            supply_pickings = self.env['stock.picking'].sudo().search([
                ('sale_id', '=', supply_so.id),
                ('picking_type_code', '=', 'outgoing'),
                ('state', 'not in', ['done', 'cancel'])
            ])
            
            for pick in supply_pickings:
                # Asignar disponibilidad antes de intentar setear quantity_done
                if pick.state not in ('assigned',):
                    pick.with_company(1).action_assign()
                for move in pick.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    # Setear qty_done en move_line_ids (forma correcta en Odoo 16)
                    for ml in move.move_line_ids:
                        ml.qty_done = ml.reserved_uom_qty
                    # Si no hay move_lines (sin stock), crearlas manualmente
                    if not move.move_line_ids:
                        move._set_quantity_done(move.product_uom_qty)
                pick.with_company(1).with_context(skip_backorder=True)._action_done()
            
            purchase_pickings = self.env['stock.picking'].sudo().search([
                ('purchase_id.partner_ref', '=', supply_so.name),
                ('company_id', '=', self.company_id.id),
                ('state', 'not in', ['done', 'cancel'])
            ])
            
            for pick in purchase_pickings:
                if pick.state not in ('assigned',):
                    pick.with_company(self.company_id.id).action_assign()
                for move in pick.move_ids.filtered(lambda m: m.state not in ['done', 'cancel']):
                    for ml in move.move_line_ids:
                        ml.qty_done = ml.reserved_uom_qty
                    if not move.move_line_ids:
                        move._set_quantity_done(move.product_uom_qty)
                pick.with_company(self.company_id.id).with_context(skip_backorder=True)._action_done()

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super(SaleOrder, self)._create_invoices(grouped=grouped, final=final, date=date)
        
        for invoice in invoices:
            sale = invoice.invoice_line_ids.mapped('sale_line_ids.order_id')
            if sale and not sale.auto_generated:
                company = self.env['res.company']._find_company_from_partner(sale.partner_id.id)
                if company and company != self.env.company:
                    sale._create_intercompany_bill(company)
                
                if sale.company_id.id != 1:
                    sale._create_supply_invoices()
        
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

    def _create_supply_invoices(self):
        supply_so = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', self.name),
            ('company_id', '=', 1)
        ], limit=1)
        
        if supply_so and supply_so.invoice_status == 'to invoice':
            supply_invoice = supply_so.with_context(
                check_move_validity=False
            )._create_invoices()
            
            po = self.env['purchase.order'].sudo().search([
                ('partner_ref', '=', supply_so.name),
                ('company_id', '=', self.company_id.id),
                ('state', 'in', ['purchase', 'done'])
            ], limit=1)
            
            if po:
                partner = po.partner_id.sudo()
                partner_id = partner.id
                
                if partner.company_id and partner.company_id.id != self.company_id.id:
                    shared_partner = self.env['res.partner'].sudo().search([
                        ('name', '=', partner.name),
                        '|',
                        ('company_id', '=', False),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                    
                    if shared_partner:
                        partner_id = shared_partner.id
                
                bill_vals = {
                    'move_type': 'in_invoice',
                    'partner_id': partner_id,
                    'invoice_date': fields.Date.today(),
                    'currency_id': po.currency_id.id,
                    'company_id': self.company_id.id,
                    'ref': supply_so.name,
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
                
                self.env['account.move'].sudo().with_company(self.company_id.id).with_context(
                    check_move_validity=False
                ).create(bill_vals)

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
            
    def action_cancel(self):
        """Override para mostrar wizard si es orden inter-empresa"""
        
        # Si viene del wizard, cancelar directo sin mostrar wizard de nuevo
        if self.env.context.get('skip_intercompany_cancel'):
            return super(SaleOrder, self).action_cancel()
        
        # Si es una sola orden de Empresa B (no Global), verificar inter-empresa
        if len(self) == 1 and self.company_id.id != 1:
            # Buscar si tiene orden supply
            supply = self.env['sale.order'].sudo().search([
                ('client_order_ref', '=', self.name),
                ('company_id', '=', 1)
            ], limit=1)
            
            if supply:
                # Mostrar wizard
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Cancelar Orden Inter-empresa',
                    'res_model': 'sale.order.cancel.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_sale_order_id': self.id,
                    }
                }
        
        # Si no es inter-empresa o son múltiples, cancelar normal
        return super(SaleOrder, self).action_cancel()