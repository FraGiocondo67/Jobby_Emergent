from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class SessionIn(BaseModel):
    session_token: str


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


class BankAccountIn(BaseModel):
    account_holder: str
    iban: str


class DisputeIn(BaseModel):
    reason: str


class MessageIn(BaseModel):
    text: str
