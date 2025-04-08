import os
import nltk
from collections import Counter
from nltk.tokenize import sent_tokenize, word_tokenize

# ✅ Tell NLTK where to find your punkt tokenizer
nltk.data.path.append("nltk_data")

def analyze_writing_style(folder_path):
    all_sentences = []
    all_words = []

    for file_name in os.listdir(folder_path):
        if file_name.endswith(".txt"):
            full_path = os.path.join(folder_path, file_name)
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()

                if not text:
                    print(f"⚠️ Skipping empty file: {file_name}")
                    continue

                try:
                    sentences = sent_tokenize(text, language="english")
                    words = word_tokenize(text)
                except Exception as e:
                    print(f"⚠️ Error processing {file_name}: {e}")
                    continue

                all_sentences.extend(sentences)
                all_words.extend(words)

    most_common_words = Counter(all_words).most_common(50)

    avg_sentence_length = (
        sum(len(s.split()) for s in all_sentences) / len(all_sentences)
        if all_sentences else 0
    )

    print("\n🔹 **Writing Style Analysis:**")
    print(f"🔸 Average sentence length: {avg_sentence_length:.2f} words")
    print("🔸 Most common words:", [word[0] for word in most_common_words[:10]])

    return most_common_words, avg_sentence_length

# ✅ Run the analysis on both writers
print("\n🎤 IBW Style:")
analyze_writing_style("writers/IBW/training")

print("\n🔥 Razzball Style:")
analyze_writing_style("writers/Razzball/training")
