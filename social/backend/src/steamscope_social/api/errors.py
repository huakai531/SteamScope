from pydantic import BaseModel, Field


class FieldError(BaseModel):
    field: str
    code: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[FieldError] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None
