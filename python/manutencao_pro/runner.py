from __future__ import annotations

import os
import re
import signal
import sys
from collections.abc import Callable
from pathlib import Path

from gi.repository import Gio, GLib

from manutencao_pro.constants import APT_STEP_IDS
from manutencao_pro.paths import WRAPPER

_DISPLAY = re.compile(r"^:[0-9]{1,4}(\.[0-9]{1,2})?$")
_WAYLAND = re.compile(r"^wayland-[0-9]{1,4}$")
ExitCallback = Callable[[int, int | None], None]
LineCallback = Callable[[str], None]


class MaintenanceRunner:
    def __init__(self) -> None:
        self.on_line: LineCallback = lambda _line: None
        self.on_exit: ExitCallback = lambda _code, _sig: None
        self._process: Gio.Subprocess | None = None
        self._pipe: Gio.InputStream | None = None
        self._buffer = bytearray()
        self._cancellable = Gio.Cancellable()
        self._exit_code: int | None = None
        self._term_sig: int | None = None
        self._eof = False
        self._finished = False
        self._demo = False
        self._current_step = "apt-update"
        self._cancel_fd: int | None = None
        self._fifo: Path | None = None
        self._generation = 0

    def is_running(self) -> bool:
        return self._process is not None and not self._finished

    def can_cancel(self) -> bool:
        if not self.is_running():
            return False
        return self._current_step not in APT_STEP_IDS

    def set_current_step(self, step_id: str) -> None:
        self._current_step = step_id

    def start_demo(self, scenario: str) -> None:
        self._demo = True
        self._current_step = "apt-update"
        self._spawn([sys.executable, "-m", "manutencao_pro", "--demo-stream", scenario])

    def start_real(self) -> None:
        if not WRAPPER.is_file():
            raise FileNotFoundError(str(WRAPPER))
        self._demo = False
        self._current_step = "apt-update"
        self._spawn(["pkexec", str(WRAPPER), *self._privilege_args()])

    def cancel(self) -> None:
        if not self.can_cancel() or self._process is None:
            return
        if self._demo:
            self._process.send_signal(signal.SIGTERM)
            return
        if self._cancel_fd is None:
            return
        try:
            os.write(self._cancel_fd, b"\n")
        except OSError:
            return

    def _privilege_args(self) -> list[str]:
        fifo = self._prepare_fifo()
        args = ["--cancel-fifo", fifo]
        display = os.environ.get("DISPLAY", "")
        if _DISPLAY.match(display):
            args.extend(["--display", display])
        xauthority = _xauthority_path()
        if xauthority:
            args.extend(["--xauthority", xauthority])
        wayland = os.environ.get("WAYLAND_DISPLAY", "")
        if _WAYLAND.match(wayland):
            args.extend(["--wayland-display", wayland])
        return args

    def _spawn(self, argv: list[str]) -> None:
        self._generation += 1
        generation = self._generation
        self._finished = False
        self._eof = False
        self._exit_code = None
        self._term_sig = None
        self._cancellable.cancel()
        self._cancellable = Gio.Cancellable()
        self._process = Gio.Subprocess.new(
            argv,
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE,
        )
        pipe = self._process.get_stdout_pipe()
        if pipe is None:
            raise RuntimeError("stdout ausente")
        self._pipe = pipe
        self._buffer = bytearray()
        self._wait_cb = self._wait_callback(generation)
        self._process.wait_async(self._cancellable, self._wait_cb, None)
        self._read_chunk(generation)

    def _read_chunk(self, generation: int) -> None:
        if self._pipe is None or generation != self._generation:
            return
        self._read_cb = self._chunk_callback(generation)
        self._pipe.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, self._cancellable, self._read_cb, None)

    def _chunk_callback(self, generation: int) -> Callable[..., None]:
        def callback(stream: Gio.InputStream, result: Gio.AsyncResult, *_rest: object) -> None:
            if generation != self._generation:
                return
            self._handle_chunk(stream, result, generation)

        return callback

    def _wait_callback(self, generation: int) -> Callable[..., None]:
        def callback(process: Gio.Subprocess, result: Gio.AsyncResult, *_rest: object) -> None:
            if generation != self._generation:
                return
            self._handle_wait(process, result)

        return callback

    def _handle_chunk(self, stream: Gio.InputStream, result: Gio.AsyncResult, generation: int) -> None:
        try:
            chunk = stream.read_bytes_finish(result)
        except GLib.Error:
            self._eof = True
            self._maybe_finish()
            return
        if chunk.get_size() == 0:
            self._emit_pending()
            self._eof = True
            self._maybe_finish()
            return
        data = chunk.get_data()
        if data:
            self._buffer.extend(data)
        self._emit_complete_lines()
        self._read_chunk(generation)

    def _emit_complete_lines(self) -> None:
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                return
            raw = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            self.on_line(raw.decode("utf-8", errors="replace"))

    def _emit_pending(self) -> None:
        if not self._buffer:
            return
        raw = bytes(self._buffer)
        self._buffer.clear()
        self.on_line(raw.decode("utf-8", errors="replace"))

    def _handle_wait(self, process: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            process.wait_finish(result)
        except GLib.Error:
            pass
        if process.get_if_exited():
            self._exit_code = int(process.get_exit_status())
            self._term_sig = None
        elif process.get_if_signaled():
            self._term_sig = int(process.get_term_sig())
            self._exit_code = 128 + self._term_sig
        else:
            self._exit_code = 1
        self._maybe_finish()

    def _maybe_finish(self) -> None:
        if self._finished or not self._eof or self._exit_code is None:
            return
        self._finished = True
        self._cleanup_fifo()
        code = self._exit_code
        term_sig = self._term_sig
        self._process = None
        self._pipe = None
        self.on_exit(code, term_sig)

    def _prepare_fifo(self) -> str:
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        directory = Path(runtime) / "manutencao-pro"
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        fifo = directory / "cancel"
        step = directory / "step"
        _unlink_special(fifo)
        _unlink_special(step)
        os.mkfifo(fifo, 0o600)
        os.chmod(fifo, 0o600)
        self._fifo = fifo
        self._cancel_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        return str(fifo)

    def _cleanup_fifo(self) -> None:
        if self._cancel_fd is not None:
            os.close(self._cancel_fd)
            self._cancel_fd = None
        if self._fifo is not None:
            try:
                self._fifo.unlink(missing_ok=True)
            except OSError:
                pass
            self._fifo = None


def _xauthority_path() -> str:
    configured = os.environ.get("XAUTHORITY", "")
    if configured:
        return configured
    default = Path.home() / ".Xauthority"
    if default.is_file():
        return str(default)
    return ""


def _unlink_special(path: Path) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()
