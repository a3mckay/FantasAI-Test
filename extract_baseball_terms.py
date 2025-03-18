import os
import re
from collections import Counter

# List of common baseball stats to check for
BASEBALL_STATS = [
    "AVG", "OPS", "ISO", "wOBA", "xwOBA", "SLG", "xSLG", "K%", "BB%", "Barrel%", 
    "MPH", "whiff%", "ERA", "xERA", "IP", "Hard Hit%", "Exit Velocity", "EV", "Max EV", 
    "Launch Angle", "BABIP", "Steamer", "WAR", "FIP", "WHIP", "wRC+", "HR", "RBI", "SB", 
    "Stolen Bases", "Steals", "OBP", "Sprint Speed", "Bat Speed", "ft/sec", "Strikeout Rate", 
    "Launch", "Bags", "Homers", "Pull%", "Swing Length", "Swing Speed", "FB/LD EV", 
    "Chase Rate", "Chase%", "FB%", "GB%", "K/BB", "Run Value"
]

def extract_baseball_terms(folder_path):
    term_counts = Counter()

    for file_name in os.listdir(folder_path):
        if file_name.endswith(".txt"):
            with open(os.path.join(folder_path, file_name), "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().upper()  # Convert to uppercase for case-insensitive matching

                for stat in BASEBALL_STATS:
                    # Improved regex to match full words & avoid substrings
                    count = len(re.findall(rf"(?<![A-Za-z0-9]){re.escape(stat)}(?![A-Za-z0-9])", text))
  

                    if count > 0:
                        term_counts[stat] += count

    print("\n🔹 **Common Baseball Terms Used:**")
    for term, count in term_counts.most_common(10):
        print(f"🔸 {term}: {count} times")

# Run extraction
extract_baseball_terms("articles")
