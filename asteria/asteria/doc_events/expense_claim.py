import frappe
from frappe.utils import add_days, date_diff, getdate, today, get_link_to_form
from frappe import bold

def execute_alert():
    expense_claim = frappe.db.sql(
        """
            Select name, workflow_state, status, creation, approval_status, posting_date
            From `tabExpense Claim`
            Where status != 'Approved' and docstatus != 2 
        """, as_dict=1
    )

    for row in expense_claim:
        if row.workflow_state == 'Waiting for Expense Approver':
            posting_date = getdate(row.posting_date)
            date_after_3_day = getdate(add_days(str(posting_date), 3))
            if getdate(today()) <= date_after_3_day:
                doc = frappe.get_doc("Expense Claim", row.name)
                notify_approver(doc)
                continue
        
        if row.workflow_state == 'Waiting for Expense Approver':
            doc = frappe.get_doc("Expense Claim", row.name)
            notify_second_level_approver(doc)


def notify_approver(doc):
    message = """
    <style>
      .body {{
        font-family: Arial, sans-serif;
        background-color: #f7f9fc;
        color: #333;
        padding: 20px;
      }}
      .container {{
        max-width: 600px;
        margin: auto;
        background: #fff;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        padding: 30px;
      }}
      .header {{
        border-bottom: 1px solid #eee;
        margin-bottom: 20px;
      }}
      .header h2 {{
        margin: 0;
        color: #2c3e50;
      }}
      .details {{
        margin-bottom: 20px;
      }}
      .details p {{
        margin: 6px 0;
      }}
      .btn {{
        display: inline-block;
        background-color: #4CAF50;
        color: white;
        padding: 12px 20px;
        text-decoration: none;
        border-radius: 4px;
      }}
      .footer {{
        margin-top: 30px;
        font-size: 12px;
        color: #888;
        text-align: center;
      }}
    </style>
    <div class="container body">
      <div class="header">
        <h2>Expense Approval Request</h2>
      </div>
      <p>Dear Approver,</p>
      <p>You have a new expense request pending for your approval. Below are the details:</p>
      <div class="details">
        <p><strong>Expense Claim: </strong>{0}</p>
        <p><strong>Submitted By: </strong>{1}</p>
        <p><strong>Amount: </strong>{2}</p>
        <p><strong>Date: </strong>{3}</p>
      </div>
      <a href="https://erp.asteria.co.in/app/expense-claim/{4}" class="btn">Review & Approve</a>
      <div class="footer">
        <p>This is an automated email from your ERP system. Please do not reply.</p>
      </div>
    </div>
    """.format(get_link_to_form("Expense Claim", doc.name), doc.employee_name, doc.grand_total, getdate(doc.creation), doc.name)

    recipients = frappe.db.get_value("Employee", doc.employee, "expense_approver")

    subject = "Expense Approval Request"
    if recipients:
        frappe.sendmail(recipients=recipients, subject=subject, message=message)


import frappe
from frappe.utils import get_link_to_form, getdate

def notify_second_level_approver(doc):
   
    expense_approver = frappe.db.get_value("Employee", doc.employee, "expense_approver")
    if expense_approver:
        expense_approver = frappe.db.get_value("User", expense_approver, "full_name")
    else:
        expense_approver = ''
    message = """
    <style>
      .body {{
        font-family: Arial, sans-serif;
        background-color: #f7f9fc;
        color: #333;
        padding: 20px;
      }}
      .container {{
        max-width: 600px;
        margin: auto;
        background: #ffffff;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
        padding: 30px;
      }}
      .header {{
        border-bottom: 1px solid #eee;
        margin-bottom: 20px;
      }}
      .header h2 {{
        margin: 0;
        color: #1e3a8a;
      }}
      .details {{
        margin-bottom: 20px;
      }}
      .details p {{
        margin: 6px 0;
      }}
      .btn {{
        display: inline-block;
        background-color: #1e3a8a;
        color: white;
        padding: 12px 20px;
        text-decoration: none;
        border-radius: 4px;
      }}
      .footer {{
        margin-top: 30px;
        font-size: 12px;
        color: #888;
        text-align: center;
      }}
    </style>

    <div class="container body">
      <div class="header">
        <h2>Second Level Approval Required</h2>
      </div>
      <p>Dear Approver,</p>
      <p>The following expense has not been approved at the first level, so your approval is required. Please review this expense claim.</p>
      <div class="details">
        <p><strong>Expense Claim: </strong>{0}</p>
        <p><strong>Submitted By:</strong> {1}</p>
        <p><strong>Amount:</strong> {2}</p>
        <p><strong>Approved By:</strong> {3}</p>
      </div>
      <a href="https://erp.asteria.co.in/app/expense-claim/{4}" class="btn">Review & Approve</a>
      <div class="footer">
        <p>This is an automated email. Please do not reply to this message.</p>
      </div>
    </div>
    """.format(
        get_link_to_form("Expense Claim", doc.name),
        doc.employee_name,
        doc.grand_total,
        expense_approver,
        doc.name
    )

    # Assuming "finance_approver" is a custom field in Employee or Expense Claim
    finance_approver = frappe.db.get_value("Employee", doc.employee, "custom_second_level_expense_approver")

    subject = "Second Level Approval Required for Expense Claim"

    if finance_approver:
        approver_email = frappe.db.get_value("User", finance_approver, "email")
        if approver_email:
            frappe.sendmail(
                recipients=approver_email,
                subject=subject,
                message=message
            )

def validate(self, method):
    if self.workflow_state == "Waiting for Expense Approver" and self.get_doc_before_save().workflow_state != 'Waiting for Expense Approver':
        expense_approver = frappe.db.get_value("User", self.expense_approver, "full_name")
        message = f"""
          <body style="margin:0; padding:0; background-color:#f4f4f4; font-family:Arial, sans-serif;">
            <table align="center" cellpadding="0" cellspacing="0" width="600" style="background-color:#ffffff; padding:20px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
              <tr>
                <td style="text-align:center;">
                  <h2 style="color:#333333;">🧾 Expense Claim Requires Your Approval</h2>
                  <p style="color:#666666;">Dear { expense_approver },</p>
                  <p style="color:#666666;">An expense claim has been submitted and requires your review and approval.</p>
                </td>
              </tr>
              <tr>
                <td>
                  <table cellpadding="6" cellspacing="0" width="100%" style="margin:20px 0; border:1px solid #dddddd; border-radius:6px;">
                    <tr style="background-color:#f9f9f9;">
                      <td><strong>Employee</strong></td>
                      <td>{ self.employee_name }</td>
                    </tr>
                    <tr>
                      <td><strong>Expense Claim ID</strong></td>
                      <td>{ self.name }</td>
                    </tr>
                    <tr>
                      <td><strong>Total Amount</strong></td>
                      <td>{ self.grand_total }</td>
                    </tr>
                    <tr>
                      <td><strong>Expense Date</strong></td>
                      <td>{ getdate(self.creation)}</td>
                    </tr>
                  </table>
                </td>
              </tr>
              <tr>
                <td style="text-align:center;">
                  <a href="https://erp.asteria.co.in/app/expense-claim/{self.name}" style="background-color:#4CAF50; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:5px; font-weight:bold;">Review & Approve</a>
                </td>
              </tr>
              <tr>
                <td style="padding-top:20px; font-size:13px; color:#999999; text-align:center;">
                  <p>This is an automated message from your ERP system. Please do not reply.</p>
                </td>
              </tr>
            </table>
          </body>
        """
        subject = "Expense Approval Request"
        approver_email = self.expense_approver
        frappe.sendmail(
                recipients=approver_email,
                subject=subject,
                message=message
            )
    if self.workflow_state == 'Waiting for Finance Manager Approval' and self.get_doc_before_save().workflow_state != 'Waiting for Finance Manager Approval':
        finance_approver = get_users_by_role("Finance Approver")
        for row in finance_approver:
            if not frappe.db.get_value("User", row, "enabled") or row  == 'Administrator':
                continue
            message = f"""
                <!DOCTYPE html>
                <html>
                <head>
                  <meta charset="UTF-8">
                  <title>Finance Approval Needed</title>
                </head>
                <body style="margin:0; padding:0; background-color:#f4f4f4; font-family:Arial, sans-serif;">
                  <table align="center" cellpadding="0" cellspacing="0" width="600" style="background-color:#ffffff; padding:20px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                      <td style="text-align:center;">
                        <h2 style="color:#333333;">💰 Finance Approval Required</h2>
                        <p style="color:#666666;">Dear { frappe.db.get_value("User", row, 'full_name') },</p>
                        <p style="color:#666666;">An expense claim has been approved by the Expense Approver and now requires your approval.</p>
                      </td>
                    </tr>
                    <tr>
                      <td>
                        <table cellpadding="6" cellspacing="0" width="100%" style="margin:20px 0; border:1px solid #dddddd; border-radius:6px;">
                          <tr style="background-color:#f9f9f9;">
                            <td><strong>Employee</strong></td>
                            <td>{ self.employee_name }</td>
                          </tr>
                          <tr>
                            <td><strong>Expense Claim ID</strong></td>
                            <td>{ self.name }</td>
                          </tr>
                          <tr>
                            <td><strong>Total Amount</strong></td>
                            <td>{ self.grand_total }</td>
                          </tr>
                          <tr>
                            <td><strong>Expense Date</strong></td>
                            <td>{ getdate(self.creation) }</td>
                          </tr>
                          <tr>
                            <td><strong>Approved By</strong></td>
                            <td>{ frappe.db.get_value("User", self.expense_approver, "full_name") }</td>
                          </tr>
                          <tr>
                            <td><strong>Approval Date</strong></td>
                            <td>{ today() }</td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                    <tr>
                      <td style="text-align:center;">
                        <a href="https://erp.asteria.co.in/app/expense-claim/{self.name}" style="background-color:#007BFF; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:5px; font-weight:bold;">Review & Approve</a>
                      </td>
                    </tr>
                    <tr>
                      <td style="padding-top:20px; font-size:13px; color:#999999; text-align:center;">
                        <p>This is an automated message from your ERP system. Please do not reply.</p>
                      </td>
                    </tr>
                  </table>
                </body>
                </html>
            """

            subject = "Finance Approval Request"
            frappe.sendmail(
                    recipients=row,
                    subject=subject,
                    message=message
            )
    if not self.is_new() and self.get_doc_before_save().workflow_state == "Waiting for Expense Approver" and self.workflow_state not in ('Rejected'):
        if self.workflow_state != "Draft":
            return
        message = f"""
            <html>
            <head>
              <meta charset="UTF-8">
              <title>Expense Claim Needs Review</title>
            </head>
            <body style="margin:0; padding:0; background-color:#f4f4f4; font-family:Arial, sans-serif;">
              <table align="center" cellpadding="0" cellspacing="0" width="600" style="background-color:#ffffff; padding:20px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                <tr>
                  <td style="text-align:center;">
                    <h2 style="color:#cc0000;">🔍 Expense Claim Sent Back for Review</h2>
                    <p style="color:#666666;">Dear { self.employee_name },</p>
                    <p style="color:#666666;">
                      Your expense claim <strong>{ self.name }</strong> has been sent back for review by the approver.
                      Please review the comments below, make the necessary corrections, and resubmit the claim.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td>
                    <table cellpadding="6" cellspacing="0" width="100%" style="margin:20px 0; border:1px solid #dddddd; border-radius:6px;">
                      <tr style="background-color:#f9f9f9;">
                        <td><strong>Approver Name</strong></td>
                        <td>{ frappe.db.get_value("User", self.expense_approver, "full_name") }</td>
                      </tr>
                      <tr>
                        <td><strong>Claim ID</strong></td>
                        <td>{ get_link_to_form("Expense Claim", self.name) }</td>
                      </tr>
                      <tr>
                        <td><strong>Total Amount</strong></td>
                        <td>{ self.grand_total }</td>
                      </tr>
                      <tr>
                        <td><strong>Submission Date</strong></td>
                        <td>{ str(getdate(self.creation)) }</td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="text-align:center;">
                    <a href="https://erp.asteria.co.in/app/expense-claim/{self.name}" style="background-color:#FFA500; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:5px; font-weight:bold;">Review & Resubmit</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:20px; font-size:13px; color:#999999; text-align:center;">
                    <p>This is an automated message from your ERP system. Please do not reply directly to this email.</p>
                  </td>
                </tr>
              </table>
            </body>
            </html>
        """
        subject = "Review Your Expense Again"
        approver_email = frappe.db.get_value("Employee", self.employee, "user_id")
        frappe.sendmail(
                recipients=approver_email,
                subject=subject,
                message=message
        )
    if self.workflow_state == "Rejected" and self.get_doc_before_save().workflow_state != 'Rejected':
        
        message = f"""
            <body style="margin:0; padding:0; background-color:#f4f4f4; font-family:Arial, sans-serif;">
              <table align="center" cellpadding="0" cellspacing="0" width="600" style="background-color:#ffffff; padding:20px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                <tr>
                  <td style="text-align:center;">
                    <h2 style="color:#d93025;">❌ Expense Claim Rejected</h2>
                    <p style="color:#666666;">Dear { self.employee_name },</p>
                    <p style="color:#666666;">
                      Your expense claim <strong>{ self.name }</strong> has been <strong>rejected</strong> by the approver.
                      Please find the details and reason below.
                    </p>
                  </td>
                </tr>
                <tr>
                  <td>
                    <table cellpadding="6" cellspacing="0" width="100%" style="margin:20px 0; border:1px solid #dddddd; border-radius:6px;">
                      <tr>
                        <td><strong>Claim ID</strong></td>
                        <td>{ self.name }</td>
                      </tr>
                      <tr>
                        <td><strong>Total Amount</strong></td>
                        <td>{ self.total_claimed_amount }</td>
                      </tr>
                      <tr>
                        <td><strong>Submission Date</strong></td>
                        <td>{ str(getdate(self.creation)) }</td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <tr>
                  <td style="text-align:center;">
                    <a href="https://erp.asteria.co.in/app/expense-claim/{self.name}" style="background-color:#6c757d; color:#ffffff; padding:12px 24px; text-decoration:none; border-radius:5px; font-weight:bold;">View Expense Claim</a>
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:20px; font-size:13px; color:#999999; text-align:center;">
                    <p>This is an automated notification from your ERP system. If you have questions, please contact your approver directly.</p>
                  </td>
                </tr>
              </table>
            </body>
        """
        subject = "Expense claim Rejection"
        approver_email = frappe.db.get_value("Employee", self.employee, "user_id")
        frappe.sendmail(
                recipients=approver_email,
                subject=subject,
                message=message
        )


import frappe
from frappe import _

@frappe.whitelist()
def get_users_by_role(role_name):
    users = frappe.get_all("Has Role", 
        filters={"role": role_name},
        fields=["parent as user"]
    )
    return [user.user for user in users]
