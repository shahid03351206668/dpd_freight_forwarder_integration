frappe.ui.form.on( 'Delivery Note', {
    refresh(frm){
        if (frm.doc.docstatus==1){
            frm.add_custom_button(__("DPD Label"), function(){
                frappe.model.open_mapped_doc({
                    method:"dpd_freight_forwarder_integration.dpd_freight_forwarder_integration.doctype.dpd_shipment.dpd_shipment.create_shipment_from_delivery_note",
                    frm:frm,
                });
            }, __("Create"));
        }
    }
})