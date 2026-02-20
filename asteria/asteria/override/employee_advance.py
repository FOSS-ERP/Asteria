import frappe
from hrms.hr.doctype.employee_advance.employee_advance import EmployeeAdvance

class CustomEmployeeAdvance(EmployeeAdvance):
    def set_status(self, update=False):
        super().set_status(update)
        self.custom_status = self.status

        