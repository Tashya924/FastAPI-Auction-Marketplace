import os
from datetime import datetime, timezone
import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Real-Time Auction Dashboard", layout="wide")

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
                login_response.raise_for_status()
                token = login_response.json()["access_token"]
                st.session_state["token"] = token
                st.session_state["username"] = username
                return "Account already existed. Logged you in."
        response.raise_for_status()
        return "Registration successful. You can now log in."

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

    if image_url.startswith("/"):
        return f"{API_BASE_URL}{image_url}"

    return image_url

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


@st.fragment(run_every="1s")
def render_auction_board() -> None:
    try:
        auctions = load_auctions()
    except Exception as exc:
        st.error(f"Unable to load auctions: {exc}")
        return

    active_auctions = [auction for auction in auctions if auction.get("status") == "Active"]

    if not active_auctions:
        st.info("No active auctions right now.")
        return

    for auction in active_auctions:
        with st.container(border=True):
            # Create columns for layout
            img_col, info_col, bid_col = st.columns([1.5, 2, 1])
            
            # Image column with clickable popover
            with img_col:
                asset = auction.get("asset") or {}
                # Prefer the asset image from the backend, and normalize relative static paths.
                image_url = resolve_image_url(asset.get("image_url") or auction.get("image_url"))
                if image_url is None:
                    image_url = "https://via.placeholder.com/300?text=No+Image"
                
                # Create popover button that displays the image and details
                with st.popover("🔍 View Details", use_container_width=True):
                    st.subheader(auction["title"])
                    
                    # Display image in popover
                    try:
                        st.image(image_url, use_container_width=True, caption=auction["title"])
                    except Exception:
                        st.warning("Could not load image")
                    
                    # Display full details
                    st.divider()
                    st.write("**Description:**")
                    st.write(auction.get("description") or "No description provided.")
                    
                    st.divider()
                    st.write("**Current Bid:**")
                    st.metric("Current Price", f"${auction['current_bid']:.2f}")
                    
                    st.write("**Starting Price:**")
                    st.metric("Starting Price", f"${auction['starting_price']:.2f}")
                    
                    st.divider()
                    st.write("**Time Remaining:**")
                    st.write(get_countdown(auction.get("end_time")))
                
                # Thumbnail display below popover button
                try:
                    st.image(image_url, use_container_width=True)
                except Exception:
                    st.info("📷 Image unavailable")
            
            # Info column
            with info_col:
                st.subheader(auction["title"])
                st.write(auction.get("description") or "No description provided.")
                st.write(f"**Current bid:** ${auction['current_bid']:.2f}")
                st.write(f"**Starting price:** ${auction['starting_price']:.2f}")
                st.write(get_countdown(auction.get("end_time")))
            
            # Bidding column
            with bid_col:
                bid_key = f"bid_amount_{auction['id']}"
                if bid_key not in st.session_state:
                    st.session_state[bid_key] = float(auction["current_bid"] + 1)

                render_bid_feedback(auction["id"])

                with st.form(f"bid_form_{auction['id']}"):
                    bid_amount = st.number_input(
                        "Bid amount",
                        key=bid_key,
                        step=1.0,
                    )
                    submit_bid = st.form_submit_button("Place bid", use_container_width=True)

                if submit_bid:
                    if not st.session_state.get("token"):
                        set_bid_feedback(auction["id"], "warning", "Please log in first.")
                    elif bid_amount <= float(auction["current_bid"]):
                        set_bid_feedback(auction["id"], "error", "Bid must be greater than the current bid.")
                    else:
                        try:
                            message = place_bid(auction["id"], bid_amount)
                            load_auctions.clear()
                            set_bid_feedback(auction["id"], "success", message)
                        except Exception as exc:
                            set_bid_feedback(auction["id"], "error", f"Bid failed: {exc}")

st.title("Real-Time Auction Dashboard")
st.caption("FastAPI backend with JWT auth, WebSocket updates, and background auction closing.")

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

# Main content tabs
tab_browse, tab_sell = st.tabs(["Browse Auctions", "Sell Item"])

with tab_browse:
    render_auction_board()

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
                    st.image(uploaded_file, caption="Image Preview", use_container_width=True)
            else:
                image_url = st.text_input(
                    "Image URL",
                    placeholder="https://example.com/image.jpg",
                    help="Provide a URL to an image of your item"
                )
                if image_url:
                    try:
                        st.image(image_url, caption="Image Preview", use_container_width=True)
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
            submit_auction = st.form_submit_button("Create Auction", use_container_width=True)
            
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
                    except Exception as exc:
                        st.error(f"Failed to create auction: {str(exc)}")