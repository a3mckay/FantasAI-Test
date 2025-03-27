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

# [Existing endpoints and code remain unchanged]

# === Updated Export Queries Endpoint ===

@app.get("/export-queries")
def export_queries():
    file_path = "/mnt/data/user_queries.xlsx"

    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Not Found")

    df = pd.read_excel(file_path, sheet_name="user_queries")

    player_columns = [col for col in df.columns if col.startswith(('summary_player', 'player_', 'teamA_', 'teamB_'))]

    player_counts = {}

    for _, row in df.iterrows():
        feature = row["feature"]
        players = set()

        if feature == "summary":
            if row["summary_player"]:
                players.add(row["summary_player"])

        elif feature == "compare":
            for col in [col for col in player_columns if col.startswith("player_")]:
                if row[col]:
                    players.add(row[col])

        elif feature == "trade":
            for col in [col for col in player_columns if col.startswith(("teamA_", "teamB_"))]:
                if row[col]:
                    players.add(row[col])

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

    with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="user_queries", index=False)
        counts_df.to_excel(writer, sheet_name="player_counts", index=False)

    return FileResponse(
        path=export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename
    )

# [Remaining existing endpoints and functions remain unchanged]

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
