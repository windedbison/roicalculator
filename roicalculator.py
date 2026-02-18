import streamlit as st
import re
import os
from playwright.sync_api import sync_playwright

# --- 1. FORCE INSTALL ---
try:
    os.system("playwright install chromium")
except:
    pass

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Real Estate ROI Calculator", layout="wide")

# --- SESSION STATE ---
if 'scraped_rent' not in st.session_state:
    st.session_state['scraped_rent'] = 0
if 'data_fetched' not in st.session_state:
    st.session_state['data_fetched'] = False
if 'debug_text' not in st.session_state:
    st.session_state['debug_text'] = ""

st.title("🏙️ Real Estate ROI Calculator")
st.markdown("Automated Scraper using **Google Cache Bypass**.")

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
def parse_clean_number(text):
    # Turns "150,000", "150, 000" into 150000
    clean = re.sub(r'[^\d.]', '', text)
    if clean:
        return int(float(clean))
    return 0

def scrape_data(bayut_url):
    # Use text-only cache (&strip=1)
    cache_url = f"http://webcache.googleusercontent.com/search?q=cache:{bayut_url}&strip=1&vwsrc=0"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(cache_url, timeout=45000)
            
            try:
                # FIXED: Use content() instead of inner_text()
                content = page.content()
                browser.close()

                if "404." in content and "That’s an error" in content:
                    return 0, content, "Page not found in Google Cache."

                # Strip HTML tags to get pure text
                clean_text = re.sub('<[^<]+?>', ' ', content)
                clean_text = re.sub(r'\s+', ' ', clean_text) # Collapse spaces

                # REGEX: Look for "Average Yearly Rental AED 150,000"
                match = re.search(r'Average Yearly Rental.*?AED\s*([\d,]+)', clean_text, re.IGNORECASE)
                
                if match:
                    raw_num = match.group(1)
                    val = parse_clean_number(raw_num)
                    return val, clean_text, None
                
                return 0, clean_text, "Regex did not find 'Average Yearly Rental ... AED ... Number'"

            except Exception as e:
                browser.close()
                return 0, str(e), str(e)

    except Exception as e:
        return 0, str(e), str(e)

# --- EXECUTION ---
if calc_button:
    loc_slug = location.lower().strip().replace(" ", "-")
    p_slug = "townhouses" if property_type == "Townhouse" else property_type.lower() + "s"
    bed_slug = "studio" if "Studio" in unit_conf else f"{unit_conf.split()[0]}-bedroom"
    
    target_url = f"https://www.bayut.com/property-market-analysis/transactions/rent/{bed_slug}-{p_slug}/dubai/{loc_slug}/?contract_renewal_status=New"
    st.session_state['final_url'] = target_url
    
    with st.status("🔍 Checking Google Cache...", expanded=True) as status:
        rent, raw_text, error = scrape_data(target_url)
        st.session_state['scraped_rent'] = rent
        st.session_state['debug_text'] = raw_text 
        st.session_state['data_fetched'] = True
        
        if rent > 0:
            status.update(label="Data Found!", state="complete", expanded=False)
        else:
            status.update(label=f"Failed: {error}", state="error", expanded=True)

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
            with st.expander("🔍 View Scraped Text"):
                st.text(st.session_state['debug_text'][:2000])
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
