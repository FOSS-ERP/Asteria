import frappe

def validate(doc, method):
    # Check workflow state
    if doc.workflow_state == "Waiting for Expense Approver":
        # Get Employee record
        employee = frappe.get_doc("Employee", doc.employee)

        if employee.expense_approver:
            approver = employee.expense_approver

            # Share Employee Advance doc with Expense Approver (with write access)
            frappe.share.add_docshare(
                doc.doctype,
                doc.name,
                approver,
                write=1,
                notify=1  # Sends notification to approver
            )