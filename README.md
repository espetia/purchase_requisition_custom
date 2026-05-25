# Purchase Requisition Custom

**purchase_requisition_custom** is a custom Odoo 15 module that adds a preliminary layer before the creation of Purchase Orders (POs). It allows basic users to create "Purchase Requisitions" that the Purchasing Department later processes to generate actual POs.

## Features

### Data Models
* **Purchase Requisition (Header):**
  * Automatically generates consecutive references (Folios) like `PR/00001`.
  * Tracks statuses: Draft (Request), In Quotation, PO in Process, Authorized, Delivered, Denied.
  * Links to a specific category (Rubro), a Requester, and a Manager.
  * Optionally links to a Fleet Vehicle if the chosen category requires it.
  * Integrates with Odoo's Chatter (mail.thread, mail.activity.mixin) and an HTML Comments field.
* **Requisition Lines:**
  * Define products, descriptions, quantities, and units of measure.
  * Automatically loads the default unit of measure upon selecting a product.
* **Categories / Rubros:**
  * Manage requisition categories.
  * Support for a `requires_vehicle` flag, enforcing vehicle selection in the requisition header.

### User Interface
* **Form View:** Full-featured form with statusbar, edit locks (read-only when not in 'draft'), and easy access to linked Purchase Orders via stat buttons.
* **Tree View:** Displays requisitions with visual warnings (red text) for expired requests in draft or quotation states.
* **Kanban View:** Organized by status, with restrictions to prevent adding custom state columns.
* **Search View:** Allows quick filtering and searching by Name, Requester, Manager, and Rubro.

### PO Generation Wizard
* A built-in wizard enables Purchase Managers to selectively generate Purchase Orders from requisition lines.
* Excludes lines that are already linked to a PO.
* Keeps full traceability by associating the newly generated POs back to the parent Requisition.

### Smart Automations & Status Sync
* **Automatic Status Updates:** Intercepts PO status changes. 
  * If all child POs reach the `purchase` or `done` states, the Requisition automatically moves to `Authorized`.
  * If all child POs are `cancel` or `reject`, the Requisition automatically updates to `Denied`.
* **Cron Job (Draft Reminders):** A daily automated action groups pending draft requisitions by Manager and sends a consolidated, modern HTML email notification directly to them via the Odoo mail queue.

### Security and Access Rights
* **Basic Requisition User:** Can create, read, and write their *own* requisitions. Cannot delete.
* **Purchase Manager:** Has full CRUD access across *all* requisitions, and exclusive rights to update the Requisition's status and generate POs.

## Technical Details
* **Depends on:** `base`, `purchase`, `mail`, `fleet`
* **Version:** 15.0.1.0.0
* **Author:** Carlos Espetia
