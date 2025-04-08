import os
import nltk
from nltk.tokenize.punkt import PunktTrainer, PunktSentenceTokenizer
import pickle

# Set up the local save path
target_dir = "nltk_data/tokenizers/punkt_tab/english"
os.makedirs(target_dir, exist_ok=True)

# Sample training text (just enough to generate the helper files)
sample_text = """
This is a sentence. Here's another one! And now a question? Followed by an abbreviation e.g. Dr. Smith.
"""

# Train the tokenizer to generate helper data
trainer = PunktTrainer()
trainer.INCLUDE_ALL_COLLOCS = True
trainer.train(sample_text)

# Save the helper components that NLTK looks for
params = trainer.get_params()
tokenizer = PunktSentenceTokenizer(params)

# These are the files NLTK tries to load at runtime
with open(os.path.join(target_dir, "abbrev_types.pickle"), "wb") as f:
    pickle.dump(tokenizer._params.abbrev_types, f)

with open(os.path.join(target_dir, "collocations.pickle"), "wb") as f:
    pickle.dump(tokenizer._params.collocations, f)

with open(os.path.join(target_dir, "sentences.pickle"), "wb") as f:
    pickle.dump(["This is a sentence.", "Here's another one!"], f)

print("✅ Generated missing punkt_tab/english helper files.")
# Create empty .tab files that NLTK tries to load
open(os.path.join(target_dir, "abbrev_types.tab"), "w").close()
open(os.path.join(target_dir, "collocations.tab"), "w").close()
open(os.path.join(target_dir, "sentences.tab"), "w").close()
open(os.path.join(target_dir, "sent_starters.txt"), "w").close()
open(os.path.join(target_dir, "abbrev_types.txt"), "w").close()
open(os.path.join(target_dir, "ortho_context.tab"), "w").close()
