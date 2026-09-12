# Notebooks

Four notebooks covering the ML fundamentals behind this project's RAG
pipeline: tokenization, embeddings, transformer inference, and retrieval
evaluation.

## Setup

```
cd agent-service
python3 -m venv .venv        # if you haven't already
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes jupyter + ipykernel
python -m ipykernel install --user --name aiops-agent-service --display-name "AI-Ops agent-service"

cd ../notebooks
jupyter lab   # open any notebook, select the "AI-Ops agent-service" kernel
```

## Network note

`01_tokenization.ipynb`, `02_embeddings.ipynb`, and `03_huggingface_inference.ipynb`
each have a cell that downloads a real model from the Hugging Face Hub. These
notebooks were authored and executed inside a network-restricted sandbox
that blocks `huggingface.co` — so those specific cells are wrapped in
`try/except` and show the real connection error when run there, with a
note on what a normal-network machine would print instead. On a laptop, in
CI, or on GCP with normal internet, they'll download the (free,
open-source) model on first run and just work — no other change needed.

`04_rag_evaluation.ipynb` needs no external network at all — it evaluates
this project's own ingestion pipeline end to end using the offline
`local-hash` embedding provider, so its 100% hit@3 result on the bundled
eval set is real and reproducible anywhere.
