import os
import json
import requests
import pandas as pd
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import re

# --- Use langchain_openai if available ---
try:
    from langchain_openai import ChatOpenAI
    LLM_PROVIDER = "langchain_openai"
except Exception:
    try:
        import openai  # type: ignore
        LLM_PROVIDER = "openai"
    except Exception:
        raise RuntimeError("No LLM provider found. Install langchain_openai or openai.")

# ---------------------------
# Configuration / Keys
# ---------------------------
load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or "Your_API_Key"
DATA_GOV_API_KEY = os.getenv("DATA_GOV_API_KEY") or "Your_gov_API_Key"

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY missing. Set it in .env file.")
if not DATA_GOV_API_KEY:
    raise ValueError("DATA_GOV_API_KEY missing. Set it in .env file.")

# --- Data Sources ---
RAINFALL_API_URL = "https://api.data.gov.in/resource/8e0bd482-4aba-4d99-9cb9-ff124f6f1c2f"
LOCAL_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "agriculture_production.csv")
RAINFALL_SOURCE_NAME = f"data.gov.in (Rainfall 1901-2017): {RAINFALL_API_URL}"
AGRICULTURE_SOURCE_NAME = f"data.gov.in (Crop Production): {LOCAL_CSV_PATH}"


# ---------------------------
# Simple LLM wrapper
# ---------------------------
def llm_call(prompt: str, max_tokens: int = 1500, temperature: float = 0.0) -> str:
    """Minimal wrapper to call the LLM."""
    if LLM_PROVIDER == "langchain_openai":
        llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model="gpt-4o-mini",
            temperature=temperature,
            max_tokens=max_tokens
        )
        try:
            resp = llm.invoke(prompt)
            return str(resp.content)
        except Exception as e:
            raise RuntimeError(f"LLM call failed (langchain_openai.invoke): {e}")
    else:
        # Legacy openai v0.x call
        import openai  # type: ignore
        openai.api_key = OPENAI_API_KEY
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content

# ---------------------------
# Data Loading Utility
# ---------------------------
_df_agri = None

def get_agri_data() -> pd.DataFrame:
    """Loads the agriculture CSV into memory (with caching) and cleans it."""
    global _df_agri
    if _df_agri is not None:
        return _df_agri
    
    if not os.path.exists(LOCAL_CSV_PATH):
        raise FileNotFoundError(f"CSV not found at {LOCAL_CSV_PATH}")
    
    df = pd.read_csv(LOCAL_CSV_PATH)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    
    # Find production column
    prod_col = next((c for c in df.columns if "production" in c), None)
    if "state" not in df.columns or prod_col is None:
        raise ValueError(f"CSV missing required 'state' or 'production' columns. Found: {list(df.columns)}")
    
    # Clean data
    df["production_tonnes"] = pd.to_numeric(df[prod_col], errors="coerce").fillna(0)
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"].astype(str).str.split("-").str[0], errors="coerce").fillna(0).astype(int)
    
    # Cache it
    _df_agri = df
    return df

# ---------------------------
# Tool Schemas and Functions
# ---------------------------

# --- Tool 1: Get Single Year Rainfall ---
def get_live_rainfall_data(state: str, year: int) -> Dict[str, Any]:
    """
    (DEPRECATED DATA: 1901-2017)
    Return a dict with rainfall summary for a single state and year.
    """
    if not (1901 <= year <= 2017):
        return {"error": f"Invalid year {year}. Data is only available from 1901 to 2017.", "source": RAINFALL_SOURCE_NAME}
    
    params = {"api-key": DATA_GOV_API_KEY, "format": "json", "limit": 5000}
    try:
        r = requests.get(RAINFALL_API_URL, params=params, timeout=20)
        r.raise_for_status()
        records = r.json().get("records", [])
        if not records:
            return {"error": "No rainfall records returned by API.", "source": RAINFALL_SOURCE_NAME}
        
        df = pd.DataFrame(records)
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df_filtered = df[(df["subdivision"].str.contains(state, case=False, na=False)) & (df["year"] == year)].copy()
        
        if df_filtered.empty:
            available = sorted(df[df["subdivision"].str.contains(state, case=False, na=False)]["year"].dropna().unique().tolist())
            return {"error": f"No data for {state} in {year}. Available years for this state: {available}", "source": RAINFALL_SOURCE_NAME}
        
        months = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
        for m in months:
            if m not in df_filtered.columns:
                df_filtered[m] = 0
        df_filtered[months] = df_filtered[months].apply(pd.to_numeric, errors="coerce").fillna(0)
        
        total = float(df_filtered[months].sum(axis=1).iloc[0])
        avg = float(df_filtered[months].mean(axis=1).iloc[0])
        
        return {
            "state": state,
            "year": int(year),
            "total_rainfall_mm": round(total, 2),
            "average_monthly_rainfall_mm": round(avg, 2),
            "source": RAINFALL_SOURCE_NAME
        }
    except Exception as e:
        return {"error": f"Unexpected error in rainfall API: {e}", "source": RAINFALL_SOURCE_NAME}

# --- Tool 2: Get Agriculture Data ---
def get_local_agriculture_data(
    state: str,
    year: int,
    crop: Optional[str] = None,
    top_n: int = 5
) -> Dict[str, Any]:
    """
    Return aggregated crop data for a state and year from local CSV.
    If 'crop' is provided, returns total production for that crop.
    If 'crop' is NOT provided, returns the 'top_n' most produced crops.
    """
    try:
        df = get_agri_data()
        mask = (df["state"].str.contains(state, case=False, na=False)) & (df["year"] == int(year))
        filtered = df[mask]
        
        if filtered.empty:
            return {"error": f"No agriculture data found for {state} in {year}.", "source": AGRICULTURE_SOURCE_NAME}

        # Query 1: Get total for a *specific* crop
        if crop:
            crop_mask = filtered["crop"].str.contains(crop, case=False, na=False)
            crop_data = filtered[crop_mask]
            if crop_data.empty:
                return {"error": f"No data found for crop '{crop}' in {state} in {year}.", "source": AGRICULTURE_SOURCE_NAME}
            
            total_production = float(crop_data["production_tonnes"].sum())
            return {
                "state": state,
                "year": year,
                "crop": crop,
                "total_production_tonnes": round(total_production, 2),
                "source": AGRICULTURE_SOURCE_NAME
            }

        # Query 2: Get Top N crops (if no specific crop is asked)
        summary = filtered.groupby("crop", as_index=False)["production_tonnes"].sum().sort_values("production_tonnes", ascending=False).head(top_n)
        rows = summary.to_dict(orient="records")
        return {"state": state, "year": year, "top_crops": rows, "source": AGRICULTURE_SOURCE_NAME}
        
    except Exception as e:
        return {"error": f"Unexpected error while reading CSV: {e}", "source": AGRICULTURE_SOURCE_NAME}

# --- Tool 3: Get District-Level Agriculture Data ---
def get_district_production(
    state: str,
    crop: str,
    year: int,
    sort_order: str = 'desc'
) -> Dict[str, Any]:
    """
    Finds the district with the highest or lowest production for a specific crop, state, and year.
    'sort_order' can be 'desc' (for highest) or 'asc' (for lowest).
    """
    try:
        df = get_agri_data()
        if "district" not in df.columns:
            return {"error": "District column not found in CSV.", "source": AGRICULTURE_SOURCE_NAME}

        mask = (df["state"].str.contains(state, case=False, na=False)) & \
               (df["year"] == int(year)) & \
               (df["crop"].str.contains(crop, case=False, na=False))
        
        filtered = df[mask]
        if filtered.empty:
            return {"error": f"No data found for {crop} in {state} in {year}.", "source": AGRICULTURE_SOURCE_NAME}

        summary = filtered.groupby("district", as_index=False)["production_tonnes"].sum()
        
        if sort_order == 'asc':
            summary = summary.sort_values("production_tonnes", ascending=True)
            result_label = "lowest_production_district"
        else:
            summary = summary.sort_values("production_tonnes", ascending=False)
            result_label = "highest_production_district"

        if summary.empty:
            return {"error": f"No district data found for {crop} in {state} in {year}.", "source": AGRICULTURE_SOURCE_NAME}

        top_district = summary.iloc[0].to_dict()
        return {
            "state": state,
            "year": year,
            "crop": crop,
            result_label: {
                "district": top_district["district"],
                "production_tonnes": round(top_district["production_tonnes"], 2)
            },
            "source": AGRICULTURE_SOURCE_NAME
        }
    except Exception as e:
        return {"error": f"Unexpected error in get_district_production: {e}", "source": AGRICULTURE_SOURCE_NAME}

# --- Tool 4: Get Production Trend ---
def get_production_trend(
    state: str,
    crop: str,
    start_year: int,
    end_year: int
) -> Dict[str, Any]:
    """Returns a time-series list of total production for a crop over a range of years."""
    try:
        df = get_agri_data()
        trend = []
        for year in range(int(start_year), int(end_year) + 1):
            mask = (df["state"].str.contains(state, case=False, na=False)) & \
                   (df["year"] == year) & \
                   (df["crop"].str.contains(crop, case=False, na=False))
            
            year_data = df[mask]
            total_production = 0.0
            if not year_data.empty:
                total_production = float(year_data["production_tonnes"].sum())
            
            trend.append({"year": year, "production_tonnes": round(total_production, 2)})
            
        return {"state": state, "crop": crop, "trend": trend, "source": AGRICULTURE_SOURCE_NAME}
    except Exception as e:
        return {"error": f"Unexpected error in get_production_trend: {e}", "source": AGRICULTURE_SOURCE_NAME}

# --- Tool 5: Get Rainfall Trend ---
def get_rainfall_trend(
    state: str,
    start_year: int,
    end_year: int
) -> Dict[str, Any]:
    """
    (DEPRECATED DATA: 1901-2017)
    Returns a time-series list of total rainfall over a range of years.
    NOTE: This tool calls the old API multiple times and is limited to 2017.
    """
    trend = []
    # Clamp years to the available data range
    query_start = max(1901, int(start_year))
    query_end = min(2017, int(end_year))

    for year in range(query_start, query_end + 1):
        result = get_live_rainfall_data(state, year)
        if "error" in result:
            trend.append({"year": year, "total_rainfall_mm": None, "note": result["error"]})
        else:
            trend.append({"year": year, "total_rainfall_mm": result.get("total_rainfall_mm")})
            
    return {
        "state": state,
        "trend": trend,
        "note": "Rainfall data is limited to 1901-2017.",
        "source": RAINFALL_SOURCE_NAME
    }

# ---------------------------
# Tools Registry
# ---------------------------
TOOLS = {
    "get_live_rainfall_data": {
        "func": get_live_rainfall_data,
        "desc": "Get total/avg rainfall for a *single state* and *single year*. (Data 1901-2017 ONLY)",
        "schema": {"state": "string", "year": "integer"}
    },
    "get_local_agriculture_data": {
        "func": get_local_agriculture_data,
        "desc": "Get agriculture data for a *single state* and *single year*. Provide 'crop' to get its total, or 'top_n' to get a list of top crops.",
        "schema": {"state": "string", "year": "integer", "crop": "string (optional)", "top_n": "integer (optional, default 5)"}
    },
    "get_district_production": {
        "func": get_district_production,
        "desc": "Finds the district with the highest ('desc') or lowest ('asc') production for a *specific crop*, *state*, and *year*.",
        "schema": {"state": "string", "crop": "string", "year": "integer", "sort_order": "string ('desc' or 'asc', default 'desc')"}
    },
    "get_production_trend": {
        "func": get_production_trend,
        "desc": "Get a time-series list of production for *one crop* in *one state* over a *range of years*.",
        "schema": {"state": "string", "crop": "string", "start_year": "integer", "end_year": "integer"}
    },
    "get_rainfall_trend": {
        "func": get_rainfall_trend,
        "desc": "Get a time-series list of total rainfall for *one state* over a *range of years*. (Data 1901-2017 ONLY)",
        "schema": {"state": "string", "start_year": "integer", "end_year": "integer"}
    }
}


# -----------------------------------------------
# Agent Orchestration (NEW MULTI-STEP ReAct LOGIC)
# -----------------------------------------------
AGENT_SYSTEM_PROMPT = """You are Project Samarth, a data analyst assistant for Indian agriculture and climate data.
Your job is to answer the user's question. You must be accurate and cite your sources.

You have access to the following tools:
{tool_definitions}

You must follow this process:
1.  **Think:** Analyze the user's question and the conversation history.
2.  **Reason:** Decide if you have enough information to answer.
    - If YES, you *must* respond with your final answer, prefixed with "Final Answer:".
    - If NO, you must choose *one* tool to call to get the missing information.
3.  **Act:** If you need to call a tool, you must respond with *only* a single JSON object. This JSON must contain "tool" (the tool name) and "args" (a dictionary of arguments).

**RULES:**
-   **Multi-step:** For complex questions (like "compare X and Y" or "correlate A and B"), you must call tools multiple times. Call for X, get the result, then call for Y, get the result, then provide the "Final Answer:".
-   **Traceability:** You *must* cite the "source" field returned by the tools for every piece of data you present.
-   **Data Limitations:** The rainfall API only has data from 1901-2017. Politely inform the user if they ask for data outside this range.
-   **Errors:** If a tool returns an error, explain the error to the user and suggest how to fix their query. Do not try to call another tool.
-   **Comparisons:** When comparing two or more items (like "compare X and Y"), you *must* present the final comparison in a Markdown table.
**Conversation History:**
{history}

**User Question:**
{user_query}

Your response (either JSON for a tool call, or "Final Answer: ..." text):
"""

MAX_STEPS = 8 # Max number of tool calls to prevent infinite loops

def get_tool_definitions() -> str:
    """Helper to format tool descriptions for the prompt."""
    defs = []
    for name, info in TOOLS.items():
        defs.append(f"- Tool: `{name}`\n  - Description: {info['desc']}\n  - Arguments (JSON Schema): {json.dumps(info['schema'])}")
    return "\n".join(defs)


def run_agent(user_query: str) -> Dict[str, Any]:
    """
    Main agent entrypoint:
    Runs a multi-step loop to reason, call tools, and get a final answer.
    """
    print(f"\n--- New Query: {user_query} ---")
    history: List[Dict[str, str]] = []
    tool_defs = get_tool_definitions()
    
    for i in range(MAX_STEPS):
        print(f"--- Step {i+1} ---")
        
        # 1. Format the prompt
        history_str = "\n".join([f"Role: {item['role']}\nContent: {item['content']}" for item in history])
        prompt = AGENT_SYSTEM_PROMPT.format(
            tool_definitions=tool_defs,
            history=history_str or "No history yet.",
            user_query=user_query # Only include query on first turn
        )
        
        # 2. Ask LLM for the next step (Reasoning)
        try:
            raw_response = llm_call(prompt)
            print(f"LLM Response:\n{raw_response}")
        except Exception as e:
            print(f"LLM Call Error: {e}")
            return {"error": f"Error communicating with LLM: {e}"}

        # 3. Decide: Is it a Final Answer or a Tool Call?
        
        if raw_response.strip().startswith("Final Answer:"):
            # --- It's a final answer. We're done. ---
            final_answer = raw_response.strip().replace("Final Answer:", "").strip()
            print(f"Final Answer Generated.\n")
            return {"final_answer": final_answer}
        
        else:
            # --- It's a tool call. ---
            try:
                # Add the LLM's "thought" (the tool call JSON) to history
                history.append({"role": "assistant (tool call)", "content": raw_response})

                choice = safe_json_parse(raw_response)
                tool_name = choice.get("tool")
                args = choice.get("args", {})

                if tool_name not in TOOLS:
                    raise ValueError(f"LLM chose unknown tool: {tool_name}")

                # 4. Execute the tool
                print(f"Calling Tool: {tool_name}({args})")
                func = TOOLS[tool_name]["func"]
                result = func(**args)
                
                # 5. Add tool output to history
                tool_output_str = json.dumps(result, ensure_ascii=False)
                print(f"Tool Output:\n{tool_output_str}")
                history.append({"role": "tool_output", "content": tool_output_str})
                
                # Loop continues, LLM will see the tool output in the next step
            
            except Exception as e:
                print(f"Tool/JSON Error: {e}")
                # Add the error to history so the LLM can see what went wrong
                error_str = f"Error: {e}. The LLM response was not valid JSON or the tool call failed. Make sure to respond with *only* JSON for tool calls or 'Final Answer:' for answers."
                history.append({"role": "tool_output", "content": error_str})
                # Continue loop, let LLM try to recover or report error

    # If we exit the loop, we've hit MAX_STEPS
    print("--- Max steps reached ---")
    return {"error": "The agent could not produce a final answer after multiple steps. The query may be too complex."}


# ---------------------------
# Utility functions
# ---------------------------

def safe_json_parse(text: str) -> Dict:
    """Try to safely extract valid JSON from LLM output."""
    try:
        # Find first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise json.JSONDecodeError("No JSON object found", text, 0)
        
        json_text = text[start:end+1]
        return json.loads(json_text)
    except json.JSONDecodeError:
        # Fallback for single quotes
        try:
            json_text = json_text.replace("'", '"')
            return json.loads(json_text)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON from LLM response: {text}") from e

# This function is not used by main.py, but kept for legacy/testing
def query_agent(query: str):
    return run_agent(query) # Reroute to the new agent

# ---------------------------
# Quick interactive test
# ---------------------------
if __name__ == "__main__":
    print("Project Samarth — local agent running (MULTI-STEP).")
    print("Ask questions like: 'Compare rainfall in Kerala and Haryana in 2012' or 'Compare wheat production in Haryana and Punjab in 2012'.\n")
    while True:
        try:
            q = input("Question (or 'quit'): ").strip()
            if not q:
                continue
            if q.lower() in ("quit", "exit"):
                break
            
            out = run_agent(q)
            
            print("\n============================\n")
            if isinstance(out, dict) and "final_answer" in out:
                print("Final Answer (human-friendly):\n")
                print(out["final_answer"])
            elif isinstance(out, dict) and "error" in out:
                print(f"Error: {out['error']}\n")
            print("============================\n")

        except KeyboardInterrupt:
            break
