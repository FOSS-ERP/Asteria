import frappe
from frappe.utils import get_url_to_form


def after_insert(doc, method):
	"""Send email notification to action_owner when an NC Action is created."""
	if not doc.action_owner:
		return

	action_owner_name = frappe.get_value("User", doc.action_owner, "full_name") or doc.action_owner
	document_link = get_url_to_form("NC Actions", doc.name)

	subject = f"NC Action Assigned – {doc.name}"

	message = f"""
	<p>Dear {action_owner_name},</p>

	<p>This is to inform you that a new <strong>NC Action</strong> has been created and assigned to you.</p>

	<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; margin: 15px 0;">
		<tr><td><strong>NC Action ID</strong></td><td>{doc.name}</td></tr>
		<tr><td><strong>NC ID</strong></td><td>{doc.nc_id or "–"}</td></tr>
		<tr><td><strong>Action Type</strong></td><td>{doc.nc_type or "–"}</td></tr>
		<tr><td><strong>Planned Completion Date</strong></td><td>{doc.exp_end_date or "–"}</td></tr>
	</table>

	<p>Please click the link below to access the document and take the necessary action:</p>
	<p><a href="{document_link}" style="padding: 8px 16px; background-color: #4CAF50; color: white;
		text-decoration: none; border-radius: 4px;">Open NC Action</a></p>

	<p>Regards,<br>{frappe.get_value("System Settings", None, "email_footer_address") or frappe.local.site}</p>
	"""

	frappe.sendmail(
		recipients=[doc.action_owner],
		subject=subject,
		message=message,
		reference_doctype="NC Actions",
		reference_name=doc.name,
		now=True,
	)
