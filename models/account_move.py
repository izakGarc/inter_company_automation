# -*- coding: utf-8 -*-
from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # -------------------------------------------------------------------------
    # Helper: obtener usuario interno de una empresa para operaciones sudo
    # -------------------------------------------------------------------------
    def _get_company_internal_user(self, company_id):
        """
        Devuelve un usuario interno activo de la empresa indicada.
        Se usa para ejecutar acciones en otras empresas sin depender del
        usuario actual (que puede no tener acceso multi-empresa).
        """
        return self.env['res.users'].sudo().search([
            ('company_id', '=', company_id),
            ('share', '=', False),
            ('active', '=', True),
        ], limit=1)

    # -------------------------------------------------------------------------
    # Validación de facturas al confirmar (action_post)
    # -------------------------------------------------------------------------
    def action_post(self):
        res = super(AccountMove, self).action_post()

        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            _logger.info(f'=== FACTURA VALIDADA: {move.name} ===')
            # Puede haber multiples SOs en una factura (batch confirm)
            # procesamos cada uno individualmente para evitar singleton error
            sales = move.invoice_line_ids.mapped('sale_line_ids.order_id')
            _logger.info(f'Sales: {sales.mapped("name")}')

            for sale in sales.filtered(lambda s: not s.auto_generated):
                _logger.info(f'Procesando SO: {sale.name} - Company: {sale.company_id.name}')

                company = self.env['res.company']._find_company_from_partner(
                    sale.partner_id.id
                )
                if company and company != self.env.company:
                    _logger.info('Validando bill inter-company')
                    move._validate_intercompany_bill(company, sale)

                if sale.company_id.id != 1:
                    _logger.info('Creando cadena de facturas supply')
                    move._create_and_validate_supply_invoices(sale)

        return res

    def _validate_intercompany_bill(self, company, sale):
        """
        Valida la bill (in_invoice) generada en la empresa compradora.

        FIX: se agrega with_user(admin_user) para que la validación se ejecute
        con un usuario interno de la empresa destino, evitando el error de
        acceso multi-empresa cuando el usuario activo solo pertenece a Empresa B.
        """
        bill = self.sudo().search([
            ('move_type', '=', 'in_invoice'),
            ('company_id', '=', company.id),
            ('state', '=', 'draft'),
            ('ref', '=', sale.name)
        ], limit=1)

        _logger.info(f'Bill encontrada: {bill.name if bill else "NO"}')

        if bill:
            odoobot = self.env['res.users'].sudo().browse(1)
            _logger.info(f'Validando bill {bill.name} con superusuario (uid=1)')
            bill.sudo().with_user(odoobot).with_company(company.id).action_post()

    def _create_and_validate_supply_invoices(self, sale):
        """
        Valida la factura de venta y la bill generadas en Empresa A (supply)
        como parte del flujo inter-empresa.

        FIX: ambas validaciones usan with_user(admin_user) para ejecutarse con
        un usuario interno de Empresa A, evitando errores de acceso cuando el
        usuario activo pertenece a otra empresa.
        """
        supply_so = self.env['sale.order'].sudo().search([
            ('client_order_ref', '=', sale.name),
            ('company_id', '=', 1)
        ], limit=1)

        _logger.info(f'Supply SO: {supply_so.name if supply_so else "NO ENCONTRADA"}')

        if not supply_so:
            return

        # --- Factura de venta A (out_invoice) ---
        supply_invoice = self.sudo().search([
            ('move_type', '=', 'out_invoice'),
            ('company_id', '=', 1),
            ('state', '=', 'draft'),
            ('invoice_line_ids.sale_line_ids.order_id', '=', supply_so.id)
        ], limit=1)

        if supply_invoice:
            odoobot = self.env['res.users'].sudo().browse(1)
            _logger.info(f'Validando factura A: {supply_invoice.name}')
            supply_invoice.sudo().with_user(odoobot).with_company(1).action_post()
            _logger.info('✓ Factura A validada')

        # --- Bill de Empresa B desde SO supply (in_invoice) ---
        supply_bill = self.sudo().search([
            ('move_type', '=', 'in_invoice'),
            ('company_id', '=', sale.company_id.id),
            ('state', '=', 'draft'),
            ('ref', '=', supply_so.name)
        ], limit=1)

        if supply_bill:
            odoobot = self.env['res.users'].sudo().browse(1)
            _logger.info(f'Validando bill B: {supply_bill.name}')
            supply_bill.sudo().with_user(odoobot).with_company(
                sale.company_id.id
            ).action_post()
            _logger.info('✓ Bill B validada')

    # -------------------------------------------------------------------------
    # Cancelación con wizard inter-empresa
    # -------------------------------------------------------------------------
    def button_cancel(self):
        """
        Intercepta la cancelación individual. Si la factura tiene documentos
        relacionados en la cadena inter-empresa, muestra el wizard de
        cancelación en lugar de cancelar directamente.
        """
        if len(self) == 1:
            related = self._get_intercompany_related_invoices()
            if related:
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

        return super(AccountMove, self).button_cancel()

    def _get_intercompany_related_invoices(self):
        """
        Devuelve el recordset de facturas relacionadas en la cadena
        inter-empresa según el tipo y empresa de la factura actual.

        Casos contemplados:
          1. out_invoice de Empresa B  → factura A + bill B
          2. out_invoice de Empresa A  → factura B + bill B
          3. in_invoice  de Empresa B  → factura A + factura B
        """
        self.ensure_one()
        related = self.env['account.move']

        # Caso 1: Factura de venta de Empresa B
        if (self.move_type == 'out_invoice'
                and self.company_id.id == 2
                and self.invoice_origin):

            so_b = self.env['sale.order'].sudo().search(
                [('name', '=', self.invoice_origin)], limit=1
            )
            if so_b:
                so_a = self.env['sale.order'].sudo().search([
                    ('client_order_ref', '=', so_b.name),
                    ('company_id', '=', 1)
                ], limit=1)

                if so_a:
                    inv_a = self.env['account.move'].sudo().search([
                        ('invoice_origin', '=', so_a.name),
                        ('company_id', '=', 1),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if inv_a:
                        related |= inv_a

                    bill_b = self.env['account.move'].sudo().search([
                        ('ref', '=', so_a.name),
                        ('company_id', '=', 2),
                        ('move_type', '=', 'in_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if bill_b:
                        related |= bill_b

        # Caso 2: Factura de venta de Empresa A (supply)
        elif (self.move_type == 'out_invoice'
              and self.company_id.id == 1
              and self.invoice_origin):

            so_a = self.env['sale.order'].sudo().search(
                [('name', '=', self.invoice_origin)], limit=1
            )
            if so_a and so_a.client_order_ref:
                inv_b = self.env['account.move'].sudo().search([
                    ('invoice_origin', '=', so_a.client_order_ref),
                    ('company_id', '=', 2),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '!=', 'cancel')
                ], limit=1)
                if inv_b:
                    related |= inv_b

                bill_b = self.env['account.move'].sudo().search([
                    ('ref', '=', so_a.name),
                    ('company_id', '=', 2),
                    ('move_type', '=', 'in_invoice'),
                    ('state', '!=', 'cancel')
                ], limit=1)
                if bill_b:
                    related |= bill_b

        # Caso 3: Bill de Empresa B (in_invoice)
        elif (self.move_type == 'in_invoice'
              and self.company_id.id == 2
              and self.ref):

            so_a = self.env['sale.order'].sudo().search(
                [('name', '=', self.ref)], limit=1
            )
            if so_a:
                inv_a = self.env['account.move'].sudo().search([
                    ('invoice_origin', '=', so_a.name),
                    ('company_id', '=', 1),
                    ('move_type', '=', 'out_invoice'),
                    ('state', '!=', 'cancel')
                ], limit=1)
                if inv_a:
                    related |= inv_a

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