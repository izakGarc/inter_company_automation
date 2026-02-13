# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrderCancelWizard(models.TransientModel):
    _name = 'sale.order.cancel.wizard'
    _description = 'Wizard para cancelar órdenes inter-empresa'

    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta', required=True)
    has_invoices = fields.Boolean(compute='_compute_has_invoices')
    has_intercompany = fields.Boolean(compute='_compute_intercompany_data')
    
    # Documentos relacionados
    supply_order_id = fields.Many2one('sale.order', string='Orden Supply', compute='_compute_intercompany_data')
    purchase_order_id = fields.Many2one('purchase.order', string='Orden de Compra', compute='_compute_intercompany_data')
    
    picking_out_a_id = fields.Many2one('stock.picking', string='Entrega Empresa A', compute='_compute_intercompany_data')
    picking_in_b_id = fields.Many2one('stock.picking', string='Recepción Empresa B', compute='_compute_intercompany_data')
    picking_out_b_id = fields.Many2one('stock.picking', string='Entrega Empresa B', compute='_compute_intercompany_data')
    
    message = fields.Html(string='Mensaje', compute='_compute_message')

    @api.depends('sale_order_id')
    def _compute_has_invoices(self):
        for wizard in self:
            if wizard.sale_order_id:
                invoices = wizard.sale_order_id.invoice_ids.filtered(lambda inv: inv.state != 'cancel')
                wizard.has_invoices = bool(invoices)
            else:
                wizard.has_invoices = False

    @api.depends('sale_order_id')
    def _compute_intercompany_data(self):
        for wizard in self:
            wizard.has_intercompany = False
            wizard.supply_order_id = False
            wizard.purchase_order_id = False
            wizard.picking_out_a_id = False
            wizard.picking_in_b_id = False
            wizard.picking_out_b_id = False
            
            if not wizard.sale_order_id or wizard.sale_order_id.company_id.id == 1:
                continue
            
            # Buscar orden supply
            supply = self.env['sale.order'].sudo().search([
                ('client_order_ref', '=', wizard.sale_order_id.name),
                ('company_id', '=', 1)
            ], limit=1)
            
            if supply:
                wizard.has_intercompany = True
                wizard.supply_order_id = supply
                
                # Buscar orden de compra
                po = self.env['purchase.order'].sudo().search([
                    ('partner_ref', '=', supply.name),
                    ('company_id', '=', wizard.sale_order_id.company_id.id)
                ], limit=1)
                
                if po:
                    wizard.purchase_order_id = po
                    
                    # Buscar recepción en Empresa B
                    picking_in = po.picking_ids.filtered(lambda p: p.picking_type_code == 'incoming' and p.state != 'cancel')
                    if picking_in:
                        wizard.picking_in_b_id = picking_in[0]
                
                # Buscar entrega de Empresa A
                picking_out_a = supply.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
                if picking_out_a:
                    wizard.picking_out_a_id = picking_out_a[0]
            
            # Buscar entrega de Empresa B al cliente
            picking_out_b = wizard.sale_order_id.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
            if picking_out_b:
                wizard.picking_out_b_id = picking_out_b[0]

    @api.depends('sale_order_id', 'has_invoices', 'has_intercompany', 'supply_order_id', 'purchase_order_id', 
                 'picking_out_a_id', 'picking_in_b_id', 'picking_out_b_id')
    def _compute_message(self):
        for wizard in self:
            if not wizard.sale_order_id:
                wizard.message = ''
                continue
            
            msg = f'''
            <div style="font-family: Arial, sans-serif; padding: 15px; max-height: 500px; overflow-y: auto;">
                <h3 style="margin-top: 0; color: #dc2626;">⚠️ Cancelar Orden y Documentos Relacionados</h3>
                <p style="font-size: 14px; margin-bottom: 15px;">
                    Está a punto de cancelar la orden <strong style="color: #dc2626;">{wizard.sale_order_id.name}</strong>.
                </p>
            '''
            
            # Advertencia de facturas
            if wizard.has_invoices:
                msg += '''
                <div style="background: #fee2e2; border-left: 4px solid #dc2626; padding: 12px; margin-bottom: 15px;">
                    <p style="margin: 0; color: #dc2626; font-weight: bold;">
                        ❌ ESTA ORDEN TIENE FACTURAS ACTIVAS
                    </p>
                    <p style="margin: 5px 0 0 0; color: #991b1b; font-size: 13px;">
                        Debe cancelar todas las facturas relacionadas antes de cancelar la orden.
                    </p>
                </div>
                '''
            
            # Documentos inter-empresa
            if wizard.has_intercompany:
                msg += '''
                <p style="font-size: 14px; margin-bottom: 10px; font-weight: bold;">
                    📋 Esta orden tiene documentos inter-empresa que también se cancelarán:
                </p>
                <ul style="margin-top: 10px; padding-left: 20px; list-style-type: none;">
                '''
                
                # Órdenes
                msg += f'''
                <li style="margin-bottom: 8px; font-size: 13px;">
                    <strong style="color: #2563eb;">🛒 Orden de Venta Supply (Empresa A):</strong> {wizard.supply_order_id.name} 
                    <span style="color: #64748b;">({wizard.supply_order_id.state})</span>
                </li>
                '''
                
                if wizard.purchase_order_id:
                    msg += f'''
                    <li style="margin-bottom: 8px; font-size: 13px;">
                        <strong style="color: #2563eb;">📦 Orden de Compra (Empresa B):</strong> {wizard.purchase_order_id.name}
                        <span style="color: #64748b;">({wizard.purchase_order_id.state})</span>
                    </li>
                    '''
                
                # Entregas
                if wizard.picking_out_a_id:
                    msg += f'''
                    <li style="margin-bottom: 8px; font-size: 13px;">
                        <strong style="color: #dc2626;">📤 Entrega Empresa A → Empresa B:</strong> {wizard.picking_out_a_id.name}
                        <span style="color: #64748b;">({wizard.picking_out_a_id.state})</span>
                    </li>
                    '''
                
                if wizard.picking_in_b_id:
                    msg += f'''
                    <li style="margin-bottom: 8px; font-size: 13px;">
                        <strong style="color: #dc2626;">📥 Recepción en Empresa B:</strong> {wizard.picking_in_b_id.name}
                        <span style="color: #64748b;">({wizard.picking_in_b_id.state})</span>
                    </li>
                    '''
                
                if wizard.picking_out_b_id:
                    msg += f'''
                    <li style="margin-bottom: 8px; font-size: 13px;">
                        <strong style="color: #dc2626;">🚚 Entrega al Cliente:</strong> {wizard.picking_out_b_id.name}
                        <span style="color: #64748b;">({wizard.picking_out_b_id.state})</span>
                    </li>
                    '''
                
                msg += '</ul>'
                
                # Advertencia de stock
                msg += '''
                <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin-top: 15px;">
                    <p style="margin: 0; color: #92400e; font-size: 13px;">
                        ⚠️ <strong>Las entregas validadas se revertirán</strong> y el stock regresará a Empresa A
                    </p>
                </div>
                '''
            else:
                msg += '<p style="color: #6b7280; font-size: 13px;">Esta orden no tiene documentos inter-empresa relacionados.</p>'
            
            msg += '</div>'
            wizard.message = msg

    def action_cancel_all(self):
        """Cancelar orden y todos los documentos inter-empresa"""
        self.ensure_one()
        
        if self.has_invoices:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Debe cancelar las facturas primero',
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        import logging
        _logger = logging.getLogger(__name__)
        
        try:
            # 1. Cancelar TODOS los pickings primero
            if self.picking_out_b_id:
                self._force_cancel_picking(self.picking_out_b_id)
            
            if self.picking_in_b_id:
                self._force_cancel_picking(self.picking_in_b_id)
            
            if self.picking_out_a_id:
                self._force_cancel_picking(self.picking_out_a_id)
            
            # Commit pickings
            self.env.cr.commit()
            
            # 2. Cancelar Purchase Order (ahora sin recepciones bloqueando)
            if self.purchase_order_id and self.purchase_order_id.state != 'cancel':
                _logger.info(f'Cancelando PO: {self.purchase_order_id.name}')
                self.purchase_order_id.sudo().with_company(
                    self.purchase_order_id.company_id
                ).with_context(
                    disable_cancel_warning=True
                ).button_cancel()
            
            # 3. Cancelar Sale Order Supply
            if self.supply_order_id and self.supply_order_id.state != 'cancel':
                _logger.info(f'Cancelando orden supply: {self.supply_order_id.name}')
                self.supply_order_id.sudo().with_company(
                    self.supply_order_id.company_id
                ).with_context(
                    skip_intercompany_cancel=True,
                    disable_cancel_warning=True
                ).action_cancel()
            
            # 4. Cancelar Sale Order Original
            if self.sale_order_id and self.sale_order_id.state != 'cancel':
                _logger.info(f'Cancelando orden original: {self.sale_order_id.name}')
                self.sale_order_id.sudo().with_company(
                    self.sale_order_id.company_id
                ).with_context(
                    skip_intercompany_cancel=True,
                    disable_cancel_warning=True
                ).action_cancel()
            
            _logger.info('✅ Cancelación completada')
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Éxito',
                    'message': 'Orden y documentos relacionados cancelados correctamente',
                    'type': 'success',
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
            
        except Exception as e:
            _logger.error(f'Error al cancelar: {e}', exc_info=True)
            self.env.cr.rollback()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def _force_cancel_picking(self, picking):
        """Forzar cancelación de picking y revertir movimientos de stock"""
        if not picking or picking.state == 'cancel':
            return
        
        # CRÍTICO: Usar sudo() con la empresa correcta
        picking = picking.sudo().with_company(picking.company_id)
        
        # Revertir movimientos de stock manualmente
        for move in picking.move_ids.sudo():
            if move.state == 'done':
                # Revertir quantity_done en move_lines
                for move_line in move.move_line_ids.sudo():
                    # Actualizar quants directamente (revertir stock)
                    quants_dest = self.env['stock.quant'].sudo().search([
                        ('product_id', '=', move.product_id.id),
                        ('location_id', '=', move.location_dest_id.id),
                        ('company_id', '=', picking.company_id.id),
                    ])
                    
                    for quant in quants_dest:
                        # Reducir del destino
                        new_qty = quant.quantity - move_line.qty_done
                        if new_qty <= 0:
                            quant.sudo().unlink()
                        else:
                            quant.sudo().write({'quantity': new_qty})
                    
                    # Aumentar en origen
                    quant_src = self.env['stock.quant'].sudo().search([
                        ('product_id', '=', move.product_id.id),
                        ('location_id', '=', move.location_id.id),
                        ('company_id', '=', picking.company_id.id),
                    ], limit=1)
                    
                    if quant_src:
                        quant_src.sudo().write({
                            'quantity': quant_src.quantity + move_line.qty_done
                        })
                    else:
                        self.env['stock.quant'].sudo().create({
                            'product_id': move.product_id.id,
                            'location_id': move.location_id.id,
                            'quantity': move_line.qty_done,
                            'company_id': picking.company_id.id,
                        })
                
                # Marcar move como cancelado usando SQL (bypass validaciones)
                self.env.cr.execute("""
                    UPDATE stock_move 
                    SET state = 'cancel' 
                    WHERE id = %s
                """, (move.id,))
        
        # Marcar picking como cancelado usando SQL (bypass validaciones)
        self.env.cr.execute("""
            UPDATE stock_picking 
            SET state = 'cancel' 
            WHERE id = %s
        """, (picking.id,))
        
        # NO hacer commit aquí, se hará automáticamente al final