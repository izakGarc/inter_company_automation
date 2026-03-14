# -*- coding: utf-8 -*-
from odoo import models


def fmt(value):
    try:
        return '{:,.2f}'.format(float(value))
    except (TypeError, ValueError):
        return '0.00'


class InterCompanyReportPdf(models.AbstractModel):
    _name = 'report.inter_company_automation.ic_report_pdf'
    _description = 'Reporte PDF Ordenes de Compra Inter-empresa'

    def _get_report_values(self, docids, data=None):
        wizard  = self.env['intercompany.report.wizard'].browse(docids)
        orders  = self.env['purchase.order'].sudo().browse(data.get('po_ids', []))

        # ── Resumen consolidado por producto ─────────────────────────
        product_summary = {}
        for order in orders:
            for line in order.order_line.filtered(lambda l: not l.display_type):
                key = line.product_id.id
                if key not in product_summary:
                    product_summary[key] = {
                        'product': line.product_id.name,
                        'sku':     line.product_id.default_code or '-',
                        'qty':     0.0,
                        'uom':     line.product_uom.name,
                        'total':   0.0,
                    }
                product_summary[key]['qty']   += line.product_qty
                product_summary[key]['total'] += line.price_subtotal

        summary_lines = sorted(product_summary.values(), key=lambda x: x['product'])
        for s in summary_lines:
            s['qty']   = '{:.2f}'.format(s['qty'])
            s['total'] = fmt(s['total'])

        # ── Detalle por OC con sus líneas ────────────────────────────
        po_lines    = []
        grand_total = 0.0

        for order in orders:
            order_total    = order.amount_total
            order_subtotal = sum(
                l.price_subtotal for l in order.order_line if not l.display_type
            )
            grand_total += order_total

            # Líneas del pedido
            lines = []
            for line in order.order_line.filtered(lambda l: not l.display_type):
                lines.append({
                    'sku':        line.product_id.default_code or '-',
                    'product':    line.product_id.name,
                    'qty':        '{:.2f}'.format(line.product_qty),
                    'uom':        line.product_uom.name,
                    'price_unit': fmt(line.price_unit),
                    'subtotal':   fmt(line.price_subtotal),
                })

            po_lines.append({
                'name':     order.name,
                'date':     order.date_order.strftime('%d/%m/%Y') if order.date_order else '',
                'partner':  order.partner_id.name,
                'ref':      order.partner_ref or '-',
                'subtotal': fmt(order_subtotal),
                'taxes':    fmt(order_total - order_subtotal),
                'total':    fmt(order_total),
                'currency': order.currency_id.symbol,
                'state':    dict(order._fields['state'].selection).get(order.state, order.state),
                'lines':    lines,
            })

        return {
            'doc_ids':        docids,
            'doc_model':      'intercompany.report.wizard',
            'docs':           wizard,
            'data':           data,
            'summary_lines':  summary_lines,
            'po_lines':       po_lines,
            'grand_total':    fmt(grand_total),
            'po_count':       len(po_lines),
            'currency_symbol': orders[0].currency_id.symbol if orders else '$',
        }