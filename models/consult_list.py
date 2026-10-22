from odoo import models, fields

class PurchaseRequisitionConsultList(models.Model):
    _name = 'purchase.requisition.consult.list'
    _description = 'Consult Lists Catalog'

    name = fields.Char(string='Name', required=True)
