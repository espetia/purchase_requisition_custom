import os

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

ALLOWED_ATTACHED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.xls', '.xlsx')
# keep in sync with the 'max_file_size_mb' option of the attached field in the views
MAX_ATTACHED_SIZE_MB = 2

class PurchaseRequisitionLineCustom(models.Model):
    _name = 'purchase.requisition.line.custom'
    _description = 'Purchase Requisition Line Custom'

    requisition_id = fields.Many2one('purchase.requisition.custom', string='Requisition', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product/Purchase Type', domain=[('purchase_ok', '=', True)])
    name = fields.Char(string='Description', required=True)
    image = fields.Binary(string='Image')
    product_qty = fields.Float(string='Quantity', required=True, default=1.0)
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    po_line_id = fields.Many2one('purchase.order.line', string='PO Line', readonly=True)
    expense_register_id = fields.Many2one('expense.register', string='Expense Register', readonly=True)
    attached = fields.Binary(string='Attached', attachment=True)
    attached_filename = fields.Char(string='Attached Filename')
    supplier_suggestion = fields.Char(string='Supplier Suggestion')
    need_invoice = fields.Boolean(string='Need Invoice', default=False)
    payment_method_id = fields.Many2one('purchase.requisition.payment.method', string='Payment Method')
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id')
    payment_import = fields.Monetary(string='Payment Amount', currency_field='currency_id')
    comment = fields.Text(string='Comment')

    @api.depends_context('company')
    def _compute_currency_id(self):
        """
        Uses the current company's currency for the payment amount.
        """
        for line in self:
            line.currency_id = self.env.company.currency_id

    @api.constrains('attached_filename')
    def _check_attached_extension(self):
        """
        Ensures the attached file is an image, PDF or Excel file.
        Raises a ValidationError if the condition is not met.
        """
        for line in self:
            if line.attached_filename and os.path.splitext(line.attached_filename)[1].lower() not in ALLOWED_ATTACHED_EXTENSIONS:
                raise ValidationError(_("Attached file must be an image, PDF or Excel file."))

    @api.constrains('attached')
    def _check_attached_size(self):
        """
        Ensures the attached file does not exceed MAX_ATTACHED_SIZE_MB.
        The size is read from the stored ir.attachment instead of decoding
        the base64 value.
        """
        attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_field', '=', 'attached'),
            ('res_id', 'in', self.ids),
        ])
        max_size = MAX_ATTACHED_SIZE_MB * 1024 * 1024
        if any(attachment.file_size > max_size for attachment in attachments):
            raise ValidationError(_("The attached file cannot exceed %s MB.") % MAX_ATTACHED_SIZE_MB)
