from odoo import models, fields, api, _
from odoo.exceptions import AccessError

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    custom_requisition_id = fields.Many2one('purchase.requisition.custom', string='Custom Requisition')
    is_warehouse_agent_only = fields.Boolean(
        compute='_compute_is_warehouse_agent_only',
        default=False,
        store=False
    )

    @api.depends_context('uid')
    def _compute_is_warehouse_agent_only(self):
        is_warehouse = self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_warehouse')
        is_manager = self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_manager')
        for rec in self:
            rec.is_warehouse_agent_only = is_warehouse and not is_manager

    def write(self, vals):
        """
        Overrides the write method to update the state of the associated custom requisition
        when the purchase order state changes. If all POs are 'purchase' or 'done', the
        requisition is 'authorized'. If all are 'cancel' or 'reject', it is 'cancel'.
        """
        # Warehouse Agent field restrictions
        is_warehouse = self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_warehouse')
        is_manager = self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_manager')
        if is_warehouse and not is_manager:
            allowed_fields = {'date_planned', 'date_invoice_partner'}
            # Allow write if vals only contains allowed fields (or system/tracking fields, but typically user only sends these)
            # Actually, standard is to just check if there's any unauthorized field in vals
            unauthorized_fields = set(vals.keys()) - allowed_fields
            if unauthorized_fields:
                raise AccessError(_("Warehouse Agents can only edit 'date_planned' and 'date_invoice_partner'."))

        res = super(PurchaseOrder, self).write(vals)
        if 'state' in vals:
            for order in self:
                req = order.custom_requisition_id
                if req:
                    all_pos = req.purchase_order_ids
                    if all_pos:
                        states = [po.state for po in all_pos]
                        if all(s in ('purchase', 'done') for s in states):
                            req.sudo().write({'state': 'authorized'})
                        elif all(s in ('cancel', 'reject') for s in states):
                            req.sudo().write({'state': 'cancel'})
        return res
