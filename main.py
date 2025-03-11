import weaviate
import weaviate.auth
import json
import openai
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fetch API Keys & URLs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

# Ensure API Keys are set correctly
if not OPENAI_API_KEY:
    raise ValueError("❌ OpenAI API key not found. Make sure it is stored in the .env file.")
if not WEAVIATE_URL:
    raise ValueError("❌ Weaviate URL not found. Make sure it is stored in the .env file.")
if not WEAVIATE_API_KEY:
    raise ValueError("❌ Weaviate API key not found. Make sure it is stored in the .env file.")

# Initialize OpenAI Client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# Load environment variables
load_dotenv()

WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")

weaviate_client = weaviate.WeaviateClient(
    http_host=WEAVIATE_URL,  
    auth_client=weaviate.auth.AuthApiKey(WEAVIATE_API_KEY)
)



# ✅ Test Weaviate connection
if weaviate_client.is_ready():
    print("✅ Successfully connected to Weaviate!")
else:
    raise ConnectionError("❌ Failed to connect to Weaviate. Check your URL and API key.")

# Function to get chatbot response
def chatbot_response(prompt):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a fantasy baseball expert providing insights on players."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content

# Test the chatbot
while True:
    user_input = input("Ask about a fantasy player (or type 'exit' to quit): ")
    if user_input.lower() == "exit":
        break
    response = chatbot_response(user_input)
    print("\nChatbot Response:", response)
