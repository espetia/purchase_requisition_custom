from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PurchaseRequisitionCustom(models.Model):
    _name = 'purchase.requisition.custom'
    _description = 'Purchase Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    requisition_name = fields.Char(string='Name', required=True)
    requester_id = fields.Many2one('res.users', string='Requester', default=lambda self: self.env.user)
    rubro_id = fields.Many2one('purchase.requisition.rubro', string='Rubro', required=True)
    manager_id = fields.Many2one(
        'res.users', 
        string='Manager', 
        required=True, 
        domain=lambda self: [('groups_id', 'in', self.env.ref('purchase_requisition_custom.group_purchase_requisition_manager').id)]
    )
    requires_vehicle = fields.Boolean(related='rubro_id.requires_vehicle')
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    expiration_date = fields.Date(string='Expiration Date', required=True)
    state = fields.Selection([
        ('draft', 'Request'),
        ('quote', 'In Quotation'),
        ('waiting', 'PO in Process'),
        ('authorized', 'Authorized'),
        ('done', 'Delivered'),
        ('cancel', 'Denied')
    ], string='Status', default='draft', tracking=True, group_expand='_group_expand_states')
    
    comments = fields.Html(string='Comments')
    line_ids = fields.One2many('purchase.requisition.line.custom', 'requisition_id', string='Lines', required=True)
    purchase_order_ids = fields.One2many('purchase.order', 'custom_requisition_id', string='Purchase Orders')
    purchase_order_count = fields.Integer(string='PO Count', compute='_compute_purchase_order_count')

    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        """
        Computes the total number of purchase orders linked to this requisition.
        """
        for rec in self:
            if self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_user') or self.env.user.has_group('purchase.group_purchase_user'):
                rec.purchase_order_count = len(rec.sudo().purchase_order_ids)
            else:
                rec.purchase_order_count = 0

    @api.model
    def _group_expand_states(self, states, domain, order):
        """
        Returns all possible states for the requisition, ensuring that the kanban view
        displays a column for every state, even if there are no records in that state.
        """
        return [key for key, val in type(self).state.selection]

    def action_view_purchase_orders(self):
        """
        Returns a dictionary representing an action to open the tree/form view 
        of the purchase orders associated with this requisition.
        """
        self.ensure_one()
        return {
            'name': _('Purchase Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'tree,form',
            'domain': [('custom_requisition_id', '=', self.id)],
            'context': {'default_custom_requisition_id': self.id},
        }

    @api.constrains('rubro_id', 'vehicle_id')
    def _check_vehicle_required(self):
        """
        Ensures that a vehicle is provided if the selected rubro requires one.
        Raises a ValidationError if the condition is not met.
        """
        for rec in self:
            if rec.rubro_id.requires_vehicle and not rec.vehicle_id:
                raise ValidationError(_("Vehicle is mandatory when Rubro requires it."))

    def write(self, vals):
        """
        Overrides the write method to prevent non-managers from updating the state.
        """
        if 'state' in vals: 
            if not self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_warehouse'):
                raise ValidationError(_("Only Purchase Managers can update the status of a requisition."))
            for rec in self:
                if rec.state == 'draft' and vals['state'] != 'draft':
                    if any(not line.product_id for line in rec.line_ids):
                        raise ValidationError(_("You cannot change the draft state if there are lines without a product."))
        return super(PurchaseRequisitionCustom, self).write(vals)

    @api.model
    def create(self, vals):
        """
        Overrides the create method to assign a unique sequence reference 
        to the requisition name if it is still set to 'New'.
        """
        if not vals.get('line_ids'):
            raise ValidationError(_("You cannot create a requisition without lines."))

        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('purchase.requisition.custom') or _('New')
        requisition = super(PurchaseRequisitionCustom, self).create(vals)

        template = self.env.ref('purchase_requisition_custom.email_template_draft_requisitions_reminder', raise_if_not_found=False)
        if template and requisition.manager_id:
            template.with_context(draft_requisitions=requisition).send_mail(
                requisition.manager_id.id,
                force_send=False
            )

        return requisition

    @api.model
    def _cron_send_draft_requisitions_reminder(self):
        """
        Finds all draft requisitions, groups them by manager,
        and sends ONE email per manager with a list of their pending requisitions.
        """
        draft_reqs = self.search([('state', '=', 'draft')])
        if not draft_reqs:
            return

        manager_reqs = {}
        for req in draft_reqs:
            if req.manager_id:
                if req.manager_id not in manager_reqs:
                    manager_reqs[req.manager_id] = self.env['purchase.requisition.custom']
                manager_reqs[req.manager_id] |= req

        template = self.env.ref('purchase_requisition_custom.email_template_draft_requisitions_reminder', raise_if_not_found=False)
        if not template:
            return

        for manager, reqs in manager_reqs.items():
            template.with_context(draft_requisitions=reqs).send_mail(
                manager.id, 
                force_send=False
            )

