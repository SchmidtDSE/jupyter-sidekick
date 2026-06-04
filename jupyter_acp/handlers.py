"""REST handlers exposing the BindingManager over HTTP.

Thin translation only: parse the request, call the manager / session, serialize
the result. All real behaviour lives in the manager and session layers.

Note: these are plain Tornado handlers (no auth) — fine for a localhost PoC.
Hardening to authenticated `jupyter_server` APIHandlers is a follow-up.
"""
from __future__ import annotations

import json
from typing import Any

from tornado.web import RequestHandler
from tornado.websocket import WebSocketHandler

from .binding import AlreadyBoundError
from .registry import HarnessNotFoundError
from .serialize import update_to_json


class _BaseHandler(RequestHandler):
    def initialize(self, registry, manager) -> None:
        self.registry = registry
        self.manager = manager

    def write_json(self, payload: Any, status: int = 200) -> None:
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(payload))

    def json_body(self):
        try:
            return json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            return None


class HarnessesHandler(_BaseHandler):
    def get(self) -> None:
        self.write_json(
            {
                "harnesses": [
                    {"id": s.id, "display_name": s.display_name}
                    for s in self.registry.list()
                ]
            }
        )


class BindHandler(_BaseHandler):
    async def post(self, chat_id: str) -> None:
        body = self.json_body()
        if body is None:
            return self.write_json({"error": "invalid JSON"}, 400)
        harness_id = body.get("harness_id")
        if not harness_id:
            return self.write_json({"error": "missing harness_id"}, 400)
        try:
            binding = await self.manager.bind(chat_id, harness_id)
        except HarnessNotFoundError:
            return self.write_json({"error": f"unknown harness {harness_id!r}"}, 404)
        except AlreadyBoundError as exc:
            return self.write_json({"error": str(exc)}, 409)
        self.write_json({"harness_id": binding.harness_id})


class StateHandler(_BaseHandler):
    def get(self, chat_id: str) -> None:
        binding = self.manager.lookup(chat_id)
        if binding is None or not binding.is_bound:
            return self.write_json({"harness_id": None})
        self.write_json(
            {"harness_id": binding.harness_id, **binding.session.session_state.snapshot()}
        )


class _SetterHandler(_BaseHandler):
    async def _apply(self, chat_id: str, method_name: str, *args) -> None:
        binding = self.manager.lookup(chat_id)
        if binding is None or not binding.is_bound:
            return self.write_json({"error": "no binding for chat"}, 404)
        await getattr(binding.session, method_name)(*args)
        self.write_json({"ok": True})


class ModelHandler(_SetterHandler):
    async def post(self, chat_id: str) -> None:
        body = self.json_body() or {}
        await self._apply(chat_id, "set_model", body.get("model_id"))


class ModeHandler(_SetterHandler):
    async def post(self, chat_id: str) -> None:
        body = self.json_body() or {}
        await self._apply(chat_id, "set_mode", body.get("mode_id"))


class ConfigOptionHandler(_SetterHandler):
    async def post(self, chat_id: str) -> None:
        body = self.json_body() or {}
        await self._apply(chat_id, "set_config_option", body.get("config_id"), body.get("value"))


class StreamHandler(WebSocketHandler):
    """Per-chat duplex stream: client sends {"type":"prompt","text":...}; server
    streams the harness's session/update events back as JSON."""

    def initialize(self, registry, manager) -> None:
        self.manager = manager
        self._binding = None
        self._listener = None

    def check_origin(self, origin: str) -> bool:
        # Localhost PoC; tighten when hardening for multi-origin deployment.
        return True

    def open(self, chat_id: str) -> None:
        self._binding = self.manager.lookup(chat_id)
        if self._binding is None or not self._binding.is_bound:
            self.close(code=4404, reason="no binding for chat")
            return
        self._listener = self._forward
        self._binding.session.client.add_update_listener(self._listener)

    def _forward(self, session_id, update) -> None:
        try:
            self.write_message(json.dumps(update_to_json(update)))
        except Exception:
            pass

    async def on_message(self, raw) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if data.get("type") == "prompt" and self._binding is not None:
            await self._binding.session.prompt(data.get("text", ""))

    def on_close(self) -> None:
        if self._listener is not None and self._binding is not None and self._binding.is_bound:
            self._binding.session.client.remove_update_listener(self._listener)
