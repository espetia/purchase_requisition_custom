from odoo import models, fields

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    custom_requisition_id = fields.Many2one('purchase.requisition.custom', string='Custom Requisition')

    def write(self, vals):
        """
        Overrides the write method to update the state of the associated custom requisition
        when the purchase order state changes. If all POs are 'purchase' or 'done', the
        requisition is 'authorized'. If all are 'cancel' or 'reject', it is 'cancel'.
        """
        res = super(PurchaseOrder, self).write(vals)
        if 'state' in vals:
            for order in self:
                req = order.custom_requisition_id
                if req:
                    all_pos = req.purchase_order_ids
                    if all_pos:
                        states = [po.state for po in all_pos]
                        if all(s in ('purchase', 'done') for s in states):
                            req.state = 'authorized'
                        elif all(s in ('cancel', 'reject') for s in states):
                            req.state = 'cancel'
        return res
