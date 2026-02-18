import streamlit as st
import re
from duckduckgo_search import DDGS

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Dubai ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False

st.title("🏙️ Dubai Real Estate ROI Calculator")
st.markdown("Uses **Smart Search** to find market data without getting blocked.")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("1. Property Details")
    property_type = st.selectbox("Property Type", ["Apartment", "Villa", "Townhouse"])
    location = st.text_input("Location", value="Dubai Marina")
    
    if property_type == "Apartment":
        unit_options = ["Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom", "4 Bedroom"]
    else:
        unit_options = ["2 Bedroom", "3 Bedroom", "4 Bedroom", "5 Bedroom", "6 Bedroom"]
        
    unit_conf = st.selectbox("Unit Configuration", unit_options)
    unit_price = st.number_input("Purchase Price (AED)", min_value=100000, value=1500000, step=50000)
    unit_size = st.number_input("Unit Size (Sq. Ft)", min_value=100, value=800, step=50)

    st.header("2. Costs & Fees")
    service_charge_per_sqft = st.number_input("Service Charge (AED/sq.ft)", min_value=0.0, value=18.0, step=0.5)
    commission_pct = st.slider("Agency Commission (%)", 0.0, 5.0, 2.0, 0.1)
    
    st.header("3. Operational")
    occupancy_rate = st.slider("Occupancy Rate (%)", 50, 100, 85, 5)
    
    st.divider()
    calc_button = st.button("Calculate ROI", type="primary", use_container_width=True)

# --- SEARCH LOGIC ---
def extract_money(text):
    # Finds "AED 150,000" or "150k" or "150,000"
    # Remove commas
    clean = text.lower().replace(',', '')
    
    # Priority 1: "AED 150000"
    match = re.search(r'aed\s*(\d+)', clean)
    if match: return int(match.group(1))
    
    # Priority 2: "150k"
    match = re.search(r'(\d+)k', clean)
    if match: return int(match.group(1)) * 1000
    
    return 0

def smart_search(query):
    try:
        results = DDGS().text(query, max_results=5)
        for r in results:
            text = (r['title'] + " " + r['body']).lower()
            # Look for pricing keywords
            if "average" in text or "price" in text or "rent" in text:
                price = extract_money(text)
                if price > 20000: # Filter out low noise
                    return price, r['href']
        return 0, ""
    except Exception as e:
        return 0, ""

# --- MAIN APP ---
if calc_button:
    # Query: "Average rent 2 bedroom apartment dubai marina bayut"
    query = f"average yearly rent {unit_conf} {property_type} {location} bayut"
    
    with st.status("🔍 Searching Market Data...", expanded=True) as status:
        rent, link = smart_search(query)
        st.session_state['scraped_rent'] = rent
        st.session_state['final_url'] = link
        st.session_state['data_fetched'] = True
        
        if rent > 0:
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            status.update(label="Could not find exact data.", state="error", expanded=False)

if st.session_state['data_fetched']:
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.session_state['scraped_rent'] > 0:
            st.success(f"✅ Market Rent: **AED {st.session_state['scraped_rent']:,.0f}**")
            final_rent = st.number_input("Annual Rent (AED)", value=float(st.session_state['scraped_rent']))
        else:
            st.warning("⚠️ Enter Rent Manually")
            final_rent = st.number_input("Manual Rent (AED)", value=0.0)
            
    with col2:
        if st.session_state['final_url']:
            st.markdown(f"<br><a href='{st.session_state['final_url']}' target='_blank'>Verify Source ↗</a>", unsafe_allow_html=True)

    if final_rent > 0:
        total_cost = unit_price * (1 + 0.04 + (commission_pct/100)) + 4580
        net = (final_rent * (occupancy_rate/100)) - (unit_size * service_charge_per_sqft)
        roi = (net / total_cost) * 100
        
        emoji = "🔴"
        if roi >= 8: emoji = "🟢"
        elif roi >= 6: emoji = "🟢"
        elif roi >= 4: emoji = "🟡"
        
        st.divider()
        st.subheader(f"📊 ROI Analysis")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investment", f"{total_cost:,.0f} AED")
        c2.metric("Net Income", f"{net:,.0f} AED")
        c3.metric("NET ROI", f"{emoji} {roi:.2f}%")
