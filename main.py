import os
import weaviate
import openai
import uvicorn
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv
from datetime import datetime
from weaviate.classes.init import Auth
from weaviate.collections.classes.filters import Filter

from fastapi import FastAPI, Query, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi import Body
from typing import List, Optional
from pydantic import BaseModel
from pathlib import Path
import pandas as pd
import re
from models import WriterQueryLog
from sqlalchemy import desc
from collections import defaultdict, Counter

# SQLModel + DB
from sqlmodel import SQLModel, create_engine, Session, select
from models import WriterProfile
from models import WriterUpload

print("🔁 This should absolutely appear if the code is live")

raise RuntimeError("☠️ THIS SHOULD CRASH IF DEPLOYED ☠️")


# Database setup
DB_PATH = "writer_data.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


# === Load environment variables ===
load_dotenv()

# === S3 Upload Helper ===
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
)

def generate_signed_url(filename: str, expiration: int = 3600) -> str:
    """
    Generates a temporary, signed URL for accessing a private S3 file.
    """
    bucket_name = os.getenv("S3_BUCKET_NAME")
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": filename},
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating signed URL: {str(e)}")


def upload_file_to_s3(file, filename: str) -> str:
    """
    Uploads a file to S3 and returns the public URL.
    """
    bucket_name = os.getenv("S3_BUCKET_NAME")
    try:
        s3_client.upload_fileobj(
            file.file,         # FastAPI UploadFile
            bucket_name,
            filename,
            ExtraArgs={"ACL": "private"}  # use "public-read" if needed
        )
        return f"https://{bucket_name}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{filename}"
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="Missing AWS credentials")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


weaviate_url = os.getenv("WEAVIATE_URL")
weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

if not weaviate_url or not weaviate_api_key or not openai_api_key:
    raise ValueError("❌ Missing environment variables.")

def log_writer_upload(writer_id: str, filename: str, file_type: str, s3_path: str):
    upload = WriterUpload(
        writer_id=writer_id,
        filename=filename,
        file_type=file_type,
        s3_path=s3_path,
    )
    with Session(engine) as session:
        session.add(upload)
        session.commit()

def log_query(
    writer_id: str,
    feature: str,
    context: Optional[str] = None,
    summary_player: Optional[str] = None,
    players: Optional[list[str]] = None,
    teamA: Optional[list[str]] = None,
    teamB: Optional[list[str]] = None,
):
    players = players or []
    teamA = teamA or []
    teamB = teamB or []

    query = WriterQueryLog(
        writer_id=writer_id,
        feature=feature,
        context=context,
        summary_player=summary_player,
        player_1=players[0] if len(players) > 0 else None,
        player_2=players[1] if len(players) > 1 else None,
        player_3=players[2] if len(players) > 2 else None,
        player_4=players[3] if len(players) > 3 else None,
        player_5=players[4] if len(players) > 4 else None,
        player_6=players[5] if len(players) > 5 else None,
        player_7=players[6] if len(players) > 6 else None,
        player_8=players[7] if len(players) > 7 else None,
        player_9=players[8] if len(players) > 8 else None,
        player_10=players[9] if len(players) > 9 else None,
        teamA_1=teamA[0] if len(teamA) > 0 else None,
        teamA_2=teamA[1] if len(teamA) > 1 else None,
        teamA_3=teamA[2] if len(teamA) > 2 else None,
        teamA_4=teamA[3] if len(teamA) > 3 else None,
        teamA_5=teamA[4] if len(teamA) > 4 else None,
        teamB_1=teamB[0] if len(teamB) > 0 else None,
        teamB_2=teamB[1] if len(teamB) > 1 else None,
        teamB_3=teamB[2] if len(teamB) > 2 else None,
        teamB_4=teamB[3] if len(teamB) > 3 else None,
        teamB_5=teamB[4] if len(teamB) > 4 else None,
    )

    with Session(engine) as session:
        session.add(query)
        session.commit()


# === Connect to Weaviate ===
print("🌐 Attempting to connect to Weaviate...")

try:
    weaviate_client = weaviate.connect_to_weaviate_cloud(
        cluster_url=weaviate_url,
        auth_credentials=Auth.api_key(weaviate_api_key),
        skip_init_checks=True
    )
    print("✅ Connected to Weaviate client object.")
    if weaviate_client.is_ready():
        print("✅ Weaviate is ready to receive queries.")
    else:
        print("❌ Weaviate client initialized but not ready.")
except Exception as e:
    print(f"🔥 Exception while connecting to Weaviate: {e}")
    raise


# === FastAPI Setup ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    print("🚀 Creating database tables (if needed)...")
    try:
        SQLModel.metadata.create_all(engine)
        print("✅ Database tables ensured.")
    except Exception as e:
        print(f"🔥 Failed to create DB tables: {e}")
        raise


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

@app.get("/writer-profile/{writer_id}")
def get_writer_profile(writer_id: str):
    with Session(engine) as session:
        profile = session.get(WriterProfile, writer_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Writer not found")
        return profile

@app.get("/writer-uploads/{writer_id}")
def get_writer_uploads(writer_id: str):
    with Session(engine) as session:
        statement = select(WriterUpload).where(WriterUpload.writer_id == writer_id)
        results = session.exec(statement).all()
        return results

@app.get("/writer-analytics/summary")
def get_writer_analytics_summary(writer_id: str):
    try:
        df = pd.read_excel("user_queries.xlsx")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read Excel file: {str(e)}")

    # Filter rows by writer (if filtering by writer_id later — for now we assume shared log)
    summary_counts = df["feature"].value_counts().to_dict()

    # Count total players mentioned
    player_cols = ["summary_player"] + [f"player_{i}" for i in range(1, 11)]
    mentioned_players = set()

    for col in player_cols:
        if col in df.columns:
            mentioned_players.update(df[col].dropna().unique())

    total_players_mentioned = len(mentioned_players)

    # Get upload counts from DB
    with Session(engine) as session:
        statement = select(WriterUpload).where(WriterUpload.writer_id == writer_id)
        uploads = session.exec(statement).all()
        uploads_by_type = {}
        for upload in uploads:
            uploads_by_type[upload.file_type] = uploads_by_type.get(upload.file_type, 0) + 1

    return {
        "query_counts_by_feature": summary_counts,
        "total_unique_players_mentioned": total_players_mentioned,
        "upload_counts_by_type": uploads_by_type
    }

@app.get("/writer-analytics/queries")
def get_recent_queries(
    writer_id: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
    start_date: Optional[str] = Query(None, description="ISO 8601 date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO 8601 date (YYYY-MM-DD)")
):
    with Session(engine) as session:
        query = select(WriterQueryLog)

        if writer_id:
            query = query.where(WriterQueryLog.writer_id == writer_id)

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.strip())
                query = query.where(WriterQueryLog.timestamp >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.strip())
                query = query.where(WriterQueryLog.timestamp <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

        query = query.order_by(desc(WriterQueryLog.timestamp)).offset(offset).limit(limit)
        results = session.exec(query).all()

    return {
        "queries": [r.dict() for r in results],
        "limit": limit,
        "offset": offset,
        "total_returned": len(results)
    }

@app.get("/writer-analytics/queries/download")
def download_queries_csv(
    writer_id: Optional[str] = None,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    with Session(engine) as session:
        query = select(WriterQueryLog)

        if writer_id:
            query = query.where(WriterQueryLog.writer_id == writer_id)

        if start_date:
            try:
                query = query.where(WriterQueryLog.timestamp >= datetime.fromisoformat(start_date.strip()))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                query = query.where(WriterQueryLog.timestamp <= datetime.fromisoformat(end_date.strip()))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

        logs = session.exec(query).all()

    # Convert to DataFrame
    df = pd.DataFrame([log.dict() for log in logs])

    # Save to a temp CSV file
    csv_path = "writer_queries_export.csv"
    df.to_csv(csv_path, index=False)

    return FileResponse(csv_path, media_type="text/csv", filename="writer_queries_export.csv")

@app.get("/writer-analytics/top-players")
def get_top_players(
    writer_id: Optional[str] = None,
    top_n: int = 10,
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format")
):
    with Session(engine) as session:
        query = select(WriterQueryLog)

        if writer_id:
            query = query.where(WriterQueryLog.writer_id == writer_id)

        if start_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.where(WriterQueryLog.timestamp >= start)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end = datetime.strptime(end_date, "%Y-%m-%d")
                query = query.where(WriterQueryLog.timestamp <= end)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD.")

        logs = session.exec(query).all()

    # Count players
    feature_counts = defaultdict(Counter)
    all_players = Counter()

    for log in logs:
        feature = log.feature
        player_fields = [
            log.summary_player,
            log.player_1, log.player_2, log.player_3, log.player_4, log.player_5,
            log.player_6, log.player_7, log.player_8, log.player_9, log.player_10
        ]
        for player in player_fields:
            if player:
                feature_counts[feature][player] += 1
                all_players[player] += 1

    return {
        "top_overall": all_players.most_common(top_n),
        "top_by_feature": {
            feature: counts.most_common(top_n)
            for feature, counts in feature_counts.items()
        }
    }

@app.post("/upload-avatar")
async def upload_avatar(file: UploadFile = File(...), writer: str = "IBW"):
    filename = f"{writer}/avatar/{datetime.now().strftime('%Y%m%d-%H%M%S')}-{file.filename}"
    upload_file_to_s3(file, filename)
    signed_url = generate_signed_url(filename)
    log_writer_upload(writer, filename, "avatar", filename)
    return {"message": "Avatar uploaded successfully", "url": signed_url}



@app.post("/upload-ranking")
async def upload_ranking(file: UploadFile = File(...), writer: str = "IBW"):
    filename = f"{writer}/ranking/{datetime.now().strftime('%Y%m%d-%H%M%S')}-{file.filename}"
    upload_file_to_s3(file, filename)
    signed_url = generate_signed_url(filename)
    log_writer_upload(writer, filename, "ranking", filename)
    return {"message": "Ranking uploaded successfully", "url": signed_url}



@app.post("/upload-article")
async def upload_article(file: UploadFile = File(...), writer: str = "IBW"):
    filename = f"{writer}/article/{datetime.now().strftime('%Y%m%d-%H%M%S')}-{file.filename}"
    upload_file_to_s3(file, filename)
    signed_url = generate_signed_url(filename)
    log_writer_upload(writer, filename, "article", filename)
    return {"message": "Article uploaded successfully", "url": signed_url}


@app.post("/writer-profile")
def upsert_writer_profile(profile: WriterProfile = Body(...)):
    profile.last_updated = datetime.now().isoformat()
    with Session(engine) as session:
        existing = session.get(WriterProfile, profile.writer_id)
        if existing:
            for field, value in profile.dict().items():
                setattr(existing, field, value)
        else:
            session.add(profile)
        session.commit()
    return {"message": "Profile saved", "writer_id": profile.dict().get("writer_id")}

@app.post("/dev/log-test-query")
def log_test_query():
    log_query(
        writer_id="IBW",
        feature="compare",
        context="Testing log insert from /log-test-query",
        summary_player="Corbin Carroll",
        players=["Corbin Carroll", "Jackson Chourio"]
    )
    return {"message": "Test query logged"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
