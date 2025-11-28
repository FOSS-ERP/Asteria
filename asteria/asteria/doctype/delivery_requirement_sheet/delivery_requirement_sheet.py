# Copyright (c) 2025, Viral and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class DeliveryRequirementSheet(Document):
    def autoname(self):
        # If this is a version (has original_reference and revision > 0)
        if self.original_reference and self.revision > 0:
            self.name = f"{self.original_reference}-{self.revision}"
        # For base documents or duplicates, let Frappe handle naming from series
    
    def before_save(self):
        # Ensure base documents have original_reference set
        if not self.original_reference and not self.get("__islocal__"):
            self.original_reference = self.name
            self.revision = 0

@frappe.whitelist()
def create_new_version(docname):
    try:
        doc = frappe.get_doc("Delivery Requirement Sheet", docname)
        
        # Validate that we have an original reference
        if not doc.original_reference:
            frappe.throw("Cannot create version: Original reference not set")
        
        # Get the latest revision
        latest_rev = frappe.db.sql("""
            SELECT COALESCE(MAX(revision), 0) as max_rev 
            FROM `tabDelivery Requirement Sheet` 
            WHERE original_reference = %s
        """, doc.original_reference, as_dict=1)[0].max_rev
        
        new_revision = latest_rev + 1
        
        # Create new version name
        new_name = f"{doc.original_reference}-{new_revision}"
        
        # Check if this name already exists (safety check)
        if frappe.db.exists("Delivery Requirement Sheet", new_name):
            frappe.throw(f"Version {new_name} already exists!")
        
        # FIRST: Deactivate ALL existing versions (including the current one)
        frappe.db.sql("""
            UPDATE `tabDelivery Requirement Sheet` 
            SET is_active = 0 
            WHERE original_reference = %s
        """, doc.original_reference)
        
        # Create new doc using copy_doc but clear the name
        new_doc = frappe.copy_doc(doc)
        new_doc.name = None  # Clear the name so autoname can set it
        
        # Set version info
        new_doc.original_reference = doc.original_reference
        new_doc.revision = new_revision
        new_doc.previous_reference = doc.name
        new_doc.is_active = 1  # This will be the ONLY active version
        
        # Don't set amended_from for versions
        if hasattr(new_doc, 'amended_from'):
            new_doc.amended_from = None
        
        # Save the new document
        new_doc.insert(ignore_permissions=True)
        
        frappe.db.commit()
        
        frappe.msgprint(f"New version {new_name} created successfully.")
        
        return {
            'name': new_doc.name,
            'original_reference': new_doc.original_reference,
            'revision': new_doc.revision
        }
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error creating new version: {str(e)}")
        frappe.throw(f"Failed to create new version: {str(e)}")