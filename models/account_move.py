# -*- coding: utf-8 -*-
from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        res = super(AccountMove, self).action_post()
        
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            _logger.info(f'=== FACTURA VALIDADA: {move.name} ===')
            sale = move.invoice_line_ids.mapped('sale_line_ids.order_id')
            _logger.info(f'Sale: {sale.mapped("name")}')
            
            if sale:
                _logger.info(f'Auto-generated: {sale.auto_generated}')
                _logger.info(f'Company: {sale.company_id.name} (ID: {sale.company_id.id})')
                
                if not sale.auto_generated:
                    company = self.env['res.company']._find_company_from_partner(sale.partner_id.id)
                    if company and company != self.env.company:
                        _logger.info('Validando bill inter-company')
                        move._validate_intercompany_bill(company, sale)
                    
                    if sale.company_id.id != 1:
                        _logger.info('Creando cadena de facturas supply')
                        move._create_and_validate_supply_invoices(sale)
        
        return res

    def _validate_intercompany_bill(self, company, sale):
        bill = self.sudo().search([
            ('move_type', '=', 'in_invoice'),
            ('company_id', '=', company.id),
            ('state', '=', 'draft'),
            ('ref', '=', sale.name)
        ], limit=1)
        
        _logger.info(f'Bill encontrada: {bill.name if bill else "NO"}')
        
        if bill:
            bill.with_company(company.id).action_post()

    def _create_and_validate_supply_invoices(self, sale):
        supply_so = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', sale.name),
            ('company_id', '=', 1)
        ], limit=1)
        
        _logger.info(f'Supply SO: {supply_so.name if supply_so else "NO ENCONTRADA"}')
        
        if supply_so:
            supply_invoice = self.sudo().search([
                ('move_type', '=', 'out_invoice'),
                ('company_id', '=', 1),
                ('state', '=', 'draft'),
                ('invoice_line_ids.sale_line_ids.order_id', '=', supply_so.id)
            ], limit=1)
            
            if supply_invoice:
                _logger.info(f'Validando factura A: {supply_invoice.name}')
                supply_invoice.with_company(1).action_post()
                _logger.info('✓ Factura A validada')
            
            supply_bill = self.sudo().search([
                ('move_type', '=', 'in_invoice'),
                ('company_id', '=', sale.company_id.id),
                ('state', '=', 'draft'),
                ('ref', '=', supply_so.name)
            ], limit=1)
            
            if supply_bill:
                _logger.info(f'Validando bill B: {supply_bill.name}')
                supply_bill.with_company(sale.company_id.id).action_post()
                _logger.info('✓ Bill B validada')
                

    def button_cancel(self):
        """Override para interceptar cancelación y mostrar wizard si hay facturas relacionadas"""
        
        # Si es una sola factura, verificar si tiene relaciones inter-empresa
        if len(self) == 1:
            related = self._get_intercompany_related_invoices()
            
            if related:
                # Mostrar wizard
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Cancelar Facturas Inter-empresa',
                    'res_model': 'account.move.cancel.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {
                        'default_invoice_id': self.id,
                    }
                }
        
        # Si no tiene relaciones o son múltiples, cancelar normal
        return super(AccountMove, self).button_cancel()

    def _get_intercompany_related_invoices(self):
        """Buscar facturas relacionadas por inter-empresa"""
        self.ensure_one()
        
        related = self.env['account.move']
        
        # Caso 1: Esta es una factura de venta de Empresa B
        if self.move_type == 'out_invoice' and self.company_id.id == 2 and self.invoice_origin:
            so_b = self.env['sale.order'].sudo().search([('name', '=', self.invoice_origin)], limit=1)
            
            if so_b:
                # Buscar SO de Empresa A
                so_a = self.env['sale.order'].sudo().search([
                    ('client_order_ref', '=', so_b.name),
                    ('company_id', '=', 1)
                ], limit=1)
                
                if so_a:
                    # Factura de venta A
                    inv_a = self.env['account.move'].sudo().search([
                        ('invoice_origin', '=', so_a.name),
                        ('company_id', '=', 1),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    
                    if inv_a:
                        related |= inv_a
                    
                    # Factura de compra B
                    bill = self.env['account.move'].sudo().search([
                        ('ref', '=', so_a.name),
                        ('company_id', '=', 2),
                        ('move_type', '=', 'in_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    
                    if bill:
                        related |= bill
        
        # Caso 2: Esta es una factura de venta de Empresa A (supply)
        elif self.move_type == 'out_invoice' and self.company_id.id == 1 and self.invoice_origin:
            so_a = self.env['sale.order'].sudo().search([('name', '=', self.invoice_origin)], limit=1)
            
            if so_a and so_a.client_order_ref:
                # Factura de venta B
                inv_b = self.env['account.move'].sudo().search([
                    ('invoice_origin', '=', so_a.client_order_ref),
                    ('company_id', '=', 2),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '!=', 'cancel')
                ], limit=1)
                
                if inv_b:
                    related |= inv_b
                
                # Factura de compra B
                bill = self.env['account.move'].sudo().search([
                    ('ref', '=', so_a.name),
                    ('company_id', '=', 2),
                    ('move_type', '=', 'in_invoice'),
                    ('state', '!=', 'cancel')
                ], limit=1)
                
                if bill:
                    related |= bill
        
        # Caso 3: Esta es una factura de compra de Empresa B (bill)
        elif self.move_type == 'in_invoice' and self.company_id.id == 2 and self.ref:
            # El ref contiene el nombre de SO A
            so_a = self.env['sale.order'].sudo().search([('name', '=', self.ref)], limit=1)
            
            if so_a:
                # Factura de venta A
                inv_a = self.env['account.move'].sudo().search([
                    ('invoice_origin', '=', so_a.name),
                    ('company_id', '=', 1),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '!=', 'cancel')
                ], limit=1)
                
                if inv_a:
                    related |= inv_a
                
                # Factura de venta B
                if so_a.client_order_ref:
                    inv_b = self.env['account.move'].sudo().search([
                        ('invoice_origin', '=', so_a.client_order_ref),
                        ('company_id', '=', 2),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    
                    if inv_b:
                        related |= inv_b
        
        return related