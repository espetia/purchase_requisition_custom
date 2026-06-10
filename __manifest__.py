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
    'version': '15.0.1.0.0',
    'depends': ['base', 'purchase', 'purchase_requisition', 'mail', 'fleet'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'data/cron_data.xml',
        'wizard/create_po_wizard_views.xml',
        'views/requisition_views.xml',
        'views/rubro_views.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
