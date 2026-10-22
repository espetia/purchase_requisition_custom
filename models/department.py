from odoo import models, fields

class PurchaseRequisitionDepartment(models.Model):
    _name = 'purchase.requisition.department'
    _description = 'Departments Catalog'

    name = fields.Char(string='Name', required=True)
    need_rubro = fields.Boolean(string='Need Rubro', default=False)
    rubro_ids = fields.Many2many(
        'purchase.requisition.rubro',
        'purchase_requisition_department_rubro_rel', 'department_id', 'rubro_id',
        string='Rubros',
    )
    need_payment_method = fields.Boolean(string='Need Payment Method', default=False)
    allow_minor_expense = fields.Boolean(string='Allow Minor Expenses', default=False)
