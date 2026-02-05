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
        _logger.info(f'Buscando supply SO con client_order_ref={sale.name}')
        
        supply_so = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', sale.name),
            ('company_id', '=', 1)
        ], limit=1)
        
        _logger.info(f'Supply SO: {supply_so.name if supply_so else "NO ENCONTRADA"}')
        
        if supply_so:
            _logger.info(f'Invoice status: {supply_so.invoice_status}')
            
            if supply_so.invoice_status == 'to invoice':
                try:
                    supply_invoice = supply_so._create_invoices()
                    _logger.info(f'Factura A creada: {supply_invoice.mapped("name")}')
                    
                    supply_invoice.with_company(1).action_post()
                    _logger.info('Factura A validada')
                    
                    supply_bill = self.sudo().search([
                        ('move_type', '=', 'in_invoice'),
                        ('company_id', '=', sale.company_id.id),
                        ('state', '=', 'draft'),
                        ('ref', '=', supply_so.name)
                    ], limit=1)
                    
                    _logger.info(f'Bill B encontrada: {supply_bill.name if supply_bill else "NO"}')
                    
                    if supply_bill:
                        supply_bill.with_company(sale.company_id.id).action_post()
                        _logger.info('Bill B validada')
                except Exception as e:
                    _logger.error(f'Error: {str(e)}')
                    import traceback
                    _logger.error(traceback.format_exc())