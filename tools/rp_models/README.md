# Roleplay-model setup

RP-tuned GGUF models pulled from Hugging Face via `ollama pull hf.co/...` often
arrive with a broken chat template (`TEMPLATE {{ .Prompt }}`), which makes them
emit incoherent output. These Modelfiles re-apply the correct Mistral-Nemo
instruct template. Build once, then use the resulting model name with the runner.

```bash
ollama pull  hf.co/TheDrummer/Rocinante-12B-v1.1-GGUF:Q4_K_M
ollama create rocinante-ru -f tools/rp_models/Rocinante.modelfile
ollama create mag-mell-ru  -f tools/rp_models/MagMell.modelfile

python tools/run_scenario.py --character both --length 10 \
    --model rocinante-ru --language Russian --user-gender male --name Alex
```

Both are Mistral-Nemo finetunes (so Russian works). For Russian, Rocinante holds
the language more consistently than Mag-Mell, which code-switches into English.
See `docs/EXAMPLE_RUN.md`.
