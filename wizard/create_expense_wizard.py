from odoo import models, fields, api, exceptions, _


class CreateExpenseWizard(models.TransientModel):
    _name = 'create.expense.wizard'
    _description = 'Create Minor Expense Wizard'

    requisition_id = fields.Many2one('purchase.requisition.custom', string='Requisition', required=True)
    line_ids = fields.Many2many('purchase.requisition.line.custom', string='Lines to Expense')

    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    concept = fields.Char(string='Concept', required=True)
    description = fields.Char(string='Description', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    depto_id = fields.Many2one('account.analytic.account', string='Area', required=True)
    payment_journal_id = fields.Many2one(
        'account.journal', string='Payment Journal',
        domain="[('type', 'in', ('bank', 'cash'))]", required=True
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )
    amount = fields.Monetary(string='Amount', required=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    fortnight = fields.Selection(
        [('q1', 'Q1'), ('q2', 'Q2')], string='Fortnight', required=True,
        default=lambda self: 'q1' if fields.Date.context_today(self).day <= 15 else 'q2'
    )
    user_id = fields.Many2one(
        'res.users', string='Employee', required=True, readonly=True,
        default=lambda self: self.env.user
    )

    @api.model
    def default_get(self, fields_list):
        res = super(CreateExpenseWizard, self).default_get(fields_list)
        req_id = self.env.context.get('active_id')
        if req_id and self.env.context.get('active_model') == 'purchase.requisition.custom':
            requisition = self.env['purchase.requisition.custom'].browse(req_id)
            res['requisition_id'] = req_id
            res['vehicle_id'] = requisition.vehicle_id.id
            lines = self.env['purchase.requisition.line.custom'].search([
                ('requisition_id', '=', req_id),
                ('product_id', '!=', False),
                ('po_line_id', '=', False),
                ('expense_register_id', '=', False),
            ])
            res['line_ids'] = [(6, 0, lines.ids)]
        return res

    def action_create_expense(self):
        self.ensure_one()

        if not self.line_ids:
            raise exceptions.UserError(_('Please select at least one line to expense.'))

        for line in self.line_ids:
            if line.po_line_id or line.expense_register_id:
                raise exceptions.UserError(
                    _('Line "%s" is already resolved by a Purchase Order or Minor Expense.') % line.name
                )

        fund = self.env['expense.fund'].search([('manager_ids', 'in', self.user_id.id)], limit=1)

        expense = self.env['expense.register'].create({
            'type': 'minor_casher',
            'apply_on': 'provider_invoice',
            'date': self.date,
            'fortnight': self.fortnight,
            'partner_id': self.partner_id.id,
            'concept': self.concept,
            'description': self.description,
            'product_id': self.product_id.id,
            'vehicle_id': self.vehicle_id.id,
            'depto_id': self.depto_id.id,
            'payment_journal_id': self.payment_journal_id.id,
            'user_id': self.user_id.id,
            'currency_id': self.currency_id.id,
            'amount': self.amount,
            'fund_id': fund.id if fund else False,
            'custom_requisition_id': self.requisition_id.id,
        })

        self.line_ids.write({'expense_register_id': expense.id})
        self.requisition_id.write({'state': 'authorized'})

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'expense.register',
            'view_mode': 'form',
            'res_id': expense.id,
        }
