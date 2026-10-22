from odoo import models, fields


class PurchaseRequisitionRejectWizard(models.TransientModel):
    _name = 'purchase.requisition.reject.wizard'
    _description = 'Reject Purchase Requisition'

    requisition_id = fields.Many2one('purchase.requisition.custom', string='Requisition', required=True, readonly=True)
    reason = fields.Text(string='Reason', required=True)

    def action_reject(self):
        self.ensure_one()
        self.requisition_id.action_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
