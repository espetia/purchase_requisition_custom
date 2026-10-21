import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    department_id became required on purchase.requisition.custom, but
    requisitions created before it have no department: PostgreSQL cannot
    apply NOT NULL and those records can no longer be saved from the form.

    Assign them a default "General" department (need_rubro=True, since
    rubro_id was mandatory before, so every existing requisition has one)
    and enforce NOT NULL.
    """
    if not version:
        return
    cr.execute("SELECT COUNT(*) FROM purchase_requisition_custom WHERE department_id IS NULL")
    missing = cr.fetchone()[0]
    if missing:
        env = api.Environment(cr, SUPERUSER_ID, {})
        Department = env['purchase.requisition.department']
        department = Department.search([('name', '=', 'General')], limit=1) or Department.create({
            'name': 'General',
            'need_rubro': True,
        })
        cr.execute(
            "UPDATE purchase_requisition_custom SET department_id = %s WHERE department_id IS NULL",
            (department.id,),
        )
        _logger.info("Assigned department '%s' to %s requisition(s) without department.", department.name, cr.rowcount)
    cr.execute("ALTER TABLE purchase_requisition_custom ALTER COLUMN department_id SET NOT NULL")
