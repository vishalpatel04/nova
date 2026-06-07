# NOVA Memory Benchmarks (experimental)

Isolated harness comparing retrieval strategies. Does not replace production hybrid retrieval.

## Run

```bash
.venv/bin/python experiments/memory-benchmarks/harness.py
```

## Strategies

- keyword-only
- vector-only (requires Ollama + nomic-embed-text)
- hybrid
- hybrid + graph traversal

## Sample queries

- Where are my Lund documents?
- Find my Sweden exchange reimbursement files.
- What did we merge yesterday?
- Which projects involved Darshan?
- What broke Ollama last time?
