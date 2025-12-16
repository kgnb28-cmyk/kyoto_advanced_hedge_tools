import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

# --- 1. PAGE CONFIG & CSS (NO HEADERS) ---
st.set_page_config(layout="wide", page_title="Kyoto Terminal", initial_sidebar_state="expanded")

# CSS to hide default headers and maximize screen real estate
st.markdown("""
    <style>
    /* Hide Streamlit Header */
    header {visibility: hidden;}
    /* Remove top padding */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    /* Compact Tiles */
    .tile-container {
        border: 1px solid #333;
        background-color: #1e1e1e;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
    }
    .live-rate-box {
        background-color: #000;
        color: #00e676;
        font-size: 1.5rem;
        font-weight: bold;
        text-align: center;
        padding: 5px;
        border-radius: 3px;
        margin-top: 10px;
    }
    .live-rate-neg { color: #ff5252; }
    
    /* Small inputs */
    div[data-baseweb="select"] > div {
        min-height: 30px;
        padding: 0px;
    }
    .stTextInput input {
        padding: 5px;
        min-height: 30px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE MANAGEMENT (TABS & TILES) ---

if 'tabs' not in st.session_state:
    # Structure: {'Tab Name': [{'id': 1, 'type': 'Butterfly', ...}, ...]}
    st.session_state['tabs'] = {'Workspace 1': []}
if 'active_tab' not in st.session_state:
    st.session_state['active_tab'] = 'Workspace 1'
if 'tile_counter' not in st.session_state:
    st.session_state['tile_counter'] = 0

# --- 3. SIDEBAR (TOKEN & TABS) ---

with st.sidebar:
    st.title("🏯 Kyoto")
    st.caption("Pro Spread Terminal")
    
    # Access Token Input
    access_token = st.text_input("Upstox Token", type="password", key="api_token")
    
    st.markdown("---")
    st.subheader("Workspaces")
    
    # Tab Manager
    tabs_list = list(st.session_state['tabs'].keys())
    active_tab = st.radio("Select Tab", tabs_list, key="tab_selector")
    st.session_state['active_tab'] = active_tab
    
    # Add/Rename/Delete Controls
    col_new, col_del = st.columns([2, 1])
    with col_new:
        new_tab_name = st.text_input("New Tab Name", placeholder="e.g. Nifty AM")
        if st.button("➕ Add Tab"):
            if new_tab_name and new_tab_name not in st.session_state['tabs']:
                st.session_state['tabs'][new_tab_name] = []
                st.rerun()
    with col_del:
        st.write("") # Spacer
        st.write("")
        if st.button("🗑️"):
            if len(tabs_list) > 1:
                del st.session_state['tabs'][active_tab]
                st.rerun()

    st.markdown("---")
    st.markdown("### Controls")
    
    # Add Tile Button
    if st.button("Add Strategy Tile"):
        st.session_state['tile_counter'] += 1
        new_tile = {
            'id': st.session_state['tile_counter'],
            'index': 'NIFTY',
            'strategy': 'Vertical Spread',
            'expiry': datetime.today(),
            'legs': {} # Will hold strike data
        }
        st.session_state['tabs'][active_tab].append(new_tile)
        st.rerun()
        
    # Clear All Tiles
    if st.button("Clear Workspace"):
        st.session_state['tabs'][active_tab] = []
        st.rerun()

    run_live = st.toggle("🔴 LIVE FEED", value=False)


# --- 4. BACKEND LOGIC ---

def get_instrument_key(index, expiry, strike, type_):
    # Simplified Symbol Logic for Upstox
    try:
        y = expiry.strftime("%y")
        m = expiry.strftime("%b").upper()
        d = expiry.strftime("%d")
        symbol = f"{index}{y}{m}{d}{int(strike)}{type_}"
        return f"NSE_FO|{symbol}"
    except:
        return ""

def fetch_batch_data(token, keys):
    if not token or not keys: return {}
    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    # Unique keys only to save bandwidth
    unique_keys = list(set(keys))
    # Chunking (Upstox limit is often 100 keys per call)
    params = {'instrument_key': ",".join(unique_keys)}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=1.5)
        return r.json().get('data', {})
    except:
        return {}

# --- 5. TILE RENDERING ---

# Helper to render a single tile
def render_tile(tile, key_prefix):
    with st.container():
        st.markdown('<div class="tile-container">', unsafe_allow_html=True)
        
        # --- Top Control Bar ---
        c1, c2, c3 = st.columns([1.2, 1.2, 1.5])
        with c1:
            tile['index'] = st.selectbox("", ["NIFTY", "BANKNIFTY", "SENSEX"], key=f"{key_prefix}_idx", label_visibility="collapsed")
        with c2:
            tile['expiry'] = st.date_input("", value=tile.get('expiry', datetime.today()), key=f"{key_prefix}_exp", label_visibility="collapsed")
        with c3:
            tile['strategy'] = st.selectbox("", ["Vertical Spread", "Butterfly", "Iron Condor", "Iron Fly", "Calendar Spread"], key=f"{key_prefix}_strat", label_visibility="collapsed")
        
        # --- Strategy Inputs ---
        strat = tile['strategy']
        legs = []
        
        # Define leg counts/types based on strategy
        # Format: (Label, DefaultType, Qty)
        config = []
        if strat == "Vertical Spread":
            config = [("Buy", "CE", 1), ("Sell", "CE", -1)]
        elif strat == "Calendar Spread":
            config = [("Buy (Near)", "CE", -1), ("Sell (Far)", "CE", 1)]
            # Note: Calendar requires 2 expiries. For Lite version, we use same expiry input or add logic.
            # Adding simple override for now.
        elif strat == "Butterfly":
            config = [("Buy Wing", "CE", 1), ("Sell Body", "CE", -2), ("Buy Wing", "CE", 1)]
        elif strat in ["Iron Condor", "Iron Fly"]:
            config = [("Buy Put", "PE", 1), ("Sell Put", "PE", -1), ("Sell Call", "CE", -1), ("Buy Call", "CE", 1)]

        # Render Leg Inputs Grid
        cols = st.columns(len(config))
        generated_keys = []
        
        for i, (label, def_type, def_qty) in enumerate(config):
            with cols[i]:
                # Unique keys for state
                s_key = f"{key_prefix}_L{i}_s"
                
                # Input
                strike = st.number_input(f"{label}", value=tile['legs'].get(s_key, 21700), step=50, key=s_key)
                tile['legs'][s_key] = strike # Save to state
                
                # Generate Instrument Key
                k = get_instrument_key(tile['index'], tile['expiry'], strike, def_type[-2:]) # Simple type logic
                generated_keys.append({'key': k, 'qty': def_qty, 'strike': strike, 'type': def_type})
        
        # --- Live Output Placeholder ---
        out_placeholder = st.empty()
        
        st.markdown('</div>', unsafe_allow_html=True)
        return generated_keys, out_placeholder

# --- 6. MAIN WORKSPACE LOGIC ---

# 1. Get Tiles for Active Tab
current_tiles = st.session_state['tabs'][active_tab]

# 2. Organize Grid (Responsive)
# User didn't specify column count, so we wrap. Let's do 4 columns max for wide screens.
cols_per_row = 4
rows = [current_tiles[i:i + cols_per_row] for i in range(0, len(current_tiles), cols_per_row)]

all_tile_requests = [] # To store what each tile needs fetching
all_placeholders = []  # To store where to write the results

# 3. Render the Static UI (Inputs)
if not current_tiles:
    st.info("Workspace is empty. Click 'Add Strategy Tile' in the sidebar.")

for row in rows:
    cols = st.columns(len(row))
    for idx, tile in enumerate(row):
        with cols[idx]:
            # Render UI and get back the keys it needs and the placeholder to write to
            req_keys, ph = render_tile(tile, f"tile_{tile['id']}")
            all_tile_requests.append(req_keys)
            all_placeholders.append(ph)

# --- 7. LIVE LOOP ---

if run_live:
    while True:
        # A. Collect ALL keys from ALL tiles
        master_key_list = []
        for tile_req in all_tile_requests:
            for leg in tile_req:
                if leg['key']: master_key_list.append(leg['key'])
        
        # B. Fetch Data (One Batch Call)
        quotes = fetch_batch_data(access_token, master_key_list)
        
        # C. Update Each Tile
        for i, tile_req in enumerate(all_tile_requests):
            total_cost = 0.0
            html_legs = ""
            
            for leg in tile_req:
                # Get Price
                ltp = quotes.get(leg['key'], {}).get('last_price', 0.0)
                
                # Calc Cost (Price * Qty). Positive Qty = Debit (Cost). Negative Qty = Credit.
                cost = ltp * leg['qty']
                total_cost += cost
                
            # Render Result in the placeholder
            color_cls = "live-rate-box" if total_cost >= 0 else "live-rate-box live-rate-neg"
            lbl = "DEBIT" if total_cost >= 0 else "CREDIT"
            
            all_placeholders[i].markdown(f"""
                <div class="{color_cls}">
                    {abs(total_cost):.2f} <span style="font-size:0.5em">{lbl}</span>
                </div>
            """, unsafe_allow_html=True)
            
        time.sleep(1)