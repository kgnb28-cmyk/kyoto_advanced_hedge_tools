import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

# --- 1. PAGE CONFIG & CSS ---
st.set_page_config(layout="wide", page_title="Kyoto Terminal", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    header[data-testid="stHeader"] { background-color: rgba(0,0,0,0); z-index: 1; }
    .stApp > header { display: none; }
    .block-container { padding-top: 2rem; }
    
    .tile-container {
        border: 1px solid #333;
        background-color: #1e1e1e;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
    }
    .live-rate-box {
        font-size: 1.5rem;
        font-weight: bold;
        text-align: center;
        padding: 5px;
        border-radius: 3px;
        margin-top: 10px;
        background-color: #000;
    }
    .rate-credit { color: #00e676; } 
    .rate-debit { color: #ff5252; }  
    .rate-waiting { color: #888; }   
    
    .ltp-tag { font-size: 0.8em; color: #aaa; background-color: #333; padding: 2px 5px; border-radius: 3px; margin-left: 5px; }
    
    /* Input Styling */
    div[data-baseweb="select"] > div { min-height: 30px; padding: 0px; }
    .stTextInput input { padding: 5px; min-height: 30px; }
    div[data-testid="stNumberInput"] input { padding: 0px 5px; min-height: 30px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if 'tabs' not in st.session_state: st.session_state['tabs'] = {'Workspace 1': []}
if 'active_tab' not in st.session_state: st.session_state['active_tab'] = 'Workspace 1'
if 'tile_counter' not in st.session_state: st.session_state['tile_counter'] = 0
if 'chain_cache' not in st.session_state: st.session_state['chain_cache'] = {}

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🏯 Kyoto")
    st.caption("Pro Spread Terminal")
    access_token = st.text_input("Upstox Token", type="password", key="api_token")
    
    st.markdown("---")
    tabs_list = list(st.session_state['tabs'].keys())
    active_tab = st.radio("Workspaces", tabs_list, key="tab_selector")
    st.session_state['active_tab'] = active_tab
    
    col_new, col_del = st.columns([2, 1])
    with col_new:
        new_tab = st.text_input("New Tab", placeholder="Name")
        if st.button("➕") and new_tab:
            st.session_state['tabs'][new_tab] = []
            st.rerun()
    with col_del:
        st.write(""); st.write("")
        if st.button("🗑️") and len(tabs_list) > 1:
            del st.session_state['tabs'][active_tab]
            st.rerun()

    st.markdown("---")
    if st.button("Add Strategy Tile"):
        st.session_state['tile_counter'] += 1
        new_tile = {
            'id': st.session_state['tile_counter'],
            'index': 'NIFTY',
            'strategy': 'Vertical Spread',
            'expiry': datetime.today(),
            'legs': {} 
        }
        st.session_state['tabs'][active_tab].append(new_tile)
        st.rerun()
        
    if st.button("Clear Workspace"):
        st.session_state['tabs'][active_tab] = []
        st.rerun()

    run_live = st.toggle("🔴 LIVE FEED", value=False)


# --- 4. BACKEND LOGIC (OPTION CHAIN FETCH) ---

SPOT_MAP = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "SENSEX": "BSE_INDEX|SENSEX"
}

def fetch_option_chain_data(token, tiles):
    """
    Groups tiles by (Index, Expiry), fetches the Option Chain ONCE per group,
    and maps the LTPs to (Index, Expiry, Strike, Type).
    """
    if not token or not tiles: return {}
    
    required_fetches = set()
    for tile in tiles:
        idx_key = SPOT_MAP.get(tile['index'])
        exp_str = tile['expiry'].strftime("%Y-%m-%d")
        if idx_key:
            required_fetches.add((idx_key, exp_str, tile['index']))
            
    lookup_map = {}
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    url = "https://api.upstox.com/v2/option/chain"
    
    for spot_key, exp_date, idx_name in required_fetches:
        params = {'instrument_key': spot_key, 'expiry_date': exp_date}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=2.0)
            data = r.json()
            
            if data.get('status') == 'success':
                for item in data['data']:
                    strike = item['strike_price']
                    ce_ltp = item['call_options']['market_data']['ltp']
                    pe_ltp = item['put_options']['market_data']['ltp']
                    
                    lookup_map[(idx_name, exp_date, float(strike), "CE")] = ce_ltp
                    lookup_map[(idx_name, exp_date, float(strike), "PE")] = pe_ltp
        except:
            pass 
            
    return lookup_map


# --- 5. TILE RENDERING ---

def render_tile(tile, key_prefix, data_lookup):
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
        
        # --- Config ---
        strat = tile['strategy']
        if strat == "Vertical Spread": config = [("Buy", "CE", 1), ("Sell", "CE", -1)]
        elif strat == "Calendar Spread": config = [("Buy", "CE", -1), ("Sell", "CE", 1)]
        elif strat == "Butterfly": config = [("Buy Wing", "CE", 1), ("Sell Body", "CE", -2), ("Buy Wing", "CE", 1)]
        elif strat in ["Iron Condor", "Iron Fly"]: config = [("Buy Put", "PE", 1), ("Sell Put", "PE", -1), ("Sell Call", "CE", -1), ("Buy Call", "CE", 1)]
        else: config = []

        cols = st.columns(len(config))
        total_cost = 0.0
        has_valid_data = False
        
        exp_str = tile['expiry'].strftime("%Y-%m-%d")
        
        for i, (label, def_type, def_qty) in enumerate(config):
            with cols[i]:
                s_key = f"{key_prefix}_L{i}_s"
                t_key = f"{key_prefix}_L{i}_t"
                
                st.caption(f"{label} (x{def_qty})")
                
                sub_c1, sub_c2 = st.columns([2, 1.2]) 
                with sub_c1:
                    strike = st.number_input("", value=tile['legs'].get(s_key, 21700), step=50, key=s_key, label_visibility="collapsed")
                with sub_c2:
                    saved_idx = tile['legs'].get(t_key, 0 if def_type=="CE" else 1)
                    op_type = st.selectbox("", ["CE", "PE"], index=saved_idx, key=t_key, label_visibility="collapsed")
                
                tile['legs'][s_key] = strike
                tile['legs'][t_key] = 0 if op_type == "CE" else 1 
                
                # --- LOOKUP LTP FROM CHAIN DATA ---
                ltp = data_lookup.get((tile['index'], exp_str, float(strike), op_type), 0.0)
                if ltp > 0: has_valid_data = True
                
                st.markdown(f"<div class='ltp-tag'>LTP: {ltp}</div>", unsafe_allow_html=True)
                
                total_cost += (ltp * def_qty)

        # Render Output
        if not has_valid_data:
            html = f'<div class="live-rate-box rate-waiting">WAITING...</div>'
        else:
            if total_cost > 0:
                html = f'<div class="live-rate-box rate-debit">{abs(total_cost):.2f} <span style="font-size:0.5em">DEBIT</span></div>'
            else:
                html = f'<div class="live-rate-box rate-credit">{abs(total_cost):.2f} <span style="font-size:0.5em">CREDIT</span></div>'

        st.markdown(html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


# --- 6. MAIN LOOP ---

current_tiles = st.session_state['tabs'][active_tab]

# --- CHANGED TO 1xN GRID LAYOUT ---
cols_per_row = 1
rows = [current_tiles[i:i + cols_per_row] for i in range(0, len(current_tiles), cols_per_row)]

if not current_tiles:
    st.info("Workspace is empty. Click 'Add Strategy Tile' in the sidebar.")

# Render using cached data first
for row in rows:
    cols = st.columns(len(row))
    for idx, tile in enumerate(row):
        with cols[idx]:
            render_tile(tile, f"tile_{tile['id']}", st.session_state['chain_cache'])

# --- 7. LIVE DATA REFRESH ---

if run_live:
    time.sleep(0.5) 
    new_data = fetch_option_chain_data(access_token, current_tiles)
    if new_data:
        st.session_state['chain_cache'] = new_data
        st.rerun()
    else:

        st.rerun()
