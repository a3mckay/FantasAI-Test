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
print("\n🔍 Existing Collections in Weaviate:")
for collection in collections:
    print(f"   - {collection}")

# ✅ Check if "FantasyPlayers" collection exists
if "FantasyPlayers" in collections:
    print("\n✅ 'FantasyPlayers' collection **exists** in Weaviate!")
else:
    print("\n⚠️ 'FantasyPlayers' collection **NOT FOUND** in Weaviate!")

# ✅ Close connection
weaviate_client.close()
print("\n✅ Weaviate connection closed.")
