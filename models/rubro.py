from odoo import models, fields

class PurchaseRequisitionRubro(models.Model):
    _name = 'purchase.requisition.rubro'
    _description = 'Categories/Rubrics Catalog'

    name = fields.Char(string='Name', required=True)
    requires_vehicle = fields.Boolean(string='Requires Vehicle', default=False)
    approver_ids = fields.One2many('purchase.requisition.rubro.approver', 'rubro_id', string='Authorization Chain')


class PurchaseRequisitionRubroApprover(models.Model):
    _name = 'purchase.requisition.rubro.approver'
    _description = 'Rubro Authorization Chain Step'
    _rec_name = 'user_id'
    _order = 'sequence, id'

    rubro_id = fields.Many2one('purchase.requisition.rubro', string='Rubro', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    user_id = fields.Many2one(
        'res.users',
        string='Approver',
        required=True,
        domain=lambda self: [('groups_id', 'in', self.env.ref('purchase_requisition_custom.group_purchase_requisition_user').id)],
    )
