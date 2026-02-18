import streamlit as st
import re
from playwright.sync_api import sync_playwright

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Dubai ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'logs' not in st.session_state:
    st.session_state['logs'] = []
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'final_url' not in st.session_state:
    st.session_state['final_url'] = ""

st.title("🏙️ Dubai Real Estate ROI Calculator")
st.markdown("Automated Bayut Scraper for **New Contract** transactions.")

# --- SIDEBAR INPUTS ---
with st.sidebar:
    st.header("1. Property Details")
    property_type = st.selectbox("Property Type", ["Apartment", "Villa", "Townhouse"])
    location = st.text_input("Location", value="Dubai Marina")
    
    # Smart Unit Selection
    if property_type == "Apartment":
        unit_options = ["Studio", "1 Bedroom", "2 Bedroom", "3 Bedroom", "4 Bedroom"]
    else:
        unit_options = ["2 Bedroom", "3 Bedroom", "4 Bedroom", "5 Bedroom", "6 Bedroom"]
        
    unit_conf = st.selectbox("Unit Configuration", unit_options)

    # Financials
    unit_price = st.number_input("Purchase Price (AED)", min_value=100000, value=1500000, step=50000)
    unit_size = st.number_input("Unit Size (Sq. Ft)", min_value=100, value=800, step=50)

    st.header("2. Costs & Fees")
    service_charge_per_sqft = st.number_input("Service Charge (AED/sq.ft)", min_value=0.0, value=18.0, step=0.5)
    commission_pct = st.slider("Agency Commission (%)", 0.0, 5.0, 2.0, 0.1)
    
    st.header("3. Operational")
    occupancy_rate = st.slider("Occupancy Rate (%)", 50, 100, 85, 5)

# --- HELPER: URL BUILDER ---
def build_smart_url(location, property_type, unit_conf):
    loc_slug = location.lower().strip().replace(" ", "-")
    
    if property_type == "Townhouse":
        p_slug = "townhouses"
    else:
        p_slug = property_type.lower() + "s" 
    
    if "Studio" in unit_conf:
        bed_slug = "studio"
    else:
        bed_slug = f"{unit_conf.split()[0]}-bedroom"
    
    unit_segment = f"{bed_slug}-{p_slug}"
    
    url = f"https://www.bayut.com/property-market-analysis/transactions/rent/{unit_segment}/dubai/{loc_slug}/?contract_renewal_status=New"
    return url

# --- HELPER: TEXT PARSER ---
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
        val = float(match.group(1))
        return int(val * multiplier)
    return None

# --- SCRAPER (Visual Anchor Logic) ---
def scrape_data(url):
    logs = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
            context = browser.new_context()
            page = context.new_page()
            
            page.goto(url, timeout=30000)
            
            try:
                # Find Anchor
                label_locator = page.get_by_text("Average Yearly Rental", exact=False).first
                label_locator.wait_for(timeout=8000)
                
                # Get Container
                container = label_locator.locator("..").locator("..") 
                text_block = container.inner_text()
                browser.close()
                
                # Parse
                lines = text_block.split('\n')
                possible_values = []
                for line in lines:
                    line = line.strip()
                    if "Average" in line or "Rental" in line or "%" in line or not line:
                        continue
                    val = parse_abbreviated_number(line)
                    if val and val > 10000: 
                        possible_values.append(val)
                
                if possible_values:
                    return possible_values[0], logs
                else:
                    return 0, logs

            except Exception as e:
                browser.close()
                return 0, logs

    except Exception as e:
        return 0, logs

# --- HELPER: EMOJI LOGIC ---
def get_roi_emoji(roi):
    if roi >= 8.0:
        return "🟢" # Excellent
    elif roi >= 6.0:
        return "🟢" # Good
    elif roi >= 4.0:
        return "🟡" # Average
    else:
        return "🔴" # Poor

# --- MAIN LOGIC ---

if st.button("Calculate ROI"):
    target_url = build_smart_url(location, property_type, unit_conf)
    st.session_state['final_url'] = target_url
    
    with st.status("🔍 Scraping Bayut Transactions...", expanded=True) as status:
        rent, logs = scrape_data(target_url)
        st.session_state['scraped_rent'] = rent
        st.session_state['data_fetched'] = True
        
        if rent > 0:
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            status.update(label="Could not find data (Check URL)", state="error", expanded=True)

# --- RESULTS DISPLAY ---

if st.session_state['data_fetched']:
    st.divider()
    
    # 1. RENT SECTION
    col_input, col_link = st.columns([3, 1])
    with col_input:
        if st.session_state['scraped_rent'] > 0:
            st.success(f"✅ Market Rent Found: **AED {st.session_state['scraped_rent']:,.0f}**")
            final_rent = st.number_input("Annual Rent (AED)", value=float(st.session_state['scraped_rent']))
        else:
            st.warning("⚠️ Auto-scrape failed. Enter manually.")
            final_rent = st.number_input("Manual Rent (AED)", value=0.0)
    with col_link:
        st.markdown(f"<br><a href='{st.session_state['final_url']}' target='_blank'>Verify on Bayut ↗</a>", unsafe_allow_html=True)
            
    if final_rent > 0:
        # 2. CALCULATIONS
        dld = unit_price * 0.04
        comm = unit_price * (commission_pct/100)
        trustee = 4580
        total_cost = unit_price + dld + comm + trustee
        
        gross = final_rent * (occupancy_rate/100)
        exp = unit_size * service_charge_per_sqft
        net = gross - exp
        roi = (net / total_cost) * 100
        
        st.divider()
        st.subheader(f"📊 ROI Analysis for {unit_conf} in {location}")
        
        # 3. METRICS WITH EMOJI
        c1, c2, c3 = st.columns(3)
        
        c1.metric("Total Investment", f"{total_cost:,.0f} AED", help="Price + 4% DLD + Agency Fee + Trustee")
        c2.metric("Net Annual Income", f"{net:,.0f} AED", help="Rent (Occupancy Adj.) - Service Charges")
        
        emoji = get_roi_emoji(roi)
        c3.metric("NET ROI", f"{emoji} {roi:.2f}%")