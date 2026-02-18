import streamlit as st
import cloudscraper
from bs4 import BeautifulSoup
import re

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Real Estate ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'debug_info' not in st.session_state:
    st.session_state['debug_info'] = ""

st.title("🏙️ Real Estate ROI Calculator")
st.markdown("Automated Scraper using **CloudScraper** (Cloudflare Bypass).")

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
    
    st.divider()
    calc_button = st.button("Calculate ROI", type="primary", use_container_width=True)

    # Financials
    st.header("Financials")
    unit_price = st.number_input("Purchase Price (AED)", min_value=100000, value=1500000, step=50000)
    unit_size = st.number_input("Unit Size (Sq. Ft)", min_value=100, value=800, step=50)
    service_charge_per_sqft = st.number_input("Service Charge (AED/sq.ft)", value=15.0)
    commission_pct = st.number_input("Commission (%)", value=2.0)
    occupancy_rate = st.slider("Occupancy (%)", 50, 100, 90)

# --- SCRAPER LOGIC ---
def parse_price(text):
    # Extracts "150,000" from "AED 150,000"
    clean = re.sub(r'[^\d.]', '', text)
    if clean:
        return int(float(clean))
    return 0

def fetch_bayut_cloudscraper(url):
    # Initialize the solver
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    try:
        # Request the page
        response = scraper.get(url)
        
        if response.status_code != 200:
            return 0, f"Blocked: {response.status_code}", response.text[:500]
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. Look for 'Average Yearly Rental'
        target = soup.find(string=re.compile("Average Yearly Rental"))
        if target:
            parent = target.find_parent()
            full_text = parent.get_text() if parent else ""
            match = re.search(r'AED\s*([\d,]+)', full_text)
            if match:
                return parse_price(match.group(1)), "Success (Bayut Direct)", ""

        # 2. Fallback: Search all text
        all_text = soup.get_text()
        match = re.search(r'Average Yearly Rental.*?AED\s*([\d,]+)', all_text, re.DOTALL)
        if match:
             return parse_price(match.group(1)), "Success (Regex)", ""

        return 0, "Page loaded, but could not parse rent.", all_text[:500]

    except Exception as e:
        return 0, str(e), ""

# --- EXECUTION ---
if calc_button:
    loc_slug = location.lower().strip().replace(" ", "-")
    p_slug = "townhouses" if property_type == "Townhouse" else property_type.lower() + "s"
    bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
    
    target_url = f"https://www.bayut.com/property-market-analysis/transactions/rent/{bed_slug}-{p_slug}/dubai/{loc_slug}/?contract_renewal_status=New"
    st.session_state['final_url'] = target_url
    
    with st.status("🔍 Solving Cloudflare Challenge...", expanded=True) as status:
        rent, msg, debug = fetch_bayut_cloudscraper(target_url)
        st.session_state['scraped_rent'] = rent
        st.session_state['debug_info'] = debug
        st.session_state['data_fetched'] = True
        
        if rent > 0:
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            status.update(label=f"Failed: {msg}", state="error", expanded=True)

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
            with st.expander("Debug Info"):
                st.text(st.session_state['debug_info'])
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
