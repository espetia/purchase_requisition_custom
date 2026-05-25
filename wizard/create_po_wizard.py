from odoo import models, fields, api

class CreatePoWizard(models.TransientModel):
    _name = 'create.po.wizard'
    _description = 'Create Purchase Order Wizard'

    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    requisition_id = fields.Many2one('purchase.requisition.custom', string='Requisition', required=True)
    line_ids = fields.Many2many('purchase.requisition.line.custom', string='Lines to Order')

    @api.model
    def default_get(self, fields_list):
        res = super(CreatePoWizard, self).default_get(fields_list)
        req_id = self.env.context.get('active_id')
        if req_id and self.env.context.get('active_model') == 'purchase.requisition.custom':
            res['requisition_id'] = req_id
            lines = self.env['purchase.requisition.line.custom'].search([
                ('requisition_id', '=', req_id),
                ('product_id', '!=', False),
                ('po_line_id', '=', False)
            ])
            res['line_ids'] = [(6, 0, lines.ids)]
        return res

    def action_create_po(self):
        self.ensure_one()
        po_vals = {
            'partner_id': self.partner_id.id,
            'custom_requisition_id': self.requisition_id.id,
            'origin': self.requisition_id.name,
        }
        po = self.env['purchase.order'].create(po_vals)

        for line in self.line_ids:
            po_line = self.env['purchase.order.line'].create({
                'order_id': po.id,
                'product_id': line.product_id.id,
                'name': line.name,
                'product_qty': line.product_qty,
                'product_uom': line.product_uom_id.id,
                'date_planned': fields.Datetime.now(),
            })
            line.po_line_id = po_line.id

        # Update state if all lines are ordered
        all_lines = self.env['purchase.requisition.line.custom'].search([('requisition_id', '=', self.requisition_id.id)])
        if all(l.po_line_id for l in all_lines):
            self.requisition_id.state = 'waiting'
            
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'form',
            'res_id': po.id,
        }
