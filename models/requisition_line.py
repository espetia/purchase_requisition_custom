from odoo import models, fields, api

class PurchaseRequisitionLineCustom(models.Model):
    _name = 'purchase.requisition.line.custom'
    _description = 'Purchase Requisition Line Custom'

    requisition_id = fields.Many2one('purchase.requisition.custom', string='Requisition', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', domain=[('purchase_ok', '=', True)])
    name = fields.Char(string='Description', required=True)
    image = fields.Binary(string='Image')
    product_qty = fields.Float(string='Quantity', required=True, default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    po_line_id = fields.Many2one('purchase.order.line', string='PO Line', readonly=True)
    expense_register_id = fields.Many2one('expense.register', string='Expense Register', readonly=True)
