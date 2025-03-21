import os
import weaviate
import openai
import uvicorn
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from fastapi import FastAPI, Query
from weaviate.collections.classes.filters import Filter
import re
from fastapi.middleware.cors import CORSMiddleware
from typing import List


# Load environment variables from .env file
load_dotenv()

# ✅ Fetch API Keys & Weaviate URL
weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")  # ✅ Keep OpenAI API Key

# ✅ Debugging: Check if values are loaded
print(f"🔍 Debug: WEAVIATE_URL = {os.getenv('WEAVIATE_URL')}")
print(f"🔍 Debug: WEAVIATE_API_KEY = {'SET' if os.getenv('WEAVIATE_API_KEY') else 'MISSING'}")
print(f"🔍 Debug: OPENAI_API_KEY = {'SET' if os.getenv('OPENAI_API_KEY') else 'MISSING'}")

# ✅ Ensure variables are properly set before using them
if not weaviate_url:
    raise ValueError("❌ WEAVIATE_URL is missing. Check your .env file.")
if not weaviate_api_key:
    raise ValueError("❌ WEAVIATE_API_KEY is missing. Check your .env file.")
if not openai_api_key:
    raise ValueError("❌ OPENAI_API_KEY is missing. Check your .env file.")

# ✅ Connect to Weaviate Cloud (Official Method)
weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
    auth_credentials=Auth.api_key(weaviate_api_key),
    skip_init_checks=True  # ✅ This alone should allow REST-only mode
)

# ✅ Verify connection
if weaviate_client.is_ready():
    print("✅ Successfully connected to Weaviate!")
else:
    raise ConnectionError("❌ Failed to connect to Weaviate. Check your credentials.")

# ✅ Create FastAPI app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Allows all domains (for now, update this later for security)
    allow_credentials=True,
    allow_methods=["*"],  # ✅ Allows GET, POST, DELETE, etc.
    allow_headers=["*"],  # ✅ Allows all headers
)

# ✅ Define SYSTEM_PROMPT globally
SYSTEM_PROMPT = """
    You are a fantasy baseball expert who writes in the style of Michael Halpern. Your writing style includes:
    - **Sentence length:** Long-form analysis, averaging 25+ words per sentence.
    - **Frequent statistical analysis:** Uses advanced baseball metrics such as K%, BB%, OPS, OBP, ERA, WHIP, and wOBA to provide insights.
    - **Tone:** Analytical, data-driven, engaging, and sometimes funny. Your responses should mimic how Michael Halpern presents fantasy baseball analysis.
    - **Player evaluations:** Compares players based on advanced metrics and real-world performance trends.
 You can only use the following provided statistics and rankings.
    Do NOT speculate beyond the provided data. If a comparison point is missing, acknowledge it instead of guessing.

    Here is the data you MUST use (no external knowledge allowed):

    {comparison_text}

    Based on this information alone, which player has the edge and why?
    """

# ✅ Function to fetch player data from Weaviate
def fetch_player_data(player_name, raw_data=False):
    """
    Fetches a player's data from Weaviate.
    - If `raw_data` is True, returns the full dictionary of the player's data.
    - Otherwise, formats and returns a readable summary.
    """
    print(f"🔍 Searching for player: {player_name}...")

    try:
        query_result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(
            filters=Filter.by_property("player_name").equal(player_name),
            limit=1
        )

        if not query_result.objects:
            return None if raw_data else f"⚠️ I'm sorry, I don't have any information on {player_name}."

        # ✅ Extract player details
        obj = query_result.objects[0]
        summary = obj.properties.get("summary", "No summary available.")
        rankings = obj.properties.get("rankings", {})
        batting_stats = obj.properties.get("batting_stats", {})
        pitching_stats = obj.properties.get("pitching_stats", {})

        if raw_data:
            return {
                "player_name": player_name,
                "summary": summary,
                "rankings": rankings,
                "batting_stats": batting_stats,
                "pitching_stats": pitching_stats,
            }

        # ✅ Format response
        return {
            "player_name": player_name,
            "summary": summary,
            "rankings": rankings,
            "batting_stats": batting_stats,
            "pitching_stats": pitching_stats
        }

    except Exception as e:
        return {"error": f"⚠️ Error retrieving player data: {e}"}

# ✅ API Endpoint to Fetch Player Data
@app.get("/player/{player_name}")
def get_player_info(player_name: str):
    return fetch_player_data(player_name, raw_data=True)

# ✅ API Endpoint for OpenAI Analysis of a Player
@app.get("/analysis/{player_name}")
def analyze_player(player_name: str):
    """Fetches player data and sends it to OpenAI for deeper analysis."""
    player_data = fetch_player_data(player_name, raw_data=True)

    if not player_data:
        return {"error": f"⚠️ No data found for {player_name}."}

    # ✅ Send data to OpenAI
    openai_response = get_openai_analysis(player_data)
    return {"player_name": player_name, "openai_analysis": openai_response}

@app.get("/compare")
def compare_players_api(
    player1: str = Query(..., description="First player's name"),
    player2: str = Query(..., description="Second player's name"),
    context: str = Query("Standard dynasty evaluation", description="User context for the comparison")
):
    """API endpoint to compare two players based on Weaviate data and OpenAI analysis."""

    # ✅ Fetch player data
    player1_data = fetch_player_data(player1, raw_data=True)
    player2_data = fetch_player_data(player2, raw_data=True)

    if not player1_data or not player2_data:
        return {"error": f"⚠️ Missing data for {player1} or {player2}."}

    # ✅ Call OpenAI comparison function
    openai_response = compare_players(player1, player1_data, player2, player2_data, context)

    return {"player1": player1, "player2": player2, "comparison": openai_response}

# Compare multiple players
@app.get("/compare-multi")
def compare_multiple_players_api(
    players: List[str] = Query(..., description="List of player names to compare"),
    context: str = Query("Standard dynasty evaluation", description="User context for the comparison")
):
    """Compare multiple players using Weaviate data and OpenAI analysis."""

    if len(players) < 2:
        return {"error": "⚠️ You must include at least two players to compare."}

    @app.get("/trade")
    def evaluate_trade(
        team1: List[str] = Query(..., description="List of players on Team 1"),
        team2: List[str] = Query(..., description="List of players on Team 2"),
        context: str = Query("Standard dynasty context", description="User context for the trade")
    ):
        """Evaluate a trade between two teams of players."""

        if not team1 or not team2:
            return {"error": "⚠️ Each team must include at least one player."}

        all_players = team1 + team2
        player_data_map = {}
        missing = []

        for player in all_players:
            data = fetch_player_data(player, raw_data=True)
            if not data:
                missing.append(player)
            else:
                player_data_map[player] = data

        if missing:
            return {"error": f"⚠️ Missing data for: {', '.join(missing)}"}

        # Format player blocks by team
        def format_team(team):
            return "\n\n".join([f"**{p}:**\n{player_data_map[p]}" for p in team])

        prompt = f"""
        You are a fantasy baseball expert evaluating a dynasty trade.

        The user wants to know who wins this trade and why. Use only the provided player data and context.

        📦 **Team 1 is trading:**  
        {format_team(team1)}

        🔄 **Team 2 is trading:**  
        {format_team(team2)}

        ⚾ **Context:** {context}

        Please compare the overall value each side is giving and receiving. Consider age, position scarcity, upside, team needs, and other dynasty trade factors.
        """

        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
        )

        return {
            "team1": team1,
            "team2": team2,
            "context": context,
            "analysis": response.choices[0].message.content
        }

    
    # ✅ Fetch data for each player
    player_data_map = {}
    missing_players = []

    for player in players:
        data = fetch_player_data(player, raw_data=True)
        if not data:
            missing_players.append(player)
        else:
            player_data_map[player] = data

    if missing_players:
        return {"error": f"⚠️ Missing data for: {', '.join(missing_players)}"}

    # ✅ Format prompt for OpenAI
    player_blocks = []
    for name, data in player_data_map.items():
        player_blocks.append(f"**{name}:**\n{data}")

    prompt = f"""
    You are a fantasy baseball expert who writes in the style of Michael Halpern.

    A user is asking for a dynasty comparison between the following players: {", ".join(players)}.
    Here is their additional context: "{context}"

    Here are the stats for each player:

    {chr(10).join(player_blocks)}

    Based on the user's needs and the provided stats, explain **who is the better dynasty option and why**.
    Be analytical, consider power, positional scarcity, upside, and other dynasty factors.
    """

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )

    return {
        "players": players,
        "context": context,
        "comparison": response.choices[0].message.content
    }


# ✅ Initialize OpenAI Client
openai_client = openai.OpenAI(api_key=openai_api_key)

# ✅ Function to get OpenAI analysis
def get_openai_analysis(comparison_text):
    prompt = f"""
    You are a fantasy baseball expert analyzing player comparisons.

    You can only use the following provided statistics and rankings.
    Do NOT speculate beyond the provided data. If a comparison point is missing, acknowledge it instead of guessing.

    Here is the data you MUST use:

    {comparison_text}

    Based on this information alone, which player has the edge and why?
    """

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content

# ✅ Function to compare two players
def compare_players(player1, player1_data, player2, player2_data, user_context):
    prompt = f"""
    You are a fantasy baseball expert who writes in the style of Michael Halpern.

    A user is asking for a dynasty comparison between **{player1}** and **{player2}**.
    Here is their additional context: "{user_context}"

    Here are the stats for each player:

    **{player1}:** 
    {player1_data}

    **{player2}:** 
    {player2_data}

    Based on the user's needs and the provided stats, explain **who is the better dynasty option**.
    Be analytical, consider power, positional scarcity, upside, and other dynasty factors.
    """

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content

@app.get("/")
def root():
    return {"message": "API is running! Visit /docs for API documentation."}

# ✅ Start FastAPI for API deployment
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
