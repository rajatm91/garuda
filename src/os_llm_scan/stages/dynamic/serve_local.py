"""Minimal OpenAI-compatible local server (transformers backend)."""
from __future__ import annotations
import argparse, time
from pathlib import Path


_model = None
_tokenizer = None
_model_id = ""


def _load(model_path: Path, model_id: str) -> None:
    global _model, _tokenizer, _model_id
    from transformers import AutoModelForCausalLM, AutoTokenizer
    _tokenizer = AutoTokenizer.from_pretrained(str(model_path))
    _model = AutoModelForCausalLM.from_pretrained(str(model_path))
    _model_id = model_id


def _build_app():
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI()

    class ChatMessage(BaseModel):
        role: str
        content: str

    class ChatRequest(BaseModel):
        model: str
        messages: list[ChatMessage]
        max_tokens: int = 512
        temperature: float = 0.7

    @app.get("/v1/models")
    def list_models():
        return {"object": "list", "data": [{"id": _model_id, "object": "model"}]}

    @app.post("/v1/chat/completions")
    def chat(req: ChatRequest):
        prompt = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
        inputs = _tokenizer(prompt, return_tensors="pt")
        out = _model.generate(**inputs, max_new_tokens=req.max_tokens,
                              do_sample=req.temperature > 0,
                              temperature=req.temperature or 1.0)
        text = _tokenizer.decode(out[0], skip_special_tokens=True)
        return {
            "id": f"chatcmpl-{int(time.time())}", "object": "chat.completion",
            "created": int(time.time()), "model": req.model,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": int(inputs["input_ids"].shape[1]),
                      "completion_tokens": int(out.shape[1] - inputs["input_ids"].shape[1]),
                      "total_tokens": int(out.shape[1])},
        }

    return app


def main(argv: list[str] | None = None) -> int:
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True, type=Path)
    p.add_argument("--model-id", required=True)
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    _load(args.model_path, args.model_id)
    uvicorn.run(_build_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
