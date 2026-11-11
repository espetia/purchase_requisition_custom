from odoo import models, fields


class PurchaseRequisitionKeyword(models.Model):
    _name = 'purchase.requisition.keyword'
    _description = 'Additional Information Keywords Catalog'
    _order = 'name'

    name = fields.Char(string='Keyword', required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'This keyword already exists.'),
    ]
