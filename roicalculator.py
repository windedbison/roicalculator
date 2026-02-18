import streamlit as st
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import re

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
st.markdown("Automated Market Data via **PropSearch** & **Smart Search**.")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("1. Property Details")
    property_type = st.selectbox("Property Type", ["Apartment", "Villa", "Townhouse"])
    # Helper for location
    location_input = st.text_input("Location", value="Dubai Marina")
    
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

# --- HELPER: CLEAN PRICE ---
def parse_price(text):
    # Extracts "150k" or "150,000"
    text = text.lower()
    multiplier = 1
    if 'k' in text: multiplier = 1000
    if 'm' in text: multiplier = 1000000
    
    clean = re.sub(r'[^\d.]', '', text)
    if clean:
        return int(float(clean) * multiplier)
    return 0

# --- HELPER: SMART SLUGIFIER ---
def get_propsearch_slug(raw_loc):
    # PropSearch is picky. We map common abbreviations to full names.
    lookup = {
        "jvc": "jumeirah-village-circle",
        "jlt": "jumeirah-lake-towers",
        "difc": "difc", # Actually this one is fine
        "downtown": "downtown-dubai",
        "business bay": "business-bay",
        "palm jumeirah": "palm-jumeirah",
        "dubai hills": "dubai-hills-estate",
        "creek harbour": "dubai-creek-harbour",
        "springs": "the-springs",
        "meadows": "the-meadows",
        "arabian ranches": "arabian-ranches",
        "motor city": "motor-city",
        "sports city": "dubai-sports-city"
    }
    
    raw = raw_loc.lower().strip()
    if raw in lookup:
        return lookup[raw]
    return raw.replace(" ", "-")

# --- SOURCE 1: PROPSEARCH AGGREGATOR ---
def fetch_propsearch(loc_name, unit_conf, prop_type):
    slug = get_propsearch_slug(loc_name)
    url = f"https://propsearch.ae/dubai/{slug}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 404:
            return 0, f"Location '{slug}' not found on PropSearch."
        if response.status_code != 200:
            return 0, f"PropSearch blocked/down ({response.status_code})."
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # PropSearch Table Logic
        # We look for a table row that matches "1 Bed" or "Studio"
        
        # Convert "1 Bedroom" -> "1 Bed"
        search_term = unit_conf.replace("Bedroom", "Bed").replace("Studio", "Studio")
        
        # Scan all table rows
        rows = soup.find_all("tr")
        debug_rows = []
        
        for row in rows:
            text = row.get_text().strip()
            debug_rows.append(text)
            
            # Check if row contains our unit type AND has a price
            if search_term in text and "AED" in text:
                # Extract the price
                match = re.search(r'([\d,]+)\s*AED', text)
                if match:
                    return parse_price(match.group(1)), "Success"
                    
                # Alternative format: "100k"
                match_k = re.search(r'([\d\.]+)k', text.lower())
                if match_k:
                    return int(float(match_k.group(1)) * 1000), "Success"

        return 0, f"Page loaded, but table didn't match '{search_term}'. Found rows: {str(debug_rows[:3])}..."

    except Exception as e:
        return 0, str(e)

# --- SOURCE 2: DUCKDUCKGO (BACKUP) ---
def fetch_duckduckgo(loc_name, unit_conf, prop_type):
    # Query: "Average rent 1 bedroom apartment dubai marina bayut"
    query = f"average yearly rent {unit_conf} {prop_type} {loc_name} bayut ae"
    
    try:
        results = DDGS().text(query, max_results=3)
        for r in results:
            snippet = r.get('body', '') + " " + r.get('title', '')
            # Look for "AED 150,000" or "150k"
            
            # Regex 1: AED 150,000
            match = re.search(r'AED\s*([\d,]+)', snippet, re.IGNORECASE)
            if match:
                val = parse_price(match.group(1))
                if val > 20000: return val, "DuckDuckGo Snippet"
                
            # Regex 2: 150k
            match = re.search(r'([\d\.]+)k\s*yearly', snippet, re.IGNORECASE)
            if match:
                val = int(float(match.group(1)) * 1000)
                if val > 20000: return val, "DuckDuckGo Snippet"
                
        return 0, "No data in search results."
    except Exception as e:
        return 0, str(e)

# --- EXECUTION ---
if calc_button:
    
    with st.status("🔍 Searching Market Data...", expanded=True) as status:
        # 1. Try PropSearch
        st.write("Checking PropSearch...")
        rent, msg = fetch_propsearch(location_input, unit_conf, property_type)
        
        # 2. Try DuckDuckGo if PropSearch fails
        if rent == 0:
            st.write(f"PropSearch failed ({msg}). Checking Search Engine...")
            rent, msg = fetch_duckduckgo(location_input, unit_conf, property_type)
            
        st.session_state['scraped_rent'] = rent
        st.session_state['debug_log'] = msg
        st.session_state['data_fetched'] = True
        
        # Generate Verification Link
        loc_slug = location_input.lower().strip().replace(" ", "-")
        bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
        st.session_state['final_url'] = f"https://www.bayut.com/to-rent/property/dubai/{loc_slug}/?beds={bed_slug}"
        
        if rent > 0:
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            status.update(label="All sources failed.", state="error", expanded=True)

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
            with st.expander("Why did it fail?"):
                st.text(st.session_state['debug_log'])
            final_rent = st.number_input("Manual Rent", value=0.0)
            
    with c2:
        st.markdown(f"<br><a href='{st.session_state['final_url']}' target='_blank'>Verify on Bayut ↗</a>", unsafe_allow_html=True)
    
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
