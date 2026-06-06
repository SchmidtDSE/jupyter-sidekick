"""REST + websocket handlers exposing the BindingManager over HTTP.

Thin translation only: parse the request, call the manager / session, serialize
the result. All real behaviour lives in the manager and session layers.

REST handlers are authenticated `jupyter_server` APIHandlers (token auth, proper
XSRF handling). The registry + manager are read from the server settings, where
the extension stored them. The websocket handler authenticates via the server's
token on the upgrade request.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from jupyter_server.base.handlers import APIHandler
from jupyter_server.extension.handler import ExtensionHandlerMixin
from tornado import web
from tornado.websocket import WebSocketHandler

from .binding import AlreadyBoundError
from .registry import HarnessNotFoundError, harness_listing
from .serialize import update_to_json


def resolve_cwd(
    requested: Optional[str],
    server_root: Optional[str],
) -> Optional[str]:
    """Pick the working directory to launch an agent subprocess in.

    Tries the client-requested cwd first, then the server root, expanding ``~``
    and ``$VARS`` in each. Returns the first that exists, or ``None`` to let the
    subprocess inherit the server's own working directory.

    Never returns a non-existent path: handing one to the spawn raises a
    ``FileNotFoundError`` whose ``filename`` is the *directory*, which is then
    easily misread as a missing *command* ("not installed on the server's
    PATH"). Resolving here keeps that error honest — a launch failure can then
    only mean the command itself is missing.
    """
    for candidate in (requested, server_root):
        if not candidate:
            continue
        path = os.path.expanduser(os.path.expandvars(candidate))
        if os.path.isdir(path):
            return path
    return None


class _BaseHandler(ExtensionHandlerMixin, APIHandler):
    @property
    def registry(self):
        return self.settings["acp_registry"]

    @property
    def manager(self):
        return self.settings["acp_manager"]

    def reply(self, payload: Any, status: int = 200) -> None:
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(payload))

    def json_body(self):
        try:
            return json.loads(self.request.body or b"{}")
        except json.JSONDecodeError:
            return None


class HarnessesHandler(_BaseHandler):
    @web.authenticated
    def get(self) -> None:
        self.reply({"harnesses": harness_listing(self.registry)})


class BindHandler(_BaseHandler):
    @web.authenticated
    async def post(self, chat_id: str) -> None:
        body = self.json_body()
        if body is None:
            return self.reply({"error": "invalid JSON"}, 400)
        harness_id = body.get("harness_id")
        if not harness_id:
            return self.reply({"error": "missing harness_id"}, 400)
        # Run the harness in the user's workspace so it sees their files/notebooks.
        # Default to the server root; allow the client to override (e.g. the
        # directory of the active notebook). resolve_cwd expands ~/$VARS and
        # falls back if the directory is missing, so a stale or unexpanded path
        # can't masquerade as a "command not installed" launch failure.
        cwd = resolve_cwd(body.get("cwd"), self.settings.get("server_root_dir"))
        try:
            binding = await self._resolve_and_bind(chat_id, harness_id, cwd)
        except HarnessNotFoundError:
            return self.reply({"error": f"unknown harness {harness_id!r}"}, 404)
        except AlreadyBoundError as exc:
            return self.reply({"error": str(exc)}, 409)
        except FileNotFoundError as exc:
            cmd = getattr(exc, "filename", None) or exc
            return self.reply(
                {"error": f"could not launch {harness_id!r}: {cmd!r} is not installed on the server's PATH"},
                502,
            )
        except Exception as exc:  # launch / download failure — surface, don't 500
            return self.reply({"error": f"could not launch {harness_id!r}: {exc}"}, 502)
        self.reply({"harness_id": binding.harness_id})

    async def _resolve_and_bind(self, chat_id, harness_id, cwd):
        try:
            return await self.manager.bind(chat_id, harness_id, cwd=cwd)
        except HarnessNotFoundError:
            # Not a built-in harness — try the shared ACP registry (the server
            # derives the npx/uvx/binary launch command; the client never
            # supplies an arbitrary command).
            remote = self.settings.get("acp_remote_registry")
            spec = await asyncio.to_thread(remote.spec_for, harness_id) if remote else None
            if spec is None:
                raise  # genuinely unknown → 404
            return await self.manager.bind_spec(chat_id, spec, cwd=cwd)


class RegistryHandler(_BaseHandler):
    @web.authenticated
    async def get(self) -> None:
        remote = self.settings.get("acp_remote_registry")
        # The first call fetches the registry over the network; offload it so we
        # don't block the event loop.
        agents = await asyncio.to_thread(remote.listing) if remote else []
        self.reply({"agents": agents})


class StateHandler(_BaseHandler):
    @web.authenticated
    def get(self, chat_id: str) -> None:
        binding = self.manager.lookup(chat_id)
        if binding is None or not binding.is_bound:
            return self.reply({"harness_id": None})
        self.reply(
            {"harness_id": binding.harness_id, **binding.session.session_state.snapshot()}
        )


class _SetterHandler(_BaseHandler):
    async def _apply(self, chat_id: str, method_name: str, *args) -> None:
        binding = self.manager.lookup(chat_id)
        if binding is None or not binding.is_bound:
            return self.reply({"error": "no binding for chat"}, 404)
        await getattr(binding.session, method_name)(*args)
        self.reply({"ok": True})


class ModelHandler(_SetterHandler):
    @web.authenticated
    async def post(self, chat_id: str) -> None:
        body = self.json_body() or {}
        await self._apply(chat_id, "set_model", body.get("model_id"))


class ModeHandler(_SetterHandler):
    @web.authenticated
    async def post(self, chat_id: str) -> None:
        body = self.json_body() or {}
        await self._apply(chat_id, "set_mode", body.get("mode_id"))


class ConfigOptionHandler(_SetterHandler):
    @web.authenticated
    async def post(self, chat_id: str) -> None:
        body = self.json_body() or {}
        await self._apply(chat_id, "set_config_option", body.get("config_id"), body.get("value"))


class CloseHandler(_BaseHandler):
    """Tear down a chat's binding (and its harness subprocess).

    Called by the client on an intentional "new chat" reset or when a chat
    panel is disposed. Idempotent: closing an unknown/already-closed chat is a
    no-op success, so a double-send or a dispose-after-reset never errors. The
    binding lifetime is deliberately *not* tied to the websocket, so a transient
    stream disconnect doesn't kill the agent."""

    @web.authenticated
    async def post(self, chat_id: str) -> None:
        await self.manager.close(chat_id)
        self.reply({"ok": True})


class StreamHandler(WebSocketHandler):
    """Per-chat duplex stream: client sends {"type":"prompt","text":...}; server
    streams the harness's session/update events back as JSON."""

    @property
    def manager(self):
        return self.settings["acp_manager"]

    def check_origin(self, origin: str) -> bool:
        # Localhost PoC; tighten when hardening for multi-origin deployment.
        return True

    def open(self, chat_id: str) -> None:
        self._binding = self.manager.lookup(chat_id)
        self._listener = None
        if self._binding is None or not self._binding.is_bound:
            self.close(code=4404, reason="no binding for chat")
            return
        client = self._binding.session.client
        self._listener = self._forward
        client.add_update_listener(self._listener)
        client.set_permission_handler(self._send_permission)

    def _forward(self, session_id, update) -> None:
        self._send({**update_to_json(update)})

    def _send_permission(self, request_id, payload) -> None:
        self._send({"type": "permission_request", "request_id": request_id, **payload})

    def _send(self, message: dict) -> None:
        try:
            self.write_message(json.dumps(message))
        except Exception:
            pass

    async def on_message(self, raw) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if getattr(self, "_binding", None) is None:
            return
        kind = data.get("type")
        if kind == "prompt":
            # Run the turn as a task so this handler stays free to receive the
            # user's permission response while the turn is mid-flight.
            asyncio.create_task(self._run_prompt(data.get("text", "")))
        elif kind == "permission_response":
            self._binding.session.client.resolve_permission(
                data.get("request_id"), data.get("option_id")
            )

    async def _run_prompt(self, text: str) -> None:
        try:
            await self._binding.session.prompt(text)
        finally:
            self._send({"type": "turn_end"})

    def on_close(self) -> None:
        binding = getattr(self, "_binding", None)
        if binding is not None and binding.is_bound:
            client = binding.session.client
            if self._listener is not None:
                client.remove_update_listener(self._listener)
            client.clear_permission_handler()
