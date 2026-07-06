from collections import defaultdict
import asyncio
import base64
import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
import models
import schemas
from database import SessionLocal, engine, get_db


models.Base.metadata.create_all(bind=engine)


def ensure_auction_schema() -> None:
    inspector = inspect(engine)
    try:
        auction_columns = {column["name"] for column in inspector.get_columns("auctions")}
    except Exception:
        return

    if "status" not in auction_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE auctions ADD COLUMN status VARCHAR NOT NULL DEFAULT 'Active'"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_auctions_status ON auctions (status)"))


ensure_auction_schema()


SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    salt, stored_hash = hashed_password.split("$", 1)
    test_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), bytes.fromhex(salt), 100000)
    return hmac.compare_digest(stored_hash, test_hash.hex())


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}${hashed.hex()}"


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_access_token(data: dict[str, Any]) -> str:
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = data.copy()
    payload["exp"] = int((datetime.now(timezone.utc).timestamp()) + (ACCESS_TOKEN_EXPIRE_MINUTES * 60))

    header_segment = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_base64url_encode(signature)}"


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
    )
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
        expected_signature = hmac.new(
            SECRET_KEY.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_base64url_encode(expected_signature), signature_segment):
            raise credentials_exception

        payload = json.loads(_base64url_decode(payload_segment))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise credentials_exception

        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except (ValueError, json.JSONDecodeError) as exc:
        raise credentials_exception from exc

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    background_task = asyncio.create_task(auction_closer_worker())
    try:
        yield
    finally:
        background_task.cancel()
        with suppress(asyncio.CancelledError):
            await background_task


async def close_expired_auctions() -> None:
    db = SessionLocal()
    try:
        expired_auctions = (
            db.query(models.Auction)
            .filter(
                models.Auction.status == "Active",
                models.Auction.end_time < utcnow_naive(),
            )
            .all()
        )
        for auction in expired_auctions:
            auction_data = cast(Any, auction)
            auction_data.status = "Closed"
        if expired_auctions:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def auction_closer_worker() -> None:
    while True:
        await close_expired_auctions()
        await asyncio.sleep(60)


# Setup static files directory
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Real-Time Auction Platform", lifespan=lifespan)

# Mount static files for serving uploaded images
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Validation error", "details": exc.errors()},
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(
        status_code=500,
        content={"error": "Database error", "details": str(exc)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "details": str(exc)},
    )


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, auction_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[auction_id].append(websocket)

    def disconnect(self, auction_id: int, websocket: WebSocket):
        connections = self.active_connections.get(auction_id)
        if connections is None:
            return

        if websocket in connections:
            connections.remove(websocket)

        if not connections:
            self.active_connections.pop(auction_id, None)

    async def broadcast(self, auction_id: int, message: dict):
        connections = list(self.active_connections.get(auction_id, []))
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                self.disconnect(auction_id, websocket)


manager = ConnectionManager()


@app.post("/users", response_model=schemas.UserRead, status_code=201)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    try:
        existing_user = db.query(models.User).filter(models.User.email == user.email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        existing_username = db.query(models.User).filter(models.User.username == user.username).first()
        if existing_username:
            raise HTTPException(status_code=400, detail="Username already taken")

        db_user = models.User(
            username=user.username,
            email=user.email,
            hashed_password=hash_password(user.password),
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create user") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error creating user") from exc


@app.post("/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.username == credentials.username).first()
        user_password_hash = cast(str, getattr(user, "hashed_password", "")) if user is not None else ""
        if user is None or not verify_password(credentials.password, user_password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        access_token = create_access_token({"sub": str(user.id), "username": user.username})
        return schemas.Token(access_token=access_token)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Failed to log in") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected login error") from exc


@app.post("/auctions", response_model=schemas.AuctionRead, status_code=201)
def create_auction(
    auction: schemas.AuctionCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if auction.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only create auctions for your own account")

        db_auction = models.Auction(
            title=auction.title,
            description=auction.description,
            starting_price=auction.starting_price,
            current_bid=auction.starting_price,
            status="Active",
            end_time=auction.end_time,
            owner_id=current_user.id,
        )
        db.add(db_auction)
        db.commit()
        db.refresh(db_auction)
        return db_auction
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create auction") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error creating auction") from exc


@app.post("/auctions/sell", response_model=schemas.AuctionRead, status_code=201)
def create_auction_with_asset(
    request: schemas.CreateAuctionRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        # Create Asset
        db_asset = models.Asset(
            name=request.title,
            image_url=request.image_url,
            category=request.category,
            condition=request.condition,
        )
        db.add(db_asset)
        db.flush()

        # Calculate end_time based on duration_hours
        end_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=request.duration_hours)

        # Create Auction linked to Asset
        db_auction = models.Auction(
            title=request.title,
            description=request.description,
            starting_price=request.starting_price,
            current_bid=request.starting_price,
            status="Active",
            end_time=end_time,
            owner_id=current_user.id,
            asset_id=db_asset.id,
        )
        db.add(db_auction)
        db.commit()
        db.refresh(db_auction)
        return db_auction
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create auction") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error creating auction") from exc


@app.get("/auctions", response_model=list[schemas.AuctionRead])
def read_auctions(db: Session = Depends(get_db)):
    try:
        return (
            db.query(models.Auction)
            .options(selectinload(models.Auction.asset), selectinload(models.Auction.bids))
            .all()
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Failed to load auctions") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected error loading auctions") from exc


def fetch_completed_auctions(db: Session) -> list[models.Auction]:
    current_time = utcnow_naive()
    return (
        db.query(models.Auction)
        .options(selectinload(models.Auction.asset), selectinload(models.Auction.bids))
        .filter(
            or_(
                models.Auction.status == "Closed",
                models.Auction.end_time < current_time,
            )
        )
        .order_by(models.Auction.end_time.desc())
        .all()
    )


@app.get("/auctions/history", response_model=list[schemas.AuctionRead])
def read_completed_auctions(db: Session = Depends(get_db)):
    try:
        return fetch_completed_auctions(db)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Failed to load auction history") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unexpected error loading auction history") from exc


@app.websocket("/ws/{auction_id}")
async def auction_updates(websocket: WebSocket, auction_id: int):
    await manager.connect(auction_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(auction_id, websocket)


@app.post("/auctions/{auction_id}/bid", response_model=schemas.AuctionRead)
async def place_bid(
    auction_id: int,
    bid: schemas.BidCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        auction = (
            db.query(models.Auction)
            .filter(models.Auction.id == auction_id)
            .with_for_update()
            .first()
        )
        if auction is None:
            raise HTTPException(status_code=404, detail="Auction not found")

        auction_data = cast(Any, auction)
        if auction_data.status != "Active" or auction_data.end_time <= utcnow_naive():
            raise HTTPException(status_code=400, detail="Auction is closed")

        current_bid = float(auction_data.current_bid)
        if bid.amount <= current_bid:
            raise HTTPException(status_code=400, detail="Bid must be greater than current bid")

        # Sniping prevention: Bid extension rule
        # If bid is placed within final 60 seconds, extend end_time by 2 minutes
        time_remaining = auction_data.end_time - utcnow_naive()
        if time_remaining.total_seconds() < 60:
            auction_data.end_time = auction_data.end_time + timedelta(minutes=2)
            print(f"Auction {auction_id} extended by 2 minutes due to last-minute bid.")

        auction_data.current_bid = bid.amount
        db_bid = models.Bid(amount=bid.amount, auction_id=auction_data.id, bidder_id=current_user.id)
        db.add(db_bid)
        db.commit()
        db.refresh(auction)
        await manager.broadcast(auction_id, {"auction_id": auction_id, "current_bid": auction_data.current_bid})
        return auction
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to place bid") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error placing bid") from exc


@app.post("/upload", response_model=schemas.UploadResponse)
async def upload_image(file: UploadFile = File(...)):
    """
    Upload a product image file.
    
    - Accepts image files (jpg, jpeg, png, gif, webp)
    - Saves to static/uploads/ directory
    - Returns the file path for use in auctions
    """
    try:
        # Validate file type
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        file_ext = Path(file.filename or "").suffix.lower()
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Validate file size (max 5MB)
        MAX_FILE_SIZE = 5 * 1024 * 1024
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is 5MB"
            )
        
        # Generate unique filename using timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        safe_filename = f"{timestamp}{file_ext}"
        file_path = UPLOAD_DIR / safe_filename
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Return path relative to static directory
        return_path = f"/static/uploads/{safe_filename}"
        
        return schemas.UploadResponse(
            filename=safe_filename,
            file_path=return_path
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(exc)}") from exc