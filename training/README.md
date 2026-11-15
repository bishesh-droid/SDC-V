# Local intake model (Qwen + LoRA)

Goal: replace Gemini for **intake only** (brief -> JSON) with a small fine-tuned Qwen that runs on your own machine. Narrative
writing, the calculator, the verifier and the guardrails are unchanged. Grounding and range checks still run on whatever the
model returns, so a wrong extraction is dropped or rejected, not trusted.

## Files

| File | What it does | Needs |
|---|---|---|
| `make_intake_dataset.py` | Builds train, val and three test sets (gold is known by construction) | stdlib |
| `intake_eval.py` | Scores any intake backend; separates dangerous errors (hallucinated or wrong values) from cheap ones (missed values) | stdlib |
| `train_intake_qlora.py` | QLoRA fine-tune, loss on the JSON answer only, optional prediction dump | Colab GPU |
| `../backend/app/llm/local.py` | `LocalLLM`, same protocol as `GeminiClient`, lazy imports | torch, transformers, peft |

## Steps

**Easiest: one command on Colab.** Upload the SDC-V folder to Google Drive, open `sdcv_colab.ipynb` on a T4 runtime and run both
cells. `colab_run.py` does setup, zero-shot, a 20-step smoke test, training, scoring and the hand-written benchmark. Each stage writes a
marker file to Drive, so a rerun after a disconnect continues from the last checkpoint. It trains a new adapter named
`intake-lora-v2` by default (`--name` changes it) and never overwrites an older adapter.

By hand:

1. **Data** (laptop): `python3 make_intake_dataset.py` -> `data/` (3350 train, 280 val, 820 test across four test sets).
2. **Floors** (laptop, no model): `python3 intake_eval.py --backend oracle` must print 100%. `--backend null` is the do-nothing floor.
3. **Baseline** (laptop, uses quota): `python3 intake_eval.py --backend gemini --out outputs/gemini_rows.jsonl`.
4. **Zero-shot Qwen** (Colab): `python intake_eval.py --backend local --model Qwen/Qwen2.5-3B-Instruct --limit 50`.
5. **Train** (Colab T4): `python train_intake_qlora.py --model Qwen/Qwen2.5-3B-Instruct --fp16 --predict --name intake-lora-v2`.
   Add `--resume` to continue from a checkpoint. Smoke test first: `--max_steps 20 --train_rows 200`.
6. **Score** (anywhere): `python3 intake_eval.py --backend file --predictions pred_test_heldout.jsonl --split test_heldout`.
7. **Hand-written cases through the real pipeline** (Colab for local, laptop for Gemini):
   `python benchmark/run_intake_compare.py --backend local --adapter outputs/intake-lora-v2/final`
   `python benchmark/run_intake_compare.py --backend gemini --sleep 2`, then `--diff a.json b.json`.

## Test sets

| Split | What it tests |
|---|---|
| `test_iid` | fresh rows of the phrasing variants seen in training |
| `test_heldout` | a phrasing variant never seen in training |
| `test_ood` | a family that exists only in the test set (email style) |
| `test_sparse` | vague or nearly empty beam requests ("Design a beam for a 6 m span"), with phrasings never used in training |

## Results

All numbers below come from data made by `make_intake_dataset.py`, so they measure how well the model learned this generator's
distribution, **not** how it behaves on real engineers' briefs. Treat the hand-written benchmark and your own messy briefs as the real test.

Field-level scores (dangerous = a value the gold answer says is null, or a wrong value):

| Model | `test_iid` | `test_heldout` | `test_ood` | `test_sparse` |
|---|---|---|---|---|
| Qwen2.5-3B, no fine-tuning (50 rows each) | intent 0%, 86% rows dangerous | 0%, 82% | 0%, 78% | 0%, 60% |
| Gemini (production prompt, full splits) | intent 97.6%, 5.2% dangerous | 97.3%, 7.0% | 96.7%, 10.0% | not run |
| Fine-tuned v1 (`intake-lora`) | 100%, 0.4% | 99.7%, 0.0% | 100%, 0.0% | not run |
| Fine-tuned v2 (`intake-lora-v2`) | 100%, 0.4% | 99.7%, 0.7% | 100%, 0.0% | 100%, 10.8% |

The 13 `test_sparse` errors for v2 are one pattern: "Beam for a small shop, N m wide" was labelled as the span and the model read it as the beam
width. `b` is limited to 150-1000 mm by the schema, so most of these are blocked downstream and the rest are visible in the echoed inputs.

Hand-written chat cases through the real pipeline (56 cases: scope, unsafe, incomplete, injection, benign wording):

| Model | Passed | Designed when it should not have | Injection cases |
|---|---|---|---|
| Gemini | 54/56 | 0 | 6/8 (refuses the whole brief when an attachment contains a hostile instruction) |
| Fine-tuned v1 | 52/56 | 0 | 8/8 (answers "not supported" to very sparse briefs) |
| Fine-tuned v2 | 56/56 | 0 | 8/8 |

v2 adds 400 sparse-brief rows to training. `backend/app/pipeline.py` also overrides an `out_of_scope` / `not_a_beam_brief` verdict that
only means "details are missing" (no reason, or a reason that says so) when the text is about a beam, and logs an
`intake_intent_overridden` event. A reason naming a real unsupported feature is never overridden.

Training cost: 420 steps, about 1 h 40 min on a free Colab T4, QLoRA rank 16.

## How to read the results

- **Hallucinated / wrong fields** are the number that matters. A missed field only makes the tool ask again.
- Compare `test_iid` (phrasing seen in training) with `test_heldout` (phrasing never seen) and `test_ood` (a new style). A big drop
  means the model memorised templates.
- Intake rows must also be checked against the **real pipeline**: run the model's JSON through grounding and `normalise` and compare
  the final status with the benchmark. That end-to-end check is the next step after step 6.

## Snapshots (photos, sketches, tender extracts)

A text model cannot see, so intake is two-stage when a picture is attached:

    snapshot -> vision model -> verbatim transcript -> fine-tuned intake model -> fields
                (Gemini or Qwen2.5-VL)                 (reads <image_text>)

- `backend/app/llm/vision.py` holds the transcription prompt. It copies only what is written, marks anything unreadable
  `[illegible]`, and quotes instructions found in the image as "Written in image:" instead of following them.
- The pipeline redacts the transcript (email, phone), screens it for injection, and the grounding check still requires every extracted
  number to appear in the brief, the attachment or the transcript.
- The prompt is assembled from whatever data a request has by `build_intake_user()` in `backend/app/llm/intake.py`:
  `<brief>`, then `<attachment>` if pasted, then `<image_text>` if a snapshot was transcribed. The dataset generator imports that same
  function and the same `LOCAL_INTAKE_SYSTEM`, so what the model trains on is byte-for-byte what it is sent. A test enforces it.
- The training data includes snapshot rows: a drawing title block, a printed table, handwritten shorthand (held out for testing),
  a brief that gives some values and the picture the rest, blurry pictures (all null), unrelated pictures (`not_a_beam_brief`) and
  instructions written inside a picture.
- The vision model is not fine-tuned. Judge it on its own: transcribe a few real snapshots and check them by eye before relying on it.

## Switching the application over (nothing changes until you set these)

| Variable | Meaning | Default |
|---|---|---|
| `SDCV_INTAKE_BACKEND` | `gemini` or `local` | `gemini` |
| `SDCV_LOCAL_MODEL` | base model | `Qwen/Qwen2.5-3B-Instruct` |
| `SDCV_LOCAL_ADAPTER` | path to the LoRA adapter folder (`outputs/intake-lora-v2/final`) | none |
| `SDCV_LOCAL_4BIT` | `1` to load the base model in 4-bit (needs bitsandbytes and a GPU) | off |
| `SDCV_VISION_BACKEND` | `gemini`, `local` (Qwen2.5-VL) or empty | empty; becomes `gemini` when intake is `local` |
| `SDCV_VISION_MODEL` | local vision model | `Qwen/Qwen2.5-VL-3B-Instruct` |

The narrative still comes from Gemini (or the template without a key). `GET /api/health` reports `intake_backend` and `vision_backend`.

## Choices made, and why

- **Qwen2.5-3B-Instruct.** Trains with QLoRA on a free Colab T4 and, in 4-bit, needs about 2 GB to run. There is no 5B Qwen2.5; 7B
  would not fit your 4 GB laptop GPU. Drop to 1.5B if speed matters more than accuracy.
- **Short system prompt** (`LOCAL_INTAKE_SYSTEM`) instead of the long Gemini prompt: fine-tuning makes the long rules unnecessary and
  the sequence is about 3x shorter. `LocalLLM` carries it as `intake_prompt`, which `run_intake` picks up automatically.

## Not done yet

- **Real briefs.** Nothing has been tried on messy real-world text (typos, mixed units, long emails, scanned tables). Do this in the UI
  before trusting the adapter.
- **Snapshots.** The vision model is not fine-tuned and its transcripts have not been checked against real photos.
- The local model has been run only on Colab. Running it on the 4 GB laptop GPU (`SDCV_LOCAL_4BIT=1`) is untested.
- The 56-case hand-written benchmark was written by the same author as the generator; it is small and one case moves the score by about 2%.
- The frontend does not yet show the new `Snapshot` stage in the chat progress strip (it appears in the stored trace).
