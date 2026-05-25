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

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        Updates the name and product_uom_id automatically when a product_id is selected.
        """
        for rec in self:
            if rec.product_id:
                rec.name = rec.product_id.display_name
                rec.product_uom_id = rec.product_id.uom_id
