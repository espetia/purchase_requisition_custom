from odoo import models, fields


class PurchaseRequisitionApproval(models.Model):
    _name = 'purchase.requisition.approval'
    _description = 'Purchase Requisition Approval Step'
    _rec_name = 'user_id'
    _order = 'sequence, id'

    requisition_id = fields.Many2one('purchase.requisition.custom', string='Requisition', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    user_id = fields.Many2one('res.users', string='Approver', required=True)
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', required=True, default='waiting')
    date = fields.Datetime(string='Date')
    comment = fields.Text(string='Comment')
