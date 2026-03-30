const DIVISION_ACRONYM_MAP = {
	"Sales & BD": "SBD",
	"Product Management-Hardware": "PMH",
	"Engineering-Hardware-Project Management": "ENH-PM",
	"Engineering-Hardware-System Engineering": "ENH-SE",
	"Engineering-Hardware-Design": "ENH-DS",
	"Engineering-Hardware-Embedded": "ENH-ES",
	"Engineering-Hardware-Validation & Verification": "ENH-VV",
	"Engineering-Hardware-Manufacturing Engineering": "ENH-ME",
	"Engineering-Software": "ENS",
	"SCM": "SCM",
	"Inventory": "INV",
	"Supplier Quality Assurance": "SQA",
	"Production-PPC": "PDN-PL",
	"Production-Shopfloor": "PDN-PS",
	"Quality Control-In coming": "QCO-IQC",
	"Quality Control-In process": "QCO-IPQC",
	"Quality Control-Flight Test": "QCO-FTQC",
	"Customer Support": "CUS",
	"Program Management": "PRM",
	"DaaS Flight Operations": "FOP",
	"Data Processing and Delivery": "DPD",
	"DaaS Project Management": "DPM",
	"Facilities & Administration": "ADM",
	"Finance": "FIN",
	"Human Resources": "HRS",
	"Legal & Compliance": "LGL",
	"Marketing": "MKT",
	"Quality Assurance": "QAS",
	"Regulatory & Policy Affairs": "RPA",
	"Strategy and Planning": "SNP",
	"Technology Support": "TSU"
};

frappe.ui.form.on("NC Actions", {
	onload(frm) {
		frm.set_df_property("division", "reqd", 1);
	},
	division(frm) {
		frm.set_value("acronym", DIVISION_ACRONYM_MAP[frm.doc.division] || "");
	},
	validate(frm) {
		frm.set_value("acronym", DIVISION_ACRONYM_MAP[frm.doc.division] || "");
	}
});
