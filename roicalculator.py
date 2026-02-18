import streamlit as st
import re
import os
import time
from playwright.sync_api import sync_playwright

# --- 1. FORCE BROWSER INSTALLATION (CRITICAL FOR CLOUD) ---
# This ensures Chromium is installed even if the cloud environment forgets it.
try:
    os.system("playwright install chromium")
except:
    pass

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Dubai ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'final_url' not in st.session_state:
    st.session_state['final_url'] = ""
if 'debug_error' not in st.session_state:
    st.session_state['debug_error'] = ""

st.title("🏙️ Dubai Real Estate ROI Calculator")
st.markdown("Automated Bayut Scraper for **New Contract** transactions.")

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

# --- SCRAPER LOGIC ---
def parse_abbreviated_number(text):
    clean = text.upper().replace(',', '').replace('AED', '').strip()
    multiplier = 1
    if 'M' in clean:
        multiplier = 1000000
        clean = clean.replace('M', '')
    elif 'K' in clean:
        multiplier = 1000
        clean = clean.replace('K', '')
    match = re.search(r'([\d\.]+)', clean)
    if match:
        return int(float(match.group(1)) * multiplier)
    return None

def scrape_data(url):
    try:
        with sync_playwright() as p:
            # --- 2. STEALTH MODE + HEADLESS ---
            browser = p.chromium.launch(headless=True)
            
            # Use a fake "User Agent" so Bayut thinks we are a real person
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # --- 3. PATIENCE (Increased Timeout) ---
            page.goto(url, timeout=60000) # 60 seconds max
            
            # Look for "Average Yearly Rental"
            # We wait up to 15 seconds for the text to appear
            label_locator = page.get_by_text("Average Yearly Rental", exact=False).first
            label_locator.wait_for(timeout=15000)
            
            # Grab the parent container
            container = label_locator.locator("..").locator("..") 
            text_block = container.inner_text()
            
            browser.close()
            
            # Parse results
            lines = text_block.split('\n')
            possible_values = []
            for line in lines:
                if "Average" in line or "Rental" in line or "%" in line or not line.strip():
                    continue
                val = parse_abbreviated_number(line)
                if val and val > 10000: 
                    possible_values.append(val)
            
            return possible_values[0] if possible_values else 0, "No valid number found in text block."
            
    except Exception as e:
        return 0, str(e)

# --- EMOJI LOGIC ---
def get_roi_emoji(roi):
    if roi >= 8.0: return "🟢" 
    elif roi >= 6.0: return "🟢" 
    elif roi >= 4.0: return "🟡" 
    else: return "🔴" 

# --- EXECUTION ---
if st.button("Calculate ROI"):
    loc_slug = location.lower().strip().replace(" ", "-")
    p_slug = "townhouses" if property_type == "Townhouse" else property_type.lower() + "s"
    bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
    
    target_url = f"https://www.bayut.com/property-market-analysis/transactions/rent/{bed_slug}-{p_slug}/dubai/{loc_slug}/?contract_renewal_status=New"
    st.session_state['final_url'] = target_url
    st.session_state['debug_error'] = ""
    
    with st.status("🔍 Syncing with Bayut (Cloud Mode)...", expanded=True) as status:
        rent, error_msg = scrape_data(target_url)
        st.session_state['scraped_rent'] = rent
        
        if rent > 0:
            st.session_state['data_fetched'] = True
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            st.session_state['data_fetched'] = True # Show manual input anyway
            st.session_state['debug_error'] = error_msg
            status.update(label="Auto-scrape failed (See below)", state="error", expanded=True)

# --- RESULTS DISPLAY ---
if st.session_state['data_fetched']:
    st.divider()
    
    col_input, col_link = st.columns([3, 1])
    with col_input:
        if st.session_state['scraped_rent'] > 0:
            st.success(f"✅ Market Rent Found: **AED {st.session_state['scraped_rent']:,.0f}**")
            final_rent = st.number_input("Annual Rent (AED)", value=float(st.session_state['scraped_rent']))
        else:
            st.warning("⚠️ Auto-scrape failed. Enter manually.")
            if st.session_state['debug_error']:
                st.caption(f"Debug Info: {st.session_state['debug_error']}")
            final_rent = st.number_input("Manual Rent (AED)", value=0.0)
            
    with col_link:
        st.markdown(f"<br><a href='{st.session_state['final_url']}' target='_blank'>Verify on Bayut ↗</a>", unsafe_allow_html=True)
            
    if final_rent > 0:
        total_cost = unit_price + (unit_price * 0.04) + (unit_price * (commission_pct/100)) + 4580
        net = (final_rent * (occupancy_rate/100)) - (unit_size * service_charge_per_sqft)
        roi = (net / total_cost) * 100
        
        st.divider()
        st.subheader(f"📊 ROI Analysis for {unit_conf} in {location}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investment", f"{total_cost:,.0f} AED")
        c2.metric("Net Income", f"{net:,.0f} AED")
        c3.metric("NET ROI", f"{get_roi_emoji(roi)} {roi:.2f}%")