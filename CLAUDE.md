# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`purchase_requisition_custom` is a custom Odoo 15 addon (not a standalone app) that adds an internal
"Purchase Requisition" pre-approval layer in front of Odoo's native Purchase Orders. Basic users submit
requisitions; Purchase Managers/Warehouse Agents convert approved lines into real `purchase.order` records
via a wizard — or, alternatively, relate lines to a Minor Expense (petty-cash) record from the `minor_expenses`
addon via a second wizard. It depends on `base`, `hr` (for the employee job title shown next to users),
`purchase`, `purchase_requisition` (Odoo's native agreements module), `mail`, `fleet`, and `minor_expenses`.

This repo (`/home/espetia/dev/odoo15/addons/purchase_requisition_custom`) is only this one addon. The Odoo
instance lives one level up at `/home/espetia/dev/odoo15`, which runs via `docker-compose.yml` (Postgres 13 +
`odoo:15.0` image, addons bind-mounted from `../addons` to `/mnt/extra-addons`).

## Running / installing the module

There is no build step, linter config, or test suite in this addon — it is Python/XML plus a few static
JS/SCSS/QWeb assets (see "Frontend assets"), all loaded by the Odoo server at runtime. The dev database is
named `odoo`.

```bash
# from /home/espetia/dev/odoo15
docker-compose up -d                      # start Postgres + Odoo
docker-compose logs -f web                # tail server/module logs

# install or upgrade this module (from the host, exec into the running container)
docker-compose exec web odoo -d <dbname> -u purchase_requisition_custom --stop-after-init
```

After editing Python model files, an `-u purchase_requisition_custom` restart (or Apps > Update) is required
for changes to take effect; after editing only XML views/data, the same upgrade applies the record updates.

When a field's `string` changes (and `i18n/es_MX.po` with it), a plain `-u` does **not** replace the existing
es_MX label translation — Odoo 15 keeps the old row, so the UI keeps showing the old Spanish label. Upgrade with
`--i18n-overwrite` (or Settings > Translations > Load a Translation with "Overwrite Existing Terms") in every
database the module is deployed to.

### Verifying changes (no automated tests)

There are no automated tests in this module — verify changes manually through the UI (requisition form,
kanban, PO generation wizard) after upgrading. Server-side behavior (constraints, computes, `name_get`,
translations, asset bundles) can be checked without a browser through `odoo shell`, rolling back at the end so
the dev data is untouched:

```bash
# from /home/espetia/dev/odoo15
docker-compose exec -T web odoo shell -d odoo --no-http --log-level=error <<'EOF'
line = env['purchase.requisition.line.custom'].search([], limit=1)
print(line.currency_id.name)
env.cr.rollback()
EOF
```

- Field labels per language: `Model.with_context(lang='es_MX').fields_get([...])`; translated view text:
  `fields_view_get(view_id, 'form')['arch']` (non-ASCII comes back as XML entities, e.g. `&#xED;`).
- Asset bundles: `env['ir.qweb']._get_asset_content('web.assets_backend')` +
  `odoo.addons.base.models.assetsbundle.AssetsBundle(...).css()/.js()` (compiles the SCSS);
  QWeb templates via `env['ir.asset']._get_asset_paths(bundle='web.assets_qweb', xml=True)`.
- Static checks: the host has no `msgfmt`/`node`, so validate the `.po` with babel inside the Odoo image
  (`docker run --rm -v $PWD/i18n:/i odoo:15.0 python3 -c "import babel.messages.pofile as p; p.read_po(open('/i/es_MX.po','rb'))"`)
  and JS with `docker run --rm -v $PWD:/m:ro node:18-alpine node --check /m/static/src/js/<file>.js`.

### Editing conventions

- Line endings are mixed: most of the original files (`__manifest__.py`, `data/`, `security/security.xml`,
  `models/requisition*.py`, `rubro.py`, `purchase_order.py`, `views/requisition_views.xml`, the PO wizard) use
  CRLF, while newer files are LF. Check with `file <path>` and preserve each file's existing endings when
  editing; git's "LF will be replaced by CRLF" warnings are just `core.autocrlf` and harmless.
- `i18n/es_MX.po` is maintained by hand (not re-exported): entries are kept roughly alphabetical by `msgid`,
  model-field labels use `#: model:ir.model.fields,field_description:...` references, Python `_()` strings use
  `#: code:addons/purchase_requisition_custom/<path>:0` + `#, python-format`, and JS/QWeb strings additionally
  need `#. openerp-web`. When a `msgid` is shared by several fields, moving one field to a new label means
  removing its reference from the old entry and adding a new entry.

## Architecture

### Core models (`models/`)

- **`purchase.requisition.custom`** (`requisition.py`) — the requisition header. Sequence-generated
  `name` (`PR/00001`, via `ir_sequence_data.xml`), a `state` statusbar
  (`draft → quote → waiting → authorized/cancel → done`), a required `department_id` whose `need_rubro`
  decides whether `rubro_id` (category) is shown and required (view `attrs` + `@api.constrains`), and that
  `rubro_id` can in turn force a `vehicle_id` (fleet) via `requires_vehicle` (same pattern). UI labels differ
  from field names: `name` = "Folio", `requisition_name` = "Purchase Reference", `manager_id` = "Process Area".
  Comments are captured in `text_comment` (plain Text). The old `comments` Html field is kept `readonly` only to
  preserve historical data (it allowed embedded images); the form shows it only when `has_legacy_comments`
  (computed with `odoo.tools.is_html_empty`, so empty editor markup like `<p><br></p>` is hidden).
  Inherits `mail.thread`/`mail.activity.mixin` for chatter.
- **`purchase.requisition.department`** (`department.py`) — department catalog (`name`, `need_rubro`, `rubro_ids` — the rubros the department may use, many2many through
  `purchase_requisition_department_rubro_rel` — `user_ids`, the members, many2many through
  `purchase_requisition_department_user_rel` and limited to requisition users — `need_payment_method`,
  `allow_minor_expense`), under Purchase > Configuration. Membership drives the basic users' record rules
  (see Security groups).
- **`res.users`** (`res_users.py`, `_inherit`) — `name_get()` appends the employee's `job_title`
  ("Carlos Espetia - Compras") only when `show_job_title` is in context; the requisition action and the
  `manager_id` form field set that key. Requires the `hr` dependency.
- **`purchase.requisition.line.custom`** (`requisition_line.py`) — requisition lines. `po_line_id` links a
  line to the `purchase.order.line` it was converted into, once generated; `expense_register_id` links it to
  the `expense.register` it was resolved by instead. These two are mutually exclusive — a line is resolved by
  *either* a PO or a Minor Expense, never both, and both wizards filter/reject lines the other has already
  claimed. `product_id` is labelled "Product/Purchase Type". Lines also carry optional purchasing info:
  `attached` (+ `attached_filename`; `@api.constrains` limit it to image/PDF/Excel extensions and to
  `MAX_ATTACHED_SIZE_MB` = 2 MB, read from the stored `ir.attachment.file_size` — keep that constant in sync with
  the `max_file_size_mb` widget option in the view, which gives the same check client-side),
  `supplier_suggestion`, `need_invoice`, `payment_method_id` (required only when the requisition's department has
  `need_payment_method`: view `attrs` on `parent.need_payment_method` in the line popup, plus `@api.constrains` on
  the line and on the header's `department_id`), `payment_import` (Monetary; `currency_id` is a
  non-stored compute of the company currency), and `comment`. A "Support" section adds a **required**
  `consult_list_id` and an optional `support_file` (+ `support_filename`), which shares the `attached`
  constraints (same extensions and size limit; both `@api.constrains` check the two files). `image` is a legacy field, kept for
  historical data but no longer shown in any view.
- **`purchase.requisition.payment.method`** (`payment_method.py`) — payment methods catalog (`name` only),
  under Purchase > Configuration.
- **`purchase.requisition.consult.list`** (`consult_list.py`) — consult lists catalog (`name` only), under
  Purchase > Configuration; referenced by the required line field `consult_list_id`.
- **`purchase.requisition.rubro`** (`rubro.py`) — simple category catalog; `requires_vehicle` drives the
  constraint on the header.
- **`purchase.order`** (`purchase_order.py`, `_inherit`) — adds `custom_requisition_id` back-link and syncs
  requisition state from PO state changes (see below). `requisition_line_ids` is a non-stored compute of the
  requisition lines converted into *this* PO (`po_line_id.order_id`), restricted with field-level
  `groups='...group_purchase_requisition_user'` because plain purchase users have no access to the line model.
  It feeds the read-only "Requisition Details" page that `views/purchase_order_views.xml` adds to the PO form
  (link to the requisition + lines with their `attached`/`support_file` downloads), shown only when
  `custom_requisition_id` is set. A non-manager Warehouse Agent only sees there the lines of requisitions they
  can see (own or department, line rule).
- **`expense.register`** (`models/expense_register.py`, `_inherit` of `minor_expenses`' own model) — adds
  `custom_requisition_id` back-link, mirroring the `purchase.order` inherit above.

### State machine and permission enforcement (business logic, not just `ir.rule`)

Field-level authorization is enforced in Python `write()` overrides, in addition to the group/record rules
in `security/security.xml` and `security/ir.model.access.csv`:

- `PurchaseRequisitionCustom.write()` blocks any `state` change unless the user is in
  `group_purchase_requisition_warehouse` (implied by the manager group), and blocks leaving `draft` if any
  line lacks a `product_id`.
- `PurchaseOrder.write()` restricts a pure Warehouse Agent (warehouse group but *not* manager group) to only
  editing `date_planned` / `date_invoice_partner` on POs.
- `PurchaseOrder.write()` also **auto-syncs the parent requisition's state** whenever a linked PO's `state`
  changes: if every PO on the requisition is `purchase`/`done` → requisition becomes `authorized`; if every
  PO is `cancel`/`reject` → requisition becomes `cancel`. This uses `sudo()` deliberately so the state
  transition isn't blocked by the same-user's own group check above — when touching this logic, keep the
  `sudo()` (see commit `190fbc5`) rather than removing it to "fix" a permission error.
- `CreateExpenseWizard.action_create_expense()` (see below) is a **second, independent path** to
  `authorized`: relating even one Minor Expense flips the requisition to `authorized` immediately, regardless
  of whether other lines are still unresolved. Unlike the PO-driven sync above, this write is **not**
  `sudo()`'d — the wizard is only reachable by a Purchase Manager, who already passes the `write()` group
  check on their own. There is no reverse sync: cancelling/deleting the `expense.register` afterward does not
  revert the requisition's state.

When modifying access control, changes usually need to land in *three* places at once: the `res.groups` /
`ir.rule` definitions in `security/security.xml`, the CRUD matrix in `security/ir.model.access.csv`, and the
corresponding `write()` guard in the model — they are not redundant, they enforce different things (model
access vs. row visibility vs. field/state-transition rules).

### Security groups (hierarchy, `security/security.xml`)

`group_purchase_requisition_user` (basic, own and own-department records) ⊂ `group_purchase_requisition_warehouse`
(can change requisition state, limited PO field edits) ⊂ `group_purchase_requisition_manager` (implies
native `purchase.group_purchase_manager`, full CRUD everywhere, generates POs). Record rules restrict basic
users to requisitions they requested **or** whose department they belong to
(`['|', ('requester_id', '=', user.id), ('department_id.user_ids', 'in', [user.id])]`, with full read/write on both);
managers see all. Requisition lines have the matching pair (`rule_purchase_requisition_line_own`: the same domain
through `requisition_id.`; `_line_all` for managers) — these also protect the line `attached`/`support_file` files,
since `/web/content` only serves a field attachment after a read check on the line. Rules of different groups
add up, so a Warehouse Agent who isn't a manager falls under these "own or department" rules too. The xml ids
keep the historical `_own` suffix.

Two more `ir.rule`s here govern `expense.register` (a model owned by `minor_expenses`, not this addon) for
requisition-linked records specifically: `rule_expense_register_requisition_user` scopes basic users to
expenses on requisitions they can see (same own-or-department domain through `custom_requisition_id.`), and
`rule_expense_register_requisition_manager` lets any Purchase Manager see all requisition-linked expenses
(`custom_requisition_id != False`) regardless of who created them — this exists because `minor_expenses`'
own native rule restricts a record to its `user_id`, which would otherwise hide one manager's Minor Expense
from another manager viewing the same requisition. Deliberately, `group_purchase_requisition_manager` does
**not** imply `minor_expenses.group_expense_register_user`/`_admin` — see the wizard note above for why.

The four configuration catalogs (`rubro`, `department`, `payment.method`, `consult.list`) all follow the same access pattern
in `ir.model.access.csv`: basic users read-only, managers full CRUD, no `ir.rule`s. Their tree/form views and
menus live in `views/<catalog>_views.xml` under `purchase.menu_purchase_config` (sequences 100/101/102/103).

### Views (`views/requisition_views.xml`)

- **Requisition action** context sets `show_job_title`, so every `res.users` many2one rendered inside it
  (Process Area, but also Requester, activity assignees) shows "Name - Job Title". The Odoo 15 web client strips
  `show_*` (and `default_*`/`search_default_*`) keys from the context when a button opens another action, so it
  does not leak into the PO / Minor Expense views or the wizards.
- **Lines** are a non-editable `<tree>` (each column has a `width` attribute, which Odoo 15 applies as a
  min-width so columns scroll horizontally instead of truncating) plus an inline `<form>` that opens as a popup
  on click, grouped into Product / Supplier / Payment / Traceability / Support sections and a Comment area. The popup
  inherits the `line_ids` `readonly` attrs, so lines are read-only once the requisition leaves `draft`. The
  wizard line trees (`wizard/*_views.xml`) reuse the line fields and pick up label changes automatically.
- **Header**: `department_id` only offers `allowed_department_ids` (non-stored, per `uid`: all departments for
  Purchase Managers, otherwise the user's own) and defaults to the user's department when they belong to exactly
  one (`_default_department_id`). It drives `rubro_id` visibility/required via `need_rubro`, and its selectable values via
  `domain=[('id', 'in', department_rubro_ids)]` (related to the department's `rubro_ids`). This rubro/department
  match is a **view-only** rule (no constraint); `_onchange_department_id` clears a rubro outside the new
  department's list and warns when the department needs a rubro but has none configured; `text_comment` sits below
  the notebook, followed by the read-only legacy `comments` block (only when `has_legacy_comments`).

### PO generation wizard (`wizard/create_po_wizard.py`)

`CreatePoWizard` is opened as a contextual action from a requisition (`default_get` reads `active_id` and
pre-populates only lines with a `product_id` and no `po_line_id` yet — i.e. not already ordered). It has two
flows selected via `action_type`:

Both flows copy the requisition's `requisition_name` into the PO's `partner_ref` (Vendor Reference), and build
every PO line through `_prepare_po_line_vals()`, which also carries the requisition's `vehicle_id` onto
`purchase.order.line.vehicle_id`. That field belongs to the `purchase_custom` addon, which is **not** a dependency
of this one, so it is only set when present in `_fields`.

- **`create_po`** — creates one `purchase.order` directly, one `purchase.order.line` per selected requisition
  line, and stamps `po_line_id` back onto each source line.
- **`create_pr`** — creates a native `purchase.requisition` (Odoo's own agreements model) plus one
  `purchase.order` per selected vendor in `vendor_ids`, replicating lines onto each PO; only the *first*
  vendor's PO lines get `po_line_id` back-linked (the others remain competing quotes under the same
  agreement, so their "Requisition Details" page shows the requisition link but no lines). Immediately calls `pr.action_in_progress()` to confirm the native requisition.

Both flows flip the custom requisition's `state` to `waiting` once every one of its lines has a `po_line_id`.

### Minor Expense wizard (`wizard/create_expense_wizard.py`)

`CreateExpenseWizard` is the alternative to the PO wizard: opened the same way (contextual action reading
`active_id`/`active_model`), it lets a Purchase Manager select one or more requisition lines (`default_get`
excludes lines with a `po_line_id` **or** an `expense_register_id` already set) and relate them all to a
single new `expense.register` record (`type='minor_casher'`, `apply_on='provider_invoice'`). Every field
`expense.register` requires (vendor, concept, product, amount, area/analytic account, payment journal,
description) is captured manually in the wizard form — it is *not* derived from the selected lines, since a
single Minor Expense can bundle lines with different products. `action_create_expense()`:

1. Re-validates server-side (not just via the view domain) that the requisition's department has
   `allow_minor_expense` and that no selected line already has a `po_line_id` or `expense_register_id` —
   raises `UserError` otherwise.
2. Replicates `expense.register`'s own fund-lookup onchange manually (`expense.fund` search by
   `manager_ids`), since `create()` never fires onchanges.
3. Creates the `expense.register` with `custom_requisition_id` set, stamps `expense_register_id` back onto
   every selected line, then writes `state='authorized'` on the requisition (see state machine notes above).

The wizard's `user_id` field ("Employee") is fixed to the acting manager and not editable — this is
deliberate, not an oversight: `minor_expenses` has its own `ir.rule`s scoped to `user_id = user.id` (and an
equivalent rule on `expense.fund` via `manager_ids`), so keeping `user_id` as the acting user is what lets the
whole flow work without `sudo()` anywhere. Making it editable would let a manager create a record they can no
longer read back.

The "Create Minor Expense" button on the requisition form (`views/requisition_views.xml`) is only visible
when the computed field `can_create_minor_expense` is `True`, which requires the department's
`allow_minor_expense` **and both** `purchase.group_purchase_manager` and
`minor_expenses.group_expense_register_user` — the view's `groups`
attribute can't express an AND condition, so this is a Python compute checked via `attrs`, mirroring the
existing `is_warehouse_agent_only` compute pattern in `purchase_order.py`. Membership in the `minor_expenses`
group is **not** granted automatically (no `implied_ids` link) — it must be assigned to a Purchase Manager
separately by whoever administers users/groups. The "Minor Expenses" page is likewise hidden whenever the
department doesn't have `allow_minor_expense`, even if expenses are already linked (the "Minor Expenses" stat
button, shown only when the count is > 0, still reaches them).

### Frontend assets (`static/src/`)

The module ships one legacy (Odoo 15, non-OWL) field widget, `binary_dropzone`
(`static/src/js/binary_dropzone.js` + `xml/` template + `scss/`), registered in `__manifest__.py` `assets`
(`web.assets_backend` / `web.assets_qweb`). It extends the native `FieldBinaryFile` and adds a drop area plus
Ctrl+V paste (document-level listener, active only while the widget is editable, empty and in the topmost dialog,
and ignored while the focus is in an input/textarea/contenteditable — copying from Excel/Word also puts a PNG in
the clipboard, so pasting text must stay text). Clicking the drop area only focuses it (ready to paste; the
dialog autofocuses its first input); the file picker is the area's "Select a file" button. Every
dropped/pasted `File` goes through the native upload flow (`on_file_uploaded`), so value/filename handling is
Odoo's own. Supported `options`: `accepted_file_extensions` (native) and `max_file_size_mb`, which lowers
`max_upload_size` and therefore also applies to the native file-picker path. Files dropped outside the drop
area are swallowed (`preventDefault`) so the browser doesn't navigate away and lose unsaved changes. Since every
widget listens on `document`, `_isPasteTarget()` makes sure only one empty drop area takes a paste: the focused one,
or else the first visible one in the same dialog. Used on the requisition line popup form for `attached` and
`support_file`; the read-only list columns keep the plain `binary` widget.
Translatable JS/QWeb strings in
`i18n/es_MX.po` need the `#. openerp-web` comment to reach the web client. After changing assets, browsers need a
hard refresh (or `?debug=assets`).

### Automation (`data/`)

- `ir_sequence_data.xml` defines the `purchase.requisition.custom` sequence (`PR/00001`).
- `cron_data.xml` runs `_cron_send_draft_requisitions_reminder` daily at 14:00, which groups all `draft`
  requisitions by `manager_id` and sends **one** consolidated email per manager (not one per requisition)
  via `mail_template_data.xml`'s `email_template_draft_requisitions_reminder`. The same template is also
  fired synchronously on `create()` for the single new requisition's manager.

### Migrations (`migrations/`)

Data fixes for existing databases go in `migrations/<version>/{pre,post}-*.py` and only run when
`__manifest__.py`'s `version` is bumped past the installed one (never on a fresh install).
`15.0.1.1.0/post-migrate.py` gives requisitions created before `department_id` existed a default "General"
department (`need_rubro=True`, since `rubro_id` used to be required) and then enforces `NOT NULL`, which Odoo
itself could not apply during the upgrade. Making a field `required=True` on a table with existing rows needs
the same treatment, otherwise those records can't be saved from the form. `15.0.1.2.0/post-migrate.py` does the
same for the required line field `consult_list_id` (default "General" consult list).
