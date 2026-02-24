# Copyright (c) 2026, Codes Soft and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cstr
from frappe.utils.file_manager import save_file
from dpd_freight_forwarder_integration.dpd_freight_forwarder_integration.doctype.dpd_settings.dpd_settings import make_call, create_api_log
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
	if self.product in ["B2C", "B2BP", "HOME", "PBOX"] and not self.predict_notification:
		frappe.throw(f"{self.product} Requires Predict")
	
	if self.product in ["B2BI", "B2B"] and self.recipient_country != 'CH' and not self.recipient_email:
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
	if (len(cstr(self.sender_country)) != 2) or (len(cstr(self.recipient_country)) != 2):
		frappe.throw("Country Must be 2-Char ISO Code (e.g., CH)")
	

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
			pickup_from_time = datetime.strptime(cstr(self.pickup_from_time), time_format)
			pickup_to_time = datetime.strptime(cstr(self.pickup_to_time), time_format)
			if pickup_from_time >= pickup_to_time:
				frappe.throw("Pickup From Time Must Be Less Than Pickup To Time")

def validate_current_auth_token():
	dpd_settings_data = frappe.db.get_value("DPD Settings", "DPD Settings", ["auth_token", "token_expires_on"], as_dict=1) or {}
	if dpd_settings_data.get("auth_token") and dpd_settings_data.get("token_expires_on"):
		token_expiry_date = datetime.fromisoformat(dpd_settings_data.get("token_expires_on"))
		now = datetime.now(token_expiry_date.tzinfo)
		if token_expiry_date < now:
			frappe.throw("Cannot Create Shipment Because Current Authentication Token is Expired")
		
def post_shipment_request(self):
	dpd_settings_values = frappe.db.get_value("DPD Settings", "DPD Settings", ["delis_id", "auth_token", "message_language", "depot", "customerUid", "shipment_service_endpoint"], as_dict=1) or {}
	post_request_data = {"authentication":None, "storeOrders": None}
	if dpd_settings_values:
		if dpd_settings_values.get("shipment_service_endpoint"):
			if dpd_settings_values.get("delis_id") and dpd_settings_values.get("auth_token") and dpd_settings_values.get("message_language"):
				post_request_data["authentication"] = {"delisId": dpd_settings_values.get("delis_id"), "authToken": dpd_settings_values.get("auth_token"), "messageLanguage":dpd_settings_values.get("message_language")}
				store_orders = {"printOptions": None, "order": []}
			if self.printer_language and self.paper_format:
				store_orders["printOptions"] = {"printerLanguage": self.printer_language, "paperFormat": self.paper_format}

			shipment_data = {}
			order_data  = {}
			if dpd_settings_values.get("depot"):
				shipment_data["sendingDepot"] = dpd_settings_values.get("depot")
			if self.product:
				shipment_data["product"] = self.product
			if self.sender_name_1 and self.sender_street and self.sender_country and self.sender_postal_code and self.sender_city:
				shipment_data["sender"] = {
					"name1": self.sender_name_1,
					"street": self.sender_street,
					"country": self.sender_country,
					"zipCode": self.sender_postal_code,
					"city": self.sender_city
				}
			if self.recipient_name_1 and self.recipient_street and self.recipient_country and self.recipient_postal_code and self.recipient_city:
				shipment_data["recipient"] = {
					"name1": self.recipient_name_1,
					"street": self.recipient_street,
					"country": self.recipient_country,
					"zipCode": self.recipient_postal_code,
					"city": self.recipient_city
				}
			order_data["generalShipmentData"] = shipment_data
			parcels = []
			for row in self.parcels:
				new_row = {
					"weight": flt(row.get("weight_in_grams")),
					"customerReferenceNumber1": cstr(row.get("customer_reference_1"))
				}
				parcels.append(json.loads(frappe.as_json(new_row))) 
		
			order_data["parcels"] = parcels
			if self.order_type:
				order_data["productAndServiceData"] = {"orderType": cstr(self.order_type)}
			
			store_orders["order"].append(order_data)
			post_request_data["storeOrders"] = store_orders
			if post_request_data.get("authentication") and post_request_data.get("storeOrders"):
				response_log_filters = {
					"method": dpd_settings_values.get("shipment_service_endpoint"),
					"request_payload": post_request_data,
					"response_status": None,
					"response_json": None,
					"timestamp": None,
					"error_message": None,
					"reference_document": self.doctype,
					"reference_record": self.name
				}
				headers = {"Content-Type": "application/json"}
				payload = post_request_data
				response_json = make_call(cstr(dpd_settings_values.get("shipment_service_endpoint")), "POST", headers, payload)
				response_log_filters['timestamp'] = frappe.utils.now()
				if response_json:
					response_log_filters['response_status'] = "Success"
					response_log_filters['response_json'] = response_json
					create_api_log(response_log_filters)
					reponse_object = response_json
					if reponse_object:
						order_result = reponse_object.get("orderResult")
						if order_result:
							if order_result.get("parcellabelsPDF"):
								pdf_base64 = cstr(order_result.get("parcellabelsPDF"))
								pdf_base64 = pdf_base64.replace('\n', "").replace("\r", "").replace(" ", "")
								if not pdf_base64:
									frappe.throw("Received empty PDF label from DPD")
								try:
									pdf_data = base64.b64decode(pdf_base64, validate=True)
								except Exception as e:
									frappe.throw(f"Failed to decode PDF label: {e}") 
								if not pdf_data.startswith(b"%PDF"):
									frappe.log_error(f"Invalid PDF data received, first bytes: {pdf_data[:20]}", "DPD PDF Error")
									frappe.throw("Received invalid PDF data from DPD")

								output_file_name = "DPD-Label.pdf"
								image = save_file(output_file_name, pdf_data, "DPD Shipment", self.name, decode=False, is_private=0) 
								self.label_generated = 1
								self.status = 'Label Generated'
								self.label_pdf_data = pdf_base64
				else:
					response_log_filters['response_status'] = "Failed"
					response_log_filters['response_json'] = response_json
					if response_json[0].get("status"):
						if response_json[0].get("status").get("message"):
							response_log_filters['error_message'] = cstr(response_json[0].get("status").get("message"))
					create_api_log(response_log_filters)
					frappe.throw("Failed to Post Shipment Request")


