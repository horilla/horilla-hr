"""
company_onboarding/gst_states.py

Indian states/UTs mapped to their 2-digit GST state code, used by
CompanyStateRegistration's `state` choices and the GSTIN-prefix cross-check.
Source: CBIC GST state code list. Kept local to this app rather than
base/countries.py since it's GST-specific, not a general geography list
(base/countries.py has no India entry in its states list at all).
"""

INDIA_STATE_GST_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}

STATE_CHOICES = tuple(INDIA_STATE_GST_CODES.items())


def gst_code_for_state(state_code: str) -> str | None:
    """
    state_code here is the dict key itself (e.g. '27'); trivial today,
    kept as a function so callers have one place to change if the choice
    representation ever moves away from "code is the stored value".
    """
    return state_code if state_code in INDIA_STATE_GST_CODES else None
