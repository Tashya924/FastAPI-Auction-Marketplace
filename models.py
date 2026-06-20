from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    auctions = relationship("Auction", back_populates="owner")
    bids = relationship("Bid", back_populates="bidder")


class Asset(Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    image_url = Column(String, nullable=True)
    category = Column(String, nullable=False, index=True)
    condition = Column(String, nullable=False)  # e.g., "New", "Like New", "Good", "Fair", "Poor"

    auction = relationship("Auction", back_populates="asset", uselist=False)


class Auction(Base):
    __tablename__ = "auctions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    starting_price = Column(Float, nullable=False)
    current_bid = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="Active", index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)

    owner = relationship("User", back_populates="auctions")
    asset = relationship("Asset", back_populates="auction", uselist=False)
    bids = relationship("Bid", back_populates="auction", cascade="all, delete-orphan")


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    auction_id = Column(Integer, ForeignKey("auctions.id"), nullable=False)
    bidder_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    auction = relationship("Auction", back_populates="bids")
    bidder = relationship("User", back_populates="bids")