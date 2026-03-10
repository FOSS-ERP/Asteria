import frappe
from hrms.hr.doctype.employee_advance.employee_advance import EmployeeAdvance


class CustomEmployeeAdvance(EmployeeAdvance):
	def set_status(self, update=False):
		super().set_status(update)
		self.custom_status = self.status
		if update and frappe.db.has_column("Employee Advance", "custom_status"):
			self.db_set("custom_status", self.status)
