import io
import json
import time
import unittest
from unittest.mock import Mock, patch

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
    def test_slow_first_token_inside_total_window_is_not_cut_off_at_ninety_seconds(self):
        # Regression: real tenant TTFT was 87.5s plus tunnel overhead, while
        # generation finished at 94.5s. One 240s request window covers both.
        with patch('orchestrator.inference.time.monotonic', return_value=195):
            r=stream_response(sse([event('ready', 'stop')]), CONFIG, 100)
        self.assertEqual(r['choices'][0]['message']['content'], 'ready')

    def test_late_read_cannot_publish_answer_and_does_not_renew_window(self):
        wire=sse([event('late', 'stop')])
        with patch('orchestrator.inference.time.monotonic', side_effect=[100, 341]):
            with self.assertRaisesRegex(Refusal, 'processing window'):
                stream_response(wire, CONFIG, 100)

    def test_explicit_short_timeout_remains_bounded(self):
        with patch('orchestrator.inference.time.monotonic', return_value=103):
            with self.assertRaisesRegex(Refusal, 'processing window'):
                stream_response(sse([event('late','stop')]), CONFIG, 100, timeout=2)

    def test_complete_stream_is_buffered_and_keeps_usage_routing(self):
        events = [event('{"answer":'), event('"hello"}'), event(finish="stop", usage={"total_tokens":30})]
        r = stream_response(sse(events), CONFIG, time.monotonic())
        self.assertEqual(r["choices"][0]["message"]["content"], '{"answer":"hello"}')
        self.assertEqual(r["usage"]["total_tokens"], 30)
        self.assertEqual(r["model"], CONFIG.model)

    def test_transport_uses_sse_accept_with_same_auth_and_no_extra_route(self):
        c = Client(CONFIG); c.opener = Mock()
        c.opener.open.return_value = sse([event("ok", "stop")])
        result = c.request("chat/completions", {"model": CONFIG.model, "max_tokens": 2048, "stream":True})
        req = c.opener.open.call_args.args[0]
        self.assertEqual(req.get_header("Accept"), "text/event-stream")
        self.assertEqual(req.get_header("Authorization"), "Bearer "+CONFIG.api_key)
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")

    def test_tenancy_final_chunk_without_blank_before_done(self):
        wire = ("data: "+json.dumps(event("ready", "stop"))+"\ndata: [DONE]\n\n").encode()
        result = stream_response(io.BytesIO(wire), CONFIG, time.monotonic())
        self.assertEqual(result["choices"][0]["message"]["content"], "ready")
        invalid = b'data: {"partial":\ndata: [DONE]\n\n'
        with self.assertRaises(ValueError): stream_response(io.BytesIO(invalid), CONFIG, time.monotonic())

    def test_adjacent_complete_json_records_and_multiline_event(self):
        wire = ''.join('data: '+json.dumps(e)+'\n' for e in [event('one'),event(' two','stop'),
            {"usage":{"total_tokens":12},"choices":[]}])+'data: [DONE]\n\n'
        r = stream_response(io.BytesIO(wire.encode()),CONFIG,time.monotonic())
        self.assertEqual(r['choices'][0]['message']['content'],'one two')
        self.assertEqual(r['usage']['total_tokens'],12)
        lines = json.dumps(event('multiline','stop'),indent=2).splitlines()
        wire = ''.join('data: '+line+'\n' for line in lines)+'\ndata: [DONE]\n\n'
        r = stream_response(io.BytesIO(wire.encode()),CONFIG,time.monotonic())
        self.assertEqual(r['choices'][0]['message']['content'],'multiline')

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
