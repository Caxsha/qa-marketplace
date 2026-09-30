from datetime import datetime
from enum import Enum
from typing import Optional
from typing import List
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ItemType(str, Enum):
    PRODUCT = "product"
    SERVICE = "service"


class Item(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    price: float
    category: str
    item_type: ItemType
    stock_quantity: Optional[int] = None
    duration_days: Optional[int] = None


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: UserRole
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class CartItemOut(BaseModel):
    item_id: int
    name: str
    item_type: ItemType
    price: float
    quantity: int
    subtotal: float


class CartOut(BaseModel):
    id: int
    user_id: int
    items: List[CartItemOut]
    total: float