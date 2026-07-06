from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BidRead(BaseModel):
    id: int
    amount: float
    auction_id: int
    bidder_id: int

    model_config = ConfigDict(from_attributes=True)


class BidCreate(BaseModel):
    amount: float


class AssetCreate(BaseModel):
    name: str
    image_url: Optional[str] = None
    category: str
    condition: str


class AssetRead(AssetCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class AuctionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    starting_price: float
    owner_id: int
    end_time: datetime


class CreateAuctionRequest(BaseModel):
    title: str
    description: str
    category: str
    image_url: Optional[str] = None
    condition: str
    starting_price: float
    duration_hours: int  # Duration in hours


class AuctionRead(AuctionCreate):
    id: int
    current_bid: float
    status: str
    asset_id: Optional[int] = None
    asset: Optional[AssetRead] = None
    bids: List[BidRead] = []

    model_config = ConfigDict(from_attributes=True)


class UploadResponse(BaseModel):
    """Response model for file upload endpoint."""
    filename: str
    file_path: str