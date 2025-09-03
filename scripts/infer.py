import argparse
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    AutoModelForCausalLM,
    pipeline
)
from peft import PeftModel

def load_model(base_name, lora_dir):
    quant_config = BitsAndBytesConfig(load_in_8bit=True, llm_int8_threshold=6.0)
    base = AutoModelForCausalLM.from_pretrained(
        base_name, quantization_config=quant_config, device_map="auto"
    )
    return PeftModel.from_pretrained(base, lora_dir)

def main():
    parser = argparse.ArgumentParser(description="Run LoRA inference")
    parser.add_argument("--base_model", default="gpt2")
    parser.add_argument("--lora_dir", default="lora_output")
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()

    model = load_model(args.base_model, args.lora_dir)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    tokenizer.pad_token_id = tokenizer.eos_token_id

    gen = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        device_map="auto",
        max_new_tokens=50,
    )

    output = gen(args.prompt)[0]["generated_text"]
    print(output)

if __name__ == "__main__":
    main()
