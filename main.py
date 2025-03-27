import os
import weaviate
import openai
import uvicorn
from dotenv import load_dotenv
from datetime import datetime
from weaviate.classes.init import Auth
from fastapi import FastAPI, Query, Request, HTTPException
from weaviate.collections.classes.filters import Filter
import re
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
from fastapi.responses import FileResponse
import pandas as pd
from pathlib import Path

# === Load environment variables ===
load_dotenv()

weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

if not weaviate_url or not weaviate_api_key or not openai_api_key:
    raise ValueError("❌ Missing environment variables.")

# === Connect to Weaviate ===
weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
    auth_credentials=Auth.api_key(weaviate_api_key),
    skip_init_checks=True
)

if weaviate_client.is_ready():
    print("✅ Successfully connected to Weaviate!")
else:
    raise ConnectionError("❌ Failed to connect to Weaviate.")

# === FastAPI Setup ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """
You are a fantasy baseball expert who writes in the style of Michael Halpern. Your writing style includes:
- Long-form analysis, averaging 25+ words per sentence
- Frequent use of K%, BB%, OPS, ERA, WHIP, etc.
- Analytical, engaging, sometimes funny
- Compare players based only on provided data
"""

# === Player Data ===

def fetch_player_data(player_name, raw_data=False):
    print(f"🔍 Fetching player: {player_name}")
    try:
        result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(
            filters=Filter.by_property("player_name").equal(player_name),
            limit=1
        )
        if not result.objects:
            return None if raw_data else f"⚠️ No data for {player_name}."

        obj = result.objects[0]
        summary = obj.properties.get("summary", "No summary available.")
        return {
            "player_name": player_name,
            "summary": summary,
            "rankings": obj.properties.get("rankings", {}),
            "batting_stats": obj.properties.get("batting_stats", {}),
            "pitching_stats": obj.properties.get("pitching_stats", {}),
        }
    except Exception as e:
        return {"error": f"⚠️ Error: {e}"}

@app.get("/")
def root():
    return {"message": "API is running."}

@app.get("/player/{player_name}")
def get_player_info(player_name: str):
    save_query("summary", [player_name])
    return fetch_player_data(player_name, raw_data=True)

@app.get("/compare")
def compare_players_api(player1: str, player2: str, context: str = "Standard dynasty evaluation"):
    data1 = fetch_player_data(player1, raw_data=True)
    data2 = fetch_player_data(player2, raw_data=True)
    if not data1 or not data2:
        return {"error": f"⚠️ Missing data for {player1} or {player2}."}
    save_query("compare", [player1, player2], context)
    return {
        "player1": player1,
        "player2": player2,
        "comparison": compare_players(player1, data1, player2, data2, context)
    }

@app.get("/compare-multi")
def compare_multiple_players_api(
    players: List[str] = Query(...), context: str = "Standard dynasty evaluation"
):
    if len(players) < 2:
        return {"error": "⚠️ Need at least two players."}

    player_data_map = {}
    missing = []

    for p in players:
        data = fetch_player_data(p, raw_data=True)
        if not data:
            missing.append(p)
        else:
            player_data_map[p] = data

    if missing:
        return {"error": f"⚠️ Missing: {', '.join(missing)}"}

    blocks = [f"**{name}:**\n{data}" for name, data in player_data_map.items()]
    prompt = f"""
You are a fantasy baseball expert comparing: {', '.join(players)}.
Context: {context}

{chr(10).join(blocks)}

Who is the best dynasty option and why?
"""

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )

    save_query("compare", players, context)
    return {"players": players, "context": context, "comparison": response.choices[0].message.content}

# === Trade Evaluator ===

class TradeRequest(BaseModel):
    teamA: List[str]
    teamB: List[str]
    context: str = ""

@app.post("/trade")
def evaluate_trade(request: TradeRequest):
    if not request.teamA or not request.teamB:
        return {"error": "Each team must have at least one player."}

    all_players = request.teamA + request.teamB
    player_data_map = {}
    missing = []

    for player in all_players:
        data = fetch_player_data(player, raw_data=True)
        if not data:
            missing.append(player)
        else:
            player_data_map[player] = data

    if missing:
        return {"error": f"Missing data for: {', '.join(missing)}"}

    def format_team(team):
        return "\n\n".join([f"**{p}:**\n{player_data_map[p]}" for p in team])

    prompt = f"""
You are a fantasy baseball expert evaluating a dynasty trade.

📦 Team A is trading:
{format_team(request.teamA)}

🔄 Team B is trading:
{format_team(request.teamB)}

📝 Context:
{request.context}

Choose the better side and explain why using ONLY the provided data.
"""

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )

    save_query("trade", [], request.context, request.teamA, request.teamB)
    return {"analysis": response.choices[0].message.content}

@app.get("/players")
def get_all_player_names():
    try:
        query_result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(limit=10000)
        names = [obj.properties["player_name"] for obj in query_result.objects if "player_name" in obj.properties]
        unique_names = sorted(set(str(name) for name in names))
        return {"players": unique_names}
    except Exception as e:
        return {"error": f"⚠️ Error fetching player names: {str(e)}"}

@app.get("/export-queries")
def export_queries():
    file_path = "/mnt/data/user_queries.xlsx"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Not Found")

    timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M")
    filename = f"halp-bot-export-{timestamp_str}.xlsx"

    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )

# === Save Queries ===

def save_query(feature_type, player_names, context="", teamA=None, teamB=None):
    file_path = "/mnt/data/user_queries.xlsx"

    if Path(file_path).exists():
        df = pd.read_excel(file_path, sheet_name=None)
        queries_df = df.get("user_queries", pd.DataFrame())
    else:
        queries_df = pd.DataFrame()

    row = {
        "timestamp": datetime.now().isoformat(),
        "feature": feature_type,
        "context": context if feature_type == "trade" else ""
    }

    # Fill all fields with empty strings first
    for i in range(1, 11):
        row[f"player_{i}"] = ""
        row[f"teamA_{i}"] = ""
        row[f"teamB_{i}"] = ""

    # Handle summary
    if feature_type == "summary":
        row["summary_player"] = player_names[0] if player_names else ""
    else:
        row["summary_player"] = ""

    # Handle compare
    if feature_type == "compare":
        for i, player in enumerate(player_names):
            if i < 10:
                row[f"player_{i+1}"] = player

    # Handle trade
    if feature_type == "trade":
        for i, player in enumerate(teamA or []):
            if i < 10:
                row[f"teamA_{i+1}"] = player
        for i, player in enumerate(teamB or []):
            if i < 10:
                row[f"teamB_{i+1}"] = player

    queries_df = pd.concat([queries_df, pd.DataFrame([row])], ignore_index=True)

    # Save
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        queries_df.to_excel(writer, sheet_name="user_queries", index=False)

# === OpenAI Setup ===

openai_client = openai.OpenAI(api_key=openai_api_key)

def get_openai_analysis(comparison_text):
    prompt = f"""
You are a fantasy baseball expert analyzing a player using the following data:

{comparison_text}

Who has the edge and why?
"""
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def compare_players(player1, data1, player2, data2, context):
    prompt = f"""
Compare {player1} and {player2} in a dynasty format.
Context: {context}

**{player1}**:
{data1}

**{player2}**:
{data2}

Who is better and why?
"""
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
