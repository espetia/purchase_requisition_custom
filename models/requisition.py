import difflib
import unicodedata

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools import is_html_empty

# Minimum difflib ratio for two normalized texts to count as similar
# (see PurchaseRequisitionCustom._is_similar_text).
SIMILARITY_RATIO = 0.8
# Shorter normalized texts are too generic to compare.
MIN_SIMILAR_TEXT_LENGTH = 4

class PurchaseRequisitionCustom(models.Model):
    _name = 'purchase.requisition.custom'
    _description = 'Purchase Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Folio', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    requisition_name = fields.Char(string='Purchase Reference', required=True)
    requester_id = fields.Many2one('res.users', string='Requester', default=lambda self: self.env.user)
    department_id = fields.Many2one(
        'purchase.requisition.department',
        string='Department',
        required=True,
        default=lambda self: self._default_department_id(),
    )
    allowed_department_ids = fields.Many2many('purchase.requisition.department', compute='_compute_allowed_department_ids')
    need_rubro = fields.Boolean(related='department_id.need_rubro')
    department_rubro_ids = fields.Many2many(related='department_id.rubro_ids')
    need_payment_method = fields.Boolean(related='department_id.need_payment_method')
    allow_minor_expense = fields.Boolean(related='department_id.allow_minor_expense')
    rubro_id = fields.Many2one('purchase.requisition.rubro', string='Rubro')
    manager_id = fields.Many2one(
        'res.users',
        string='Process Area',
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
    
    comments = fields.Html(string='Comments (Legacy)', readonly=True)
    has_legacy_comments = fields.Boolean(compute='_compute_has_legacy_comments')
    text_comment = fields.Text(string='Comments')
    line_ids = fields.One2many('purchase.requisition.line.custom', 'requisition_id', string='Lines', required=True)
    purchase_order_ids = fields.One2many('purchase.order', 'custom_requisition_id', string='Purchase Orders')
    purchase_order_count = fields.Integer(string='PO Count', compute='_compute_purchase_order_count')
    expense_register_ids = fields.One2many('expense.register', 'custom_requisition_id', string='Minor Expenses')
    expense_register_count = fields.Integer(string='Minor Expense Count', compute='_compute_expense_register_count')
    can_create_minor_expense = fields.Boolean(compute='_compute_can_create_minor_expense')
    duplicate_requisition_ids = fields.Many2many(
        'purchase.requisition.custom', compute='_compute_duplicate_requisition_ids', string='Similar Requisitions')

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

    @api.depends('expense_register_ids')
    def _compute_expense_register_count(self):
        """
        Computes the total number of minor expenses linked to this requisition.
        """
        for rec in self:
            if self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_user') or self.env.user.has_group('purchase.group_purchase_user'):
                rec.expense_register_count = len(rec.sudo().expense_register_ids)
            else:
                rec.expense_register_count = 0

    @api.depends('comments')
    def _compute_has_legacy_comments(self):
        """
        The legacy HTML comments are only shown when they hold real content,
        ignoring empty editor markup such as '<p><br></p>'.
        """
        for rec in self:
            rec.has_legacy_comments = not is_html_empty(rec.comments)

    @api.model
    def _default_department_id(self):
        """
        Defaults to the user's department when they belong to exactly one.
        """
        departments = self.env['purchase.requisition.department'].search([('user_ids', 'in', self.env.uid)], limit=2)
        return departments if len(departments) == 1 else False

    @api.depends_context('uid')
    def _compute_allowed_department_ids(self):
        """
        Departments selectable on the requisition: all of them for Purchase
        Managers, otherwise only those the user belongs to.
        """
        Department = self.env['purchase.requisition.department']
        if self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_manager'):
            departments = Department.search([])
        else:
            departments = Department.search([('user_ids', 'in', self.env.uid)])
        for rec in self:
            rec.allowed_department_ids = departments

    @api.depends('department_id.allow_minor_expense')
    @api.depends_context('uid')
    def _compute_can_create_minor_expense(self):
        """
        A Minor Expense can only be created on requisitions whose department
        allows it, by a Purchase Manager who is also a member of the
        minor_expenses module's basic expense register group.
        """
        can_create = (
            self.env.user.has_group('purchase.group_purchase_manager')
            and self.env.user.has_group('minor_expenses.group_expense_register_user')
        )
        for rec in self:
            rec.can_create_minor_expense = can_create and rec.department_id.allow_minor_expense

    @api.model
    def _normalize_text(self, text):
        """
        Lowercases the text, strips accents and collapses whitespace.
        """
        text = unicodedata.normalize('NFKD', text or '')
        text = ''.join(char for char in text if not unicodedata.combining(char))
        return ' '.join(text.lower().split())

    @api.model
    def _is_similar_text(self, text_a, text_b):
        """
        Two texts are similar when, once normalized, one contains the other or
        they are close enough (difflib ratio >= SIMILARITY_RATIO).
        """
        text_a, text_b = self._normalize_text(text_a), self._normalize_text(text_b)
        if len(text_a) < MIN_SIMILAR_TEXT_LENGTH or len(text_b) < MIN_SIMILAR_TEXT_LENGTH:
            return False
        if text_a in text_b or text_b in text_a:
            return True
        return difflib.SequenceMatcher(None, text_a, text_b).ratio() >= SIMILARITY_RATIO

    @api.depends('state', 'department_id', 'requisition_name', 'vehicle_id', 'line_ids.product_id', 'line_ids.name')
    def _compute_duplicate_requisition_ids(self):
        """
        Draft requisitions of the same department that look like this one, to
        warn about possible duplicates while it is being filled. A candidate
        matches on any of: similar purchase reference, same vehicle, a shared
        product or a similar line description. Searched without sudo: the
        "own or department" rule already shows the whole department.
        """
        drafts_by_department = {}
        for rec in self:
            if rec.state != 'draft' or not rec.department_id:
                rec.duplicate_requisition_ids = False
                continue
            department = rec.department_id._origin
            if department.id not in drafts_by_department:
                drafts_by_department[department.id] = self.search([
                    ('state', '=', 'draft'),
                    ('department_id', '=', department.id),
                ])
            candidates = drafts_by_department[department.id].filtered(lambda r: r.id != rec._origin.id)
            products = rec.line_ids.product_id._origin
            descriptions = [name for name in rec.line_ids.mapped('name') if name]
            rec.duplicate_requisition_ids = candidates.filtered(lambda candidate: (
                self._is_similar_text(rec.requisition_name, candidate.requisition_name)
                or (rec.vehicle_id and rec.vehicle_id._origin == candidate.vehicle_id)
                or (products & candidate.line_ids.product_id)
                or any(
                    self._is_similar_text(description, candidate_name)
                    for description in descriptions
                    for candidate_name in candidate.line_ids.mapped('name')
                )
            ))

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

    def action_view_expense_registers(self):
        """
        Returns a dictionary representing an action to open the tree/form view
        of the minor expenses associated with this requisition.
        """
        self.ensure_one()
        return {
            'name': _('Minor Expenses'),
            'type': 'ir.actions.act_window',
            'res_model': 'expense.register',
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

    @api.constrains('department_id', 'rubro_id')
    def _check_rubro_required(self):
        """
        Ensures that a rubro is provided if the selected department needs one.
        Raises a ValidationError if the condition is not met.
        """
        for rec in self:
            if rec.department_id.need_rubro and not rec.rubro_id:
                raise ValidationError(_("Rubro is mandatory for the selected Department."))

    @api.constrains('department_id')
    def _check_lines_payment_method_required(self):
        """
        Ensures the existing lines have a payment method when the requisition
        moves to a department that needs one.
        """
        self.line_ids._check_payment_method_required()

    @api.onchange('department_id')
    def _onchange_department_id(self):
        """
        Clears the rubro when the selected department does not need one
        (the field is hidden in that case) or does not include it among its
        rubros, and warns when the department needs a rubro but has none
        configured, since none can be selected.
        """
        department = self.department_id
        if not department.need_rubro or self.rubro_id not in department.rubro_ids:
            self.rubro_id = False
        if department.need_rubro and not department.rubro_ids:
            return {'warning': {
                'title': _("Warning"),
                'message': _("The selected Department has no Rubros configured. Ask an administrator to configure them in Purchase > Configuration > Departments."),
            }}

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

