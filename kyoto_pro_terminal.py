import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime, timedelta

# --- 1. PAGE CONFIG & CSS ---
st.set_page_config(layout="wide", page_title="Kyoto Terminal", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* Headers */
    header[data-testid="stHeader"] { background-color: rgba(0,0,0,0); z-index: 1; }
    .stApp > header { display: none; }
    .block-container { padding-top: 2rem; padding-bottom: 0rem; }
    
    /* Tiles */
    .tile-container {
        border: 1px solid #333;
        background-color: #1e1e1e;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 10px;
    }
    
    /* Live Rate Box */
    .live-rate-box {
        font-size: 1.5rem;
        font-weight: bold;
        text-align: center;
        padding: 5px;
        border-radius: 3px;
        margin-top: 10px;
        background-color: #000;
    }
    .rate-credit { color: #00e676; } /* Green for Credit (Money In) */
    .rate-debit { color: #ff5252; }  /* Red for Debit (Money Out) */
    .rate-waiting { color: #888; }   /* Grey for 0/No Data */
    
    /* LTP Tag */
    .ltp-tag {
        font-size: 0.8em;
        color: #aaa;
        background-color: #333;
        padding: 2px 5px;
        border-radius: 3px;
        margin-left: 5px;
    }

    /* Input Tweaks */
    div[data-baseweb="select"] > div { min-height: 30px; padding: 0px; }
    .stTextInput input { padding: 5px; min-height: 30px; }
    div[data-testid="stNumberInput"] input { padding: 0px 5px; min-height: 30px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if 'tabs' not in st.session_state: st.session_state['tabs'] = {'Workspace 1': []}
if 'active_tab' not in st.session_state: st.session_state['active_tab'] = 'Workspace 1'
if 'tile_counter' not in st.session_state: st.session_state['tile_counter'] = 0
if 'last_quotes' not in st.session_state: st.session_state['last_quotes'] = {}

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🏯 Kyoto")
    st.caption("Pro Spread Terminal")
    access_token = st.text_input("Upstox Token", type="password", key="api_token")
    
    st.markdown("---")
    st.subheader("Workspaces")
    tabs_list = list(st.session_state['tabs'].keys())
    active_tab = st.radio("Select Tab", tabs_list, key="tab_selector")
    st.session_state['active_tab'] = active_tab
    
    col_new, col_del = st.columns([2, 1])
    with col_new:
        new_tab_name = st.text_input("New Tab Name", placeholder="e.g. Nifty AM")
        if st.button("➕ Add"):
            if new_tab_name and new_tab_name not in st.session_state['tabs']:
                st.session_state['tabs'][new_tab_name] = []
                st.rerun()
    with col_del:
        st.write(""); st.write("")
        if st.button("🗑️"):
            if len(tabs_list) > 1:
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

# --- 4. BACKEND LOGIC ---

def get_instrument_key(index, expiry, strike, type_):
    # Upstox Format: NSE_FO|NIFTY23DEC2821700CE
    try:
        y = expiry.strftime("%y")     # 23
        m = expiry.strftime("%b").upper() # DEC
        d = expiry.strftime("%d")     # 28 (Padded)
        symbol = f"{index}{y}{m}{d}{int(strike)}{type_}"
        return f"NSE_FO|{symbol}"
    except:
        return ""

def fetch_batch_data(token, keys):
    if not token or not keys: return {}
    url = "https://api.upstox.com/v2/market-quote/quotes"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    unique_keys = list(set(keys))
    # Upstox usually allows 100 keys per call. 
    # If keys are failing, the response might be partial.
    params = {'instrument_key': ",".join(unique_keys)}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=1.0)
        data = r.json().get('data', {})
        return data
    except:
        return {}

# --- 5. TILE RENDERING ---

def render_tile(tile, key_prefix, quotes):
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
        
        # --- Strategy Config ---
        strat = tile['strategy']
        
        # (Label, Type, Qty)
        if strat == "Vertical Spread":
            config = [("Buy", "CE", 1), ("Sell", "CE", -1)]
        elif strat == "Calendar Spread":
            config = [("Buy (Near)", "CE", -1), ("Sell (Far)", "CE", 1)]
        elif strat == "Butterfly":
            config = [("Buy Wing", "CE", 1), ("Sell Body", "CE", -2), ("Buy Wing", "CE", 1)]
        elif strat in ["Iron Condor", "Iron Fly"]:
            config = [("Buy Put", "PE", 1), ("Sell Put", "PE", -1), ("Sell Call", "CE", -1), ("Buy Call", "CE", 1)]
        else:
            config = []

        cols = st.columns(len(config))
        tile_legs_data = [] # Store key/qty for calculation
        
        for i, (label, def_type, def_qty) in enumerate(config):
            with cols[i]:
                s_key = f"{key_prefix}_L{i}_s"
                t_key = f"{key_prefix}_L{i}_t"
                
                # Header with Leg Label
                st.caption(f"{label} (x{def_qty})")
                
                # Input Row
                sub_c1, sub_c2 = st.columns([2, 1.2]) 
                with sub_c1:
                    strike = st.number_input("", value=tile['legs'].get(s_key, 21700), step=50, key=s_key, label_visibility="collapsed")
                with sub_c2:
                    saved_idx = tile['legs'].get(t_key, 0 if def_type=="CE" else 1)
                    op_type = st.selectbox("", ["CE", "PE"], index=saved_idx, key=t_key, label_visibility="collapsed")
                
                # Save Inputs
                tile['legs'][s_key] = strike
                tile['legs'][t_key] = 0 if op_type == "CE" else 1 
                
                # Generate Key & Get LTP
                instr_key = get_instrument_key(tile['index'], tile['expiry'], strike, op_type)
                
                # CHECK LTP FROM SESSION STATE (Or 0.0)
                ltp = quotes.get(instr_key, {}).get('last_price', 0.0)
                
                # DISPLAY LTP (Debugging for User)
                st.markdown(f"<div class='ltp-tag'>LTP: {ltp}</div>", unsafe_allow_html=True)
                
                tile_legs_data.append({'ltp': ltp, 'qty': def_qty})
                
                # Return the key so we can fetch it next loop
                if instr_key:
                    tile_legs_data[-1]['key'] = instr_key

        # --- Calculate Net Spread ---
        total_cost = 0.0
        data_valid = False
        
        for leg in tile_legs_data:
            # Formula: Cost = Price * Qty. 
            # Buy (+1) * 100 = 100 (Debit). 
            # Sell (-1) * 100 = -100 (Credit).
            if leg['ltp'] > 0: data_valid = True
            total_cost += (leg['ltp'] * leg['qty'])
        
        # Render Output
        if not data_valid:
            # All prices 0 -> Waiting
            html = f'<div class="live-rate-box rate-waiting">WAITING...</div>'
        else:
            if total_cost > 0:
                # Debit
                html = f'<div class="live-rate-box rate-debit">{abs(total_cost):.2f} <span style="font-size:0.5em">DEBIT</span></div>'
            else:
                # Credit (Negative Cost)
                html = f'<div class="live-rate-box rate-credit">{abs(total_cost):.2f} <span style="font-size:0.5em">CREDIT</span></div>'

        st.markdown(html, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Return keys needed for next fetch
        return [l.get('key') for l in tile_legs_data if 'key' in l]

# --- 6. MAIN LOOP ---

current_tiles = st.session_state['tabs'][active_tab]
cols_per_row = 2 
rows = [current_tiles[i:i + cols_per_row] for i in range(0, len(current_tiles), cols_per_row)]

all_needed_keys = []

if not current_tiles:
    st.info("Workspace is empty. Click 'Add Strategy Tile' in the sidebar.")

# Render UI using cached quotes
for row in rows:
    cols = st.columns(len(row))
    for idx, tile in enumerate(row):
        with cols[idx]:
            keys = render_tile(tile, f"tile_{tile['id']}", st.session_state['last_quotes'])
            all_needed_keys.extend(keys)

# --- 7. LIVE DATA REFRESH ---

if run_live:
    time.sleep(1) # Wait 1 sec
    new_quotes = fetch_batch_data(access_token, all_needed_keys)
    
    # Update state if we got data
    if new_quotes:
        st.session_state['last_quotes'] = new_quotes
        st.rerun() # Force UI refresh with new data
    else:
        # If fetch fails or empty, just rerun to keep loop alive
        st.rerun()