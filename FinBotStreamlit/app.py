import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import ollama
import uuid
from datetime import datetime, timedelta
import numpy as np

# ==========================================
# 1. PAGE CONFIG & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="FinChat Prototype", layout="wide")

def inject_custom_css():
    st.markdown("""
        <style>
        .stApp { background-color: #0B0E14; color: #E2E8F0; font-family: 'Inter', sans-serif; }
        
        [data-testid="stChatMessage"] {
            background-color: transparent;
            padding: 0.5rem 1rem;
        }
        
        .utility-btn button {
            background: transparent !important;
            border: none !important;
            color: #6B7280 !important;
            padding: 0 !important;
            box-shadow: none !important;
        }
        .utility-btn button:hover {
            color: #E2E8F0 !important;
        }
        
        .dash-btn button {
            background: #1E3A8A !important;
            color: #E2E8F0 !important;
            border-radius: 4px !important;
            padding: 2px 10px !important;
            font-size: 0.8rem !important;
            margin-top: 10px !important;
        }
        .dash-btn button:hover {
            background: #3B82F6 !important;
        }
        
        [data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
        }
        
        header {visibility: hidden;} #MainMenu {visibility: hidden;} footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. STATE MANAGEMENT
# ==========================================
def init_state():
    if "msg_tree" not in st.session_state:
        st.session_state.msg_tree = {}
    if "current_leaf" not in st.session_state:
        st.session_state.current_leaf = None
    if "dashboard_view" not in st.session_state:
        st.session_state.dashboard_view = None  
    if "active_mode" not in st.session_state:
        st.session_state.active_mode = "None"
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None 
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None # Used to trigger chat from dashboard buttons

def add_message(role, content, parent_id, attached_dashboard=None):
    msg_id = str(uuid.uuid4())
    st.session_state.msg_tree[msg_id] = {
        "id": msg_id, 
        "role": role, 
        "content": content, 
        "parent_id": parent_id, 
        "children": [],
        "attached_dashboard": attached_dashboard # Save the dashboard state to the message
    }
    if parent_id and parent_id in st.session_state.msg_tree:
        st.session_state.msg_tree[parent_id]["children"].append(msg_id)
    return msg_id

def get_chat_path(leaf_id):
    path = []
    curr = leaf_id
    while curr:
        path.append(st.session_state.msg_tree[curr])
        curr = st.session_state.msg_tree[curr]["parent_id"]
    return path[::-1]

def get_siblings(msg_id):
    parent_id = st.session_state.msg_tree[msg_id]["parent_id"]
    if parent_id is None:
        return [m_id for m_id, m in st.session_state.msg_tree.items() if m["parent_id"] is None]
    return st.session_state.msg_tree[parent_id]["children"]

# ==========================================
# 3. DASHBOARD TOOLS (MOCK DATA)
# ==========================================
def render_market_discovery():
    st.subheader("📊 Market Discovery")
    st.markdown("### Top Algorithmic Setups")
    
    with st.container():
        st.markdown("#### Tesla Inc. (TSLA)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected Profit", "37%", "+37%") 
        c2.metric("Suggested Buy", "$170.50")
        c3.metric("Stop Loss", "$150.00", "-12%", delta_color="inverse")
        c4.metric("Take Profit", "$233.00", "+37%")
        st.divider()

    with st.container():
        st.markdown("#### NVIDIA Corp. (NVDA)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected Profit", "22%", "+22%")
        c2.metric("Suggested Buy", "$880.00")
        c3.metric("Stop Loss", "$800.00", "-9%", delta_color="inverse")
        c4.metric("Take Profit", "$1073.00", "+22%")
        st.divider()

    with st.container():
        st.markdown("#### Xiaomi Corp. (1810.HK)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Expected Profit", "15%", "+15%")
        c2.metric("Suggested Buy", "HK$16.00")
        c3.metric("Stop Loss", "HK$14.50", "-9%", delta_color="inverse")
        c4.metric("Take Profit", "HK$18.40", "+15%")
        st.write("") 
        
    if st.button("Suggest more...", key="more_market"):
        st.session_state.pending_prompt = "Can you suggest more market setups like these?"
        st.rerun()

def render_stock_deep_analysis():
    st.subheader("🔎 Stock Deep Analysis")
    st.markdown("### NVIDIA Corporation (NVDA)")
    
    # Set a seed so the graph doesn't change when we click other buttons in the app
    np.random.seed(42)
    dates = [datetime.today() - timedelta(days=x) for x in range(30)]
    open_p = np.random.uniform(850, 900, 30)
    close_p = open_p + np.random.uniform(-15, 15, 30)
    high_p = np.maximum(open_p, close_p) + np.random.uniform(0, 10, 30)
    low_p = np.minimum(open_p, close_p) - np.random.uniform(0, 10, 30)
    
    fig = go.Figure(data=[go.Candlestick(x=dates, open=open_p, high=high_p, low=low_p, close=close_p)])
    fig.update_layout(
        margin=dict(t=10, l=10, r=10, b=10), 
        paper_bgcolor='rgba(0,0,0,0)', 
        plot_bgcolor='rgba(0,0,0,0)', 
        font_color="white", 
        xaxis_rangeslider_visible=False
    )
    st.plotly_chart(fig, use_container_width=True)
    
    if st.button("Suggest more...", key="more_stock"):
        st.session_state.pending_prompt = "Can you provide deeper technical analysis for this stock?"
        st.rerun()

# ==========================================
# 4. MAIN APP UI
# ==========================================
def main():
    inject_custom_css()
    init_state()

    if st.session_state.dashboard_view:
        chat_col, dash_col = st.columns([1.5, 1])
    else:
        chat_col, dash_col = st.columns([1, 0.01])

    with dash_col:
        if st.session_state.dashboard_view:
            st.button("✖️ Close Dashboard", on_click=lambda: st.session_state.update(dashboard_view=None))
            if st.session_state.dashboard_view == "Market Discovery":
                render_market_discovery()
            elif st.session_state.dashboard_view == "Stock Deep Analysis":
                render_stock_deep_analysis()

    with chat_col:
        chat_container = st.container(height=650, border=False)
        
        with chat_container:
            active_path = get_chat_path(st.session_state.current_leaf)
            for msg in active_path:
                with st.chat_message(msg["role"]):
                    
                    # --- 1. USER MESSAGES ---
                    if msg["role"] == "user":
                        
                        if st.session_state.editing_id == msg["id"]:
                            new_text = st.text_area("Edit message", value=msg["content"], label_visibility="collapsed")
                            col1, col2, _ = st.columns([2, 2, 8])
                            
                            if col1.button("Submit Edit", key=f"sub_{msg['id']}"):
                                st.session_state.editing_id = None
                                new_user_msg_id = add_message("user", new_text, msg["parent_id"])
                                st.session_state.current_leaf = new_user_msg_id
                                
                                api_history = [{"role": m["role"], "content": m["content"]} for m in get_chat_path(new_user_msg_id)]
                                try:
                                    with st.spinner("Generating new response..."):
                                        response = ollama.chat(model='mistral', messages=api_history)
                                        bot_reply = response['message']['content']
                                except Exception as e:
                                    bot_reply = f"[Ollama Error] {str(e)}"

                                # Pass the currently active mode so it attaches to the new AI reply
                                attached_dash = st.session_state.active_mode if st.session_state.active_mode != "None" else None
                                ai_msg_id = add_message("assistant", bot_reply, new_user_msg_id, attached_dashboard=attached_dash)
                                st.session_state.current_leaf = ai_msg_id
                                st.session_state.dashboard_view = attached_dash
                                st.rerun()
                                
                            if col2.button("Cancel", key=f"can_{msg['id']}"):
                                st.session_state.editing_id = None
                                st.rerun()
                        
                        else:
                            st.write(msg["content"])
                            siblings = get_siblings(msg["id"])
                            show_nav = len(siblings) > 1
                            curr_idx = siblings.index(msg["id"]) if show_nav else 0
                            
                            edit_col, del_col, prev_col, count_col, next_col, _ = st.columns([0.5, 0.5, 0.5, 1, 0.5, 6])
                            
                            with edit_col:
                                st.markdown('<div class="utility-btn">', unsafe_allow_html=True)
                                if st.button("✏️", key=f"edit_{msg['id']}", help="Edit message"):
                                    st.session_state.editing_id = msg["id"]
                                    st.rerun()
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                            with del_col:
                                st.markdown('<div class="utility-btn">', unsafe_allow_html=True)
                                if st.button("🗑️", key=f"del_{msg['id']}", help="Delete message"):
                                    st.session_state.current_leaf = msg["parent_id"]
                                    st.rerun()
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                            if show_nav:
                                with prev_col:
                                    st.markdown('<div class="utility-btn">', unsafe_allow_html=True)
                                    if st.button("◀", key=f"prev_{msg['id']}") and curr_idx > 0:
                                        curr = siblings[curr_idx - 1]
                                        while st.session_state.msg_tree[curr]["children"]:
                                            curr = st.session_state.msg_tree[curr]["children"][-1]
                                        st.session_state.current_leaf = curr
                                        st.rerun()
                                    st.markdown('</div>', unsafe_allow_html=True)
                                    
                                with count_col:
                                    st.markdown(f"<div style='text-align:center; color:#6B7280; font-size:0.9rem; margin-top:5px;'>{curr_idx + 1}/{len(siblings)}</div>", unsafe_allow_html=True)
                                    
                                with next_col:
                                    st.markdown('<div class="utility-btn">', unsafe_allow_html=True)
                                    if st.button("▶", key=f"next_{msg['id']}") and curr_idx < len(siblings) - 1:
                                        curr = siblings[curr_idx + 1]
                                        while st.session_state.msg_tree[curr]["children"]:
                                            curr = st.session_state.msg_tree[curr]["children"][-1]
                                        st.session_state.current_leaf = curr
                                        st.rerun()
                                    st.markdown('</div>', unsafe_allow_html=True)

                    # --- 2. AI MESSAGES ---
                    else:
                        st.write(msg["content"])
                        # If this message has a dashboard attached, give a button to recall it
                        if msg.get("attached_dashboard"):
                            st.markdown('<div class="dash-btn">', unsafe_allow_html=True)
                            if st.button(f"📊 View {msg['attached_dashboard']}", key=f"recall_{msg['id']}"):
                                st.session_state.dashboard_view = msg["attached_dashboard"]
                                st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)

        # --- BOTTOM INPUT AREA ---
        st.session_state.active_mode = st.radio(
            "Attach Tool to Next Query:", 
            ["None", "Market Discovery", "Stock Deep Analysis"], 
            horizontal=True,
            label_visibility="collapsed"
        )
        
        # Determine if we should process a chat (either typed by user or triggered by a "Suggest more" button)
        user_prompt = st.chat_input("Ask FinChat...")
        
        if st.session_state.pending_prompt:
            user_prompt = st.session_state.pending_prompt
            st.session_state.pending_prompt = None # Clear it immediately

        if user_prompt:
            user_msg_id = add_message("user", user_prompt, st.session_state.current_leaf)
            st.session_state.current_leaf = user_msg_id
            
            api_history = [{"role": m["role"], "content": m["content"]} for m in get_chat_path(user_msg_id)]
            
            try:
                with st.spinner("Analyzing..."):
                    response = ollama.chat(model='mistral', messages=api_history)
                    bot_reply = response['message']['content']
            except Exception as e:
                bot_reply = f"[Ollama Error] {str(e)}"

            # Attach the currently selected tool to the AI's response so we can recall it later
            attached_dash = st.session_state.active_mode if st.session_state.active_mode != "None" else None
            ai_msg_id = add_message("assistant", bot_reply, user_msg_id, attached_dashboard=attached_dash)
            st.session_state.current_leaf = ai_msg_id
            st.session_state.dashboard_view = attached_dash

            st.rerun()

if __name__ == "__main__":
    main()