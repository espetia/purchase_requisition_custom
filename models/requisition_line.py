import os

from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.tools.misc import formatLang

ALLOWED_ATTACHED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.pdf', '.xls', '.xlsx')
# keep in sync with the 'max_file_size_mb' option of the attached and support_file fields in the views
MAX_ATTACHED_SIZE_MB = 2
# editable fields logged in the requisition's chatter, in display order
TRACKED_LINE_FIELDS = (
    'product_id', 'name', 'product_qty', 'product_uom_id', 'attached', 'supplier_suggestion', 'need_invoice',
    'payment_method_id', 'payment_import', 'comment', 'consult_list_id', 'support_file',
)
# binary fields and the field holding their file name
FILE_FIELDS = {'attached': 'attached_filename', 'support_file': 'support_filename'}

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
    attached = fields.Binary(string='Attached', attachment=True, required=True)
    attached_filename = fields.Char(string='Attached Filename')
    supplier_suggestion = fields.Char(string='Supplier Suggestion')
    need_invoice = fields.Boolean(string='Need Invoice', default=False)
    payment_method_id = fields.Many2one('purchase.requisition.payment.method', string='Payment Method')
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id')
    payment_import = fields.Monetary(string='Payment Amount', currency_field='currency_id')
    comment = fields.Text(string='Comment')
    consult_list_id = fields.Many2one('purchase.requisition.consult.list', string='Consult List', required=True)
    support_file = fields.Binary(string='Support File', attachment=True, required=True)
    support_filename = fields.Char(string='Support Filename')

    @api.model_create_multi
    def create(self, vals_list):
        requisition_ids = [vals['requisition_id'] for vals in vals_list if vals.get('requisition_id')]
        self.env['purchase.requisition.custom'].browse(requisition_ids)._check_lines_editable()
        lines = super().create(vals_list)
        if not self.env.context.get('skip_line_tracking'):
            lines._log_line_changes([(line.requisition_id, line._get_added_fragment()) for line in lines])
        return lines

    def write(self, vals):
        self.requisition_id._check_lines_editable()
        moved = self.browse()
        if 'requisition_id' in vals:
            self.env['purchase.requisition.custom'].browse(vals['requisition_id'])._check_lines_editable()
            moved = self.filtered(lambda line: line.requisition_id.id != vals['requisition_id'])
        # the wizards only write po_line_id / expense_register_id, which are not tracked
        tracked = [field for field in TRACKED_LINE_FIELDS if field in vals or FILE_FIELDS.get(field) in vals]
        if not (tracked or moved) or self.env.context.get('skip_line_tracking'):
            return super().write(vals)
        # a line moved to another requisition is logged as removed from the old one and added to the new one,
        # where the other changes of the same write are logged too
        entries = [(line.requisition_id, line._get_removed_fragment()) for line in moved]
        before = self._get_tracking_snapshot(tracked)
        res = super().write(vals)
        after = self._get_tracking_snapshot(tracked)
        entries += [(line.requisition_id, line._get_added_fragment()) for line in moved]
        for line in self:
            changes = []
            for field in tracked:
                old, new = before[line.id][field], after[line.id][field]
                # the web client may send back values that did not change
                if old == new:
                    continue
                if field in FILE_FIELDS and old[0] == new[0]:
                    value = _("%s (replaced)") % line._format_tracking_value(field, new)
                else:
                    value = Markup("%s &rarr; %s") % (
                        line._format_tracking_value(field, old), line._format_tracking_value(field, new))
                changes.append(Markup("<li>%s: %s</li>") % (self._fields[field]._description_string(self.env), value))
            if changes:
                entries.append((line.requisition_id, Markup(_('Modified: "%s"')) % line.name + Markup("<ul>%s</ul>") % Markup().join(changes)))
        self._log_line_changes(entries)
        return res

    def unlink(self):
        self.requisition_id._check_lines_editable()
        # deleting the requisition removes its lines in SQL (ondelete='cascade'), without calling this method
        entries = []
        if not self.env.context.get('skip_line_tracking'):
            entries = [(line.requisition_id, line._get_removed_fragment()) for line in self]
        # logged once the lines are actually deleted
        res = super().unlink()
        self._log_line_changes(entries)
        return res

    def _get_file_attachments(self, field_names=tuple(FILE_FIELDS)):
        """
        Returns the stored ir.attachment of the given binary fields of the lines.
        """
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_field', 'in', list(field_names)),
            ('res_id', 'in', self.ids),
        ])

    def _get_tracking_snapshot(self, field_names):
        """
        Returns {line_id: {field: value}} with comparable values of the given
        tracked fields. A file is compared by (file name, checksum), read from
        the stored ir.attachment instead of decoding the base64 value.
        """
        file_fields = [field for field in field_names if field in FILE_FIELDS]
        checksums = {}
        if file_fields:
            checksums = {
                (attachment.res_id, attachment.res_field): attachment.checksum
                for attachment in self._get_file_attachments(file_fields)
            }
        snapshot = {}
        for line in self:
            snapshot[line.id] = {
                field: (line[FILE_FIELDS[field]] or False, checksums.get((line.id, field), False))
                if field in FILE_FIELDS else line[field] or False
                for field in field_names
            }
        return snapshot

    def _format_tracking_value(self, field_name, value):
        """
        Returns the text shown in the chatter for a value of a tracked field
        (as returned by _get_tracking_snapshot).
        """
        self.ensure_one()
        field = self._fields[field_name]
        if field_name in FILE_FIELDS:
            value = value[0]
        elif field.type == 'boolean':
            return _("Yes") if value else _("No")
        elif field.type == 'float':
            return formatLang(self.env, value or 0.0, dp='Product Unit of Measure')
        elif field.type == 'monetary':
            return formatLang(self.env, value or 0.0, currency_obj=self.currency_id)
        elif field.type == 'many2one':
            # the user may not be allowed to read the old value (e.g. another company's product)
            value = value and value.sudo().display_name
        return value or '\u2014'

    def _get_added_fragment(self):
        self.ensure_one()
        return Markup(_('Added: "%s" (%s %s)')) % (
            self.name, self._format_tracking_value('product_qty', self.product_qty), self.product_uom_id.sudo().display_name)

    def _get_removed_fragment(self):
        self.ensure_one()
        return Markup(_('Removed: "%s"')) % self.name

    def _log_line_changes(self, entries):
        """
        Logs changes of lines, given as [(requisition, fragment)], in the
        chatter of their requisitions. While a requisition is being saved, they
        are collected in its 'line_tracking_buffer' context dict
        ({requisition_id: [fragments]}), so it posts one note per save;
        otherwise (a direct create/write/unlink of lines) one note per
        requisition is posted at once.
        """
        buffer = self.env.context.get('line_tracking_buffer')
        # a closed buffer belongs to a save that is already over
        if buffer is not None and buffer.closed:
            buffer = None
        changes = {} if buffer is None else buffer
        for requisition, fragment in entries:
            if requisition:
                changes.setdefault(requisition.id, []).append(fragment)
        if buffer is None:
            self.env['purchase.requisition.custom'].browse(list(changes))._post_line_changes(changes)

    @api.depends_context('company')
    def _compute_currency_id(self):
        """
        Uses the current company's currency for the payment amount.
        """
        for line in self:
            line.currency_id = self.env.company.currency_id

    @api.constrains('payment_method_id', 'requisition_id')
    def _check_payment_method_required(self):
        """
        Ensures that a payment method is provided if the requisition's
        department needs one.
        Raises a ValidationError if the condition is not met.
        """
        for line in self:
            if line.requisition_id.department_id.need_payment_method and not line.payment_method_id:
                raise ValidationError(_("Payment Method is mandatory for the selected Department."))

    @api.constrains('attached', 'support_file', 'name')
    def _check_required_files(self):
        """
        Ensures every line has an attached file and a support file. The view
        already marks both fields as required, but attachment-stored binaries
        have no database column, so neither the ORM nor PostgreSQL enforce
        required=True. 'name' (required, always written on create) makes the
        check also run when a line is created without the files.
        """
        for line in self:
            if not line.attached:
                raise ValidationError(_('Line "%s" must have an attached file.', line.name))
            if not line.support_file:
                raise ValidationError(_('Line "%s" must have a support file.', line.name))

    @api.constrains('attached_filename', 'support_filename')
    def _check_attached_extension(self):
        """
        Ensures the attached and support files are images, PDF or Excel files.
        Raises a ValidationError if the condition is not met.
        """
        for line in self:
            for filename in (line.attached_filename, line.support_filename):
                if filename and os.path.splitext(filename)[1].lower() not in ALLOWED_ATTACHED_EXTENSIONS:
                    raise ValidationError(_("Attached file must be an image, PDF or Excel file."))

    @api.constrains('attached', 'support_file')
    def _check_attached_size(self):
        """
        Ensures the attached and support files do not exceed MAX_ATTACHED_SIZE_MB.
        The size is read from the stored ir.attachment instead of decoding
        the base64 value.
        """
        attachments = self._get_file_attachments()
        max_size = MAX_ATTACHED_SIZE_MB * 1024 * 1024
        if any(attachment.file_size > max_size for attachment in attachments):
            raise ValidationError(_("The attached file cannot exceed %s MB.") % MAX_ATTACHED_SIZE_MB)
