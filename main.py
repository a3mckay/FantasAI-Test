import os
import weaviate
import openai
import uvicorn
from dotenv import load_dotenv
from weaviate.classes.init import Auth
from fastapi import FastAPI
from weaviate.collections.classes.filters import Filter

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

def fetch_player_data(player_name, raw_data=False):
    """
    Fetches a player's data from Weaviate.
    - If `raw_data` is True, returns the full dictionary of the player's data.
    - Otherwise, formats and returns a readable summary.
    """
    print(f"🔍 Searching for player: {player_name}...")

    from weaviate.collections.classes.filters import Filter

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
        return (
            f"\n🔹 **Player Name:** {player_name}\n"
            f"📌 **Summary:** {summary}\n"
            f"📊 **Rankings:** {rankings}\n"
            f"⚾ **Batting Stats:** {batting_stats if batting_stats else 'N/A'}\n"
            f"⚾ **Pitching Stats:** {pitching_stats if pitching_stats else 'N/A'}"
        )

    except Exception as e:
        return f"⚠️ Error retrieving player data: {e}"


# ✅ Chatbot System Prompt
SYSTEM_PROMPT = """
You are a fantasy baseball expert who writes in the style of Michael Halpern. Your writing style includes:
- **Sentence length:** Long-form analysis, averaging 25+ words per sentence.
- **Frequent statistical analysis:** Uses advanced baseball metrics such as K%, BB%, OPS, OBP, ERA, WHIP, and wOBA to provide insights.
- **Tone:** Analytical, data-driven, engaging, and sometimes funny. Your responses should mimic how Michael Halpern presents fantasy baseball analysis.
- **Player evaluations:** Compares players based on advanced metrics and real-world performance trends.
"""

# ✅ Initialize OpenAI Client
openai_client = openai.OpenAI(api_key=openai_api_key)

# ✅ Create FastAPI app
app = FastAPI()

# ✅ Convert Chatbot to Work Over Web API
@app.get("/player/{player_name}")
def get_player_info(player_name: str):
    """Fetches player information from Weaviate."""
    print(f"🔍 Searching for player: {player_name}...")
    # ✅ API Endpoint for OpenAI Analysis of a Player
    @app.get("/analysis/{player_name}")
    def analyze_player(player_name: str):
        """Fetches player data and sends it to OpenAI for deeper analysis."""
        player_data = get_player_info(player_name)  # Fetch player data

        if "error" in player_data:
            return player_data  # Return error if player not found

        # ✅ Send data to OpenAI
        openai_response = get_openai_analysis(player_data)
        return {"player_name": player_name, "openai_analysis": openai_response}

    try:
        # ✅ Search Weaviate for the player
        query_result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(
            filters=Filter.by_property("player_name").equal(player_name),
            limit=1
        )

        if not query_result.objects:
            return {"error": f"No information found for {player_name}."}

        # ✅ Extract player data
        obj = query_result.objects[0]
        summary = obj.properties.get("summary", "No summary available.")
        rankings = obj.properties.get("rankings", {})
        batting_stats = obj.properties.get("batting_stats", {})
        pitching_stats = obj.properties.get("pitching_stats", {})

        return {
            "player_name": player_name,
            "summary": summary,
            "rankings": rankings,
            "batting_stats": batting_stats,
            "pitching_stats": pitching_stats
        }

    except Exception as e:
        return {"error": f"⚠️ Error retrieving player data: {e}"}


# ✅ Function to get OpenAI analysis ONLY using retrieved data
def get_openai_analysis(comparison_text):
    prompt = f"""
    You are a fantasy baseball expert analyzing player comparisons. You can only use the following provided statistics and rankings.
    Do NOT speculate beyond the provided data. If a comparison point is missing, acknowledge it instead of guessing.

    Here is the data you MUST use (no external knowledge allowed):

    {comparison_text}

    Based on this information alone, which player has the edge and why?
    """

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},  # ✅ Include SYSTEM_PROMPT
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# ✅ Function to get chatbot response
from weaviate.collections.classes.filters import Filter
import re
from weaviate.collections.classes.filters import Filter

def chatbot_response(user_input):
    """
    Processes a user request, identifies players mentioned, retrieves relevant data from Weaviate,
    and provides a structured response based on the context (e.g., player comparison, team needs).
    """

    print(f"🔍 Processing request: {user_input}...")

    # ✅ Extract player names using regex (assumes proper name capitalization)
    potential_players = re.findall(r'\b[A-Z][a-z]+\s[A-Z][a-z]+\b', user_input)

    if not potential_players:
        return "⚠️ I couldn't identify any player names in your request. Try again with specific player names."

    # ✅ Compare two players using OpenAI
    def compare_players(player1, player1_data, player2, player2_data, user_context):
        """
        Compares two players using Weaviate stats and considers user context (e.g., team needs).
        """
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
                {"role": "system", "content": SYSTEM_PROMPT},  # ✅ Ensures it follows Michael Halpern's style
                {"role": "user", "content": prompt}
            ]
        )

        return response.choices[0].message.content


    # ✅ Now, the function can be used in the main player lookup logic
    # ✅ If one player, treat it as a single-player lookup
    if len(potential_players) == 1:
        player_name = potential_players[0]
        return fetch_player_data(player_name)

    # ✅ If two players, handle a comparison
    elif len(potential_players) == 2:
        player1, player2 = potential_players

    
    # ✅ If one player, treat it as a single-player lookup
    if len(potential_players) == 1:
        player_name = potential_players[0]
        return fetch_player_data(player_name)

    # ✅ If two players, handle a comparison
    elif len(potential_players) == 2:
        player1, player2 = potential_players

        # ✅ Retrieve both players' data from Weaviate
        player1_data = fetch_player_data(player1, raw_data=True)
        player2_data = fetch_player_data(player2, raw_data=True)

        if not player1_data or not player2_data:
            return f"⚠️ I'm sorry, I don't have enough information on both {player1} and {player2} to compare them."

        # ✅ Send data + user context to OpenAI
        return compare_players(player1, player1_data, player2, player2_data, user_input)

    else:
        return "⚠️ I can only compare two players at a time. Try again with just two names."

try:
    # Your chatbot execution logic here
    while True:
        user_input = input("Ask about a fantasy player (or type 'exit' to quit): ").strip()

        if user_input.lower() == "exit":
            print("👋 Exiting chatbot. Have a great day!")
            break

        if not user_input:
            print("⚠️ Please enter a valid player name.")
            continue

        response = chatbot_response(user_input)
        print("\n💬 Chatbot Response:", response)

except KeyboardInterrupt:
    print("\n🛑 Chatbot interrupted by user.")

finally:
    # ✅ Ensure Weaviate client is closed properly
    try:
        weaviate_client.close()
        print("✅ Weaviate connection closed. Exiting cleanly.")
    except Exception as e:
        print(f"⚠️ Error closing Weaviate: {e}")
