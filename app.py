import os
from datetime import datetime, timezone
import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Real-Time Auction Dashboard", layout="wide")

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Premium background */
.stApp {
    background: #f8fafc;
}

/* Hide header/footer */
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}

/* Modern Card styling for containers */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    border-radius: 16px !important;
    background: white !important;
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.05) !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-4px) !important;
    box-shadow: 0 12px 24px -4px rgba(0, 0, 0, 0.1) !important;
}

/* Titles and Typography */
h1, h2, h3 {
    color: #0f172a !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}
p {
    color: #475569 !important;
}

/* Refined inputs & buttons */
.stButton > button {
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
    font-weight: 600 !important;
}
.stButton > button:hover {
    transform: scale(1.02) !important;
}
button[kind="primary"] {
    background: #1e3a8a !important; /* Dark Blue */
    color: white !important;
    border: none !important;
    box-shadow: 0 4px 14px 0 rgba(30, 58, 138, 0.3) !important;
}
button[kind="secondary"] {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    color: #334155 !important;
}

/* Forms & Inputs */
div[data-baseweb="input"] > div {
    border-radius: 8px !important;
    border-color: #e2e8f0 !important;
    background: #f8fafc !important;
}
div[data-baseweb="input"] > div:focus-within {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 1px #3b82f6 !important;
}

/* Metrics */
[data-testid="stMetricValue"] {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem !important;
    color: #64748b !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-weight: 600 !important;
}

/* Countdowns */
.countdown-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    background: #f1f5f9;
    color: #334155;
    font-size: 0.875rem;
    font-weight: 600;
    margin-top: 0.5rem;
    border: 1px solid #e2e8f0;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

import streamlit.components.v1 as components
components.html("""
<script>
setInterval(() => {
    const parent = window.parent.document;
    const badges = parent.querySelectorAll('.countdown-badge');
    badges.forEach(badge => {
        const endTimeStr = badge.getAttribute('data-endtime');
        if (!endTimeStr) return;
        const safeStr = endTimeStr.endsWith('Z') || endTimeStr.includes('+') ? endTimeStr : endTimeStr + 'Z';
        const endTime = new Date(safeStr).getTime();
        const now = new Date().getTime();
        const diff = Math.floor((endTime - now) / 1000);
        const textSpan = badge.querySelector('.countdown-text');
        if (!textSpan) return;
        if (diff <= 0) {
            textSpan.innerText = "Status: Auction ended";
        } else {
            const h = Math.floor(diff / 3600);
            const m = Math.floor((diff % 3600) / 60);
            const s = diff % 60;
            textSpan.innerText = `Ends in: ${h}h ${m}m ${s}s`;
        }
    });
}, 1000);
</script>
""", height=0)

def auth_headers() -> dict[str, str]:
    token = st.session_state.get("token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}

def api_client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=10.0)

def parse_api_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        return str(payload.get("error") or payload.get("detail") or response.text or f"HTTP {response.status_code}")
    return response.text or f"HTTP {response.status_code}"


def bid_feedback_store() -> dict[str, dict[str, str]]:
    return st.session_state.setdefault("bid_feedback", {})


def set_bid_feedback(auction_id: int, level: str, message: str) -> None:
    bid_feedback_store()[str(auction_id)] = {"level": level, "message": message}


def clear_bid_feedback(auction_id: int) -> None:
    bid_feedback_store().pop(str(auction_id), None)


def render_bid_feedback(auction_id: int) -> None:
    feedback = bid_feedback_store().get(str(auction_id))
    if feedback is None:
        return

    feedback_slot = st.empty()
    with feedback_slot.container():
        if feedback["level"] == "success":
            st.success(feedback["message"])
        elif feedback["level"] == "warning":
            st.warning(feedback["message"])
        else:
            st.error(feedback["message"])

        if st.button("Dismiss message", key=f"dismiss_feedback_{auction_id}"):
            clear_bid_feedback(auction_id)

def register_user(username: str, email: str, password: str) -> str:
    with api_client() as client:
        response = client.post("/users", json={"username": username, "email": email, "password": password})
        if response.status_code == 400:
            error_message = parse_api_error(response)
            if error_message in {"Email already registered", "Username already taken"}:
                login_response = client.post("/login", json={"username": username, "password": password})
                if login_response.status_code == 401:
                    raise Exception("Account already exists, but the password provided is incorrect.")
                login_response.raise_for_status()
                token = login_response.json()["access_token"]
                st.session_state["token"] = token
                st.session_state["username"] = username
                return "Account already existed. Logged you in."
        response.raise_for_status()
        
        login_response = client.post("/login", json={"username": username, "password": password})
        login_response.raise_for_status()
        st.session_state["token"] = login_response.json()["access_token"]
        st.session_state["username"] = username
        
        return "Registration successful. You have been logged in."

def login_user(username: str, password: str) -> str:
    with api_client() as client:
        response = client.post("/login", json={"username": username, "password": password})
        response.raise_for_status()
        token = response.json()["access_token"]
        st.session_state["token"] = token
        st.session_state["username"] = username
        return "Logged in successfully."

@st.cache_data(ttl=1, show_spinner=False)
def load_auctions() -> list[dict]:
    with api_client() as client:
        response = client.get("/auctions")
        response.raise_for_status()
        return response.json()


@st.cache_data(ttl=5, show_spinner=False)
def load_completed_auctions() -> list[dict]:
    with api_client() as client:
        response = client.get("/auctions/history")
        response.raise_for_status()
        return response.json()


def parse_auction_end_time(raw_time: object) -> datetime | None:
    if not isinstance(raw_time, str):
        return None

    try:
        end_dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError:
        return None

    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    else:
        end_dt = end_dt.astimezone(timezone.utc)

    return end_dt


def get_countdown(raw_time: object) -> str:
    end_dt = parse_auction_end_time(raw_time)
    if end_dt is None:
        return "Ends at: Not available"

    remaining = end_dt - datetime.now(timezone.utc)
    total_seconds = int(remaining.total_seconds())
    if total_seconds <= 0:
        return "Status: Auction ended"

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"Ends in: {hours}h {minutes}m {seconds}s"


def resolve_image_url(image_url: object) -> str | None:
    if not isinstance(image_url, str) or not image_url.strip():
        return None

    if image_url.startswith(("http://", "https://")):
        return image_url

    base = API_BASE_URL.rstrip("/")
    if image_url.startswith("/"):
        return f"{base}{image_url}"
    else:
        return f"{base}/{image_url}"


def get_auction_image_url(auction: dict) -> str:
    asset = auction.get("asset") or {}
    resolved = resolve_image_url(asset.get("image_url") or auction.get("image_url"))
    return resolved or "https://via.placeholder.com/640x420?text=No+Image"


def get_status_badge(auction: dict, *, history_view: bool = False) -> tuple[str, str]:
    status = str(auction.get("status") or "Unknown")
    starting_price = float(auction.get("starting_price") or 0)
    current_bid = float(auction.get("current_bid") or 0)

    if history_view:
        if status == "Closed" and current_bid > starting_price:
            return "Sold", "success"
        if status == "Closed":
            return "Expired", "danger"
        return status, "secondary"

    if status == "Active":
        return "Active", "info"

    if status == "Closed":
        return "Closed", "secondary"

    return status, "secondary"


def render_status_badge(label: str, tone: str) -> None:
    colors = {
        "success": ("#166534", "#dcfce7"),
        "danger": ("#991b1b", "#fee2e2"),
        "info": ("#1e40af", "#dbeafe"),
        "secondary": ("#334155", "#f1f5f9"),
    }
    text_color, background = colors.get(tone, colors["secondary"])
    st.markdown(
        f"<span style='display:inline-block;padding:0.35rem 0.8rem;border-radius:9999px;font-size:0.75rem;font-weight:600;color:{text_color};background:{background};letter-spacing:0.025em;text-transform:uppercase;box-shadow:0 1px 2px 0 rgba(0,0,0,0.05);'>{label}</span>",
        unsafe_allow_html=True,
    )

def place_bid(auction_id: int, amount: float) -> str:
    with api_client() as client:
        response = client.post(
            f"/auctions/{auction_id}/bid",
            json={"amount": amount},
            headers=auth_headers(),
        )
        response.raise_for_status()
        return "Bid placed successfully."


def upload_image_file(file) -> str | None:
    """Upload an image file to the backend."""
    if file is None:
        return None
    
    try:
        with api_client() as client:
            files = {"file": (file.name, file.getvalue(), file.type)}
            response = client.post(
                "/upload",
                files=files,
                headers=auth_headers(),
            )
            response.raise_for_status()
            upload_response = response.json()
            return upload_response.get("file_path")
    except Exception as exc:
        st.error(f"Failed to upload image: {exc}")
        return None


def create_auction_with_asset(
    title: str,
    description: str,
    category: str,
    image_url: str | None,
    condition: str,
    starting_price: float,
    duration_hours: int,
) -> str:
    """Create an auction with an asset using the OLX-style endpoint."""
    with api_client() as client:
        response = client.post(
            "/auctions/sell",
            json={
                "title": title,
                "description": description,
                "category": category,
                "image_url": image_url,
                "condition": condition,
                "starting_price": starting_price,
                "duration_hours": duration_hours,
            },
            headers=auth_headers(),
        )
        response.raise_for_status()
        return "Auction created successfully!"


def render_auction_card(auction: dict, *, history_view: bool = False) -> None:
    image_url = get_auction_image_url(auction)
    badge_label, badge_tone = get_status_badge(auction, history_view=history_view)
    current_bid = float(auction.get("current_bid") or 0)
    starting_price = float(auction.get("starting_price") or 0)
    countdown = get_countdown(auction.get("end_time"))
    end_time_str = auction.get("end_time", "")
    category = ((auction.get("asset") or {}).get("category") or "Uncategorized")

    with st.container(border=True):
        image_col, info_col, action_col = st.columns([1, 2.5, 0.8])

        with image_col:
            st.image(image_url, width="stretch", caption=auction["title"])

            with st.popover("View details"):
                st.image(image_url, width="stretch", caption=auction["title"])
                st.write(auction.get("description") or "No description provided.")
                st.metric("Current bid", f"${current_bid:.2f}")
                st.metric("Starting price", f"${starting_price:.2f}")
                st.write(countdown)

        with info_col:
            st.markdown(f"### {auction['title']}")
            render_status_badge(badge_label, badge_tone)
            st.caption(category)
            st.write(auction.get("description") or "No description provided.")

            meta_left, meta_right = st.columns(2)
            with meta_left:
                st.metric("Current bid", f"${current_bid:.2f}")
            with meta_right:
                st.metric("Starting price", f"${starting_price:.2f}")

            st.markdown(f"<div class='countdown-badge' data-endtime='{end_time_str}'>⏳ <span class='countdown-text'>{countdown}</span></div>", unsafe_allow_html=True)

        with action_col:
            if history_view:
                final_label = "Winning bid" if badge_label == "Sold" else "Final state"
                st.metric(final_label, f"${current_bid:.2f}")
                st.caption("Completed auctions are read-only.")
            else:
                st.metric("Current bid", f"${current_bid:.2f}")
            
            if st.button("Open", key=f"open_auction_{auction['id']}", type="primary"):
                st.session_state["selected_auction_id"] = auction["id"]
                st.rerun()


def render_auction_grid(auctions: list[dict], *, history_view: bool = False) -> None:
    if not auctions:
        st.info("No auctions to display here yet.")
        return

    for auction in auctions:
        render_auction_card(auction, history_view=history_view)

def render_dedicated_auction_page(auction_id: int) -> None:
    try:
        auctions = load_auctions()
        auction = next((a for a in auctions if a["id"] == auction_id), None)
        if not auction:
            auctions = load_completed_auctions()
            auction = next((a for a in auctions if a["id"] == auction_id), None)
            
        if not auction:
            st.error("Auction not found.")
            if st.button("Back to Dashboard"):
                del st.session_state["selected_auction_id"]
                st.rerun()
            return
    except Exception as exc:
        st.error(f"Failed to load auction data: {exc}")
        return

    if st.button("← Back to Dashboard"):
        del st.session_state["selected_auction_id"]
        st.rerun()

    image_url = get_auction_image_url(auction)
    current_bid = float(auction.get("current_bid") or 0)
    starting_price = float(auction.get("starting_price") or 0)
    countdown = get_countdown(auction.get("end_time"))
    end_time_str = auction.get("end_time", "")
    category = ((auction.get("asset") or {}).get("category") or "Uncategorized")
    status = auction.get("status")
    history_view = status == "Closed"
    badge_label, badge_tone = get_status_badge(auction, history_view=history_view)

    st.markdown(f"## {auction['title']}")
    
    col1, col2 = st.columns([1.5, 1])
    with col1:
        st.image(image_url, width="stretch", caption=auction["title"])
        st.write(auction.get("description") or "No description provided.")
    
    with col2:
        render_status_badge(badge_label, badge_tone)
        st.caption(category)
        st.markdown(f"<div class='countdown-badge' data-endtime='{end_time_str}' style='margin-bottom:1rem;'>⏳ <span class='countdown-text'>{countdown}</span></div>", unsafe_allow_html=True)
        
        is_ended = countdown.startswith("Status: Auction ended") or status == "Closed"
        
        # Inject WebSocket HTML
        ws_url = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/{auction_id}"
        rest_url = f"{API_BASE_URL}/auctions"
        html_code = f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@600;800&display=swap');
        .live-bid-panel {{
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: white;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin-bottom: 1rem;
        }}
        .live-bid-label {{
            font-size: 0.75rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }}
        .live-bid-value {{
            font-size: 3rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(to right, #60a5fa, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1.2;
            margin-top: 0.5rem;
        }}
        </style>
        <div class="live-bid-panel">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div class="live-bid-label">Live Current bid</div>
                <div id="ws-status" style="font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.6rem; border-radius: 999px; background: rgba(0,0,0,0.2); color: #ff4b4b;">🔴 Connecting...</div>
            </div>
            <div id="live-bid-value" class="live-bid-value">Loading...</div>
        </div>
        <script>
            const auctionId = {auction_id};
            const wsUrl = "{ws_url}";
            const restUrl = "{rest_url}";
            let ws;
            let reconnectAttempts = 0;
            
            function updateUI(newBid) {{
                document.getElementById('live-bid-value').innerText = "$" + newBid.toFixed(2);
                
                const parent = window.parent.document;
                
                // Update metrics if present
                const labels = parent.querySelectorAll('[data-testid="stMetricLabel"]');
                labels.forEach(label => {{
                    if (label.textContent.includes('Current bid') || label.textContent.includes('Winning bid') || label.textContent.includes('Final state')) {{
                        const valueEl = label.parentElement.querySelector('[data-testid="stMetricValue"]');
                        if (valueEl) valueEl.textContent = "$" + newBid.toFixed(2);
                    }}
                }});
                
                // Update number input and validation
                const numberInputs = parent.querySelectorAll('input[type="number"]');
                numberInputs.forEach(input => {{
                    const ariaLabel = input.getAttribute('aria-label');
                    if (ariaLabel && ariaLabel.includes('Your Bid Amount')) {{
                        const minBid = newBid + 1;
                        input.min = minBid;
                        input.setAttribute('aria-valuemin', minBid);
                        if (parseFloat(input.value) < minBid) {{
                            input.value = minBid;
                            
                            // Trigger react updates
                            const event = new Event('input', {{ bubbles: true }});
                            let tracker = input._valueTracker;
                            if (tracker) tracker.setValue(input.value);
                            input.dispatchEvent(event);
                        }}
                    }}
                }});
            }}

            function fetchInitial() {{
                fetch(restUrl)
                    .then(r => r.json())
                    .then(data => {{
                        const auction = Array.isArray(data) ? data.find(a => a.id === auctionId) : null;
                        if (auction) updateUI(parseFloat(auction.current_bid));
                    }})
                    .catch(console.error);
            }}

            function connect() {{
                document.getElementById('ws-status').innerText = "🔴 Connecting...";
                document.getElementById('ws-status').style.color = "#ff4b4b";
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function() {{
                    document.getElementById('ws-status').innerText = "🟢 Live";
                    document.getElementById('ws-status').style.color = "#00cc66";
                    reconnectAttempts = 0;
                    fetchInitial();
                }};
                
                ws.onmessage = function(event) {{
                    const data = JSON.parse(event.data);
                    if (data.current_bid) {{
                        updateUI(parseFloat(data.current_bid));
                    }}
                }};
                
                ws.onclose = function() {{
                    document.getElementById('ws-status').innerText = "🔴 Reconnecting...";
                    document.getElementById('ws-status').style.color = "#ff4b4b";
                    let delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
                    reconnectAttempts++;
                    setTimeout(connect, delay);
                }};
            }}
            
            connect();
        </script>
        """
        import streamlit.components.v1 as components
        components.html(html_code, height=180)

        if is_ended:
            st.error("This auction is closed. Bidding is disabled.")
        else:
            bid_key = f"bid_amount_dedicated_{auction_id}"
            if bid_key not in st.session_state:
                st.session_state[bid_key] = float(current_bid + 1)

            render_bid_feedback(auction_id)

            with st.form(f"bid_form_dedicated_{auction_id}"):
                bid_amount = st.number_input(
                    "Your Bid Amount",
                    key=bid_key,
                    step=1.0,
                    min_value=float(current_bid + 1),
                )
                submit_bid = st.form_submit_button("Place bid", use_container_width=True, type="primary")

            if submit_bid:
                if not st.session_state.get("token"):
                    set_bid_feedback(auction_id, "warning", "Please log in first.")
                elif bid_amount <= current_bid:
                    set_bid_feedback(auction_id, "error", "Bid must be greater than the current bid.")
                else:
                    try:
                        message = place_bid(auction_id, bid_amount)
                        load_auctions.clear()
                        load_completed_auctions.clear()
                        set_bid_feedback(auction_id, "success", message)
                    except Exception as exc:
                        set_bid_feedback(auction_id, "error", f"Bid failed: {exc}")

st.title("Marketplace Dashboard")
st.caption("Browse live listings, review completed history, and sell items with a clean marketplace flow.")

with st.sidebar:
    st.header("Account")
    tab_register, tab_login = st.tabs(["Register", "Login"])
    with tab_register:
        with st.form("register_form"):
            reg_username = st.text_input("Username", key="register_username")
            reg_email = st.text_input("Email", key="register_email")
            reg_password = st.text_input("Password", type="password", key="register_password")
            register_submit = st.form_submit_button("Create account")
            if register_submit:
                try:
                    st.success(register_user(reg_username, reg_email, reg_password))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Registration failed: {exc}")
    with tab_login:
        with st.form("login_form"):
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_submit = st.form_submit_button("Log in")
            if login_submit:
                try:
                    st.success(login_user(login_username, login_password))
                except Exception as exc:
                    st.error(f"Login failed: {exc}")
    if st.session_state.get("token"):
        st.success(f"Authenticated as {st.session_state.get('username', 'user')}")
    else:
        st.info("Log in to place bids.")

if "selected_auction_id" in st.session_state:
    render_dedicated_auction_page(st.session_state["selected_auction_id"])
    st.stop()

tab_active, tab_history, tab_sell = st.tabs(["Active Auctions", "Completed History", "Sell Item"])

with tab_active:
    try:
        auctions = load_auctions()
        active_auctions = [auction for auction in auctions if auction.get("status") == "Active"]
        render_auction_grid(active_auctions)
    except Exception as exc:
        st.error(f"Unable to load active auctions: {exc}")

with tab_history:
    try:
        completed_auctions = load_completed_auctions()
        render_auction_grid(completed_auctions, history_view=True)
    except Exception as exc:
        st.error(f"Unable to load completed history: {exc}")

with tab_sell:
    st.header("Sell Your Item")
    
    if not st.session_state.get("token"):
        st.warning("Please log in first to sell items.")
    else:
        st.subheader("Item Details")
        
        with st.form("create_auction_form"):
            # Item Information
            col1, col2 = st.columns(2)
            with col1:
                item_title = st.text_input("Item Title", placeholder="e.g., Vintage Camera")
                item_category = st.selectbox(
                    "Category",
                    ["Electronics", "Furniture", "Fashion", "Books", "Sports", "Collectibles", "Home & Garden"]
                )
            with col2:
                item_condition = st.selectbox(
                    "Condition",
                    ["New", "Like New", "Good", "Fair", "Poor"]
                )
                starting_price = st.number_input("Starting Price ($)", min_value=0.01, step=0.01)
            
            # Description
            item_description = st.text_area(
                "Item Description",
                placeholder="Provide details about your item...",
                height=100
            )
            
            # Image Upload Section
            st.subheader("Product Image")
            upload_option = st.radio(
                "How would you like to provide an image?",
                ["Upload File", "Use Image URL"]
            )
            
            image_url = None
            if upload_option == "Upload File":
                uploaded_file = st.file_uploader(
                    "Choose an image file",
                    type=["jpg", "jpeg", "png", "gif", "webp"],
                    help="Maximum file size: 5MB"
                )
                if uploaded_file is not None:
                    # Show preview of uploaded image
                    st.image(uploaded_file, caption="Image Preview", width="stretch")
            else:
                image_url = st.text_input(
                    "Image URL",
                    placeholder="https://example.com/image.jpg",
                    help="Provide a URL to an image of your item"
                )
                if image_url:
                    try:
                        st.image(image_url, caption="Image Preview", width="stretch")
                    except Exception:
                        st.warning("Could not load image from URL")
            
            # Duration
            duration_hours = st.number_input(
                "Auction Duration (Hours)",
                min_value=1,
                max_value=168,
                value=24,
                step=1
            )
            
            # Submit button
            submit_auction = st.form_submit_button("Create Auction", use_container_width=True, type="primary")
            
            if submit_auction:
                # Validation
                if not item_title:
                    st.error("Please provide an item title.")
                elif not item_description:
                    st.error("Please provide an item description.")
                elif starting_price <= 0:
                    st.error("Starting price must be greater than $0.")
                else:
                    # Handle image upload
                    final_image_url = image_url
                    if upload_option == "Upload File" and uploaded_file is not None:
                        with st.spinner("Uploading image..."):
                            final_image_url = upload_image_file(uploaded_file)
                            if final_image_url is None:
                                st.stop()
                    
                    try:
                        message = create_auction_with_asset(
                            title=item_title,
                            description=item_description,
                            category=item_category,
                            image_url=final_image_url,
                            condition=item_condition,
                            starting_price=starting_price,
                            duration_hours=duration_hours,
                        )
                        st.success(message)
                        load_auctions.clear()  # Refresh auction list
                        st.balloons()
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to create auction: {str(exc)}")