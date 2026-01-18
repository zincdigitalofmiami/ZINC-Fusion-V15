#!/usr/bin/env python3
"""
HuggingFace Sentiment via ONNX Runtime
======================================

Uses ONNX runtime to avoid PyTorch threading issues on Mac.
"""

import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

import json
import sys
from pathlib import Path

def main():
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer
    import numpy as np

    model_name = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"
    cache_dir = Path.home() / ".cache" / "zinc_onnx_models"
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading ONNX model: {model_name}", file=sys.stderr)

    # Load tokenizer (this is lightweight)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Load or convert to ONNX
    try:
        model = ORTModelForSequenceClassification.from_pretrained(
            model_name,
            export=True,  # Export to ONNX on the fly
        )
    except Exception as e:
        print(f"Error loading model: {e}", file=sys.stderr)
        sys.exit(1)

    print("Model loaded successfully!", file=sys.stderr)

    # Label mapping
    labels = ["negative", "neutral", "positive"]

    # Test texts
    test_texts = [
        "Soybean oil prices surge on strong China demand and biofuel mandates",
        "Trump tariffs crush agricultural exports to China",
        "Weather conditions remain favorable for soybean harvest",
        "Palm oil production declines amid labor shortages",
        "Federal Reserve signals potential rate cuts ahead",
    ]

    print("\n" + "=" * 60, file=sys.stderr)
    print("SENTIMENT ANALYSIS RESULTS", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    results = []
    for text in test_texts:
        inputs = tokenizer(text, return_tensors="np", truncation=True, max_length=512)

        outputs = model(**inputs)
        logits = outputs.logits

        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / exp_logits.sum()

        pred_idx = probs.argmax()
        confidence = probs[0][pred_idx]

        # Convert to sentiment score
        if pred_idx == 0:  # negative
            score = -confidence
        elif pred_idx == 2:  # positive
            score = confidence
        else:  # neutral
            score = 0.0

        result = {
            "text": text[:60] + "..." if len(text) > 60 else text,
            "label": labels[pred_idx],
            "score": round(float(score), 4),
            "confidence": round(float(confidence), 4),
        }
        results.append(result)

        sentiment_emoji = "🔴" if score < -0.3 else "🟢" if score > 0.3 else "⚪"
        print(f"\n{sentiment_emoji} {labels[pred_idx].upper()} ({confidence:.1%})", file=sys.stderr)
        print(f"   Score: {score:+.3f}", file=sys.stderr)
        print(f"   Text: {text[:70]}...", file=sys.stderr)

    print("\n" + "=" * 60, file=sys.stderr)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
