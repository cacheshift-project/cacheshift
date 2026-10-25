# Cache quality (Story 2), seed 601

Rates are per request; brackets are 95% bootstrap intervals over question groups.

| Model | Cache | Hit rate | False hits | False-hit errors | Inherited errors | Accuracy change vs fresh |
|---|---|---:|---:|---:|---:|---:|
| gpt-4-1106-preview | exact | 50.0% [48.3, 51.6] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 2.2% [1.4, 3.1] | 0.0% [0.0, 0.0] |
| gpt-4-1106-preview | cos>=0.98 | 50.2% [48.5, 51.7] | 0.2% [0.0, 0.4] | 0.1% [0.0, 0.3] | 2.2% [1.4, 3.1] | -0.1% [-0.3, 0.0] |
| gpt-4-1106-preview | cos>=0.95 | 50.3% [48.6, 51.8] | 0.3% [0.1, 0.5] | 0.2% [0.1, 0.4] | 2.2% [1.4, 3.1] | -0.2% [-0.4, -0.1] |
| gpt-4-1106-preview | cos>=0.90 | 50.4% [48.7, 51.9] | 0.4% [0.1, 0.7] | 0.3% [0.1, 0.5] | 2.2% [1.4, 3.1] | -0.3% [-0.5, -0.1] |
| gpt-4-1106-preview | cos>=0.85 | 50.7% [49.0, 52.2] | 1.2% [0.5, 2.2] | 1.1% [0.4, 2.0] | 2.2% [1.4, 3.1] | -1.0% [-2.0, -0.3] |
| gpt-4-1106-preview | cos>=0.80 | 51.6% [49.9, 53.2] | 3.2% [2.0, 4.6] | 2.6% [1.4, 3.9] | 2.2% [1.4, 3.1] | -2.5% [-3.9, -1.4] |
| mistralai/mixtral-8x7b-chat | exact | 50.0% [48.3, 51.6] | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] | 8.5% [6.7, 10.3] | 0.0% [0.0, 0.0] |
| mistralai/mixtral-8x7b-chat | cos>=0.98 | 50.2% [48.5, 51.7] | 0.2% [0.0, 0.4] | 0.1% [0.0, 0.3] | 8.5% [6.7, 10.3] | -0.1% [-0.3, 0.0] |
| mistralai/mixtral-8x7b-chat | cos>=0.95 | 50.3% [48.6, 51.8] | 0.3% [0.1, 0.5] | 0.2% [0.0, 0.4] | 8.5% [6.7, 10.3] | -0.2% [-0.4, 0.0] |
| mistralai/mixtral-8x7b-chat | cos>=0.90 | 50.4% [48.7, 51.9] | 0.4% [0.1, 0.7] | 0.2% [0.1, 0.4] | 8.5% [6.7, 10.3] | -0.2% [-0.4, -0.1] |
| mistralai/mixtral-8x7b-chat | cos>=0.85 | 50.7% [49.0, 52.2] | 1.2% [0.5, 2.2] | 1.1% [0.4, 2.0] | 8.3% [6.5, 10.2] | -0.8% [-1.6, -0.2] |
| mistralai/mixtral-8x7b-chat | cos>=0.80 | 51.6% [49.9, 53.2] | 3.2% [2.0, 4.6] | 2.7% [1.6, 4.0] | 8.2% [6.5, 10.1] | -2.3% [-3.5, -1.3] |

Nearest *different* question, cosine similarity: median 0.646, 90th percentile 0.758, 99th 0.941, max 0.995.

Replay mode: re-asking a question returns the identical recorded answer, so inherited errors cost no accuracy versus a fresh call here; with live models they can. Uniform repeats and no rewordings yet. Full prompts are embedded, including shared instructions.
