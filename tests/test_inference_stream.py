import io
import json
import time
import unittest
from unittest.mock import Mock

from orchestrator.core import Refusal
from orchestrator.inference import Client, MAX_STREAM_BYTES, stream_response
from test_assistant import CONFIG


def event(content=None, finish=None, **extra):
    return {"model": CONFIG.model, "request_key_source":"local-inference", "choices":[
        {"index":0, "delta":{"content":content}, "finish_reason":finish}], **extra}


def sse(events, done=True):
    return io.BytesIO((": heartbeat\n\n"+"".join("data: "+json.dumps(e)+"\n\n" for e in events)
                       +("data: [DONE]\n\n" if done else "")).encode())


class InferenceStreamTest(unittest.TestCase):
    def test_complete_stream_is_buffered_and_keeps_usage_routing(self):
        events = [event('{"answer":'), event('"hello"}'), event(finish="stop", usage={"total_tokens":30})]
        r = stream_response(sse(events), CONFIG, time.monotonic())
        self.assertEqual(r["choices"][0]["message"]["content"], '{"answer":"hello"}')
        self.assertEqual(r["usage"]["total_tokens"], 30)
        self.assertEqual(r["model"], CONFIG.model)

    def test_transport_uses_sse_accept_with_same_auth_and_no_extra_route(self):
        c = Client(CONFIG); c.opener = Mock()
        c.opener.open.return_value = sse([event("ok", "stop")])
        result = c.request("chat/completions", {"stream":True})
        req = c.opener.open.call_args.args[0]
        self.assertEqual(req.get_header("Accept"), "text/event-stream")
        self.assertEqual(req.get_header("Authorization"), "Bearer "+CONFIG.api_key)
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")

    def test_reject_missing_done_finish_and_routing(self):
        for stream in (sse([event("partial")]), sse([event("partial","stop")], done=False),
                       sse([{"choices":[{"delta":{"content":"unknown"},"finish_reason":"stop"}]}])):
            with self.assertRaises(Refusal): stream_response(stream, CONFIG, time.monotonic())

    def test_reject_model_change_tool_calls_errors_content_after_finish(self):
        tool = event(); tool["choices"][0]["delta"] = {"tool_calls":[{"name":"shell"}]}
        for events in ([event("x", model="external")], [event("x", request_key_source="hosted")], [tool],
                       [{"error":"untrusted upstream error"}], [event("a","stop"),event("b")],
                       [event("a","stop"),event(finish="stop")], [event("x"*12001)]):
            with self.subTest(events=events), self.assertRaises(Refusal): stream_response(sse(events), CONFIG, time.monotonic())

    def test_size_time_and_secret_guards(self):
        with self.assertRaises(Refusal): stream_response(sse([event(CONFIG.api_key,"stop")]), CONFIG, time.monotonic())
        with self.assertRaises(Refusal): stream_response(sse([event("ok","stop")]), CONFIG, time.monotonic()-241)
        with self.assertRaises(Refusal): stream_response(io.BytesIO(b":"+b"x"*(128*1024)+b"\n"), CONFIG, time.monotonic())
        with self.assertRaises(Refusal): stream_response(io.BytesIO(b": heartbeat\n\n"*(MAX_STREAM_BYTES//10)), CONFIG, time.monotonic())
