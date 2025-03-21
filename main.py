import os
import weaviate
import openai
import uvicorn
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from fastapi import FastAPI, Query, Request
from weaviate.collections.classes.filters import Filter
import re
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel

# Load environment variables
load_dotenv()

weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

if not weaviate_url or not weaviate_api_key or not openai_api_key:
    raise ValueError("❌ Missing environment variables.")

weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
    auth_credentials=Auth.api_key(weaviate_api_key),
    skip_init_checks=True
)

if weaviate_client.is_ready():
    print("✅ Successfully connected to Weaviate!")
else:
    raise ConnectionError("❌ Failed to connect to Weaviate.")

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
    return fetch_player_data(player_name, raw_data=True)

@app.get("/analysis/{player_name}")
def analyze_player(player_name: str):
    data = fetch_player_data(player_name, raw_data=True)
    if not data:
        return {"error": f"⚠️ No data for {player_name}."}
    return {"player_name": player_name, "openai_analysis": get_openai_analysis(data)}

@app.get("/compare")
def compare_players_api(player1: str, player2: str, context: str = "Standard dynasty evaluation"):
    data1 = fetch_player_data(player1, raw_data=True)
    data2 = fetch_player_data(player2, raw_data=True)
    if not data1 or not data2:
        return {"error": f"⚠️ Missing data for {player1} or {player2}."}
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

    return {"analysis": response.choices[0].message.content}

# === OpenAI Support ===

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
