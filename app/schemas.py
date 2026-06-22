from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    userId: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    clientContext: Optional[str] = None
    role: Optional[str] = "client"
    salonId: Optional[str] = None
    model: Optional[str] = None
    stream: bool = False
    temperature: Optional[float] = None



class ChatResponse(BaseModel):
    model: str
    content: str
    done: bool
    actionPerformed: Optional[str] = None
