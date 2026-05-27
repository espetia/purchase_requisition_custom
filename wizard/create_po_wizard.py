from odoo import models, fields, api, exceptions, _

class CreatePoWizard(models.TransientModel):
    _name = 'create.po.wizard'
    _description = 'Create Purchase Order Wizard'

    action_type = fields.Selection([
        ('create_po', 'Create Purchase Order'),
        ('create_pr', 'Create Purchase Requisition')
    ], string='Action', default='create_po', required=True)

    partner_id = fields.Many2one('res.partner', string='Vendor')
    type_id = fields.Many2one('purchase.requisition.type', string='Agreement Type')
    vendor_ids = fields.Many2many('res.partner', string='Vendors')
    
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
        
        # ---------------------------------------------
        # FLOW A: CREATE DIRECT PURCHASE ORDER
        # ---------------------------------------------
        if self.action_type == 'create_po':
            if not self.partner_id:
                raise exceptions.UserError(_('Please select a vendor.'))
                
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
            
        # ---------------------------------------------
        # FLOW B: CREATE PURCHASE REQUISITION
        # ---------------------------------------------
        elif self.action_type == 'create_pr':
            if not self.vendor_ids:
                raise exceptions.UserError(_('Please select at least one vendor.'))
            if not self.type_id:
                raise exceptions.UserError(_('Please select an agreement type.'))
                
            # 1. Create native Purchase Requisition
            pr_vals = {
                'type_id': self.type_id.id,
                'origin': self.requisition_id.name,
                'user_id': self.env.user.id,
                'company_id': self.env.company.id,
            }
            pr = self.env['purchase.requisition'].create(pr_vals)
            
            # 2. Add Requisition Lines
            for line in self.line_ids:
                self.env['purchase.requisition.line'].create({
                    'requisition_id': pr.id,
                    'product_id': line.product_id.id,
                    'product_qty': line.product_qty,
                    'product_uom_id': line.product_uom_id.id,
                    'price_unit': 0.0,
                })

            # 3. Create a Purchase Order for each selected vendor
            for index, vendor in enumerate(self.vendor_ids):
                po = self.env['purchase.order'].create({
                    'partner_id': vendor.id,
                    'requisition_id': pr.id,
                    'custom_requisition_id': self.requisition_id.id,
                    'origin': self.requisition_id.name,
                })
                
                for line in self.line_ids:
                    po_line = self.env['purchase.order.line'].create({
                        'order_id': po.id,
                        'product_id': line.product_id.id,
                        'name': line.name,
                        'product_qty': line.product_qty,
                        'product_uom': line.product_uom_id.id,
                        'date_planned': fields.Datetime.now(),
                    })
                    
                    # Link back to the custom line using the first PO created.
                    if index == 0:
                        line.po_line_id = po_line.id
            
            # 4. Confirm the newly created Requisition
            pr.action_in_progress()

            # 5. Update custom requisition state if all lines are ordered
            all_lines = self.env['purchase.requisition.line.custom'].search([('requisition_id', '=', self.requisition_id.id)])
            if all(l.po_line_id for l in all_lines):
                self.requisition_id.state = 'waiting'
                
            # 6. Redirect user to the new native Purchase Requisition
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.requisition',
                'view_mode': 'form',
                'res_id': pr.id,
            }
