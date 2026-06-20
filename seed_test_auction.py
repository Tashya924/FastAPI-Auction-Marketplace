from datetime import datetime, timedelta, timezone

from faker import Faker

import models
from database import Base, SessionLocal, engine


FAKER = Faker()

# Realistic product categories for a marketplace
CATEGORIES = [
    "Electronics",
    "Furniture",
    "Fashion",
    "Books",
    "Sports",
    "Collectibles",
    "Home & Garden",
]

# Product conditions
CONDITIONS = ["New", "Like New", "Good", "Fair", "Poor"]

# Sample product names and their default categories
PRODUCTS = [
    {"name": "Vintage Camera", "category": "Collectibles", "image": "https://via.placeholder.com/300?text=Vintage+Camera"},
    {"name": "Mechanical Keyboard", "category": "Electronics", "image": "https://via.placeholder.com/300?text=Mechanical+Keyboard"},
    {"name": "Leather Sofa", "category": "Furniture", "image": "https://via.placeholder.com/300?text=Leather+Sofa"},
    {"name": "Designer Handbag", "category": "Fashion", "image": "https://via.placeholder.com/300?text=Designer+Handbag"},
    {"name": "Signed First Edition Book", "category": "Books", "image": "https://via.placeholder.com/300?text=Signed+Book"},
    {"name": "Mountain Bike", "category": "Sports", "image": "https://via.placeholder.com/300?text=Mountain+Bike"},
    {"name": "Antique Desk Lamp", "category": "Home & Garden", "image": "https://via.placeholder.com/300?text=Antique+Lamp"},
]


def get_or_create_owner(db):
    owner = db.query(models.User).filter(models.User.username == "test_owner").first()
    if owner is not None:
        return owner

    owner = models.User(
        username="test_owner",
        email="test_owner@example.com",
        hashed_password="unused",
    )
    db.add(owner)
    db.flush()
    return owner


def main() -> None:
    # Drop all existing tables and recreate them with new schema
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        owner = get_or_create_owner(db)

        # Generate 5-7 realistic item listings
        num_products = FAKER.random_int(min=5, max=7)
        for idx, product in enumerate(PRODUCTS[:num_products]):
            # Create Asset
            asset = models.Asset(
                name=product["name"],
                image_url=product["image"],
                category=product["category"],
                condition=FAKER.random_element(CONDITIONS),
            )
            db.add(asset)
            db.flush()

            # Create Auction linked to Asset
            starting_price = FAKER.pyfloat(left_digits=3, right_digits=2, positive=True, min_value=10, max_value=500)
            end_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=FAKER.random_int(min=1, max=7))

            auction = models.Auction(
                title=product["name"],
                description=f"{FAKER.sentence(nb_words=8)}. {FAKER.sentence(nb_words=6)}",
                starting_price=starting_price,
                current_bid=starting_price,
                status="Active",
                end_time=end_time,
                owner_id=owner.id,
                asset_id=asset.id,
            )
            db.add(auction)
            print(f"Created auction: {auction.title} (${starting_price:.2f}) with asset: {asset.name}")

        db.commit()
        print(f"\nSuccessfully seeded {num_products} auction listings with assets.")
    except Exception as exc:
        db.rollback()
        print(f"Error during seeding: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
    with api_client() as client:
        response = client.get("/auctions")
        response.raise_for_status()
        return response.json()

def get_countdown(raw_time):
    """Debugged date parser to handle UTC sync."""
    if not isinstance(raw_time, str):
        return "Status: No end date"
    try:
        clean_time = raw_time.replace("Z", "+00:00")
        end_dt = datetime.fromisoformat(clean_time)
        if end_dt.tzinfo is not None:
            end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
            
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        remaining = end_dt - now
        
        if remaining.total_seconds() > 0:
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            hours, mins = divmod(mins, 60)
            return f"Ends in: {hours}h {mins}m {secs}s"
        return "Status: **Auction ended**"
    except Exception as e:
        return f"Status: Date Error ({e})"

st.title("Real-Time Auction Dashboard")
st_autorefresh(interval=5000, key="auction_refresh")

try:
    auctions = load_auctions()
except Exception as exc:
    st.error(f"Unable to load auctions: {exc}")
    st.stop()

active_auctions = [a for a in auctions if a.get("status") == "Active"]

if not active_auctions:
    st.info("No active auctions right now. Run your seed script!")
else:
    for auction in active_auctions:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader(auction["title"])
                st.write(f"Current bid: ${auction['current_bid']:.2f}")
                st.write(get_countdown(auction.get("end_time")))
            with col2:
                if st.button("Place bid", key=f"btn_{auction['id']}"):
                    st.write("Bid button clicked")

with st.expander("Troubleshooting: Why is it showing 'Auction ended'?"):
    st.write("""
    1. **Restart API:** Make sure you restarted your FastAPI server after running the seed script.
    2. **Check Time:** Current UTC time is used. Ensure your system clock is correct.
    3. **Clear DB:** If you have multiple auctions, it might be picking up an old one. Delete `auction.db` and re-run your seed script.
    """)