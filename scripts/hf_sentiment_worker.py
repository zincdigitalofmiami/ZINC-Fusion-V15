#!/usr/bin/env python3
"""
Isolated HuggingFace Sentiment Worker
=====================================

Runs in a subprocess to avoid mutex lock issues with transformers on Mac.
Communicates via stdin/stdout JSON.

Usage:
    echo '{"text": "Oil prices surge on China demand"}' | python scripts/hf_sentiment_worker.py
"""

import json
import sys
import os

# Disable tokenizer parallelism before any imports
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

def main():
    # Import inside main to ensure env vars are set first
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch

    model_name = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"

    # Load model and tokenizer
    print(json.dumps({"status": "loading", "model": model_name}), file=sys.stderr)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.eval()

    print(json.dumps({"status": "ready"}), file=sys.stderr)

    # Label mapping for this model
    labels = ["negative", "neutral", "positive"]

    # Process stdin line by line
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            text = request.get("text", "")

            if not text:
                print(json.dumps({"error": "no text provided"}))
                sys.stdout.flush()
                continue

            # Tokenize and predict
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)

            with torch.no_grad():
                outputs = model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

            # Get prediction
            pred_idx = probs.argmax().item()
            confidence = probs[0][pred_idx].item()

            # Convert to sentiment score (-1 to 1)
            # negative = -1, neutral = 0, positive = 1
            if pred_idx == 0:  # negative
                score = -confidence
            elif pred_idx == 2:  # positive
                score = confidence
            else:  # neutral
                score = 0.0

            result = {
                "label": labels[pred_idx],
                "score": round(score, 4),
                "confidence": round(confidence, 4),
                "probs": {
                    "negative": round(probs[0][0].item(), 4),
                    "neutral": round(probs[0][1].item(), 4),
                    "positive": round(probs[0][2].item(), 4)
                }
            }

            print(json.dumps(result))
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"invalid JSON: {e}"}))
            sys.stdout.flush()
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
