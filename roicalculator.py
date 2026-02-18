import streamlit as st
import re
import os
import time
from playwright.sync_api import sync_playwright

# --- 1. FORCE INSTALL ---
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
if 'debug_screenshot' not in st.session_state:
    st.session_state['debug_screenshot'] = None

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
    screenshot
