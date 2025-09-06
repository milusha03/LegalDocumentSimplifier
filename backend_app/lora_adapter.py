import os
import re
import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, pipeline
from peft import PeftModel

# ─── Configuration ────────────────────────────────────────────
BASE_MODEL = "google/flan-t5-small"
ADAPTER_DIR = os.path.join(os.path.dirname(__file__), "utils", "lora_adapter")

# ─── Load & Quantize Base Model ───────────────────────────────
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
base_model = AutoModelForSeq2SeqLM.from_pretrained(BASE_MODEL)

# Dynamically quantize only the Linear layers to int8
base_model = torch.quantization.quantize_dynamic(
    base_model, {torch.nn.Linear}, dtype=torch.qint8
)

# ─── Apply Your LoRA Adapter ──────────────────────────────────
try:
    model = PeftModel.from_pretrained(
        base_model,
        ADAPTER_DIR,
        torch_dtype=torch.qint8  # keep weights in int8
    )
    print("✅ LoRA adapter applied successfully on quantized model.")
except Exception as e:
    print("❌ LoRA adapter failed:", e)
    model = base_model

# ─── Build Pipelines ───────────────────────────────────────────
summarizer = pipeline(
    "summarization",
    model=model,
    tokenizer=tokenizer,
    device_map="auto" if torch.cuda.is_available() else None
)
simplifier = pipeline(
    "text2text-generation",
    model=model,
    tokenizer=tokenizer,
    device_map="auto" if torch.cuda.is_available() else None
)

# ─── Helpers ─────────────────────────────────────────────────
def split_into_chunks(text, max_chars=800):
    paras = re.split(r'\n\s*\n', text.strip())
    chunks, curr = [], ""
    for p in paras:
        if len(curr) + len(p) < max_chars:
            curr += p + "\n\n"
        else:
            chunks.append(curr.strip())
            curr = p + "\n\n"
    if curr:
        chunks.append(curr.strip())
    return chunks

# ─── Main Simplification Function ────────────────────────────
def generate_with_lora(full_text: str) -> str:
    """
    1) Segment by paragraph  
    2) Summarize each segment  
    3) Simplify that summary  
    4) Label sections
    """
    try:
        sections = split_into_chunks(full_text)
        outputs = []

        for idx, sec in enumerate(sections, start=1):
            # 1) Summarize
            sum_res = summarizer(sec, max_length=150, min_length=50, do_sample=False)
            summary = sum_res[0]["summary_text"]

            # 2) Simplify summary
            simp_res = simplifier(
                f"simplify for a small business owner:\n\n{summary}",
                max_length=150,
                do_sample=False
            )
            simple = simp_res[0]["generated_text"]

            # 3) Label & include excerpt
            excerpt = sec.replace("\n"," ")[:200].strip() + "..."
            outputs.append(
                f"Section {idx}\n"
                f"Original excerpt: {excerpt}\n\n"
                f"Simplified: {simple.strip()}\n"
            )

        return "\n\n".join(outputs)

    except Exception as e:
        print("❌ Two-pass simplification error:", e)
        return "⚠️ Error during simplification."
