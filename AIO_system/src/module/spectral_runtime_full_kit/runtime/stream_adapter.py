from __future__ import annotations

from dataclasses import dataclass
import json
import os
import socket
from typing import Iterable
from urllib.parse import unquote


class StreamAdapterError(RuntimeError):
    pass


@dataclass(slots=True)
class StreamEndpoint:
    scheme: str
    target: str


def parse_stream_endpoint(endpoint: str) -> StreamEndpoint:
    text = str(endpoint).strip()
    if not text:
        raise ValueError("stream endpoint must not be empty.")
    if text.startswith("tcp://"):
        target = text[len("tcp://") :].strip()
        if ":" not in target:
            raise ValueError("tcp endpoint must follow tcp://host:port")
        host, port_text = target.rsplit(":", 1)
        if not host.strip():
            raise ValueError("tcp endpoint host is empty.")
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("tcp endpoint port must be an integer.") from exc
        if port <= 0 or port > 65535:
            raise ValueError("tcp endpoint port must be between 1 and 65535.")
        return StreamEndpoint(scheme="tcp", target=f"{host.strip()}:{port}")
    if text.startswith("ipc://"):
        target = unquote(text[len("ipc://") :].strip())
        if not target:
            raise ValueError("ipc endpoint must follow ipc://<address>")
        return StreamEndpoint(scheme="ipc", target=target)
    raise ValueError("unsupported stream endpoint scheme. Use tcp:// or ipc://")


class RuntimeEventStreamer:
    def __init__(self, *, endpoint: str, connect_timeout_s: float = 3.0) -> None:
        self._parsed = parse_stream_endpoint(endpoint)
        self._connect_timeout_s = max(0.1, float(connect_timeout_s))
        self._tcp_socket: socket.socket | None = None
        self._ipc_connection = None

    def __enter__(self) -> RuntimeEventStreamer:
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def connect(self) -> None:
        if self._parsed.scheme == "tcp":
            self._connect_tcp()
        elif self._parsed.scheme == "ipc":
            self._connect_ipc()
        else:
            raise StreamAdapterError(f"Unsupported scheme: {self._parsed.scheme}")

    def send(self, payload: dict[str, object]) -> None:
        line = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._parsed.scheme == "tcp":
            if self._tcp_socket is None:
                raise StreamAdapterError("TCP stream is not connected.")
            self._tcp_socket.sendall(line + b"\n")
            return

        if self._parsed.scheme == "ipc":
            if self._ipc_connection is None:
                raise StreamAdapterError("IPC stream is not connected.")
            if os.name == "nt":
                self._ipc_connection.send_bytes(line)
            else:
                self._ipc_connection.sendall(line + b"\n")
            return

        raise StreamAdapterError(f"Unsupported scheme: {self._parsed.scheme}")

    def close(self) -> None:
        if self._tcp_socket is not None:
            try:
                self._tcp_socket.close()
            finally:
                self._tcp_socket = None
        if self._ipc_connection is not None:
            try:
                self._ipc_connection.close()
            finally:
                self._ipc_connection = None

    def _connect_tcp(self) -> None:
        host, port_text = self._parsed.target.rsplit(":", 1)
        port = int(port_text)
        try:
            sock = socket.create_connection((host, port), timeout=self._connect_timeout_s)
            sock.settimeout(self._connect_timeout_s)
            self._tcp_socket = sock
        except OSError as exc:
            raise StreamAdapterError(f"Failed to connect TCP stream endpoint {self._parsed.target}: {exc}") from exc

    def _connect_ipc(self) -> None:
        target = self._parsed.target
        if os.name == "nt":
            try:
                from multiprocessing.connection import Client

                self._ipc_connection = Client(address=target, family="AF_PIPE")
            except Exception as exc:  # noqa: BLE001
                raise StreamAdapterError(f"Failed to connect IPC pipe endpoint {target}: {exc}") from exc
            return 

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self._connect_timeout_s)
            sock.connect(target)
            self._ipc_connection = sock
        except OSError as exc:
            raise StreamAdapterError(f"Failed to connect IPC unix endpoint {target}: {exc}") from exc


def stream_json_messages(*, endpoint: str, messages: Iterable[dict[str, object]], connect_timeout_s: float = 3.0) -> int:
    sent = 0
    with RuntimeEventStreamer(endpoint=endpoint, connect_timeout_s=connect_timeout_s) as streamer:
        for payload in messages:
            streamer.send(payload)
            sent += 1
    return sent
