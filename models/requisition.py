import difflib
import unicodedata

from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import is_html_empty

# Minimum difflib ratio for two normalized texts to count as similar
# (see PurchaseRequisitionCustom._is_similar_text).
SIMILARITY_RATIO = 0.8
# Shorter normalized texts are too generic to compare.
MIN_SIMILAR_TEXT_LENGTH = 4
# States before quotation: lines may still lack a product (it is only required
# from 'quote' onwards).
PRE_QUOTE_STATES = ('draft', 'preauthorized')
# Business fields that cannot change while the authorization chain is in
# progress: what the approvers approve is what gets purchased.
APPROVAL_LOCKED_FIELDS = (
    'requisition_name', 'requester_id', 'department_id', 'rubro_id', 'manager_id',
    'vehicle_id', 'expiration_date', 'text_comment', 'line_ids',
)

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
        domain=lambda self: self._department_domain(),
    )
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
        ('preauthorized', 'Pre-authorized'),
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
    approval_ids = fields.One2many('purchase.requisition.approval', 'requisition_id', string='Authorizations', readonly=True)
    approval_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Authorization', default='not_sent', required=True, readonly=True, copy=False)
    current_approver_id = fields.Many2one(
        'res.users', string='Current Approver', compute='_compute_current_approver_id', store=True)
    is_current_approver = fields.Boolean(compute='_compute_is_current_approver')
    can_edit_lines = fields.Boolean(compute='_compute_can_edit_lines')
    approval_step = fields.Char(string='Authorization Step', compute='_compute_approval_step')
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

    @api.model
    def _department_domain(self):
        """
        Departments selectable on the requisition: all of them for Purchase
        Managers, otherwise only those the user belongs to. Evaluated for the
        current user whenever the view's fields are loaded (a non-stored
        compute used in a view domain is not recomputed by the form's first
        onchange, so it reached the client empty).
        """
        if self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_manager'):
            return []
        return [('user_ids', 'in', self.env.uid)]

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

    @api.depends('approval_status', 'approval_ids.state', 'approval_ids.user_id')
    def _compute_current_approver_id(self):
        """
        The approver whose turn it is, while the authorization chain is in
        progress.
        """
        for rec in self:
            pending = rec.approval_ids.filtered(lambda a: a.state == 'pending')[:1]
            rec.current_approver_id = pending.user_id if rec.approval_status == 'in_progress' else False

    @api.depends('current_approver_id')
    @api.depends_context('uid')
    def _compute_is_current_approver(self):
        for rec in self:
            rec.is_current_approver = rec.current_approver_id == self.env.user

    @api.depends('state', 'approval_status')
    @api.depends_context('uid')
    def _compute_can_edit_lines(self):
        """
        Lines are editable in draft (outside the authorization chain) and, so
        the products can be completed before quoting, in pre-authorized by
        Warehouse Agents and Purchase Managers. Mirrors _check_lines_editable().
        """
        is_warehouse = self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_warehouse')
        for rec in self:
            rec.can_edit_lines = (
                (rec.state == 'draft' and rec.approval_status != 'in_progress')
                or (rec.state == 'preauthorized' and is_warehouse)
            )

    @api.depends('approval_ids.state')
    def _compute_approval_step(self):
        """
        Progress of the authorization chain, e.g. "2/3" while the second
        approver has to act.
        """
        for rec in self:
            approvals = rec.approval_ids
            if not approvals:
                rec.approval_step = False
                continue
            done = len(approvals.filtered(lambda a: a.state == 'approved'))
            current = done + 1 if rec.approval_status == 'in_progress' else done
            rec.approval_step = '%s/%s' % (current, len(approvals))

    def _send_approval_template(self, xmlid, **ctx):
        """
        Queues one of the authorization chain e-mails (see
        data/mail_template_data.xml). The recipients are resolved by the
        template itself. The e-mail is kept off the requisition's thread (the
        chatter already logs every authorization action).
        """
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if template:
            for rec in self:
                template.sudo().with_context(**ctx).send_mail(
                    rec.id, force_send=False, email_values={'model': False, 'res_id': False})

    def _post_approval_message(self, body):
        """
        Logs an authorization action in the chatter, authored by the acting
        user. Approvers may only have read access to the requisition, so the
        message is posted with sudo.
        """
        self.sudo().message_post(body=body, author_id=self.env.user.partner_id.id, subtype_xmlid='mail.mt_note')

    def _notify_current_approver(self):
        """
        Notifies the approver whose turn it is, by e-mail and with a to-do
        activity.
        """
        for rec in self:
            approver = rec.current_approver_id
            if not approver:
                continue
            rec._send_approval_template('purchase_requisition_custom.email_template_requisition_approval_request')
            rec.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=approver.id,
                summary=_("Authorize requisition"),
            )

    def _check_current_approver(self):
        for rec in self:
            if rec.approval_status != 'in_progress' or not rec.is_current_approver:
                raise UserError(_("Requisition %s is not waiting for your authorization.", rec.name))

    def action_send_for_approval(self):
        """
        Starts the authorization chain configured on the rubro. A requisition
        without rubro, or whose rubro has no chain, is pre-authorized at once.
        Only users who can edit the requisition may send it (approvers only
        have read access to the requisitions they authorize).
        """
        self.check_access_rights('write')
        self.check_access_rule('write')
        for rec in self:
            if rec.state != 'draft' or rec.approval_status not in ('not_sent', 'rejected'):
                raise UserError(_("Only draft requisitions that have not been sent can be sent for authorization."))
            approvers = rec.rubro_id.approver_ids
            rec.sudo().approval_ids.unlink()
            if not approvers:
                rec._post_approval_message(_("Sent for authorization: no authorization chain configured, pre-authorized directly."))
                rec._finish_approval()
                continue
            rec.sudo().write({
                'approval_status': 'in_progress',
                'approval_ids': [(0, 0, {
                    'sequence': index,
                    'user_id': approver.user_id.id,
                    'state': 'pending' if index == 0 else 'waiting',
                }) for index, approver in enumerate(approvers)],
            })
            rec._post_approval_message(Markup(_("Sent for authorization. Waiting for %s (step %s).")) % (
                rec.current_approver_id.name, rec.approval_step))
            rec._notify_current_approver()
        return True

    def action_approve(self):
        """
        Approves the current step and passes the requisition to the next
        approver, or pre-authorizes it when the chain is complete.
        """
        self._check_current_approver()
        for rec in self:
            approvals = rec.sudo().approval_ids
            current = approvals.filtered(lambda a: a.state == 'pending')[:1]
            step = rec.approval_step
            current.write({'state': 'approved', 'date': fields.Datetime.now()})
            rec.sudo().activity_feedback(['mail.mail_activity_data_todo'], user_id=self.env.uid)
            following = approvals.filtered(lambda a: a.state == 'waiting')[:1]
            if following:
                following.write({'state': 'pending'})
                rec._post_approval_message(Markup(_("Approved by %s (step %s). Waiting for %s.")) % (
                    self.env.user.name, step, following.user_id.name))
                rec._notify_current_approver()
            else:
                rec._post_approval_message(Markup(_("Approved by %s (step %s). Authorization chain completed: pre-authorized.")) % (
                    self.env.user.name, step))
                rec._finish_approval()
        return True

    def action_reject(self, reason):
        """
        Rejects the requisition at the current step: it goes back to an
        editable draft and the requester is notified. Sending it again
        restarts the chain from the first approver.
        """
        self._check_current_approver()
        for rec in self:
            current = rec.sudo().approval_ids.filtered(lambda a: a.state == 'pending')[:1]
            current.write({'state': 'rejected', 'date': fields.Datetime.now(), 'comment': reason})
            rec.sudo().activity_unlink(['mail.mail_activity_data_todo'])
            rec.sudo().write({'approval_status': 'rejected'})
            rec._post_approval_message(Markup(_("Rejected by %s: %s")) % (self.env.user.name, reason))
            rec._send_approval_template('purchase_requisition_custom.email_template_requisition_rejected', reason=reason)
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        self._check_current_approver()
        return {
            'name': _("Reject Requisition"),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.requisition.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_requisition_id': self.id},
        }

    def _finish_approval(self):
        """
        Completes the authorization chain: the requisition becomes
        pre-authorized (the only way to reach that state) and the requester is
        notified.
        """
        self.sudo().with_context(approval_chain_done=True).write({
            'approval_status': 'approved',
            'state': 'preauthorized',
        })
        self._send_approval_template('purchase_requisition_custom.email_template_requisition_preauthorized')

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
        Overrides the write method to prevent non-managers from updating the
        state, to keep the authorization chain as the only way out of draft,
        and to lock the requisition while the chain is in progress.
        """
        chain_done = self.env.context.get('approval_chain_done')
        if 'state' in vals: 
            if not self.env.su and not self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_warehouse'):
                raise ValidationError(_("Only Purchase Managers can update the status of a requisition."))
            for rec in self:
                if rec.state in PRE_QUOTE_STATES and vals['state'] not in PRE_QUOTE_STATES + ('cancel',):
                    if any(not line.product_id for line in rec.line_ids):
                        raise ValidationError(_("A requisition cannot move to quotation or later stages while it has lines without a product."))
                if not chain_done and rec.state != vals['state']:
                    if rec.state == 'draft' and vals['state'] != 'cancel':
                        raise ValidationError(_("A requisition can only leave the draft state through its authorization chain."))
                    if vals['state'] == 'preauthorized' and rec.approval_status != 'approved':
                        raise ValidationError(_("Only a completed authorization chain can pre-authorize a requisition."))
            if vals['state'] in ('draft', 'cancel') and not chain_done:
                # going back to draft (or cancelling) restarts the authorization chain
                to_reset = self.filtered(lambda r: r.state != vals['state'] and r.approval_status != 'not_sent')
                if to_reset:
                    to_reset.sudo().activity_unlink(['mail.mail_activity_data_todo'])
                    super(PurchaseRequisitionCustom, to_reset).write({'approval_status': 'not_sent'})
        if any(field in vals for field in APPROVAL_LOCKED_FIELDS):
            self._check_not_in_approval()
        return super(PurchaseRequisitionCustom, self).write(vals)

    def _check_not_in_approval(self):
        """
        Raises when a requisition is waiting on its authorization chain, during
        which it cannot be modified.
        """
        in_approval = self.filtered(lambda r: r.approval_status == 'in_progress')
        if in_approval:
            raise ValidationError(_(
                "Requisition %s is waiting for authorization and cannot be modified. "
                "It can be changed again once it is rejected.", in_approval[0].name))

    def _check_lines_editable(self):
        """
        Raises when the lines of these requisitions cannot be modified: during
        the authorization chain, or in pre-authorized by anyone but Warehouse
        Agents and Purchase Managers.
        """
        self._check_not_in_approval()
        if self.env.su or self.env.user.has_group('purchase_requisition_custom.group_purchase_requisition_warehouse'):
            return
        preauthorized = self.filtered(lambda r: r.state == 'preauthorized')
        if preauthorized:
            raise ValidationError(_(
                "Only Warehouse Agents and Purchase Managers can modify the lines of the "
                "pre-authorized requisition %s.", preauthorized[0].name))

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

