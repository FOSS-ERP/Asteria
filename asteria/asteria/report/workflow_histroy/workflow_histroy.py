# Copyright (c) 2025, Viral and contributors
# For license information, please see license.txt


import json
import frappe
from frappe import _

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("DocType"), "fieldname": "ref_doctype", "fieldtype": "Link", "options": "DocType", "width": 130},
        {"label": _("Document Name"), "fieldname": "docname", "fieldtype": "Dynamic Link", "options": "ref_doctype", "width": 180},
        {"label": _("Property"), "fieldname": "property", "fieldtype": "Data", "width": 200},
        {"label": _("Old Timestamp"), "fieldname": "old_timestamp", "fieldtype": "Datetime", "width": 200},
        {"label": _("Old User"), "fieldname": "old_user", "fieldtype": "Link", "options": "User", "width": 200},
        {"label": _("Old Value"), "fieldname": "old_value", "fieldtype": "Data", "width": 200},
        {"label": _("New Timestamp"), "fieldname": "new_timestamp", "fieldtype": "Datetime", "width": 200},
        {"label": _("New User"), "fieldname": "new_user", "fieldtype": "Link", "options": "User", "width": 200},
        {"label": _("New Value"), "fieldname": "new_value", "fieldtype": "Data", "width": 200},
        {"label": _("Version ID"), "fieldname": "version_id", "fieldtype": "Link", "options": "Version", "width": 120},
    ]

def get_data(filters):
    conditions = ["1=1"]
    values = {}
    
    if filters.get("doctype"):
        conditions.append("v.ref_doctype = %(doctype)s")
        values["doctype"] = filters["doctype"]
    
    if filters.get("from_date"):
        conditions.append("v.creation >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    
    if filters.get("to_date"):
        conditions.append("v.creation <= %(to_date)s")
        values["to_date"] = filters["to_date"]
    
    where_clause = " AND ".join(conditions)
    
    
    versions = frappe.db.sql(f"""
        SELECT 
            v.name as version_id,
            v.ref_doctype,
            v.docname,
            v.data,
            v.owner as new_user,
            v.creation as new_timestamp
        FROM `tabVersion` v
        WHERE {where_clause}
        ORDER BY v.creation DESC
        LIMIT 200
    """, values, as_dict=True)
    
    result = []
    
    for v in versions:
        if not v.data:
            continue
        
        try:
            version_data = json.loads(v.data)
        except:
            continue
        
        # get original document
        old_user, old_timestamp = get_doc_meta(v.ref_doctype, v.docname)
        
        # Process changed fields
        for change_item in version_data.get("changed", []):
            if isinstance(change_item, list) and len(change_item) >= 3:
                fieldname = change_item[0] if len(change_item) > 0 else ""
                old_value = change_item[1] if len(change_item) > 1 else ""
                new_value = change_item[2] if len(change_item) > 2 else ""
                
                result.append({
                    "ref_doctype": v.ref_doctype,
                    "docname": v.docname,
                    "property": str(fieldname) if fieldname is not None else "",
                    "old_timestamp": old_timestamp,
                    "old_user": old_user,
                    "old_value": str(old_value) if old_value is not None else "",
                    "new_timestamp": v.new_timestamp,
                    "new_user": v.new_user,
                    "new_value": str(new_value) if new_value is not None else "",
                    "version_id": v.version_id
                })
        
        # Process row changes
        for row_change in version_data.get("row_changed", []):
            if isinstance(row_change, list) and len(row_change) >= 4:
                child_table = row_change[0] if len(row_change) > 0 else ""
                row_index = row_change[1] if len(row_change) > 1 else ""
                row_id = row_change[2] if len(row_change) > 2 else ""
                changed_fields = row_change[3] if len(row_change) > 3 else []
                
                if isinstance(changed_fields, list):
                    for field_change in changed_fields:
                        if isinstance(field_change, list) and len(field_change) >= 3:
                            fieldname = field_change[0] if len(field_change) > 0 else ""
                            old_value = field_change[1] if len(field_change) > 1 else ""
                            new_value = field_change[2] if len(field_change) > 2 else ""
                            
                            property_name = f"{child_table} ({fieldname})"
                            
                            result.append({
                                "ref_doctype": v.ref_doctype,
                                "docname": v.docname,
                                "property": property_name,
                                "old_timestamp": old_timestamp,
                                "old_user": old_user,
                                "old_value": str(old_value) if old_value is not None else "",
                                "new_timestamp": v.new_timestamp,
                                "new_user": v.new_user,
                                "new_value": str(new_value) if new_value is not None else "",
                                "version_id": v.version_id
                            })
    
    return result

def get_doc_meta(doctype, docname):
    try:
        meta = frappe.db.get_value(
            doctype,
            docname,
            ["owner", "creation"],
            as_dict=True
        )
        if meta:
            return meta.get("owner"), meta.get("creation")
    except:
        pass
    return None, None
