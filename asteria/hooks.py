app_name = "asteria"
app_title = "Asteria"
app_publisher = "Viral"
app_description = "Test"
app_email = "viral@fosserp.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "asteria",
# 		"logo": "/assets/asteria/logo.png",
# 		"title": "Asteria",
# 		"route": "/asteria",
# 		"has_permission": "asteria.api.permission.has_app_permission"
# 	}
# ]
# app_include_js = [
#     "asteria.bundle.js"
# ]
# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/asteria/css/asteria.css"
# app_include_js = "/assets/asteria/js/asteria.js"

# include js, css files in header of web template
# web_include_css = "/assets/asteria/css/asteria.css"
# web_include_js = "/assets/asteria/js/asteria.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "asteria/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Stock Entry" : "public/js/stock_entry.js",
	"Expense Claim" : "public/js/expense_claim.js",
	"Expense Claim Type" : "public/js/expense_claim_type.js",
	"Job Card" : "public/js/job_card.js",
	}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "asteria/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "asteria.utils.jinja_methods",
# 	"filters": "asteria.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "asteria.install.before_install"
# after_install = "asteria.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "asteria.uninstall.before_uninstall"
# after_uninstall = "asteria.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "asteria.utils.before_app_install"
# after_app_install = "asteria.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "asteria.utils.before_app_uninstall"
# after_app_uninstall = "asteria.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "asteria.notifications.get_notification_config"
after_migrate = "asteria.asteria.create_custom_field.setup_custom_fields"
# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"Stock Entry": "asteria.asteria.override.stock_entry.CustomStockEntry"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Serial and Batch Bundle": {
		"validate": "asteria.asteria.override.serial_and_batch_bundle.validate",
		"on_submit" : "asteria.asteria.doc_events.purchase_receipt.on_submit"
	},
	"Stock Entry": {
		"on_submit": "asteria.asteria.stock_entry.on_submit"
	},
	"Expense Claim" : {
		"validate" : "asteria.asteria.doc_events.expense_claim.validate"
	},
	"Employee Advance" : { 
		"validate" : "asteria.asteria.doc_events.employee_advance.validate"
	},
	"Job Card": {
		"on_submit": "asteria.asteria.doc_events.job_card.on_submit"
	},
	"Quality Inspection": {
		"validate" : "asteria.asteria.doc_events.quality_inspection.validate"
	},
	"Payment Request" : {
		"validate" : "asteria.asteria.api.update_aging_in_pr"
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"0 6 * * *" : [
			"asteria.asteria.doc_events.expense_claim.execute_alert"
		],
		"0 * * * *" : [
			"asteria.asteria.doc_events.check_sftp_payment_status.check_status"
		]
	},
	"Daily" : [
		"asteria.asteria.api.set_payment_aging_for_payment_request"
	]
}

# Testing
# -------

# before_tests = "asteria.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle.get_auto_data": "asteria.asteria.override.serial_and_batch_bundle.get_auto_data",
	"hrms.overrides.employee_payment_entry.get_payment_entry_for_employee" : "asteria.asteria.override.employee_payment_entry.get_payment_entry_for_employee"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "asteria.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["asteria.utils.before_request"]
# after_request = ["asteria.utils.after_request"]

# Job Events
# ----------
# before_job = ["asteria.utils.before_job"]
# after_job = ["asteria.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"asteria.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

