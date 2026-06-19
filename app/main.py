from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import ChatRequest, ChatResponse
from app.services.kora_agent import KoraAgentService
from app.settings import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent service instance
agent_service = KoraAgentService()

def verify_token(x_api_token: str | None = Header(default=None)):
    if x_api_token != settings.api_shared_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "env": settings.app_env,
        "status": "running",
        "model": settings.ollama_model,
    }

@app.get("/v1/health")
async def health():
    return {"status": "ok"}

@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(verify_token)])
async def chat(request: ChatRequest):
    # Convert ChatMessage list to dict format
    messages_dict = [{"role": msg.role, "content": msg.content} for msg in request.messages]
    
    result = await agent_service.chat(
        messages=messages_dict,
        user_id=request.userId,
        latitude=request.latitude,
        longitude=request.longitude,
        client_context=request.clientContext,
    )
    
    return ChatResponse(
        model=result.get("model", settings.ollama_model),
        content=result.get("content", ""),
        done=result.get("done", True),
        actionPerformed=result.get("actionPerformed", None),
    )
