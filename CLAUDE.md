# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`purchase_requisition_custom` is a custom Odoo 15 addon (not a standalone app) that adds an internal
"Purchase Requisition" pre-approval layer in front of Odoo's native Purchase Orders. Basic users submit
requisitions; Purchase Managers/Warehouse Agents convert approved lines into real `purchase.order` records
via a wizard. It depends on `base`, `purchase`, `purchase_requisition` (Odoo's native agreements module),
`mail`, and `fleet`.

This repo (`/home/espetia/dev/odoo15/addons/purchase_requisition_custom`) is only this one addon. The Odoo
instance lives one level up at `/home/espetia/dev/odoo15`, which runs via `docker-compose.yml` (Postgres 13 +
`odoo:15.0` image, addons bind-mounted from `../addons` to `/mnt/extra-addons`).

## Running / installing the module

There is no build step, linter config, or test suite in this addon — it is pure Python/XML loaded by the
Odoo server at runtime.

```bash
# from /home/espetia/dev/odoo15
docker-compose up -d                      # start Postgres + Odoo
docker-compose logs -f web                # tail server/module logs

# install or upgrade this module (from the host, exec into the running container)
docker-compose exec web odoo -d <dbname> -u purchase_requisition_custom --stop-after-init
```

After editing Python model files, an `-u purchase_requisition_custom` restart (or Apps > Update) is required
for changes to take effect; after editing only XML views/data, the same upgrade applies the record updates.
There are no automated tests in this module — verify changes manually through the UI (requisition form,
kanban, PO generation wizard) after upgrading.

## Architecture

### Core models (`models/`)

- **`purchase.requisition.custom`** (`requisition.py`) — the requisition header. Sequence-generated
  `name` (`PR/00001`, via `ir_sequence_data.xml`), a `state` statusbar
  (`draft → quote → waiting → authorized/cancel → done`), and a required `rubro_id` (category) that can
  force a `vehicle_id` (fleet) via `requires_vehicle` (related field + `@api.constrains`). Inherits
  `mail.thread`/`mail.activity.mixin` for chatter.
- **`purchase.requisition.line.custom`** (`requisition_line.py`) — requisition lines. `po_line_id` links a
  line to the `purchase.order.line` it was converted into, once generated; this is the flag used everywhere
  to detect "already ordered" lines.
- **`purchase.requisition.rubro`** (`rubro.py`) — simple category catalog; `requires_vehicle` drives the
  constraint on the header.
- **`purchase.order`** (`purchase_order.py`, `_inherit`) — adds `custom_requisition_id` back-link and syncs
  requisition state from PO state changes (see below).

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

When modifying access control, changes usually need to land in *three* places at once: the `res.groups` /
`ir.rule` definitions in `security/security.xml`, the CRUD matrix in `security/ir.model.access.csv`, and the
corresponding `write()` guard in the model — they are not redundant, they enforce different things (model
access vs. row visibility vs. field/state-transition rules).

### Security groups (hierarchy, `security/security.xml`)

`group_purchase_requisition_user` (basic, own records only) ⊂ `group_purchase_requisition_warehouse`
(can change requisition state, limited PO field edits) ⊂ `group_purchase_requisition_manager` (implies
native `purchase.group_purchase_manager`, full CRUD everywhere, generates POs). Record rules restrict basic
users to `requester_id = user.id`; managers see all.

### PO generation wizard (`wizard/create_po_wizard.py`)

`CreatePoWizard` is opened as a contextual action from a requisition (`default_get` reads `active_id` and
pre-populates only lines with a `product_id` and no `po_line_id` yet — i.e. not already ordered). It has two
flows selected via `action_type`:

- **`create_po`** — creates one `purchase.order` directly, one `purchase.order.line` per selected requisition
  line, and stamps `po_line_id` back onto each source line.
- **`create_pr`** — creates a native `purchase.requisition` (Odoo's own agreements model) plus one
  `purchase.order` per selected vendor in `vendor_ids`, replicating lines onto each PO; only the *first*
  vendor's PO lines get `po_line_id` back-linked (the others remain competing quotes under the same
  agreement). Immediately calls `pr.action_in_progress()` to confirm the native requisition.

Both flows flip the custom requisition's `state` to `waiting` once every one of its lines has a `po_line_id`.

### Automation (`data/`)

- `ir_sequence_data.xml` defines the `purchase.requisition.custom` sequence (`PR/00001`).
- `cron_data.xml` runs `_cron_send_draft_requisitions_reminder` daily at 14:00, which groups all `draft`
  requisitions by `manager_id` and sends **one** consolidated email per manager (not one per requisition)
  via `mail_template_data.xml`'s `email_template_draft_requisitions_reminder`. The same template is also
  fired synchronously on `create()` for the single new requisition's manager.

### Known inconsistency

`views/purchase_order_views.xml` still exists in the tree but is **not** referenced in `__manifest__.py`'s
`data` list (removed in commit `75d4cbd`) — it is currently dead/unloaded. Don't assume its contents are
active in the UI; if PO view changes are needed, check whether this file should be re-wired into the
manifest or whether the intent was to delete it.
