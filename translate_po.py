import re

translations = {
    "Action": "Acción",
    "Action Needed": "Acción requerida",
    "Activities": "Actividades",
    "Activity Exception Decoration": "Decoración de Excepción de Actividad",
    "Activity State": "Estado de la Actividad",
    "Activity Type Icon": "Icono de Tipo de Actividad",
    "Agreement Type": "Tipo de Acuerdo",
    "Attachment Count": "Número de archivos adjuntos",
    "Authorized": "Autorizado",
    "Basic Requisition User": "Usuario Básico de Requisiciones",
    "Cancel": "Cancelar",
    "Categories/Rubrics Catalog": "Catálogo de Categorías/Rubros",
    "Comments": "Comentarios",
    "Create": "Crear",
    "Create PO": "Crear OC",
    "Create Purchase Document": "Crear Documento de Compra",
    "Create Purchase Order": "Crear Orden de Compra",
    "Create Purchase Order Wizard": "Asistente para Crear Orden de Compra",
    "Create Purchase Requisition": "Crear Requisición de Compra",
    "Create a new purchase requisition": "Crear una nueva requisición de compra",
    "Created by": "Creado por",
    "Created on": "Creado el",
    "Custom Requisition": "Requisición Personalizada",
    "Delivered": "Entregado",
    "Denied": "Denegado",
    "Description": "Descripción",
    "Display Name": "Nombre a mostrar",
    "Expiration Date": "Fecha de Expiración",
    "Expired:": "Expirado:",
    "Expires:": "Expira:",
    "Followers": "Seguidores",
    "Followers (Partners)": "Seguidores (Contactos)",
    "Font awesome icon e.g. fa-tasks": "Icono de Font Awesome, ej. fa-tasks",
    "Has Message": "Tiene mensaje",
    "Helps you manage purchase requisitions.": "Ayuda a gestionar las requisiciones de compra.",
    "ID": "ID",
    "Icon": "Icono",
    "Icon to indicate an exception activity.": "Icono para indicar una actividad de excepción.",
    "If checked, new messages require your attention.": "Si está marcado, los nuevos mensajes requieren su atención.",
    "If checked, some messages have a delivery error.": "Si está marcado, algunos mensajes tienen un error de entrega.",
    "Image": "Imagen",
    "In Quotation": "En cotización",
    "Is Follower": "Es seguidor",
    "Last Modified on": "Última modificación el",
    "Last Updated by": "Última actualización por",
    "Last Updated on": "Última actualización el",
    "Lines": "Líneas",
    "Lines to Order": "Líneas a Pedir",
    "Main Attachment": "Archivo adjunto principal",
    "Manager": "Gerente",
    "Manager:": "Gerente:",
    "Message Delivery error": "Error de entrega de mensaje",
    "Messages": "Mensajes",
    "My Activity Deadline": "Mi fecha límite de actividad",
    "Name": "Nombre",
    "New": "Nuevo",
    "Next Activity Calendar Event": "Siguiente evento en el calendario de actividades",
    "Next Activity Deadline": "Fecha límite de la siguiente actividad",
    "Next Activity Summary": "Resumen de la siguiente actividad",
    "Next Activity Type": "Tipo de la siguiente actividad",
    "Number of Actions": "Número de acciones",
    "Number of errors": "Número de errores",
    "Number of messages which requires an action": "Número de mensajes que requieren una acción",
    "Number of messages with delivery error": "Número de mensajes con error de entrega",
    "Number of unread messages": "Número de mensajes no leídos",
    "Only Purchase Managers can update the status of a requisition.": "Solo los Gerentes de Compras pueden actualizar el estado de una requisición.",
    "PO Count": "Cantidad de OC",
    "PO Line": "Línea de OC",
    "PO in Process": "OC en Proceso",
    "Please select a vendor.": "Por favor, seleccione un proveedor.",
    "Please select an agreement type.": "Por favor, seleccione un tipo de acuerdo.",
    "Please select at least one vendor.": "Por favor, seleccione al menos un proveedor.",
    "Product": "Producto",
    "Purchase Manager": "Gerente de Compras",
    "Purchase Order": "Orden de compra",
    "Purchase Orders": "Órdenes de Compra",
    "Purchase Requisition": "Requisición de Compra",
    "Purchase Requisition Line Custom": "Línea de Requisición de Compra Personalizada",
    "Purchase Requisition: Draft Reminder": "Requisición de Compra: Recordatorio de Borrador",
    "Purchase Requisitions": "Requisiciones de Compra",
    "Quantity": "Cantidad",
    "Recordatorio: Requisiciones de Compra Pendientes": "Recordatorio: Requisiciones de Compra Pendientes",
    "Reference": "Referencia",
    "Request": "Solicitud",
    "Requester": "Solicitante",
    "Requester:": "Solicitante:",
    "Requires Vehicle": "Requiere Vehículo",
    "Requisition": "Requisición",
    "Responsible User": "Usuario Responsable",
    "Rubro": "Rubro",
    "Rubro:": "Rubro:",
    "Rubros": "Rubros",
    "SMS Delivery error": "Error de entrega de SMS",
    "Search Requisitions": "Buscar Requisiciones",
    "Status": "Estado",
    "Status based on activities\nOverdue: Due date is already passed\nToday: Activity date is today\nPlanned: Future activities.": "Estado basado en actividades\nVencido: La fecha de vencimiento ya pasó\nHoy: La fecha de la actividad es hoy\nPlanificado: Actividades futuras.",
    "Type of the exception activity on record.": "Tipo de actividad de excepción registrada.",
    "Unit of Measure": "Unidad de Medida",
    "Unread Messages": "Mensajes no leídos",
    "Unread Messages Counter": "Contador de mensajes no leídos",
    "Vehicle": "Vehículo",
    "Vehicle is mandatory when Rubro requires it.": "El vehículo es obligatorio cuando el rubro lo requiere.",
    "Vendor": "Proveedor",
    "Vendors": "Proveedores",
    "Website Messages": "Mensajes del sitio web",
    "Website communication history": "Historial de comunicación del sitio web",
    "You cannot change the draft state if there are lines without a product.": "No puede cambiar el estado borrador si hay líneas sin producto."
}

with open("i18n/es_MX.po", "r", encoding="utf-8") as f:
    content = f.read()

# We need to parse msgid and msgstr pairs, being careful with multiline ones.
# Simple state machine to read the .po file
lines = content.split('\n')
out_lines = []
current_msgid = ""
in_msgid = False
in_msgstr = False

i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith('msgid "'):
        # Extract msgid
        current_msgid = line[7:-1]
        out_lines.append(line)
        i += 1
        # Check for multiline msgid
        while i < len(lines) and lines[i].startswith('"'):
            current_msgid += lines[i][1:-1]
            out_lines.append(lines[i])
            i += 1
        
        # Now we should be at msgstr
        if i < len(lines) and lines[i].startswith('msgstr "'):
            msgstr_val = lines[i][8:-1]
            
            # Read multiline msgstr if any
            next_i = i + 1
            while next_i < len(lines) and lines[next_i].startswith('"'):
                msgstr_val += lines[next_i][1:-1]
                next_i += 1
            
            # If msgstr is empty or equal to "Orden de compra" (which was already there)
            # Try to replace
            if current_msgid in translations:
                # Replace with translation
                if "\\n" in translations[current_msgid]:
                    out_lines.append('msgstr ""')
                    for part in translations[current_msgid].split("\\n"):
                        out_lines.append('"{}\\n"'.format(part))
                    # Remove the last \\n
                    out_lines[-1] = out_lines[-1].replace('\\n"', '"')
                else:
                    out_lines.append('msgstr "{}"'.format(translations[current_msgid]))
                i = next_i
            else:
                # Keep original msgstr
                out_lines.append(lines[i])
                i += 1
                while i < next_i:
                    out_lines.append(lines[i])
                    i += 1
            continue
    out_lines.append(line)
    i += 1

with open("i18n/es_MX.po", "w", encoding="utf-8") as f:
    f.write('\n'.join(out_lines))
