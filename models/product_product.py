from odoo import models, fields, api

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.depends('stock_quant_ids', 'stock_move_ids')
    def _compute_quantities(self):
        res = super(ProductProduct, self)._compute_quantities()
        
        # Solo aplicar para Loomber Digital (empresa B)
        if self.env.company.id != 1:
            base_company = self.env['res.company'].browse(1)
            
            for product in self:
                # Obtener stock de la empresa base (Global)
                base_qty = product.with_company(base_company).qty_available
                
                # Sumar al stock actual
                product.qty_available += base_qty
                product.virtual_available += base_qty
        
        return res