import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth
import os

# ✅ Load environment variables
load_dotenv()
weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_api_key = os.getenv("WEAVIATE_API_KEY")

# ✅ Connect to Weaviate
weaviate_client = weaviate.connect_to_weaviate_cloud(
    cluster_url=weaviate_url,
    auth_credentials=Auth.api_key(weaviate_api_key),
)

# ✅ List all collections
collections = weaviate_client.collections.list_all()
print("🔍 Existing Collections in Weaviate:", collections)

# ✅ Check if "FantasyPlayers" collection exists
if "FantasyPlayers" in collections:
    print("✅ 'FantasyPlayers' collection **exists** in Weaviate!")
else:
    print("⚠️ 'FantasyPlayers' collection **NOT FOUND** in Weaviate!")

# ✅ Close connection
weaviate_client.close()
