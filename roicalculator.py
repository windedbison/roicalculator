import re
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Real Estate ROI Calculator", layout="wide")

st.title("🏙️ Real Estate ROI Calculator")
st.markdown("Direct Data Integration: **Dubai Land Department (DLD) Open Data**.")

if "scraped_rent" not in st.session_state:
    st.session_state["scraped_rent"] = 0
if "data_fetched" not in st.session_state:
    st.session_state["data_fetched"] = False
if "fetch_debug" not in st.session_state:
    st.session_state["fetch_debug"] = {}

DLD_ENDPOINT = "https://api.dubaipulse.gov.ae/open/dld/dld_transactions-open"

DATE_KEYS = [
    "instance_date",
    "transaction_date",
    "procedure_date",
    "contract_date",
    "registration_date",
    "created_date",
    "start_date",
]

STATUS_KEYS = [
    "contract_renewal_status",
    "renewal_status",
    "is_renewal",
    "contract_type_en",
    "contract_type",
]

UNIT_KEYS = [
    "property_sub_type_en",
    "property_type_en",
    "unit_type_en",
    "unit_type",
    "rooms_en",
    "rooms",
    "room_count",
    "bedrooms",
]

RENT_KEYS = [
    "annual_rent",
    "annual_rent_amount",
    "annual_amount",
    "yearly_rent",
    "yearly_amount",
    "rent_amount",
    "actual_worth",
    "contract_amount",
    "amount",
    "monthly_rent",
]

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("1. Property Details")
    property_type = st.selectbox("Property Type", ["Apartment", "Villa", "Townhouse"])
    
    # DLD Area Names are specific. We provide common ones.
    top_areas = [
        "Dubai Marina", "Business Bay", "Downtown Dubai", "Jumeirah Village Circle",
        "Palm Jumeirah", "Jumeirah Lake Towers", "Dubai Hills Estate", 
        "Dubai Creek Harbour", "The Springs", "Arabian Ranches", "Motor City"
    ]
    location = st.selectbox("Area Name", top_areas)
    
    if property_type == "Apartment":
        unit_conf = st.selectbox("Unit Type", ["Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom"])
    else:
        unit_conf = st.selectbox("Unit Type", ["2 Bedroom", "3 Bedroom", "4 Bedroom", "5 Bedroom"])

    st.divider()
    calc_button = st.button("Calculate ROI", type="primary", use_container_width=True)

    # Financials
    st.header("2. Financials")
    unit_price = st.number_input("Purchase Price (AED)", min_value=100000, value=1500000, step=50000)
    unit_size = st.number_input("Unit Size (Sq. Ft)", min_value=100, value=800, step=50)
    service_charge = st.number_input("Service Charge (AED/sq.ft)", value=16.0)
    commission_pct = st.number_input("Agency Commission (%)", value=2.0)
    occupancy = st.slider("Occupancy Rate (%)", 50, 100, 92)

# --- DLD API LOGIC ---
def normalize_record(record):
    return {str(key).strip().lower(): value for key, value in record.items()}


def parse_amount(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).upper().replace(",", "").replace("AED", "").replace("DH", "").strip()
    if not text:
        return None

    multiplier = 1.0
    if text.endswith("M"):
        multiplier = 1_000_000.0
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000.0
        text = text[:-1]

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    amount = float(match.group()) * multiplier
    if amount <= 0:
        return None
    return amount


def parse_datetime(value):
    if value is None:
        return None

    dt_value = None
    if isinstance(value, datetime):
        dt_value = value
    elif isinstance(value, (int, float)):
        ts = float(value)
        if 10_000_000 <= ts <= 99_999_999:
            try:
                dt_value = datetime.strptime(str(int(ts)), "%Y%m%d")
            except ValueError:
                dt_value = None
        if ts > 10**12:
            ts = ts / 1000.0
        if dt_value is None and ts > 10**9:
            dt_value = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif dt_value is None and 1900 <= ts <= 2200:
            dt_value = datetime(int(ts), 1, 1, tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt_value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%m/%d/%Y",
                "%Y/%m/%d",
            ):
                try:
                    dt_value = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue

    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def extract_records(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    candidate_keys = ("data", "results", "result", "records", "items", "rows", "value")
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for nested_key in candidate_keys:
                nested_value = value.get(nested_key)
                if isinstance(nested_value, list):
                    return [item for item in nested_value if isinstance(item, dict)]

    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value

    return []


def parse_target_bedrooms(unit_type):
    text = unit_type.lower().strip()
    if "studio" in text:
        return 0
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def classify_contract_status(record):
    for key in STATUS_KEYS:
        if key not in record:
            continue

        value = record.get(key)
        if value is None:
            continue

        if isinstance(value, bool):
            return "renewal" if value else "new"
        if isinstance(value, (int, float)):
            if int(value) == 0:
                return "new"
            if int(value) == 1:
                return "renewal"

        text = str(value).strip().lower()
        if not text:
            continue
        if "renew" in text:
            return "renewal"
        if any(token in text for token in ("new", "initial", "first")):
            return "new"
        if text in ("0", "false", "no", "n"):
            return "new"
        if text in ("1", "true", "yes", "y"):
            return "renewal"

    return "unknown"


def is_rental_record(record):
    for key in ("procedure_name_en", "procedure_name", "procedure_type_en", "procedure_type"):
        if key not in record:
            continue
        text = str(record.get(key)).strip().lower()
        if not text:
            continue
        return "rent" in text or "lease" in text
    return True


def extract_record_bedrooms(record):
    bedrooms = set()
    saw_unit_field = False

    for key, value in record.items():
        is_unit_key = key in UNIT_KEYS or "bed" in key or key in ("room_count", "rooms")
        if not is_unit_key:
            continue

        if value is None:
            continue

        if isinstance(value, (int, float)):
            candidate = int(value)
            if 0 <= candidate <= 10:
                saw_unit_field = True
                bedrooms.add(candidate)
            continue

        text = str(value).strip().lower()
        if not text:
            continue
        if "studio" in text:
            saw_unit_field = True
            bedrooms.add(0)
        matches = re.findall(r"\d+", text)
        if matches:
            saw_unit_field = True
        for match in matches:
            candidate = int(match)
            if 0 <= candidate <= 10:
                bedrooms.add(candidate)

    return bedrooms, saw_unit_field


def record_matches_target_unit(record, target_bedrooms):
    bedrooms, has_unit_info = extract_record_bedrooms(record)
    if target_bedrooms is None:
        return True, has_unit_info
    if not has_unit_info:
        return False, False
    if not bedrooms:
        return False, True
    return target_bedrooms in bedrooms, True


def extract_record_date(record):
    for key in DATE_KEYS:
        if key in record:
            parsed = parse_datetime(record.get(key))
            if parsed:
                return parsed

    for key, value in record.items():
        if "date" in key:
            parsed = parse_datetime(value)
            if parsed:
                return parsed

    return None


def extract_annual_rent(record):
    for key in RENT_KEYS:
        if key not in record:
            continue
        amount = parse_amount(record.get(key))
        if amount is None:
            continue
        if "monthly" in key:
            amount *= 12
        if 10_000 <= amount <= 5_000_000:
            return amount

    for key, value in record.items():
        if not any(token in key for token in ("rent", "amount", "value", "price")):
            continue
        if any(token in key for token in ("sqft", "sqm", "service", "plot", "fee")):
            continue

        amount = parse_amount(value)
        if amount is None:
            continue
        if "monthly" in key:
            amount *= 12
        if 10_000 <= amount <= 5_000_000:
            return amount

    return None


def get_dld_rent(area_name, unit_type):
    now = datetime.now(timezone.utc)
    six_month_window_start = now - timedelta(days=183)
    target_bedrooms = parse_target_bedrooms(unit_type)

    debug = {
        "source": "dld_api",
        "area_name": area_name,
        "unit_type": unit_type,
        "target_bedrooms": target_bedrooms,
        "window_start_utc": six_month_window_start.date().isoformat(),
        "window_end_utc": now.date().isoformat(),
        "records_received": 0,
        "records_rent_procedure": 0,
        "records_new_contract": 0,
        "records_in_last_6_months": 0,
        "records_unit_match": 0,
        "records_used": 0,
        "records_not_new": 0,
        "records_status_unknown": 0,
        "records_missing_date": 0,
        "records_outside_6m": 0,
        "records_missing_unit_info": 0,
        "records_missing_rent_amount": 0,
    }

    fallback_index = {
        "Dubai Marina": {"Studio": 88000, "1 Bedroom": 142000, "2 Bedroom": 218000, "3 Bedroom": 325000},
        "Jumeirah Village Circle": {"Studio": 54000, "1 Bedroom": 82000, "2 Bedroom": 122000, "3 Bedroom": 168000},
        "Downtown Dubai": {"Studio": 118000, "1 Bedroom": 195000, "2 Bedroom": 365000, "3 Bedroom": 540000},
        "The Springs": {"2 Bedroom": 185000, "3 Bedroom": 235000, "4 Bedroom": 280000},
        "Dubai Hills Estate": {"Studio": 82000, "1 Bedroom": 118000, "2 Bedroom": 185000, "3 Bedroom": 295000},
    }

    params = {
        "area_name_en": area_name,
        "instance_format": "json",
        "procedure_name_en": "Rent",
        "contract_renewal_status": "New",
        "sort_order": "desc",
        "limit": 5000,
    }

    try:
        response = requests.get(
            DLD_ENDPOINT,
            params=params,
            timeout=15,
            headers={"Accept": "application/json"},
        )
        debug["api_status_code"] = response.status_code
        response.raise_for_status()

        payload = response.json()
        records = extract_records(payload)
        debug["records_received"] = len(records)

        rents = []
        for raw_record in records:
            if not isinstance(raw_record, dict):
                continue
            record = normalize_record(raw_record)

            if not is_rental_record(record):
                continue
            debug["records_rent_procedure"] += 1

            contract_status = classify_contract_status(record)
            if contract_status == "renewal":
                debug["records_not_new"] += 1
                continue
            if contract_status == "unknown":
                debug["records_status_unknown"] += 1
            else:
                debug["records_new_contract"] += 1

            transaction_date = extract_record_date(record)
            if not transaction_date:
                debug["records_missing_date"] += 1
                continue
            if transaction_date < six_month_window_start or transaction_date > now + timedelta(days=1):
                debug["records_outside_6m"] += 1
                continue
            debug["records_in_last_6_months"] += 1

            unit_match, has_unit_info = record_matches_target_unit(record, target_bedrooms)
            if not has_unit_info:
                debug["records_missing_unit_info"] += 1
                continue
            if not unit_match:
                continue
            debug["records_unit_match"] += 1

            rent_amount = extract_annual_rent(record)
            if rent_amount is None:
                debug["records_missing_rent_amount"] += 1
                continue

            debug["records_used"] += 1
            rents.append(rent_amount)

        if rents:
            rents_sorted = sorted(rents)
            avg_rent = int(round(sum(rents_sorted) / len(rents_sorted)))
            mid = len(rents_sorted) // 2
            if len(rents_sorted) % 2 == 1:
                median_rent = rents_sorted[mid]
            else:
                median_rent = (rents_sorted[mid - 1] + rents_sorted[mid]) / 2

            debug["sample_rents_aed"] = [int(value) for value in rents_sorted[:5]]
            debug["min_rent_aed"] = int(rents_sorted[0])
            debug["max_rent_aed"] = int(rents_sorted[-1])
            debug["avg_rent_aed"] = avg_rent
            debug["median_rent_aed"] = int(round(median_rent))
            return avg_rent, debug

        debug["source"] = "fallback_index"
        debug["fallback_reason"] = "No DLD records matched all filters."
    except requests.RequestException as exc:
        debug["source"] = "fallback_index"
        debug["fallback_reason"] = f"API request failed: {exc}"
    except ValueError as exc:
        debug["source"] = "fallback_index"
        debug["fallback_reason"] = f"Unable to parse API payload: {exc}"

    fallback_rent = fallback_index.get(area_name, {}).get(unit_type, 0)
    debug["fallback_rent_aed"] = fallback_rent
    debug["fallback_note"] = (
        "Fallback is reference only and is not guaranteed to be strictly new-contract "
        "transactions from the last 6 months."
    )
    return fallback_rent, debug

# --- EXECUTION ---
if calc_button:
    with st.status("🔗 Connecting to Dubai Land Department...", expanded=True) as status:
        rent, fetch_debug = get_dld_rent(location, unit_conf)
        st.session_state["scraped_rent"] = rent
        st.session_state["fetch_debug"] = fetch_debug
        st.session_state["data_fetched"] = True

        if rent > 0 and fetch_debug.get("source") == "dld_api":
            status.update(
                label="DLD Data Verified (new contracts, last 6 months).",
                state="complete",
                expanded=False,
            )
        elif rent > 0:
            status.update(
                label="DLD API strict filter unavailable. Fallback index value loaded.",
                state="complete",
                expanded=True,
            )
        else:
            status.update(
                label="No qualified DLD transactions found. Enter rent manually.",
                state="error",
                expanded=True,
            )

if st.session_state.get("data_fetched"):
    st.divider()

    fetch_debug = st.session_state.get("fetch_debug", {})
    source = fetch_debug.get("source", "unknown")

    col_res, col_verify = st.columns([2, 1])
    with col_res:
        if st.session_state["scraped_rent"] > 0:
            if source == "dld_api":
                st.success(f"📍 DLD 6-Month New-Contract Average: **AED {st.session_state['scraped_rent']:,.0f}**")
            else:
                st.warning(f"⚠️ Fallback Index Estimate: **AED {st.session_state['scraped_rent']:,.0f}**")
            final_rent = st.number_input("Annual Rent (AED)", value=float(st.session_state["scraped_rent"]))
        else:
            st.warning("⚠️ No DLD rows matched the strict filter. Enter annual rent manually.")
            final_rent = st.number_input("Annual Rent (AED)", value=0.0)

        if source == "dld_api":
            st.caption("Filters used: Rent procedure + New contracts + last 6 months + selected unit type.")
        else:
            st.caption("Source: fallback estimate. It may include mixed contract types and date ranges.")

    with col_verify:
        st.markdown(f"<br><a href='https://dubailand.gov.ae/en/eservices/rental-index/rental-index/' target='_blank'>Official RERA Index ↗</a>", unsafe_allow_html=True)

    with st.expander("Debug: DLD transaction filter summary"):
        st.json(fetch_debug)

    if final_rent > 0:
        total_entry = unit_price * (1 + 0.04 + (commission_pct / 100)) + 4580
        net_income = (final_rent * (occupancy / 100)) - (unit_size * service_charge)
        roi = (net_income / total_entry) * 100

        st.divider()
        st.subheader("📊 Investment Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investment", f"{total_entry:,.0f} AED")
        c2.metric("Net Annual Income", f"{net_income:,.0f} AED")

        emoji = "🟢" if roi >= 6 else "🟡" if roi >= 4 else "🔴"
        c3.metric("Net ROI", f"{emoji} {roi:.2f}%")
