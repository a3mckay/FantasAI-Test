import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
import os

# ✅ Load environment variables
load_dotenv()
weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_api_key = os.getenv("WEAVIATE_API_KEY")

# ✅ Connect to Weaviate Cloud
weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
    auth_credentials=Auth.api_key(weaviate_api_key),
)

# ✅ Verify connection
if not weaviate_client.is_ready():
    raise ConnectionError("❌ Failed to connect to Weaviate. Check your credentials.")

# ✅ Query Weaviate for stored players
print("\n🔍 Fetching sample players from Weaviate...")
try:
    # Get a sample of 5 players
    query_result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(limit=5)

    if not query_result.objects:
        print("⚠️ No player data found in Weaviate.")
    else:
        print("✅ Sample Players Found in Weaviate:\n")
        for obj in query_result.objects:
            player_name = obj.properties.get("player_name", "Unknown")
            summary = obj.properties.get("summary", "No summary available.")
            rankings = obj.properties.get("rankings", {})
            batting_stats = obj.properties.get("batting_stats", {})
            pitching_stats = obj.properties.get("pitching_stats", {})

            # ✅ Print player details
            print(f"🔹 **{player_name}**")
            print(f"📌 **Summary:** {summary}")
            print(f"📊 **Rankings:** {rankings}")
            print(f"⚾ **Batting Stats:** {batting_stats}")
            print(f"⚾ **Pitching Stats:** {pitching_stats}")
            print("-" * 60)  # Separator line

except Exception as e:
    print(f"⚠️ Error querying Weaviate: {e}")

# ✅ Close Weaviate connection
weaviate_client.close()
print("\n✅ Weaviate connection closed.")