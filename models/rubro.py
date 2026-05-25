from odoo import models, fields

class PurchaseRequisitionRubro(models.Model):
    _name = 'purchase.requisition.rubro'
    _description = 'Categories/Rubrics Catalog'

    name = fields.Char(string='Name', required=True)
    requires_vehicle = fields.Boolean(string='Requires Vehicle', default=False)
