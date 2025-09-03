#!/usr/bin/env python
"""
scripts/augment_dataset.py

Reads data/clause_pairs.json and writes out:
  - data/clause_pairs_augmented.json   (original + new examples)
  - data/clause_pairs_augmented.csv
"""

import json
import random
from pathlib import Path

import pandas as pd
from transformers import (
    MarianMTModel, MarianTokenizer,
    pipeline
)

# 1) Back-translation models
en_fr_tokenizer = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-fr")
en_fr_model     = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-en-fr")
fr_en_tokenizer = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-fr-en")
fr_en_model     = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-fr-en")

def back_translate(text: str) -> str:
    # English → French
    tokens = en_fr_tokenizer(text, return_tensors="pt", truncation=True)
    fr_ids = en_fr_model.generate(**tokens, max_length=256)
    fr_text = en_fr_tokenizer.decode(fr_ids[0], skip_special_tokens=True)
    # French → English
    tokens = fr_en_tokenizer(fr_text, return_tensors="pt", truncation=True)
    en_ids = fr_en_model.generate(**tokens, max_length=256)
    return fr_en_tokenizer.decode(en_ids[0], skip_special_tokens=True)

# 2) Synonym-replacement map (sample a variant)
SYNONYMS = {
    "indemnify":   ["reimburse", "compensate", "hold harmless"],
    "seller":      ["vendor", "provider"],
    "buyer":       ["purchaser", "client"],
    "terminate":   ["end", "cancel"],
    "warranty":    ["guarantee", "assurance"],
    "liability":   ["responsibility", "obligation"],
    "notwithstanding": ["despite", "regardless of"]
}

def synonym_replace(text: str, p: float = 0.3) -> str:
    tokens = text.split()
    out = []
    for tok in tokens:
        key = tok.strip(".,’\"").lower()
        if key in SYNONYMS and random.random() < p:
            out.append(random.choice(SYNONYMS[key]))
        else:
            out.append(tok)
    return " ".join(out)

# 3) Paraphrase pipeline (few-shot LLM)
paraphraser = pipeline("text2text-generation", model="Vamsi/T5_Paraphrase_Paws")

def paraphrase(text: str, num_return_sequences: int = 1) -> str:
    prompt = f"paraphrase: {text} </s>"
    res = paraphraser(
        prompt,
        max_length=256,
        num_beams=5,
        num_return_sequences=num_return_sequences,
        do_sample=False
    )
    # return the top beam
    return res[0]["generated_text"].strip()

def main():
    src = Path("data/clause_pairs.json")
    assert src.exists(), f"{src} not found!"
    records = json.loads(src.read_text(encoding="utf-8"))
    
    augmented = []
    for rec in records:
        inp, tgt = rec["input"], rec["target"]
        
        # A) back-translation of both sides
        bt_inp = back_translate(inp)
        bt_tgt = back_translate(tgt)
        augmented.append({"input": bt_inp, "target": bt_tgt})
        
        # B) synonym replacement on input
        syn_inp = synonym_replace(inp, p=0.4)
        syn_tgt = synonym_replace(tgt, p=0.4)
        augmented.append({"input": syn_inp, "target": syn_tgt})
        
        # C) LLM paraphrase of target
        llm_tgt = paraphrase(tgt)
        augmented.append({"input": inp, "target": llm_tgt})
    
    # Combine and dedupe
    all_recs = records + augmented
    # drop exact-duplicate pairs
    unique = { (r["input"], r["target"]): r for r in all_recs }
    final = list(unique.values())
    
    # Shuffle to mix originals & augments
    random.shuffle(final)
    
    # Write JSON + CSV
    out_json = Path("data/clause_pairs_augmented.json")
    out_csv  = Path("data/clause_pairs_augmented.csv")
    
    out_json.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")
    
    df = pd.DataFrame(final)
    df.to_csv(out_csv, index=False, encoding="utf-8")
    
    print(f"Original: {len(records)} pairs")
    print(f"Augmented: {len(final)-len(records)} new pairs")
    print(f"Total: {len(final)} pairs")
    print(f"Saved to {out_json} and {out_csv}")

if __name__ == "__main__":
    main()
