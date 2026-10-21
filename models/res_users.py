from odoo import models, api

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.depends(lambda self: (self._rec_name,) if self._rec_name else ())
    @api.depends_context('show_job_title')
    def _compute_display_name(self):
        """
        Keeps the cached display_name separated per 'show_job_title' context,
        so the job title suffix never leaks into other views.
        """
        return super(ResUsers, self)._compute_display_name()

    def name_get(self):
        """
        Appends the related employee's job title to the user's name
        (e.g. "Carlos Espetia - Compras") when 'show_job_title' is in context.
        """
        res = super(ResUsers, self).name_get()
        if not self.env.context.get('show_job_title'):
            return res
        job_titles = {user.id: user.sudo().employee_id.job_title for user in self}
        return [
            (user_id, '%s - %s' % (name, job_titles[user_id]) if job_titles.get(user_id) else name)
            for user_id, name in res
        ]
