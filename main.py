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

# === Writer Prompts ===
WRITER_PROMPTS = {
    "IBW": '''
    You are a fantasy baseball expert who writes in the style of Michael Halpern (Imaginary Brick Wall).
    Your tone includes: long-form analysis, 25+ word sentences, heavy use of K%, BB%, OPS, ERA, WHIP.
    You write analytically, engagingly, and sometimes with humor.
    Compare players only using provided data.
    ''',
    "Razzball": '''
    You are a fantasy baseball expert who writes for Razzball in the style of Grey Albright. You give advice for single season leagues -- no dynasty or keeper stuff.
    Your tone is casual, witty, and full of personality.
    You often use terms like "shizz", references to pop culture, use a lot of double entendres with player names, and a ton of humor to convey advice.
    Always base your takes only on provided data.
    ''',
    "Both": '''
    You are two fantasy baseball writers — one from Imaginary Brick Wall (long-form, stats-heavy, serious -- presents strictly a dynasty fantasy baseball perspective),
    and one from Razzball (funny, sarcastic, personality-driven -- presents strictly from a single season fantasy baseball perspective).
    Present both of your takes on the players being discussed, making sure each uses their respective tone.
    Do not blend the perspectives. Present them as separate viewpoints. 
    Be sure to highlight the differences in dynasty vs. single-season fantasy baseball when responding as each writer.
    '''
}

# === Projection Formatter ===
def format_projection(column_name: str, value: str, tab_name: str = "") -> str:
    if column_name == "2025 BATTING":
        return f"📊 *2025 projected batting stats:* {value}"
    elif column_name == "2025 PITCHING":
        return f"📊 *2025 projected pitching stats:* {value}"
    elif column_name == "PRIME BATTING":
        return f"🔮 *Prime batting projection:* {value}"
    elif column_name == "PRIME PITCHING" or column_name == "PRIME PITCHING ":
        return f"🔮 *Prime pitching projection:* {value}"
    if tab_name in {"Batters", "C", "1B", "2B", "3B", "SS", "OF", "DH"}:
        if column_name.endswith(".1"):
            base_stat = column_name.replace(".1", "")
            return f"🔮 *Prime projection for {base_stat}:* {value}"
        else:
            return f"📊 *2025 projected {column_name}:* {value}"
    if tab_name in {"SP", "RP"}:
        if column_name.endswith(".1"):
            base_stat = column_name.replace(".1", "")
            return f"🔮 *Prime projection for {base_stat}:* {value}"
        else:
            return f"📊 *2025 projected {column_name}:* {value}"
    return f"*{column_name}:* {value}"

# === Player Data ===
def fetch_player_data(player_name, raw_data=False, writer="IBW"):
    print(f"🔍 Fetching player: {player_name} [Writer: {writer}]")

    # Choose the collection based on writer
    collection_name = {
        "IBW": "FantasyPlayers",
        "Razzball": "FantasyPlayersRazzball"
    }.get(writer, "FantasyPlayers")  # Default fallback to IBW

    try:
        result = weaviate_client.collections.get(collection_name).query.fetch_objects(
            filters=Filter.by_property("player_name").equal(player_name),
            limit=1
        )
        if not result.objects:
            return None if raw_data else f"⚠️ No data for {player_name}."

        obj = result.objects[0]
        summary = obj.properties.get("summary", "No summary available.")
        tab_name = obj.properties.get("tab", "")
        projections = []

        for col, val in obj.properties.items():
            if val and any(kw in col for kw in ["2025", "PRIME", ".1"]):
                projections.append(format_projection(col, str(val), str(tab_name)))

        return {
            "player_name": player_name,
            "summary": str(summary) + ("\n\n" + "\n".join(projections) if projections else ""),
            "rankings": obj.properties.get("rankings", {}),
            "batting_stats": obj.properties.get("batting_stats", {}),
            "pitching_stats": obj.properties.get("pitching_stats", {}),
        }
    except Exception as e:
        return {"error": f"⚠️ Error: {e}"}


# === OpenAI Setup ===
openai_client = openai.OpenAI(api_key=openai_api_key)

def get_prompt_for_writer(writer: str) -> str:
    return WRITER_PROMPTS.get(writer, WRITER_PROMPTS["IBW"])  # fallback to IBW


def compare_players(player1, data1, player2, data2, context, writer="IBW"):
    format_label = "a dynasty format" if writer == "IBW" else "a single-season format"
    prompt = f"""
    Compare {player1} and {player2} in {format_label}.
    Context: {context}

    **{player1}**:
    {data1}

    **{player2}**:
    {data2}

    Who is better and why?
    """

    response = openai_client.chat.completions.create(
        model="gpt-4",
        temperature=0.4,
        messages=[
            {"role": "system", "content": get_prompt_for_writer(writer)},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

def save_query(feature_type, player_names, context="", teamA=None, teamB=None, writer="IBW"):
    file_path = "/mnt/data/user_queries.xlsx"

    if Path(file_path).exists():
        df = pd.read_excel(file_path, sheet_name=None)
        queries_df = df.get("user_queries", pd.DataFrame())
    else:
        queries_df = pd.DataFrame()

    row = {
        "timestamp": datetime.now().isoformat(),
        "feature": feature_type,
        "context": context if feature_type == "trade" else "",
        "writer": writer
    }


    for i in range(1, 11):
        row[f"player_{i}"] = ""
        row[f"teamA_{i}"] = ""
        row[f"teamB_{i}"] = ""

    row["summary_player"] = player_names[0] if feature_type == "summary" and player_names else ""

    if feature_type == "compare":
        for i, player in enumerate(player_names):
            if i < 10:
                row[f"player_{i+1}"] = player

    if feature_type == "trade":
        for i, player in enumerate(teamA or []):
            if i < 10:
                row[f"teamA_{i+1}"] = player
        for i, player in enumerate(teamB or []):
            if i < 10:
                row[f"teamB_{i+1}"] = player

    queries_df = pd.concat([queries_df, pd.DataFrame([row])], ignore_index=True)

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        queries_df.to_excel(writer, sheet_name="user_queries", index=False)

# === Routes ===
@app.get("/")
def root():
    return {"message": "API is running."}

@app.get("/player/{player_name}")
def get_player_info(player_name: str, writer: str = "IBW"):
    save_query("summary", [player_name], writer=writer)
    return fetch_player_data(player_name, raw_data=True, writer=writer)

@app.get("/compare")
def compare_players_api(player1: str, player2: str, context: str = "Standard dynasty evaluation", writer: str = "IBW"):

    data1 = fetch_player_data(player1, raw_data=True, writer=writer)
    data2 = fetch_player_data(player2, raw_data=True, writer=writer)
    if not data1 or not data2:
        return {"error": f"⚠️ Missing data for {player1} or {player2}."}
    save_query("compare", [player1, player2], context, writer=writer)
    return {
        "player1": player1,
        "player2": player2,
        "comparison": compare_players(player1, data1, player2, data2, context, writer)
    }

@app.get("/compare-multi")
def compare_multiple_players_api(
    players: List[str] = Query(...), 
    context: str = "Standard dynasty evaluation",
    writer: str = "IBW"
    ):
    if len(players) < 2:
        return {"error": "⚠️ Need at least two players."}

    player_data_map = {}
    missing = []

    for p in players:
        data = fetch_player_data(p, raw_data=True, writer=writer)
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

{"Who is the best dynasty option and why?" if writer == "IBW" else "Who is the best single-season option and why?"}

"""

    response = openai_client.chat.completions.create(
        model="gpt-4",
        temperature=0.4,
        messages=[
            {"role": "system", "content": get_prompt_for_writer(writer)},
            {"role": "user", "content": prompt}
        ]
    )



    save_query("compare", players, context, writer=writer)
    return {"players": players, "context": context, "comparison": response.choices[0].message.content}

class TradeRequest(BaseModel):
    teamA: List[str]
    teamB: List[str]
    context: str = ""
    writer: str = "IBW"


@app.post("/trade")
def evaluate_trade(request: TradeRequest):
    if not request.teamA or not request.teamB:
        return {"error": "Each team must have at least one player."}

    all_players = request.teamA + request.teamB
    player_data_map = {}
    missing = []

    for player in all_players:
        data = fetch_player_data(player, raw_data=True, writer=request.writer)
        if not data:
            missing.append(player)
        else:
            player_data_map[player] = data

    if missing:
        return {"error": f"Missing data for: {', '.join(missing)}"}

    def format_team(team):
        return "\n\n".join([f"**{p}:**\n{player_data_map[p]}" for p in team])

    evaluation_type = "a dynasty trade" if request.writer == "IBW" else "a single-season trade"

    prompt = f"""
    You are a fantasy baseball expert evaluating {evaluation_type}.

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
        temperature=0.3,
        messages=[
            {"role": "system", "content": get_prompt_for_writer(request.writer)},
            {"role": "user", "content": prompt}
        ]
    )

    save_query("trade", [], request.context, request.teamA, request.teamB, writer=request.writer)
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

    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Not Found")

    df = pd.read_excel(file_path, sheet_name="user_queries")

    column_order = ['timestamp', 'feature', 'writer', 'context', 'summary_player'] + \
                   [col for col in df.columns if col not in ['timestamp', 'feature', 'context', 'summary_player']]
    df = df[column_order]

    player_columns = [col for col in df.columns if col.startswith(('summary_player', 'player_', 'teamA_', 'teamB_'))]

    player_counts = {}

    for _, row in df.iterrows():
        feature = row["feature"]
        players = set()

        if feature == "summary":
            summary_player = row["summary_player"]
            if isinstance(summary_player, str) and summary_player.strip():
                players.add(summary_player.strip())

        elif feature == "compare":
            for col in player_columns:
                if col.startswith("player_"):
                    player = row[col]
                    if isinstance(player, str) and player.strip():
                        players.add(player.strip())

        elif feature == "trade":
            for col in player_columns:
                if col.startswith(("teamA_", "teamB_")):
                    player = row[col]
                    if isinstance(player, str) and player.strip():
                        players.add(player.strip())

        for player in players:
            if player not in player_counts:
                player_counts[player] = {"total": 0, "summary": 0, "compare": 0, "trade": 0}
            player_counts[player]["total"] += 1
            player_counts[player][feature] += 1

    counts_df = pd.DataFrame.from_records([
        {"player": player,
         "total_count": counts["total"],
         "summary_count": counts["summary"],
         "compare_count": counts["compare"],
         "trade_count": counts["trade"]}
        for player, counts in player_counts.items()
    ])

    timestamp_str = datetime.now().strftime("%Y-%m-%d-%H-%M")
    filename = f"halp-bot-export-{timestamp_str}.xlsx"
    export_path = f"/mnt/data/{filename}"

    # === Writer Counts ===
    if "writer" in df.columns:
        writer_feature_counts = df.groupby(["writer", "feature"]).size().unstack(fill_value=0).reset_index()
        writer_feature_counts["total_queries"] = writer_feature_counts.sum(axis=1, numeric_only=True)
    else:
        writer_feature_counts = pd.DataFrame()

    
    with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="user_queries", index=False)
        counts_df.to_excel(writer, sheet_name="player_counts", index=False)
        writer_feature_counts.to_excel(writer, sheet_name="writer_counts", index=False)

    return FileResponse(
        path=export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
