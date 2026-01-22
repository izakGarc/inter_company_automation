# -*- coding: utf-8 -*-
# from odoo import http


# class InterCompanyAutomation(http.Controller):
#     @http.route('/inter_company_automation/inter_company_automation', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/inter_company_automation/inter_company_automation/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('inter_company_automation.listing', {
#             'root': '/inter_company_automation/inter_company_automation',
#             'objects': http.request.env['inter_company_automation.inter_company_automation'].search([]),
#         })

#     @http.route('/inter_company_automation/inter_company_automation/objects/<model("inter_company_automation.inter_company_automation"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('inter_company_automation.object', {
#             'object': obj
#         })
