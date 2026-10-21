# -*- coding: utf-8 -*-
{
    'name': "Purchase Requisition Custom",
    'summary': "Purchase custom module",
    'description': """
        Purchase custom module for san_mex
    """,
    'author': "Carlos Espetia",
    'website': "http://www.carlosespetia.com",
    'category': 'Uncategorized',
    'version': '15.0.1.1.0',
    'depends': ['base', 'hr', 'purchase', 'purchase_requisition', 'mail', 'fleet', 'minor_expenses'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'data/cron_data.xml',
        'wizard/create_po_wizard_views.xml',
        'wizard/create_expense_wizard_views.xml',
        'views/requisition_views.xml',
        'views/rubro_views.xml',
        'views/department_views.xml',
        'views/payment_method_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'purchase_requisition_custom/static/src/js/binary_dropzone.js',
            'purchase_requisition_custom/static/src/scss/binary_dropzone.scss',
        ],
        'web.assets_qweb': [
            'purchase_requisition_custom/static/src/xml/binary_dropzone.xml',
        ],
    },
    'demo': [
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
