from odoo import models, fields

class PurchaseRequisitionDepartment(models.Model):
    _name = 'purchase.requisition.department'
    _description = 'Departments Catalog'

    name = fields.Char(string='Name', required=True)
    need_rubro = fields.Boolean(string='Need Rubro', default=False)
