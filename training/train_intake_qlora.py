"""QLoRA fine-tune of a Qwen2.5 Instruct model on the intake dataset. Meant for a Colab T4 (16 GB), not the laptop.

Loss is taken on the assistant JSON only (prompt/completion format), so the model is not trained to reproduce the system prompt.

Colab (see training/README.md):
    !pip install -q "transformers>=4.46" "trl>=0.12" "peft>=0.13" bitsandbytes accelerate datasets
    !python train_intake_qlora.py --model Qwen/Qwen2.5-3B-Instruct --fp16 --predict
Smoke test (a few minutes):  add  --max_steps 20 --train_rows 200

Outputs:  outputs/<name>/final              LoRA adapter + tokenizer
          outputs/<name>/pred_<split>.jsonl  one {"id","output"} per test row, scored on any machine with
                                             python3 intake_eval.py --backend file --predictions <file> --split <split>

TRL and transformers change their arguments between releases. This script was written against the documented API but has not
been run in this repository; if SFTConfig rejects an argument, check the installed TRL docs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--name", default="intake-lora")
    ap.add_argument("--max_len", type=int, default=1024)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--fp16", action="store_true", help="T4 has no bf16")
    ap.add_argument("--max_steps", type=int, default=-1)
    ap.add_argument("--train_rows", type=int, default=0, help="use only the first N training rows (smoke test)")
    ap.add_argument("--resume", action="store_true", help="continue from the newest checkpoint-* folder if there is one")
    ap.add_argument("--retrain", action="store_true", help="train again even if outputs/<name>/final already exists")
    ap.add_argument("--predict", action="store_true", help="after training, answer every test row and write pred_*.jsonl")
    a = ap.parse_args()

    import torch
    from datasets import load_dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    dtype = torch.float16 if a.fp16 else torch.bfloat16
    out = HERE / "outputs" / a.name
    tok = AutoTokenizer.from_pretrained(a.model)
    tok.pad_token = tok.pad_token or tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        a.model, device_map="auto", torch_dtype=dtype,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype))
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    lora = LoraConfig(r=a.rank, lora_alpha=2 * a.rank, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])

    def split(name):
        ds = load_dataset("json", data_files=str(Path(a.data) / f"{name}.jsonl"), split="train")
        return ds.map(lambda ex: {"prompt": ex["messages"][:2], "completion": ex["messages"][2:]}, remove_columns=ds.column_names)

    train, val = split("train"), split("val")
    if a.train_rows:
        train = train.select(range(min(a.train_rows, len(train))))
    import dataclasses
    import math
    steps = a.max_steps if a.max_steps > 0 else math.ceil(len(train) / (a.batch * a.accum)) * a.epochs
    want = dict(output_dir=str(out), num_train_epochs=a.epochs, max_steps=a.max_steps, per_device_train_batch_size=a.batch,
                per_device_eval_batch_size=a.batch, gradient_accumulation_steps=a.accum, learning_rate=a.lr,
                lr_scheduler_type="cosine", warmup_steps=max(1, int(0.05 * steps)), max_grad_norm=0.3, optim="paged_adamw_8bit",
                bf16=not a.fp16, fp16=a.fp16, gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
                logging_steps=10, eval_strategy="steps", eval_steps=100, save_strategy="steps", save_steps=50,
                save_total_limit=2, max_length=a.max_len, report_to="none", seed=42)
    known = {f.name for f in dataclasses.fields(SFTConfig)}
    dropped = sorted(set(want) - known)
    if dropped:   # TRL and transformers rename arguments between releases; say so instead of crashing
        print("SFTConfig does not know these arguments in this version, dropped:", dropped)
    cfg = SFTConfig(**{k: v for k, v in want.items() if k in known})

    final = out / "final"
    if final.exists() and not a.retrain:
        # training already finished (e.g. the session was cut off during prediction): load the saved adapter
        from peft import PeftModel
        print("found", final, "- skipping training")
        trainer, m = None, PeftModel.from_pretrained(model, str(final))
    else:
        trainer = SFTTrainer(model=model, args=cfg, train_dataset=train, eval_dataset=val, processing_class=tok, peft_config=lora)
        for prm in trainer.model.parameters():   # fp16 mixed precision (the T4 path) needs fp32 trainable weights; newer libraries can leave them bf16
            if prm.requires_grad and prm.dtype != torch.float32:
                prm.data = prm.data.float()
        trainer.model.print_trainable_parameters()
        resume = a.resume and out.exists() and any(out.glob("checkpoint-*"))
        if resume:
            print("resuming from the latest checkpoint in", out)
        trainer.train(resume_from_checkpoint=True if resume else None)
        trainer.save_model(str(final)); tok.save_pretrained(str(final))
        print("adapter saved to", final)
        m = trainer.model

    if a.predict:
        tok.padding_side = "left"
        m = m.eval()
        for name in ("test_iid", "test_heldout", "test_ood", "test_sparse"):
            recs = [json.loads(line) for line in (Path(a.data) / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            done = out / f"pred_{name}.jsonl"
            if done.exists() and sum(1 for line in done.read_text(encoding="utf-8").splitlines() if line.strip()) == len(recs):
                print("already complete:", done); continue
            with (out / f"pred_{name}.jsonl").open("w", encoding="utf-8") as f:
                for i in range(0, len(recs), 8):
                    chunk = recs[i:i + 8]
                    texts = [tok.apply_chat_template(r["messages"][:2], tokenize=False, add_generation_prompt=True) for r in chunk]
                    enc = tok(texts, return_tensors="pt", padding=True).to(m.device)
                    with torch.no_grad():
                        gen = m.generate(**enc, max_new_tokens=400, do_sample=False, pad_token_id=tok.pad_token_id)
                    for r, g in zip(chunk, gen):
                        f.write(json.dumps({"id": r["id"], "output": tok.decode(g[enc["input_ids"].shape[1]:], skip_special_tokens=True)}) + "\n")
            print("wrote", out / f"pred_{name}.jsonl")


if __name__ == "__main__":
    main()
