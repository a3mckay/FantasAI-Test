import os
import re
import pandas as pd
import weaviate
from dotenv import load_dotenv
from weaviate.classes.init import Auth

# ✅ Load environment variables
load_dotenv()

# ✅ Function to safely connect to Weaviate
def connect_weaviate():
    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")

    if not weaviate_url or not weaviate_api_key:
        raise EnvironmentError("❌ Missing WEAVIATE_URL or WEAVIATE_API_KEY in environment variables.")

    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_api_key),
    )

    if not client.is_ready():
        raise ConnectionError("❌ Failed to connect to Weaviate. Check your credentials.")

    print("✅ Connected to Weaviate!")
    return client

# ✅ Connect
weaviate_client = connect_weaviate()

# ✅ Parsing functions
def parse_batting_stats(stats_string):
    try:
        stats_values = stats_string.split("/")
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

def parse_pitching_stats(stats_string):
    try:
        stats_values = stats_string.split("/")
        if len(stats_values) < 4:
            raise ValueError(f"Unexpected format: {stats_string}")
        wins = int(stats_values[0])
        era = float(stats_values[1])
        whip = float(stats_values[2])
        match = re.search(r"(\d+)\s+in\s+(\d+)\s+IP", stats_values[3])
        if match:
            strikeouts = int(match.group(1))
            innings_pitched = int(match.group(2))
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

# ✅ Upload function for any writer
def upload_writer_data(writer_name="IBW"):
    print(f"🚀 Uploading data for writer: {writer_name}")
    rankings_folder = f"writers/{writer_name}/rankings"

    for filename in os.listdir(rankings_folder):
        if not filename.endswith(".xlsx"):
            continue

        file_path = os.path.join(rankings_folder, filename)
        xls = pd.ExcelFile(file_path)

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name)

            if "NAME" not in df.columns or "SUMMARY" not in df.columns:
                print(f"⚠️ Skipping {sheet_name}, required columns missing.")
                continue

            # ✅ Clean sheet name for Weaviate-safe usage
            safe_sheet_name = re.sub(r'\W+', '_', sheet_name.strip())

            for _, row in df.iterrows():
                player_name = row.get("NAME", "Unknown Player")
                summary = row.get("SUMMARY", "No summary available.")
                rankings = {}

                valid_columns = {
                    "MAR RANK": "MAR_RANK",
                    "FEB RANK": "FEB_RANK",
                    "OBP RANK": "OBP_RANK",
                    "Δ": "Delta",
                    "OF RANK": "OF_RANK",
                    "SP RANK": "SP_RANK",
                    "RP RANK": "RP_RANK",
                    "FYPD RANK": "FYPD_RANK"
                }

                for col, new_col in valid_columns.items():
                    if col in df.columns:
                        rankings[safe_sheet_name] = rankings.get(safe_sheet_name, {})
                        value = row.get(col, "NR")
                        if isinstance(value, str) and value.strip().upper() == "NR":
                            rankings[safe_sheet_name][new_col] = None
                        else:
                            try:
                                rankings[safe_sheet_name][new_col] = int(value)
                            except ValueError:
                                print(f"⚠️ Skipping invalid ranking for {player_name}: {col} = {value}")

                batting_stats = {}
                if "2025 BATTING" in df.columns:
                    batting_stats = parse_batting_stats(row.get("2025 BATTING", ""))
                elif all(stat in df.columns for stat in ["R", "HR", "RBI", "AVG", "OBP", "SLG", "SB"]):
                    batting_stats = {
                        "R": row.get("R", 0), "HR": row.get("HR", 0), "RBI": row.get("RBI", 0),
                        "AVG": row.get("AVG", 0.0), "OBP": row.get("OBP", 0.0), "SLG": row.get("SLG", 0.0), "SB": row.get("SB", 0)
                    }

                pitching_stats = {}
                if "2025 PITCHING" in df.columns:
                    pitching_stats = parse_pitching_stats(row.get("2025 PITCHING", ""))
                elif all(stat in df.columns for stat in ["W", "ERA", "WHIP", "SO", "IP"]):
                    pitching_stats = {
                        "Wins": row.get("W", 0), "ERA": row.get("ERA", 0.0),
                        "WHIP": row.get("WHIP", 0.0), "K": row.get("SO", 0), "IP": row.get("IP", 0)
                    }
                # ✅ Convert NaN to None (JSON-safe)
                if pd.isna(summary):
                    summary = "No summary available."
                    
                player_data = {
                    "player_name": player_name,
                    "rankings": rankings,
                    "batting_stats": batting_stats,
                    "pitching_stats": pitching_stats,
                    "summary": summary,
                    "source": f"{writer_name} - {safe_sheet_name}"
                }

                print(f"📝 Preparing to upload: {player_data}")
                try:
                    weaviate_client.collections.get("FantasyPlayers").data.insert(player_data)
                    print(f"✅ Uploaded {player_name} from {sheet_name}")
                except Exception as e:
                    print(f"⚠️ Error inserting data into Weaviate: {e}")

    print(f"🎉 Upload for {writer_name} complete!")

# ✅ Upload Razzball now!
upload_writer_data("Razzball")

# ✅ Sample check + close
try:
    query_result = weaviate_client.collections.get("FantasyPlayers").query.fetch_objects(limit=5)
    print("✅ Sample Players in Weaviate:", query_result.objects)
except Exception as e:
    print(f"⚠️ Error querying Weaviate: {e}")

try:
    weaviate_client.close()
    print("✅ Weaviate connection closed.")
except Exception as e:
    print(f"⚠️ Error closing Weaviate: {e}")
