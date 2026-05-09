# Copyright (c) 2026, Codes Soft and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cstr
from frappe.model.mapper import get_mapped_doc
from frappe.utils.file_manager import save_file
from dpd_freight_forwarder_integration.dpd_freight_forwarder_integration.doctype.dpd_settings.dpd_settings import (
    make_call,
    create_api_log,
)
from datetime import datetime, timedelta
import json
import base64


class DPDShipment(Document):
    def validate(self):
        validate_mandatory(self)
        validate_addresses(self)
        validate_product_requirements(self)
        validate_parcels_quantity(self)
        validate_pickup_data(self)

    def before_submit(self):
        validate_current_auth_token()

    def on_submit(self):
        post_shipment_request(self)


def validate_mandatory(self):
    if not self.customer:
        frappe.throw("Customer is Required")
    if self.identification_number and len(self.identification_number) > 999:
        frappe.throw("Identification Number Length Cannot Exceed 999 Characters")


def validate_product_requirements(self):
    # if self.product in ["B2C", "B2BP", "HOME", "PBOX"] and not self.predict_notification:
    # 	frappe.throw(f"{self.product} Requires Predict")

    if (
        self.product in ["B2BI", "B2B"]
        and self.recipient_country != "CH"
        and not self.recipient_email
    ):
        frappe.throw("Email Required for International B2B Shipments")


def validate_addresses(self):
    if not self.sender_name_1:
        frappe.throw("Sender Name is Required")
    if len(cstr(self.sender_name_1)) > 35:
        frappe.throw("Sender Name Length Cannot Exceed 35 Characters")
    if not self.recipient_name_1:
        frappe.throw("Recipient Name is Required")
    if len(cstr(self.recipient_name_1)) > 35:
        frappe.throw("Recipient Name Length Cannot Exceed 35 Characters")
    if not self.sender_country:
        frappe.throw("Sender Country is Required")
    # if (len(cstr(self.sender_country)) != 2) or (len(cstr(self.recipient_country)) != 2):
    # 	frappe.throw("Country Must be 2-Char ISO Code (e.g., CH)")


def validate_parcels_quantity(self):
    if len(self.parcels) > 30:
        frappe.throw("""Maximum Quantity of Parcels Allow per Shipment is 30""")
    for row in self.parcels:
        if bool(row.cod_required):
            if flt(row.cod_amount) == 0:
                frappe.throw(f"COD Amount Should be Greater than 0 at row: {row.idx}")


def validate_pickup_data(self):
    if bool(self.pickup_required):
        if not self.pickup_date:
            frappe.throw(cstr("Pickup Date is Required"))
        if self.pickup_from_time and self.pickup_to_time:
            time_format = "%H:%M:%S"
            pickup_from_time = datetime.strptime(
                cstr(self.pickup_from_time), time_format
            )
            pickup_to_time = datetime.strptime(cstr(self.pickup_to_time), time_format)
            if pickup_from_time >= pickup_to_time:
                frappe.throw("Pickup From Time Must Be Less Than Pickup To Time")


def validate_current_auth_token():
    dpd_settings_data = (
        frappe.db.get_value(
            "DPD Settings",
            "DPD Settings",
            ["auth_token", "token_expires_on"],
            as_dict=1,
        )
        or {}
    )
    if dpd_settings_data.get("auth_token") and dpd_settings_data.get(
        "token_expires_on"
    ):
        token_expiry_date = datetime.fromisoformat(
            dpd_settings_data.get("token_expires_on")
        )
        now = datetime.now(token_expiry_date.tzinfo)
        if token_expiry_date < now:
            frappe.throw(
                "Cannot Create Shipment Because Current Authentication Token is Expired"
            )


def post_shipment_request(self):
    dpd_settings_values = (
        frappe.db.get_value(
            "DPD Settings",
            "DPD Settings",
            [
                "delis_id",
                "auth_token",
                "message_language",
                "depot",
                "customerUid",
                "shipment_service_endpoint",
            ],
            as_dict=1,
        )
        or {}
    )
    post_request_data = {"authentication": None, "storeOrders": None}
    if dpd_settings_values:
        if dpd_settings_values.get("shipment_service_endpoint"):
            if (
                dpd_settings_values.get("delis_id")
                and dpd_settings_values.get("auth_token")
                and dpd_settings_values.get("message_language")
            ):
                post_request_data["authentication"] = {
                    "delisId": dpd_settings_values.get("delis_id"),
                    "authToken": dpd_settings_values.get("auth_token"),
                    "messageLanguage": dpd_settings_values.get("message_language"),
                }
                store_orders = {"printOptions": None, "order": []}
            if self.printer_language and self.paper_format:
                store_orders["printOptions"] = {
                    "printerLanguage": self.printer_language,
                    "paperFormat": self.paper_format,
                }

            shipment_data = {}
            order_data = {}
            if dpd_settings_values.get("depot"):
                shipment_data["sendingDepot"] = dpd_settings_values.get("depot")
            if self.product:
                shipment_data["product"] = self.product

            if not self.sender_country:
                frappe.throw("Select Country Code in Sender Country")

            if (
                self.sender_name_1
                and self.sender_street
                and self.sender_country
                and self.sender_country_code
                and self.sender_postal_code
                and self.sender_city
            ):
                # country_code = frappe.db.get_value("Country", self.sender_country, "code") or False
                country_code = cstr(self.sender_country).upper()
                shipment_data["sender"] = {
                    "name1": self.sender_name_1,
                    "street": self.sender_street,
                    "country": self.sender_country_code,
                    "zipCode": self.sender_postal_code,
                    "city": self.sender_city,
                    "phone": self.sender_phone,
                    "email": self.sender_email
                }
            if not self.recipient_country:
                frappe.throw("Select Country Code in Recipient Country")
            if (
                self.recipient_name_1
                and self.recipient_street
                and self.recipient_country
                and self.recipient_country_code
                and self.recipient_postal_code
                and self.recipient_city
            ):
                # country_code = frappe.db.get_value("Country", self.recipient_country, "code") or False
                country_code = cstr(country_code).upper()
                shipment_data["recipient"] = {
                    "name1": self.recipient_name_1,
                    "street": self.recipient_street,
                    "country": self.recipient_country_code,
                    "zipCode": self.recipient_postal_code,
                    "city": self.recipient_city,
                    "name2": self.recipient_name_2,
                    "street2": self.recipient_street_2,
                    "contact": self.recipient_contact,
                    "email": self.recipient_email,
                    "phone": self.recipient_phone
                }
            order_data["generalShipmentData"] = shipment_data
            parcels = []
            for row in self.parcels:
                customer_reference_2 = ""
                if row.get("customer_reference_2"):
                    customer_reference_2 += f"""{row.get("customer_reference_2")}"""
                if row.get("content"):
                    customer_reference_2 += f",{row.get('content')}"
                new_row = {
                    "weight": flt(row.get("weight_in_grams"))/10,
                    "customerReferenceNumber1": cstr(row.get("customer_reference_1")),
                    "customerReferenceNumber2": cstr(customer_reference_2),
                    "content": cstr(row.get("content")),
                }
                parcels.append(json.loads(frappe.as_json(new_row)))

            order_data["parcels"] = parcels
            if self.order_type:
                order_data["productAndServiceData"] = {
                    "orderType": cstr(self.order_type)
                }

            store_orders["order"].append(order_data)
            post_request_data["storeOrders"] = store_orders
            if post_request_data.get("authentication") and post_request_data.get(
                "storeOrders"
            ):
                response_log_filters = {
                    "method": dpd_settings_values.get("shipment_service_endpoint"),
                    "request_payload": post_request_data,
                    "response_status": None,
                    "response_json": None,
                    "timestamp": None,
                    "error_message": None,
                    "reference_document": self.doctype,
                    "reference_record": self.name,
                }
                headers = {"Content-Type": "application/json"}
                payload = post_request_data
                response_json = make_call(
                    cstr(dpd_settings_values.get("shipment_service_endpoint")),
                    "POST",
                    headers,
                    payload,
                )
                response_log_filters["timestamp"] = frappe.utils.now()
                if response_json:
                    response_log_filters["response_status"] = "Success"
                    response_log_filters["response_json"] = response_json
                    create_api_log(response_log_filters)
                    reponse_object = response_json
                    if reponse_object:
                        order_result = reponse_object.get("orderResult")
                        if order_result:
                            if order_result.get("parcellabelsPDF"):
                                pdf_base64 = cstr(order_result.get("parcellabelsPDF"))
                                pdf_base64 = (
                                    pdf_base64.replace("\n", "")
                                    .replace("\r", "")
                                    .replace(" ", "")
                                )
                                if not pdf_base64:
                                    frappe.throw("Received empty PDF label from DPD")
                                try:
                                    pdf_data = base64.b64decode(
                                        pdf_base64, validate=True
                                    )
                                except Exception as e:
                                    frappe.throw(f"Failed to decode PDF label: {e}")
                                if not pdf_data.startswith(b"%PDF"):
                                    frappe.log_error(
                                        f"Invalid PDF data received, first bytes: {pdf_data[:20]}",
                                        "DPD PDF Error",
                                    )
                                    frappe.throw("Received invalid PDF data from DPD")

                                output_file_name = "DPD-Label.pdf"
                                image = save_file(
                                    output_file_name,
                                    pdf_data,
                                    "DPD Shipment",
                                    self.name,
                                    decode=False,
                                    is_private=0,
                                )
                                self.label_generated = 1
                                self.status = "Label Generated"
                                self.label_pdf_data = pdf_base64
                            if order_result.get("shipmentResponses"):
                                parcel_info = (
                                    order_result.get("shipmentResponses")[0].get(
                                        "parcelInformation"
                                    )
                                    or []
                                )
                                if len(parcel_info) == len(self.parcels):
                                    for idx, row in enumerate(self.parcels):
                                        row.parcel_label_number = parcel_info[idx].get(
                                            "parcelLabelNumber"
                                        )

                else:
                    response_log_filters["response_status"] = "Failed"
                    response_log_filters["response_json"] = response_json
                    if response_json[0].get("status"):
                        if response_json[0].get("status").get("message"):
                            response_log_filters["error_message"] = cstr(
                                response_json[0].get("status").get("message")
                            )
                    create_api_log(response_log_filters)
                    frappe.throw("Failed to Post Shipment Request")


@frappe.whitelist()
def create_shipment_from_delivery_note(source_name, target_doc=None):
    def set_missing_values(source, target):
        shipment_recipient = None
        if source.shopify_order_number:
            shipment_recipient = source.shipping_address_name or ""
        else:
            shipment_recipient = target_doc.customer_name
        company_address_details = {}
        customer_address_details = {}
        customer_address = None
        if source.shipping_address_name:
            customer_address = source.shipping_address_name
        elif source.customer_address:
            customer_address = source.customer_address
        if customer_address:
            customer_address_details = (
                frappe.db.get_value(
                    "Address",
                    customer_address,
                    ["city", "country", "pincode", "address_line1", "address_line2"],
                    as_dict=1,
                )
                or {}
            )
            if customer_address_details.get("country"):
                country_code = (
                    frappe.db.get_value(
                        "Country", customer_address_details.get("country"), "code"
                    )
                    or None
                )
                if country_code:
                    customer_address_details["country_code"] = cstr(
                        country_code
                    ).upper()

        if source.customer:
            customer_address_details["sender_name_2"] = frappe.db.get_value(
                "Customer", source.customer, "custom_customer_additional_designation"
            )
            customer_contact_details = frappe.db.sql(
                f"""SELECT p.name FROM `tabContact`p INNER JOIN `tabDynamic Link`c ON p.name = c.parent WHERE c.link_doctype = 'Customer' AND c.link_name = '{source.customer}' ORDER BY p.creation DESC LIMIT 1""",
                as_dict=1,
            )
            if customer_contact_details:
                try:
                    contact_doc = frappe.get_doc(
                        "Contact", customer_contact_details[0].get("name")
                    )
                    for row in contact_doc.email_ids:
                        if bool(row.is_primary) and row.email_id:
                            customer_address_details["recipient_email"] = row.email_id
                    for contact_row in contact_doc.phone_nos:
                        if bool(contact_row.is_primary_mobile_no) and contact_row.phone:
                            customer_address_details["recipient_phone"] = (
                                contact_row.phone
                            )
                except Exception as e:
                    frappe.log_error(
                        message=f"""Failed To Access Contact Record: {customer_contact_details[0].get("name")}""",
                        title="Customer Contact Record Access Error",
                    )

        if source.company:
            company_contact_details = frappe.db.sql(
                f"""SELECT p.name FROM `tabContact`p INNER JOIN `tabDynamic Link`c ON p.name = c.parent WHERE c.link_doctype = 'Company' AND c.link_name = '{source.company}' ORDER BY p.creation DESC LIMIT 1""",
                as_dict=1,
            )
            if company_contact_details:
                try:
                    company_contact_doc = frappe.get_doc(
                        "Contact", company_contact_details[0].get("name")
                    )
                    for company_row in company_contact_doc.email_ids:
                        if bool(company_row.is_primary) and company_row.email_id:
                            company_address_details["sender_email"] = (
                                company_row.email_id
                            )
                    for company_contact_row in company_contact_doc.phone_nos:
                        if (
                            bool(company_contact_row.is_primary_mobile_no)
                            and company_contact_row.phone
                        ):
                            company_address_details["sender_phone"] = (
                                company_contact_row.phone
                            )
                except Exception as e:
                    frappe.log_error(
                        message=f"""Failed To Access Contact Record: {company_contact_details[0].get("name")}""",
                        title="Company Contact Record Access Error",
                    )
            # frappe.msgprint(cstr(company_address_details))

        default_dpd_sender_warehouse = (
            frappe.db.get_value(
                "DPD Settings", "DPD Settings", "default_dpd_sender_warehouse"
            )
            or None
        )
        if source.company and default_dpd_sender_warehouse:
            # "AND p.address_type = 'Plant' AND p.is_shipping_address = 1 AND p.is_your_company_address = 1",
            address_conditions = [
                "AND p.address_type = 'Billing' AND p.is_shipping_address = 1"
            ]
            base_query = """
				SELECT p.city, p.country, p.pincode, p.address_line1, p.address_line2
				FROM `tabAddress` p
				INNER JOIN `tabDynamic Link` c ON p.name = c.parent
				WHERE c.link_doctype = 'Warehouse'
				AND c.link_name = %s
				{conditions}
				LIMIT 1
			"""
            for conditions in address_conditions:
                result = frappe.db.sql(
                    base_query.format(conditions=conditions),
                    values=(default_dpd_sender_warehouse,),
                    as_dict=1,
                )
                if result:
                    company_address_details.update(result[0])
                    if company_address_details.get("country"):
                        country_code = (
                            frappe.db.get_value(
                                "Country",
                                company_address_details.get("country"),
                                "code",
                            )
                            or None
                        )
                        if country_code:
                            company_address_details["country_code"] = cstr(
                                country_code
                            ).upper()

                    break

        # frappe.msgprint(cstr(company_address_details))
        target.customer = source.customer
        target.product = "PBOX"
        target.sender_name_1 = source.company
        target.sender_city = company_address_details.get("city")
        target.sender_country = company_address_details.get("country")
        target.sender_postal_code = company_address_details.get("pincode")
        target.sender_street = company_address_details.get("address_line1")
        target.sender_street_2 = company_address_details.get("address_line2")
        target.sender_country_code = company_address_details.get("country_code")
        target.sender_phone = company_address_details.get("sender_phone")
        target.sender_email = company_address_details.get("sender_email")
        target.recipient_name_1 = shipment_recipient
        target.recipient_name_2 = customer_address_details.get("sender_name_2")
        target.recipient_city = customer_address_details.get("city")
        target.recipient_country = customer_address_details.get("country")
        target.recipient_country_code = customer_address_details.get("country_code")
        target.recipient_postal_code = customer_address_details.get("pincode")
        target.recipient_street = customer_address_details.get("address_line1")
        target.recipient_street_2 = customer_address_details.get("address_line2")
        target.recipient_customer_number = source.customer
        target.recipient_phone = customer_address_details.get("recipient_phone")
        target.recipient_email = customer_address_details.get("recipient_email")

    doc = get_mapped_doc(
        "Delivery Note",
        source_name,
        {"Delivery Note": {"doctype": "DPD Shipment"}},
        target_doc,
        set_missing_values,
    )
    return doc
