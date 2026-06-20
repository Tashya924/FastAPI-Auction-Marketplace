# Real-Time Auction Platform

FastAPI-based auction system that combines JWT authentication, SQLAlchemy-backed persistence, row-level locking for safe concurrent bids, WebSocket broadcasting for live updates, and a lifespan-managed background worker that closes expired auctions automatically.

This project was built to demonstrate the kind of engineering tradeoffs expected in production systems: protecting shared state, keeping latency low for users watching the same auction, and ensuring that background cleanup work does not interfere with request handling.

## What I Solved

The application is designed around three hard problems that often show up in real products:

Concurrency control. The bid endpoint locks the auction row before updating `current_bid`, so two users racing to bid at the same moment do not overwrite each other.

Real-time state propagation. After a successful bid is committed, the server broadcasts the new price to every client subscribed to that auction over WebSockets.

Background lifecycle management. Expired auctions are closed by an asyncio worker started with FastAPI's lifespan context manager, and the worker is cancelled cleanly on shutdown.

## Tech Stack

FastAPI, SQLAlchemy, SQLite, WebSockets, JWT auth, Streamlit, pytest, and httpx.

## Features

- User registration and JWT login.
- Authenticated auction creation and bidding.
- Row-level locking with `with_for_update()` for bid safety.
- WebSocket endpoint for live bid broadcasts.
- Lifespan-based background worker that closes expired auctions.
- Streamlit dashboard for browsing auctions and placing bids.
- Pytest/httpx test suite covering the core API flows.

## Project Structure

- `main.py` - FastAPI app, auth, WebSockets, bid logic, and lifespan worker.
- `models.py` - SQLAlchemy models.
- `schemas.py` - Pydantic request/response models.
- `database.py` - SQLAlchemy engine and session configuration.
- `app.py` - Streamlit dashboard.
- `tests/` - pytest suite.

## Setup

Create a virtual environment, then install the dependencies:

```bash
pip install -r requirements.txt
```

Set a production secret before running the app:

```bash
set SECRET_KEY=your-secure-random-secret
```

## Run the API

```bash
uvicorn main:app --reload
```

## Run the Dashboard

```bash
streamlit run app.py
```

## Run Tests

```bash
pytest
```

## API Highlights

- `POST /users` registers a user.
- `POST /login` returns a JWT access token.
- `POST /auctions` creates an auction for the authenticated owner.
- `POST /auctions/{auction_id}/bid` places a protected bid.
- `WS /ws/{auction_id}` streams live bid updates to connected clients.

## Notes

SQLite is sufficient for local development and testing, but the row-level locking path is most meaningful on a database such as PostgreSQL. The code is structured so that swapping the database backend later is straightforward.

The schema changes in this version add password hashing, auction status tracking, and expiration timestamps. If you already have an existing `auction.db` file, recreate it or run a migration before using the updated app.