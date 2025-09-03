import os
import argparse

from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
    pipeline
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel
from transformers import StoppingCriteria, StoppingCriteriaList


def train(args):
    model_name = args.base_model
    data_path  = args.dataset_path
    output_dir = args.output_dir

    # 1. Tokenizer & data
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token

    raw_ds = load_dataset("json", data_files={"train": data_path})
    def preprocess(batch):
        inputs = [
            f"[Simplify]\n{inp}\n[Output]\n{tgt}"
            for inp, tgt in zip(batch["input"], batch["target"])
        ]
        return tokenizer(
            inputs,
            truncation=True,
            padding="max_length",
            max_length=512
        )

    tokenized_ds = raw_ds.map(
        preprocess, batched=True, remove_columns=["input", "target"]
    )
    data_collator = DataCollatorForLanguageModeling(tokenizer, mlm=False)

    # 2. Load base model 8-bit + LoRA prep
    quant_config = BitsAndBytesConfig(load_in_8bit=True)
    base = AutoModelForCausalLM.from_pretrained(
        model_name, quantization_config=quant_config, device_map="auto"
    )
    base = prepare_model_for_kbit_training(base)

    # 3. Attach LoRA
    lora_cfg = LoraConfig(
        r=8,
        lora_alpha=32,
        target_modules=["c_attn","q_proj","v_proj"],
        lora_dropout=0.1,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(base, lora_cfg)
    model.print_trainable_parameters()

    # 4. Training setup
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=1,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        fp16=True,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ds["train"],
        data_collator=data_collator,
        tokenizer=tokenizer
    )

    # 5. Train & save
    trainer.train()
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"Training complete. Artifacts in {output_dir}")


def infer(args):
    # 1. Load model + LoRA
    quant_config = BitsAndBytesConfig(load_in_8bit=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.base_model, quantization_config=quant_config, device_map="auto"
    )
    model = PeftModel.from_pretrained(base, args.output_dir)

    # 2. Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    tokenizer.pad_token_id = tokenizer.eos_token_id

    # 3. Prepare more few-shot demonstrations
    demos = [
        {
            "inp": "The lessee shall pay rent on time.",
            "out": "The tenant must pay rent on time."
        },
        {
            "inp": "All notices must be in writing and delivered to the other party’s registered office.",
            "out": "All notices must be written and sent to the other party’s office."
        },
        {
            "inp": "The borrower must repay the principal amount within thirty days after maturity.",
            "out": "The borrower must repay the loan within thirty days of due date."
        },
        {
            "inp": "This agreement may be terminated by either party upon thirty days written notice.",
            "out": "Either party can end this agreement with thirty days’ written notice."
        }
    ]

    # 4. Assemble the prompt with a hard “one sentence” instruction
    prompt = ""
    for d in demos:
        prompt += f"Clause: {d['inp']}\nSimplified: {d['out']}\n\n"
    prompt += (
        f"Clause: {args.prompt.strip()}\n"
        "Simplified (exactly one plain English sentence):"
    )

    # 5. Custom stopping criteria: stop as soon as a period is generated
    period_id = tokenizer.encode(".", add_special_tokens=False)[0]
    class StopOnPeriod(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            return input_ids[0, -1] == period_id

    stoppoints = StoppingCriteriaList([StopOnPeriod()])

    # 6. Generate with stopping_criteria
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        repetition_penalty=args.repetition_penalty,
        do_sample=True,
        stopping_criteria=stoppoints,
        eos_token_id=tokenizer.eos_token_id,
        pad_token_id=tokenizer.eos_token_id,
        num_return_sequences=1
    )

    # 7. Decode & strip prompt
    text = tokenizer.decode(output_ids[0], skip_special_tokens=True)
    simplified = text[len(prompt):].strip()
    # ensure there’s a trailing period
    if not simplified.endswith("."):
        simplified += "."

    # 8. Print result
    print("===== SIMPLIFIED CLAUSE =====")
    print(simplified)


def main():
    parser = argparse.ArgumentParser(
        description="Train or Infer for Legal Document Simplification with LoRA"
    )
    # Global flags
    parser.add_argument("--base_model",  type=str, default="gpt2")
    parser.add_argument("--output_dir",  type=str, default="lora_output")

    sub = parser.add_subparsers(dest="mode", required=True)

    # Train
    p_train = sub.add_parser("train")
    p_train.add_argument("--dataset_path", type=str, default="data/clause_pairs.json")
    p_train.add_argument("--epochs",       type=int,   default=3)
    p_train.add_argument("--batch_size",   type=int,   default=4)
    p_train.add_argument("--lr",           type=float, default=2e-4)

    # Infer
    p_inf = sub.add_parser("infer")
    p_inf.add_argument("--prompt",              type=str,   required=True)
    p_inf.add_argument("--max_new_tokens",      type=int,   default=15)
    p_inf.add_argument("--temperature",         type=float, default=0.2)
    p_inf.add_argument("--top_p",               type=float, default=0.9)
    p_inf.add_argument("--repetition_penalty",  type=float, default=2.0)

    args = parser.parse_args()
    if args.mode == "train":
        train(args)
    else:
        infer(args)


if __name__ == "__main__":
    main()
