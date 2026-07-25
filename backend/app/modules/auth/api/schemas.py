from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
