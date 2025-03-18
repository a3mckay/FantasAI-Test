import os
import nltk
from collections import Counter
from nltk.tokenize import sent_tokenize, word_tokenize

# Download NLTK tokenizer
nltk.download('punkt')

def analyze_writing_style(folder_path):
    all_sentences = []
    all_words = []

    for file_name in os.listdir(folder_path):
        if file_name.endswith(".txt"):
            with open(os.path.join(folder_path, file_name), "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
                sentences = sent_tokenize(text)
                words = word_tokenize(text)

                all_sentences.extend(sentences)
                all_words.extend(words)

    # Find most common words (excluding stopwords)
    most_common_words = Counter(all_words).most_common(50)

    # Find average sentence length
    avg_sentence_length = sum(len(s.split()) for s in all_sentences) / len(all_sentences)

    print("\n🔹 **Writing Style Analysis:**")
    print(f"🔸 Average sentence length: {avg_sentence_length:.2f} words")
    print("🔸 Most common words:", [word[0] for word in most_common_words[:10]])

    return most_common_words, avg_sentence_length

# Run the analysis on the 'articles' folder
analyze_writing_style("articles")
