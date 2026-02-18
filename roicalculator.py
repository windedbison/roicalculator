import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Real Estate ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'debug_log' not in st.session_state:
    st.session_state['debug_log'] = ""

st.title("🏙️ Real Estate ROI Calculator")
st.markdown("Automated Market Data via **PropSearch Table Extraction**.")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("1. Property Details")
    property_type = st.selectbox("Property Type", ["Apartment", "Villa", "Townhouse"])
    
    # Common Locations + Custom
    top_locations = [
        "Dubai Marina", "Jumeirah Village Circle (JVC)", "Downtown Dubai", 
        "Business Bay", "Palm Jumeirah", "Jumeirah Lake Towers (JLT)",
        "Dubai Hills Estate", "Dubai Creek Harbour", "The Springs", 
        "Arabian Ranches", "Damac Hills 2", "Motor City", "Town Square"
    ]
    location_input = st.selectbox("Location", top_locations + ["Other..."])
    if location_input == "Other...":
        location_input = st.text_input("Enter Location Name")
    
    if property_type == "Apartment":
        unit_options = ["Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom", "4 Bedroom"]
    else:
        unit_options = ["2 Bedroom", "3 Bedroom", "4 Bedroom", "5 Bedroom", "6 Bedroom"]
        
    unit_conf = st.selectbox("Unit Configuration", unit_options)
    
    st.divider()
    calc_button = st.button("Calculate ROI", type="primary", use_container_width=True)

    # Financials
    st.header("Financials")
    unit_price = st.number_input("Purchase Price (AED)", min_value=100000, value=1500000, step=50000)
    unit_size = st.number_input("Unit Size (Sq. Ft)", min_value=100, value=800, step=50)
    service_charge_per_sqft = st.number_input("Service Charge (AED/sq.ft)", value=15.0)
    commission_pct = st.number_input("Commission (%)", value=2.0)
    occupancy_rate = st.slider("Occupancy (%)", 50, 100, 90)

# --- HELPER: URL SLUGIFIER ---
def get_slug(loc):
    # PropSearch URL mapping
    mapping = {
        "jvc": "jumeirah-village-circle",
        "jlt": "jumeirah-lake-towers",
        "springs": "the-springs",
        "meadows": "the-meadows",
        "ranches": "arabian-ranches",
        "hills estate": "dubai-hills-estate"
    }
    clean = loc.lower().strip()
    
    # Check known aliases
    for key, val in mapping.items():
        if key in clean: return val
        
    return clean.replace(" ", "-")

# --- CORE LOGIC: TABLE EXTRACTOR ---
def parse_price(text):
    # Handles "150,000 AED" or "150k"
    clean = re.sub(r'[^\d.]', '', text.lower().replace('k', '000'))
    if clean: return int(float(clean))
    return 0

def fetch_propsearch_table(loc_name, unit_conf):
    slug = get_slug(loc_name)
    url = f"https://propsearch.ae/dubai/{slug}"
    
    headers = {"User-Agent": "Mozilla/5.0"}
    log = [f"Checking: {url}"]
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return 0, f"PropSearch returned {response.status_code}", url

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. FIND ALL TABLES
        # PropSearch often puts data in generic <table> tags
        tables = soup.find_all("table")
        if not tables:
            return 0, "No tables found on page.", url

        # 2. SCAN TABLES FOR RENT DATA
        target_bed = unit_conf.split()[0].lower() # "studio", "1", "2"
        best_price = 0
        
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                text = row.get_text(" ").lower()
                
                # Check if row has "Rent" or "Price" context
                # And matches our bedroom count
                
                # Match Logic:
                # 1. Must contain the unit type (e.g. "1 bed", "studio")
                is_match = False
                if "studio" in target_bed and "studio" in text: is_match = True
                elif target_bed in text and ("bed" in text or "br" in text): is_match = True
                
                if is_match:
                    # Extract all numbers from this row
                    # We look for numbers > 20,000 (likely rent)
                    candidates = re.findall(r'([\d,]{3,})', text)
                    for c in candidates:
                        val = parse_price(c)
                        if 25000 < val < 800000: # Sanity check range
                            best_price = val
                            log.append(f"Found match in row: '{text.strip()[:50]}...' -> {val}")
                            # If we find a match, we prefer "Average" if noted, otherwise take first
                            if "avg" in text or "average" in text:
                                return val, "\n".join(log), url
        
        if best_price > 0:
            return best_price, "\n".join(log), url
            
        return 0, "Table parsed but no matching unit price found.\n" + "\n".join(log), url

    except Exception as e:
        return 0, str(e), url

# --- EXECUTION ---
if calc_button:
    with st.status("🔍 Scanning PropSearch Market Tables...", expanded=True) as status:
        rent, debug, final_url = fetch_propsearch_table(location_input, unit_conf)
        
        st.session_state['scraped_rent'] = rent
        st.session_state['debug_log'] = debug
        st.session_state['data_fetched'] = True
        st.session_state['final_url'] = final_url # Link to PropSearch source
        
        if rent > 0:
            status.update(label="Data Extracted Successfully!", state="complete", expanded=False)
        else:
            status.update(label="Could not find exact unit match.", state="error", expanded=True)

# --- RESULTS ---
if st.session_state['data_fetched']:
    st.divider()
    
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.session_state['scraped_rent'] > 0:
            st.success(f"✅ Market Rent: **AED {st.session_state['scraped_rent']:,.0f}**")
            final_rent = st.number_input("Annual Rent", value=float(st.session_state['scraped_rent']))
        else:
            st.warning("⚠️ Enter Manually")
            with st.expander("Show Debug Log"):
                st.text(st.session_state['debug_log'])
            final_rent = st.number_input("Manual Rent", value=0.0)
            
    with c2:
        st.markdown(f"<br><a href='{st.session_state['final_url']}' target='_blank'>View Source on PropSearch ↗</a>", unsafe_allow_html=True)
    
    if final_rent > 0:
        total = unit_price * (1 + 0.04 + (commission_pct/100)) + 4580
        net = (final_rent * (occupancy_rate/100)) - (unit_size * service_charge_per_sqft)
        roi = (net / total) * 100
        
        emoji = "🔴"
        if roi >= 8: emoji = "🟢"
        elif roi >= 6: emoji = "🟢"
        elif roi >= 4: emoji = "🟡"
        
        st.divider()
        st.subheader("📊 ROI Results")
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Investment", f"{total:,.0f} AED")
        m2.metric("Net Income", f"{net:,.0f} AED")
        m3.metric("NET ROI", f"{emoji} {roi:.2f}%")
