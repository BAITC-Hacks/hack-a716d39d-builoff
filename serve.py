"""Local viewer and read-only question API. Run: python serve.py."""

import argparse
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from dotenv import dotenv_values

from ask import Results, ask
from input_check import check, policy


ROOT = Path(__file__).resolve().parent


def answer_question(question, data, client, model):
    checks = {"guard": {"status": "skipped", "reason": "input check not completed"},
              "ontology": {"status": "skipped", "reason": "input check not completed"}}
    try:
        result = check(question, client, model)
        checks = result
        terminal, answer, hint = policy(result)
        if terminal == "REJECT":
            return {"answer": answer, "terminal": terminal, "checks": checks}
    except Exception as exc:
        reason = "input check failed: " + type(exc).__name__
        checks = {"guard": {"status": "skipped", "reason": reason},
                  "ontology": {"status": "skipped", "reason": reason}}
        hint = None
    try:
        answer, _, _ = ask(question, data, client, model, hint=hint)
        return {"answer": answer, "terminal": "ANSWER", "checks": checks}
    except Exception as exc:
        return {"answer": "Ошибка AI-ассистента: " + type(exc).__name__,
                "terminal": "ERROR", "checks": checks}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def allowed_path(self):
        path = unquote(urlsplit(self.path).path)
        parts = Path(path).parts
        return len(parts) >= 2 and parts[1] in ("viewer", "out") and ".." not in parts

    def do_GET(self):
        if not self.allowed_path():
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        if not self.allowed_path():
            self.send_error(404)
            return
        super().do_HEAD()

    def send_json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/ask":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Размер запроса должен быть не больше 4096 байт.")
            payload = json.loads(self.rfile.read(length))
            question = payload.get("question") if isinstance(payload, dict) else None
            if not isinstance(question, str) or not 3 <= len(question.strip()) <= 1000:
                raise ValueError("Вопрос должен содержать от 3 до 1000 символов.")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"answer": str(exc), "terminal": "VALIDATION", "checks": {}})
            return
        env = dotenv_values(ROOT / ".env")
        key = os.getenv("OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL") or env.get("OPENAI_MODEL")
        if not key or key == "your_key_here" or not model or model == "your_model_here":
            self.send_json(503, {"answer": "AI-ассистент недоступен: задайте OPENAI_API_KEY и OPENAI_MODEL в .env.",
                                 "terminal": "ERROR", "checks": {}})
            return
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key, timeout=45.0, max_retries=0)
            result = answer_question(question.strip(), Results(ROOT / "out"), client, model)
            self.send_json(500 if result["terminal"] == "ERROR" else 200, result)
        except Exception as exc:
            self.send_json(500, {"answer": "Ошибка AI-ассистента: " + type(exc).__name__,
                                 "terminal": "ERROR", "checks": {}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"Viewer: http://{args.bind}:{args.port}/viewer/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
