from odoo import models, fields

class ExpenseRegister(models.Model):
    _inherit = 'expense.register'

    custom_requisition_id = fields.Many2one('purchase.requisition.custom', string='Custom Requisition')
