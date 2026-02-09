# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountMoveCancelWizard(models.TransientModel):
    _name = 'account.move.cancel.wizard'
    _description = 'Wizard para cancelar facturas inter-empresa'

    invoice_id = fields.Many2one('account.move', string='Factura a Cancelar', required=True)
    cancel_mode = fields.Selection([
        ('single', 'Cancelar solo esta factura'),
        ('all', 'Cancelar todas las facturas relacionadas')
    ], string='Modo de Cancelación', default='single', required=True)
    
    related_invoice_ids = fields.Many2many(
        'account.move',
        string='Facturas Relacionadas',
        compute='_compute_related_invoices'
    )
    
    message = fields.Html(string='Mensaje', compute='_compute_message')
    has_related = fields.Boolean(compute='_compute_related_invoices')

    @api.depends('invoice_id')
    def _compute_related_invoices(self):
        for wizard in self:
            related = self.env['account.move']
            
            if wizard.invoice_id:
                related = wizard.invoice_id.sudo()._get_intercompany_related_invoices()
            
            wizard.related_invoice_ids = related
            wizard.has_related = bool(related)

    @api.depends('invoice_id', 'related_invoice_ids')
    def _compute_message(self):
        for wizard in self:
            if not wizard.invoice_id:
                wizard.message = ''
                continue
            
            msg = f'''
            <div style="font-family: Arial, sans-serif;">
                <h3>Cancelar Factura y Documentos Relacionados</h3>
                <p>Está a punto de cancelar la factura <strong>{wizard.invoice_id.name}</strong>.</p>
            '''
            
            if wizard.related_invoice_ids:
                msg += '''
                <p>Esta factura tiene documentos relacionados en la operación inter-empresa:</p>
                <ul style="margin-top: 10px;">
                '''
                
                for inv in wizard.related_invoice_ids.sudo():
                    tipo = 'Factura de Venta' if inv.move_type == 'out_invoice' else 'Factura de Compra'
                    empresa = inv.company_id.name
                    msg += f'<li><strong>{tipo}</strong> ({empresa}): <strong>{inv.name}</strong></li>'
                
                msg += '</ul>'
            else:
                msg += '<p style="color: #666;">Esta factura no tiene documentos inter-empresa relacionados.</p>'
            
            msg += '</div>'
            wizard.message = msg

    def action_cancel_single(self):
        """Cancelar solo la factura seleccionada"""
        self.ensure_one()
        if self.invoice_id:
            invoice = self.invoice_id.sudo()
            invoice.write({'state': 'cancel'})
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel_all(self):
        """Cancelar todas las facturas relacionadas"""
        self.ensure_one()
        
        invoices_to_cancel = (self.invoice_id | self.related_invoice_ids).sudo()
        
        for invoice in invoices_to_cancel:
            if invoice.state != 'cancel':
                invoice.write({'state': 'cancel'})
        
        return {'type': 'ir.actions.act_window_close'}