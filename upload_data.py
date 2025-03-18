import os
import pandas as pd
import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth

# ✅ Load environment variables
load_dotenv()

# ✅ Fetch API Keys & Weaviate URL
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

# ✅ Parsing functions for batting & pitching stats
def parse_batting_stats(stats_string):
    """Convert batting stats from string format into a structured dictionary."""
    try:
        stats_values = stats_string.split("/")  # Split by "/"
        return {
            "R": int(stats_values[0]),
            "HR": int(stats_values[1]),
            "RBI": int(stats_values[2]),
            "AVG": float(stats_values[3]),
            "OBP": float(stats_values[4]),
            "SLG": float(stats_values[5]),
            "SB": int(stats_values[6])
        }
    except Exception as e:
        print(f"⚠️ Error parsing batting stats: {stats_string} - {e}")
        return {}

import re  # Import regex module

def parse_pitching_stats(stats_string):
    """Convert pitching stats from string format into a structured dictionary."""
    try:
        stats_values = stats_string.split("/")  # Split by "/"

        if len(stats_values) < 4:  # Ensure we have at least 4 elements before processing
            raise ValueError(f"Unexpected format: {stats_string}")

        # Extract Wins, ERA, WHIP, and Strikeouts safely
        wins = int(stats_values[0])
        era = float(stats_values[1])
        whip = float(stats_values[2])

        # Extract Strikeouts and Innings Pitched using regex
        match = re.search(r"(\d+)\s+in\s+(\d+)\s+IP", stats_values[3])
        if match:
            strikeouts = int(match.group(1))  # Extract "142" from "142 in 120 IP"
            innings_pitched = int(match.group(2))  # Extract "120" from "142 in 120 IP"
        else:
            raise ValueError(f"Could not parse strikeouts and IP: {stats_values[3]}")

        return {
            "Wins": wins,
            "ERA": era,
            "WHIP": whip,
            "K": strikeouts,
            "IP": innings_pitched
        }
    except Exception as e:
        print(f"⚠️ Error parsing pitching stats: {stats_string} - {e}")
        return {}

# ✅ Read the Excel file (update file path)
file_path = "march_update_2025_ibw_dynasty_top_1000.xlsx"  # Update with the correct filename
xls = pd.ExcelFile(file_path)

# ✅ Iterate over all sheets
for sheet_name in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name)

    # ✅ Ensure required columns exist
    if "NAME" not in df.columns or "SUMMARY" not in df.columns:
        print(f"⚠️ Skipping {sheet_name}, required columns missing.")
        continue

    for _, row in df.iterrows():
        player_name = row.get("NAME", "Unknown Player")
        summary = row.get("SUMMARY", "No summary available.")

        # ✅ Extract rankings
        rankings = {}
        # ✅ Fix column names by replacing spaces with underscores
        valid_columns = {
            "MAR RANK": "MAR_RANK",
            "FEB RANK": "FEB_RANK",
            "OBP RANK": "OBP_RANK",
            "Δ": "Delta",  # Change "Δ" to "Delta" since symbols aren't allowed
            "OF RANK": "OF_RANK",
            "SP RANK": "SP_RANK",
            "RP RANK": "RP_RANK",
            "FYPD RANK": "FYPD_RANK"
        }

        for col, new_col in valid_columns.items():
            if col in df.columns:
                rankings[sheet_name] = rankings.get(sheet_name, {})

                # ✅ Handle "NR" values safely
                value = row.get(col, "NR")
                if isinstance(value, str) and value.strip().upper() == "NR":
                    rankings[sheet_name][new_col] = None  # Use None instead of an invalid integer
                else:
                    try:
                        rankings[sheet_name][new_col] = int(value)
                    except ValueError:
                        print(f"⚠️ Skipping invalid ranking for {player_name}: {col} = {value}")

        # ✅ Extract batting stats
        batting_stats = {}
        if "2025 BATTING" in df.columns:
            batting_stats = parse_batting_stats(row.get("2025 BATTING", ""))
        elif all(stat in df.columns for stat in ["R", "HR", "RBI", "AVG", "OBP", "SLG", "SB"]):
            batting_stats = {
                "R": row.get("R", 0), "HR": row.get("HR", 0), "RBI": row.get("RBI", 0),
                "AVG": row.get("AVG", 0.0), "OBP": row.get("OBP", 0.0), "SLG": row.get("SLG", 0.0), "SB": row.get("SB", 0)
            }

        # ✅ Extract pitching stats
        pitching_stats = {}
        if "2025 PITCHING" in df.columns:
            pitching_stats = parse_pitching_stats(row.get("2025 PITCHING", ""))
        elif all(stat in df.columns for stat in ["W", "ERA", "WHIP", "SO", "IP"]):
            pitching_stats = {
                "Wins": row.get("W", 0), 
                "ERA": row.get("ERA", 0.0), 
                "WHIP": row.get("WHIP", 0.0),
                "K": row.get("SO", 0), 
                "IP": row.get("IP", 0)
            }

        # ✅ Prepare player object for Weaviate
        player_data = {
            "player_name": player_name,
            "rankings": rankings,
            "batting_stats": batting_stats,
            "pitching_stats": pitching_stats,
            "summary": summary,
            "source": sheet_name  # Store sheet name as source
        }

        # ✅ Debugging: Print player data before inserting
        print(f"📝 Preparing to upload: {player_data}")

        # ✅ Upload to Weaviate
        try:
            weaviate_client.collections.get("FantasyPlayers").data.insert(player_data)
            print(f"✅ Uploaded {player_name} from {sheet_name}")
        except Exception as e:
            print(f"⚠️ Error inserting data into Weaviate: {e}")

# ✅ Upload complete
print("🎉 All data uploaded successfully!")

# ✅ Confirm Data Exists in Weaviate
print("🔍 Verifying stored player names in Weaviate...")

try:
    query_result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(limit=5)
    print("✅ Sample Players in Weaviate:", query_result.objects)
except Exception as e:
    print(f"⚠️ Error querying Weaviate: {e}")

# ✅ Close the Weaviate connection properly
try:
    weaviate_client.close()
    print("✅ Weaviate connection closed.")
except Exception as e:
    print(f"⚠️ Error closing Weaviate: {e}")
