import streamlit as st
from duckduckgo_search import DDGS
import re
import time

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Real Estate ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'data_source' not in st.session_state:
    st.session_state['data_source'] = ""

st.title("🏙️ Real Estate ROI Calculator")
st.markdown("Automated Market Data via **Smart Database** + **Live Search**.")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("1. Property Details")
    property_type = st.selectbox("Property Type", ["Apartment", "Villa", "Townhouse"])
    
    # Common Dubai Locations (Matches DB keys)
    top_locations = [
        "Dubai Marina", "Jumeirah Village Circle (JVC)", "Downtown Dubai", 
        "Business Bay", "Palm Jumeirah", "Jumeirah Lake Towers (JLT)",
        "Dubai Hills Estate", "Dubai Creek Harbour", "The Springs", 
        "Arabian Ranches", "Arabian Ranches 3", "Damac Hills 2", 
        "Motor City", "Town Square", "Discovery Gardens", "Arjan"
    ]
    location_input = st.selectbox("Location (or type custom)", top_locations + ["Other..."])
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

# --- LAYER 1: MASSIVE STATIC DATABASE (Q1 2026 DATA) ---
# Data sourced from Bayut/PropertyFinder/DLD Reports Feb 2026
MARKET_DB = {
    # APARTMENT ZONES
    "dubai-marina": {"studio": 90000, "1-bedroom": 140000, "2-bedroom": 215000, "3-bedroom": 310000, "4-bedroom": 450000},
    "jumeirah-village-circle": {"studio": 52000, "1-bedroom": 75000, "2-bedroom": 115000, "3-bedroom": 160000},
    "jumeirah-village-circle-(jvc)": {"studio": 52000, "1-bedroom": 75000, "2-bedroom": 115000, "3-bedroom": 160000},
    "downtown-dubai": {"studio": 115000, "1-bedroom": 190000, "2-bedroom": 360000, "3-bedroom": 520000},
    "business-bay": {"studio": 90000, "1-bedroom": 130000, "2-bedroom": 195000, "3-bedroom": 290000},
    "palm-jumeirah": {"studio": 145000, "1-bedroom": 230000, "2-bedroom": 390000, "3-bedroom": 560000},
    "jumeirah-lake-towers": {"studio": 75000, "1-bedroom": 115000, "2-bedroom": 165000, "3-bedroom": 230000},
    "jumeirah-lake-towers-(jlt)": {"studio": 75000, "1-bedroom": 115000, "2-bedroom": 165000, "3-bedroom": 230000},
    "dubai-hills-estate": {"studio": 78000, "1-bedroom": 110000, "2-bedroom": 175000, "3-bedroom": 280000},
    "dubai-creek-harbour": {"1-bedroom": 115000, "2-bedroom": 175000, "3-bedroom": 290000},
    "motor-city": {"studio": 55000, "1-bedroom": 85000, "2-bedroom": 135000, "3-bedroom": 190000},
    "discovery-gardens": {"studio": 48000, "1-bedroom": 68000, "2-bedroom": 95000},
    "arjan": {"studio": 50000, "1-bedroom": 72000, "2-bedroom": 105000, "3-bedroom": 145000},
    
    # VILLA/TOWNHOUSE ZONES
    "the-springs": {"2-bedroom": 155000, "3-bedroom": 210000, "4-bedroom": 240000},
    "arabian-ranches": {"2-bedroom": 165000, "3-bedroom": 225000, "4-bedroom": 350000, "5-bedroom": 450000},
    "arabian-ranches-3": {"3-bedroom": 150000, "4-bedroom": 190000},
    "damac-hills-2": {"2-bedroom": 85000, "3-bedroom": 110000, "4-bedroom": 130000, "5-bedroom": 150000},
    "town-square": {"3-bedroom": 145000, "4-bedroom": 175000},
    "dubai-hills-estate": {"3-bedroom": 320000, "4-bedroom": 380000, "5-bedroom": 450000}, # Villas overlap name
}

def clean_slug(loc):
    return loc.lower().strip().replace(" ", "-")

def get_database_rent(loc, unit, prop_type):
    slug = clean_slug(loc)
    unit_key = unit.lower().replace(" ", "-") # "1-bedroom" or "studio"
    
    # 1. Direct Lookup
    if slug in MARKET_DB:
        val = MARKET_DB[slug].get(unit_key, 0)
        if val > 0: return val, "Direct Database Match"
        
        # 2. Smart Fallback (Estimation)
        # If user asks for "Studio Townhouse" (doesn't exist), give them nothing?
        # No, better to try to map.
        if "studio" in unit_key and "1-bedroom" in MARKET_DB[slug]:
             return int(MARKET_DB[slug]["1-bedroom"] * 0.7), "Estimated (Studio ~70% of 1-Bed)"
             
    return 0, ""

# --- LAYER 2: LIVE SEARCH (BACKUP) ---
def parse_price(text):
    clean = re.sub(r'[^\d.]', '', text)
    if clean: return int(float(clean))
    return 0

def fetch_search_data(loc, unit, prop):
    # Query: "Average rent 1 bedroom apartment dubai marina bayut"
    query = f"average yearly rent {unit} {prop} {loc} bayut"
    
    try:
        # backend="html" is lighter and less likely to block
        results = DDGS().text(query, max_results=3, backend="html")
        for r in results:
            text = (r.get('title', '') + " " + r.get('body', '')).lower()
            
            # Look for explicit "AED 150,000" pattern
            match = re.search(r'aed\s*([\d,]+)', text)
            if match:
                val = parse_price(match.group(1))
                if val > 20000: return val
                
            # Look for "150k"
            match_k = re.search(r'([\d\.]+)k\s*yearly', text)
            if match_k:
                val = int(float(match_k.group(1)) * 1000)
                if val > 20000: return val
                
        return 0
    except Exception as e:
        return 0

# --- EXECUTION ---
if calc_button:
    with st.status("🔍 Analyzing Market Data...", expanded=True) as status:
        rent = 0
        source = ""
        
        # 1. Check Database First (Instant & Reliable)
        st.write("Checking Internal Database...")
        rent, msg = get_database_rent(location_input, unit_conf, property_type)
        if rent > 0:
            source = f"Internal Database ({msg})"
        
        # 2. If DB fails, try Live Search
        if rent == 0:
            st.write("Database miss. Checking Live Search...")
            rent = fetch_search_data(location_input, unit_conf, property_type)
            if rent > 0:
                source = "Live Search Snippet"
        
        # 3. Final State
        st.session_state['scraped_rent'] = rent
        st.session_state['data_source'] = source
        st.session_state['data_fetched'] = True
        
        # Link Generation
        loc_slug = clean_slug(location_input)
        bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
        st.session_state['final_url'] = f"https://www.bayut.com/to-rent/property/dubai/{loc_slug}/?beds={bed_slug}"
        
        if rent > 0:
            status.update(label=f"Data Found! Source: {source}", state="complete", expanded=False)
        else:
            status.update(label="All sources failed. Enter manually.", state="error", expanded=True)

# --- RESULTS ---
if st.session_state['data_fetched']:
    st.divider()
    
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.session_state['scraped_rent'] > 0:
            st.success(f"✅ Market Rent: **AED {st.session_state['scraped_rent']:,.0f}**")
            st.caption(f"Source: {st.session_state['data_source']}")
            final_rent = st.number_input("Annual Rent", value=float(st.session_state['scraped_rent']))
        else:
            st.warning("⚠️ Could not find data. Enter manually.")
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
