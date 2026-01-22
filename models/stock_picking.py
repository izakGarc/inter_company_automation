# -*- coding: utf-8 -*-
from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        
        for picking in self:
            if picking.picking_type_code == 'outgoing' and picking.sale_id:
                sale = picking.sale_id
                partner_company = sale.partner_id.commercial_partner_id.company_id
                
                if partner_company and partner_company != self.env.company:
                    picking._validate_inter_company_receipt(partner_company, sale)
                    picking._create_inter_company_invoice(partner_company, sale)
        
        return res

    def _validate_inter_company_receipt(self, partner_company, sale):
        PurchaseOrder = self.env['purchase.order'].sudo()
        po = PurchaseOrder.search([
            ('partner_ref', '=', sale.name),
            ('company_id', '=', partner_company.id),
            ('state', 'in', ['purchase', 'done'])
        ], limit=1)
        
        if po:
            for picking in po.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel']):
                try:
                    picking.button_validate()
                    _logger.info(f'Recepción validada: {picking.name}')
                except Exception as e:
                    _logger.error(f'Error validando recepción {picking.name}: {str(e)}')

    def _create_inter_company_invoice(self, partner_company, sale):
        if sale.invoice_status != 'to invoice':
            return
        
        try:
            invoice = sale._create_invoices()
            if invoice:
                invoice.action_post()
                _logger.info(f'Factura creada y validada: {invoice.name}')
                
                self.env.cr.commit()
                
                self._create_vendor_bill(partner_company, sale, invoice)
        except Exception as e:
            _logger.error(f'Error creando factura: {str(e)}')

    def _create_vendor_bill(self, partner_company, sale, customer_invoice):
        PurchaseOrder = self.env['purchase.order'].sudo()
        po = PurchaseOrder.search([
            ('partner_ref', '=', sale.name),
            ('company_id', '=', partner_company.id)
        ], limit=1)
        
        if po and po.invoice_status == 'to invoice':
            try:
                bill = po._create_invoices()
                if bill:
                    bill.action_post()
                    _logger.info(f'Factura proveedor creada: {bill.name}')
            except Exception as e:
                _logger.error(f'Error creando bill: {str(e)}')