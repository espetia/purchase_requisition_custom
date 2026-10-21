from odoo import models, fields

class PurchaseRequisitionPaymentMethod(models.Model):
    _name = 'purchase.requisition.payment.method'
    _description = 'Payment Methods Catalog'

    name = fields.Char(string='Name', required=True)
