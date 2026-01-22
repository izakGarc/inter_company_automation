# -*- coding: utf-8 -*-
from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Override para crear factura después de confirmar OV inter-empresa"""
        res = super(SaleOrder, self).action_confirm()
        
        # Solo para órdenes inter-empresa
        if self.partner_id.commercial_partner_id.company_id:
            # Verificar si hay regla inter-empresa activa
            if self._check_inter_company_rule():
                # Esperar a que se cree la OC
                self.env.cr.commit()
                # Generar factura automáticamente si está configurado
                if self.company_id.rule_type == 'sale_purchase':
                    pass  # La factura se generará desde picking
        
        return res
    
    def _check_inter_company_rule(self):
        """Verifica si hay regla inter-empresa activa"""
        company = self.env.user.company_id
        return company.rule_type in ('sale_purchase', 'invoice_bill')