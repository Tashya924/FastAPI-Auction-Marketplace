from datetime import datetime, timedelta, timezone

import pytest


async def register_and_login(client, payload):
    register_response = await client.post("/users", json=payload)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/login",
        json={"username": payload["username"], "password": payload["password"]},
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


@pytest.mark.anyio
async def test_user_registration(client, auth_user_payload):
    response = await client.post("/users", json=auth_user_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == auth_user_payload["username"]
    assert body["email"] == auth_user_payload["email"]
    assert "hashed_password" not in body


@pytest.mark.anyio
async def test_create_auction(client, auth_user_payload):
    token = await register_and_login(client, auth_user_payload)

    response = await client.post(
        "/auctions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Vintage Camera",
            "description": "Classic film camera in excellent condition",
            "starting_price": 100.0,
            "owner_id": 1,
            "end_time": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)).isoformat(),
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Vintage Camera"
    assert body["status"] == "Active"


@pytest.mark.anyio
async def test_place_valid_bid(client, auth_user_payload, bidder_payload):
    owner_token = await register_and_login(client, auth_user_payload)
    bidder_token = await register_and_login(client, bidder_payload)

    auction_response = await client.post(
        "/auctions",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Antique Desk",
            "description": "Mahogany desk with brass handles",
            "starting_price": 250.0,
            "owner_id": 1,
            "end_time": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)).isoformat(),
        },
    )
    assert auction_response.status_code == 201
    auction_id = auction_response.json()["id"]

    bid_response = await client.post(
        f"/auctions/{auction_id}/bid",
        headers={"Authorization": f"Bearer {bidder_token}"},
        json={"amount": 300.0},
    )

    assert bid_response.status_code == 200
    body = bid_response.json()
    assert body["current_bid"] == 300.0