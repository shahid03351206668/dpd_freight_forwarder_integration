// Copyright (c) 2026, Codes Soft and contributors
// For license information, please see license.txt

frappe.ui.form.on("DPD Shipment", {
	refresh(frm){
        if (frm.doc.docstatus==1){
            frm.add_custom_button("Print Label", () => {
                frappe.db.get_value("File", {
                    "attached_to_doctype": "DPD Shipment",
                    "attached_to_name": frm.doc.name
                }, "file_url").then(res => {
                    if (res.message && res.message.file_url) {
                        window.open(res.message.file_url, '_blank');
                    } else {
                        frappe.msgprint("No Label Found for this Shipment.");
                    }
                });
            });
        }
    },
    product(frm) {
        enable_predict_notification(frm)
	},
});

function enable_predict_notification(frm){
    if (['B2C', 'B2BP', 'HOME', 'PBOX'].includes(frm.doc.product)){
        frm.set_value("predict_notification", 1)
        frm.set_df_property("predict_notification", "read_only", 1)
    }
    else{
        frm.set_value("predict_notification", 0)
        frm.set_df_property("predict_notification", "read_only", 0)
    }
}

