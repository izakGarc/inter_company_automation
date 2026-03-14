{
    'name': "Inter Company Automation",
    'summary': """
        Automatiza facturación y recepciones en transacciones inter-empresa""",
    'description': """
        - Valida automáticamente recepciones cuando se valida entrega
        - Genera facturas proveedor cuando se genera factura cliente
        - Valida facturas proveedor automáticamente
    """,
    'author': "Ili-Dev",
    'website': "https://github.com/izakGarc",
    'category': 'Inventory',
    'version': '16.0',
    'depends': [
        'base',
        'sale',
        'purchase',
        'stock',
        'account',
        'account_inter_company_rules',
        'sale_purchase_inter_company_rules',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizard/account_move_cancel_wizard_view.xml',
        'wizard/sale_order_cancel_wizard_view.xml',
        'wizard/intercompany_report_wizard.xml',
        'reports/intercompany_report_pdf.xml',
    ],
  
}