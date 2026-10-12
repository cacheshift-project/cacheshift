"""CPU inference using RouteLLM's released BERT checkpoint and score convention."""

import math

CHECKPOINT = "routellm/bert"
REVISION = "874d4aa9758c88ff6a71c6c469fba88e42248304"
UPSTREAM_REVISION = "0b64fdafe049e596a3f5657c219329f24af24198"


def strong_score(logits):
    """RouteLLM BERT uses P(label 0), excluding tie and weak-win classes."""
    values = [float(value) for value in logits]
    if len(values) != 3 or not all(math.isfinite(value) for value in values):
        raise ValueError("Expected three finite RouteLLM BERT logits")
    maximum = max(values)
    weights = [math.exp(value - maximum) for value in values]
    return weights[0] / sum(weights)


class LocalBERTRouter:
    """No model API calls; downloads public weights on first use unless offline."""

    def __init__(self, cache_dir, offline=False, threads=4):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if threads < 1:
            raise ValueError("threads must be positive")
        torch.set_num_threads(threads)
        self.torch = torch
        # Resolve a local snapshot first: some Transformers versions perform Hub
        # metadata requests even when a tokenizer is given local_files_only=True.
        snapshot = snapshot_download(
            CHECKPOINT, revision=REVISION, cache_dir=str(cache_dir),
            local_files_only=offline,
            allow_patterns=["config.json", "model.safetensors", "tokenizer.json",
                            "tokenizer_config.json", "special_tokens_map.json",
                            "sentencepiece.bpe.model"],
        )
        options = dict(local_files_only=True, trust_remote_code=False)
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, **options)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            snapshot, use_safetensors=True, **options
        ).to("cpu").eval()
        if self.model.config.num_labels != 3:
            raise ValueError("Expected the official three-label checkpoint")

    def score(self, prompt):
        return self.score_many([prompt])[0]

    def score_many(self, prompts, batch_size=4):
        """Batch CPU inference without changing the checkpoint or score rule."""
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be positive")
        prompts = list(prompts)
        if any(not isinstance(prompt, str) or not prompt.strip() for prompt in prompts):
            raise ValueError("prompt must be a nonempty string")
        results = []
        for start in range(0, len(prompts), batch_size):
            batch = prompts[start:start + batch_size]
            lengths = [len(self.tokenizer.encode(prompt)) for prompt in batch]
            inputs = self.tokenizer(batch, return_tensors="pt", padding=True,
                                    truncation=True, max_length=512)
            with self.torch.inference_mode():
                logits = self.model(**inputs).logits.tolist()
            used = inputs["attention_mask"].sum(dim=1).tolist()
            results.extend({"router_score": strong_score(values), "input_tokens": length,
                            "used_tokens": int(count), "truncated": length > 512}
                           for values, length, count in zip(logits, lengths, used))
        return results
