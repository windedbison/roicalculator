import streamlit as st
import requests
from bs4 import BeautifulSoup
import re

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
st.markdown("Automated Market Data via **Google Translate Proxy**.")

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

# --- HELPER: CLEAN PRICE ---
def parse_price(text):
    clean = re.sub(r'[^\d.]', '', text)
    if clean:
        return int(float(clean))
    return 0

# --- METHOD 1: GOOGLE TRANSLATE PROXY ---
def fetch_via_translate(target_url):
    # We ask Google Translate to fetch Bayut for us
    proxy_url = f"https://translate.google.com/translate?sl=auto&tl=en&u={target_url}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(proxy_url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Google wraps the content in iframes or weird tags, so we search raw text
        all_text = soup.get_text()
        
        # Regex for "Average Yearly Rental ... AED 150,000"
        # The proxy often adds spaces, so we are flexible
        match = re.search(r'Average Yearly Rental.*?AED\s*([\d,]+)', all_text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return parse_price(match.group(1)), "Bayut (via Google Translate)"
            
        return 0, "Failed"
    except:
        return 0, "Failed"

# --- METHOD 2: PROPSEARCH (FALLBACK) ---
def fetch_via_propsearch(loc_name, unit_name):
    slug = loc_name.lower().strip().replace(" ", "-")
    url = f"https://propsearch.ae/dubai/{slug}"
    
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the table row for the unit
        # PropSearch uses "1 Bed", "2 Bed" etc.
        search_term = unit_name.replace("Bedroom", "Bed").replace("Studio", "Studio")
        
        rows = soup.find_all('tr')
        for row in rows:
            text = row.get_text()
            if search_term in text and "Average" not in text: # Skip header
                # Look for price in the row
                prices = re.findall(r'([\d,]{3,})', text)
                if prices:
                    # Usually the first number is the average or low end
                    val = parse_price(prices[0])
                    if val > 20000:
                        return val, "PropSearch Aggregation"
        return 0, "Failed"
    except:
        return 0, "Failed"

# --- EXECUTION ---
if calc_button:
    # 1. Setup URLs
    loc_slug = location.lower().strip().replace(" ", "-")
    p_slug = "townhouses" if property_type == "Townhouse" else property_type.lower() + "s"
    bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
    bayut_url = f"https://www.bayut.com/property-market-analysis/transactions/rent/{bed_slug}-{p_slug}/dubai/{loc_slug}/?contract_renewal_status=New"
    st.session_state['final_url'] = bayut_url
    
    with st.status("🔍 Finding Market Data...", expanded=True) as status:
        # ATTEMPT 1: Google Translate Proxy
        st.write("Trying Google Translate Proxy...")
        rent, source = fetch_via_translate(bayut_url)
        
        # ATTEMPT 2: PropSearch Fallback
        if rent == 0:
            st.write("Google blocked. Switching to Aggregator...")
            rent, source = fetch_via_propsearch(location, unit_conf)
        
        st.session_state['scraped_rent'] = rent
        st.session_state['data_source'] = source
        st.session_state['data_fetched'] = True
        
        if rent > 0:
            status.update(label=f"Data Found! Source: {source}", state="complete", expanded=False)
        else:
            status.update(label="All sources blocked. Enter manually.", state="error", expanded=True)

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
            st.warning("⚠️ Could not scrape. Enter manually.")
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
