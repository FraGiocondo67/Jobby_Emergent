from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class SessionIn(BaseModel):
    session_token: str


class PriceItem(BaseModel):
    name: str
    price: float = Field(default=0.0, ge=0)
    unit: Optional[str] = ""


class Availability(BaseModel):
    days: List[str] = []      # ["mon","tue","wed","thu","fri","sat","sun"]
    start: str = ""           # "09:00"
    end: str = ""             # "18:00"


class ProfileUpdate(BaseModel):
    role: Optional[str] = None            # client | provider | business
    language: Optional[str] = None
    bio: Optional[str] = None
    business_name: Optional[str] = None
    hourly_rate: Optional[float] = None
    radius_km: Optional[float] = None
    services: Optional[List[str]] = None  # candidate activities
    service_mode: Optional[str] = None    # outdoor | in_shop | both (business/provider)
    online: Optional[bool] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    # contact & preferences
    address: Optional[str] = None
    phone: Optional[str] = None
    contact_email: Optional[str] = None
    preferences: Optional[str] = None
    # provider/business
    availability: Optional[Availability] = None
    price_list: Optional[List[PriceItem]] = None


class MissionIn(BaseModel):
    category: str
    service_type: str
    config: Dict[str, Any] = {}
    address: str
    lat: float
    lng: float
    date: str
    time: str
    duration_hours: float
    recurrence: str = "once"


class AcceptIn(BaseModel):
    price: Optional[float] = None


class SelectIn(BaseModel):
    provider_id: str


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


class ClientRatingIn(BaseModel):
    rating: int
    brief_accuracy: int = 5
    tip: float = 0.0


class WalletIn(BaseModel):
    amount: float


class PaymentIn(BaseModel):
    service_id: str
    label: str
    amount: float
    answers: Dict[str, Any] = {}


class PaymentMethodIn(BaseModel):
    card_holder: str
    card_last4: str
    card_brand: str = "visa"
    expiry: str
    cvv: str = ""   # collected for setup; never persisted


class BankAccountIn(BaseModel):
    account_holder: str
    iban: str


class CryptoWalletIn(BaseModel):
    token: str      # USDT_TRC | USDT_ETH | USDC_ETH | XRP | BTC
    name: str = ""
    address: str
    network: str = ""


class DisputeIn(BaseModel):
    reason: str


class MessageIn(BaseModel):
    text: str


class BusinessRequestIn(BaseModel):
    business_id: str
    category: str
    note: str = ""
    address: str = ""
    lat: float = 0.0
    lng: float = 0.0


class BusinessResponseIn(BaseModel):
    accept: bool
    eta: str = ""             # estimated time (free text, e.g. "oggi 18:00")
    mode: str = "pickup"      # pickup (in-shop) | delivery
    delivery_cost: float = Field(default=0.0, ge=0)
    price: float = Field(default=0.0, ge=0)
    note: str = ""
