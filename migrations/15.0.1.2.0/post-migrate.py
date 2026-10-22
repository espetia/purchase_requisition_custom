import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    consult_list_id became required on purchase.requisition.line.custom, but
    lines created before it have no consult list: PostgreSQL cannot apply
    NOT NULL and those lines can no longer be saved from the form.

    Assign them a default "General" consult list and enforce NOT NULL.
    """
    if not version:
        return
    cr.execute("SELECT COUNT(*) FROM purchase_requisition_line_custom WHERE consult_list_id IS NULL")
    missing = cr.fetchone()[0]
    if missing:
        env = api.Environment(cr, SUPERUSER_ID, {})
        ConsultList = env['purchase.requisition.consult.list']
        consult_list = ConsultList.search([('name', '=', 'General')], limit=1) or ConsultList.create({
            'name': 'General',
        })
        cr.execute(
            "UPDATE purchase_requisition_line_custom SET consult_list_id = %s WHERE consult_list_id IS NULL",
            (consult_list.id,),
        )
        _logger.info("Assigned consult list '%s' to %s requisition line(s) without consult list.", consult_list.name, cr.rowcount)
    cr.execute("ALTER TABLE purchase_requisition_line_custom ALTER COLUMN consult_list_id SET NOT NULL")
