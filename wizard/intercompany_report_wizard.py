# -*- coding: utf-8 -*-
from datetime import datetime
from odoo import fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import pytz


class InterCompanyReportWizard(models.TransientModel):
    _name = "intercompany.report.wizard"
    _description = "Reporte de Ordenes de Compra Inter-empresa"

    date_start = fields.Date(required=True, string="Fecha inicio")
    date_end   = fields.Date(required=True, string="Fecha fin")

    company_id = fields.Many2one(
        'res.company',
        string="Empresa compradora",
        default=lambda self: self.env.company,
        readonly=True,
    )

    def _get_tz_datetime(self, date, end=False):
        user_tz = pytz.timezone(
            self.env.context.get('tz') or self.env.user.tz or 'UTC'
        )
        if end:
            return datetime(date.year, date.month, date.day, 23, 59, 59, 0, user_tz)
        return datetime(date.year, date.month, date.day, 0, 0, 0, 0, user_tz)

    def _get_purchase_orders(self):
        """
        OCs inter-empresa: generadas automáticamente (auto_generated=True)
        cuyo proveedor es una empresa del sistema (Loomber Global).
        """
        ic_partner_ids = self.env['res.company'].sudo().search([
            ('id', '!=', self.company_id.id)
        ]).mapped('partner_id').ids

        domain = [
            ('auto_generated',  '=',  True),
            ('partner_id',      'in', ic_partner_ids),
            ('company_id',      '=',  self.company_id.id),
            ('date_order',      '>=', self._get_tz_datetime(self.date_start)),
            ('date_order',      '<=', self._get_tz_datetime(self.date_end, end=True)),
            ('state',           'in', ['purchase', 'done']),
        ]
        return self.env['purchase.order'].sudo().search(domain, order='date_order asc')

    def action_print_pdf(self):
        orders = self._get_purchase_orders()
        if not orders:
            raise ValidationError(
                "No se encontraron órdenes de compra inter-empresa en el periodo seleccionado."
            )

        data = {
            'date_start':   self.date_start.strftime('%d/%m/%Y'),
            'date_end':     self.date_end.strftime('%d/%m/%Y'),
            'company_name': self.company_id.name,
            'po_ids':       orders.ids,
        }

        return self.env.ref(
            'inter_company_automation.action_intercompany_report_pdf'
        ).report_action(self, data=data)