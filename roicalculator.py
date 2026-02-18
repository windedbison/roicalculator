import streamlit as st
import re
import os
import time
from playwright.sync_api import sync_playwright
# NEW: Import the stealth masker
from playwright_stealth import stealth_sync

# --- 1. FORCE INSTALL ---
try:
    os.system("playwright install chromium")
except:
    pass

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Rabdan ROI Calculator", layout="wide")

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
st.markdown("Automated Bayut Scraper with **Stealth Mode**.")

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

    # Financials (Hidden unless needed for calc)
    st.header("Financials")
    unit_price = st.number_input("Purchase Price (AED)", min_value=100000, value=1500000, step=50000)
    unit_size = st.number_input("Unit Size (Sq. Ft)", min_value=100, value=800, step=50)
    service_charge_per_sqft = st.number_input("Service Charge (AED/sq.ft)", value=15.0)
    commission_pct = st.number_input("Commission (%)", value=2.0)
    occupancy_rate = st.slider("Occupancy (%)", 50, 100, 90)

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
            # 1. Launch with specific args to hide the automation bar
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            
            # 2. Create Context with specific user agent and viewport
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            
            page = context.new_page()
            
            # 3. APPLY STEALTH (The Secret Sauce)
            stealth_sync(page)
            
            # 4. Go to Bayut
            page.goto(url, timeout=60000)
            
            try:
                # Wait for the specific text
                label_locator = page.get_by_text("Average Yearly Rental", exact=False).first
                label_locator.wait_for(timeout=25000)
                
                # Extract Text
                container = label_locator.locator("..").locator("..") 
                text_block = container.inner_text()
                
                browser.close()
                
                # Parse
                lines = text_block.split('\n')
                possible_values = []
                for line in lines:
                    if "Average" in line or "Rental" in line or "%" in line: continue
                    val = parse_abbreviated_number(line)
                    if val and val > 10000: possible_values.append(val)
                
                return (possible_values[0] if possible_values else 0), None
                
            except Exception as e:
                # Capture failure screenshot
                screenshot = page.screenshot(full_page=False)
                browser.close()
                return 0, screenshot

    except Exception as e:
        return 0, None

# --- EXECUTION ---
if calc_button:
    loc_slug = location.lower().strip().replace(" ", "-")
    p_slug = "townhouses" if property_type == "Townhouse" else property_type.lower() + "s"
    bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
    
    target_url = f"https://www.bayut.com/property-market-analysis/transactions/rent/{bed_slug}-{p_slug}/dubai/{loc_slug}/?contract_renewal_status=New"
    st.session_state['final_url'] = target_url
    st.session_state['debug_screenshot'] = None
    
    with st.status("🔍 Infiltrating Bayut (Stealth Mode)...", expanded=True) as status:
        rent, screenshot = scrape_data(target_url)
        st.session_state['scraped_rent'] = rent
        st.session_state['debug_screenshot'] = screenshot
        st.session_state['data_fetched'] = True
        
        if rent > 0:
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            status.update(label="Scrape blocked or failed.", state="error", expanded=True)

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
            # DEBUGGER
            if st.session_state['debug_screenshot']:
                with st.expander("📸 Debug View"):
                    st.image(st.session_state['debug_screenshot'], caption="What the bot saw")
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
