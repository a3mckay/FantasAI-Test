import os

# Path to your articles folder
folder_path = "articles"

# List all files in the folder
files = os.listdir(folder_path)

print(f"✅ Found {len(files)} articles in '{folder_path}/'")
print("📄 Sample files:", files[:5])  # Print first 5 file names
