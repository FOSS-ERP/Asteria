# Copyright (c) 2025, Viral and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname



class H2HLog(Document):
	def autoname(self):
		prefix = f"PAY-H2H-LOG-{self.log_type}-.#####"
		self.name = make_autoname(prefix)
	
	def validate(self):
		self.total_no_of_payments = len(self.vendor_payment_processor)

