from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from app.agent import run_agent 

app = FastAPI(
    title="Project Samarth API",
    description="API for the AI-powered data insights chatbot.",
    version="1.0.0",
)

origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Query(BaseModel):
    query: str

@app.get("/")
def read_root():
    return {"status": "Project Samarth API is running"}

@app.post("/query")
def handle_query(query: Query):
    """
    Receives a user query, passes it to the full agent (which decides tools + returns results).
    """
    try:
        # The new run_agent function will handle the multi-step logic
        result = run_agent(query.query)

        # This logic correctly handles the output from the new multi-step agent
        if isinstance(result, dict) and "final_answer" in result:
            return {"output": result["final_answer"]}
        elif isinstance(result, dict) and "error" in result:
            return {"output": f"❌ {result['error']}"}
        else:
            return {"output": "Sorry, I couldn’t generate a valid answer."}
            
    except Exception as e:
        return {"output": f"❌ Unexpected error: {e}"}
