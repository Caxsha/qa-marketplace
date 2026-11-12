from datetime import datetime
from decimal import Decimal
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
    price: Decimal
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
    login: Optional[str] = None
    email: str
    phone: Optional[str] = None
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
    price: Decimal
    quantity: int
    subtotal: Decimal


class CartOut(BaseModel):
    id: int
    user_id: int
    items: List[CartItemOut]
    total: Decimal

class FulfillmentMethod(str, Enum):
    DELIVERY = "delivery"
    PICKUP = "pickup"

class OrderStatus(str, Enum):
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class OrderItemOut(BaseModel):
    item_id: Optional[int]
    name: str
    item_type: ItemType
    price: Decimal
    quantity: int
    subtotal: Decimal

class OrderOut(BaseModel):
    id: int
    user_id: int
    items: List[OrderItemOut]
    total: Decimal
    fulfillment_method: FulfillmentMethod
    address: Optional[str]
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class CreateOrderRequest(BaseModel):
    fulfillment_method: FulfillmentMethod
    address: Optional[str] = Field(default=None, max_length=300)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
