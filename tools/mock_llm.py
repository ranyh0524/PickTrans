"""本地 mock 大模型服务器：模拟 OpenAI 兼容的 /v1/chat/completions 接口。

用途：不依赖真实 API key，端到端测试 PopTrans 的完整链路。
用法：python tools/mock_llm.py  （监听 127.0.0.1:8765）
配置：api_base = http://127.0.0.1:8765/v1, api_key = test, model = mock-model
"""
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST, PORT = "127.0.0.1", 8765


def fake_translate(user_text: str) -> str:
    """生成一段假的“译文”：前缀 + 简单处理，足够验证流式渲染。"""
    if any("\u4e00" <= ch <= "\u9fff" for ch in user_text):
        return f"[mock译文] {user_text[::-1]} —— 这是来自本地模拟服务器的中文→英文方向测试输出。"
    return f"[mock translation] {user_text} -- streamed by local mock server."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[mock] {fmt % args}")

    def _send_sse(self, text: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        # 把译文切成小块逐段推送，模拟流式
        step = max(2, len(text) // 8)
        for i in range(0, len(text), step):
            payload = {
                "id": "mock-1",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": text[i:i + step]}, "finish_reason": None}],
            }
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.12)
        done = {
            "id": "mock-1",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        self.wfile.write(f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode("utf-8"))
        self.wfile.flush()

    def _send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.path.rstrip().endswith("/chat/completions"):
            self._send_json({"error": {"message": f"unknown path {self.path}"}})
            return
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        user_text = "".join(m.get("content", "") for m in req.get("messages", []) if m.get("role") == "user")
        text = fake_translate(user_text.strip())
        if req.get("stream"):
            self._send_sse(text)
        else:  # 测试连接用
            self._send_json({
                "id": "mock-1", "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            })


if __name__ == "__main__":
    print(f"mock LLM listening on http://{HOST}:{PORT}/v1 ...")
    HTTPServer((HOST, PORT), Handler).serve_forever()
