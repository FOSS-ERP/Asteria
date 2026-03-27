const DIVISION_ACRONYM_MAP = {
	"Sales & BD": "SBD",
	"Product Management-Hardware": "PMH",
	"Product Management-Software": "PMS",
	"Engineering - Hardware-Project Management": "ENH-PM",
	"Engineering - Hardware-Systems Engineering": "ENH-SE",
	"Engineering - Hardware-Design": "ENH-DS",
	"Engineering - Hardware-Embedded Systems": "ENH-ES",
	"Engineering - Hardware-Validation & Verification": "ENH-VV",
	"Engineering - Hardware-Manufacturing Engineering": "ENH-ME",
	"Engineering - Software": "ENS",
	"Supply Chain Management": "SCM",
	"Supplier Quality Assurance": "SQA",
	"Production-PPC": "PDN-PL",
	"Production-Shopfloor": "PDN-PS",
	"Quality Control-IQC": "QCO-IQC",
	"Quality Control-IPQC": "QCO-IPQC",
	"Quality Control-FTQC": "QCO-FTQC",
	"Customer Support": "CUS",
	"Program Management": "PRM",
	"DaaS Flight Operations": "FOP",
	"Data Processing and Delivery": "DPD",
	"DaaS Project Management": "DPM",
	"Facilities and Administration": "ADM",
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
	division(frm) {
		frm.set_value("acronym", DIVISION_ACRONYM_MAP[frm.doc.division] || "");
	}
});
