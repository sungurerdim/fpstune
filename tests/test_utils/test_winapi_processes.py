"""utils/winapi/processes.py: the socket-owner table, parsed and read for real.

The parser runs on hand-built buffers (a real table never holds the odd rows a
test needs). Everything that asks the kernel runs against this test's own
process and sockets, and against one child the test itself spawns and ends.
"""

from __future__ import annotations

import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fpstune.utils import instance_reclaim
from fpstune.utils.winapi import processes

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows socket table")


def _row(state: int, laddr: str, lport: int, raddr: str, rport: int, pid: int) -> bytes:
    """One MIB_TCPROW_OWNER_PID the way iphlpapi writes it (ports big-endian in the low word)."""

    def addr(text: str) -> int:
        return struct.unpack("<I", socket.inet_aton(text))[0]

    def port(value: int) -> int:
        return struct.unpack("<I", struct.pack(">H", value) + b"\x00\x00")[0]

    return struct.pack("<6I", state, addr(laddr), port(lport), addr(raddr), port(rport), pid)


def _table(*rows: bytes) -> bytes:
    return struct.pack("<I", len(rows)) + b"".join(rows)


class TestParseTcpOwnerTable:
    def test_a_bound_socket_row_reads_back_field_for_field(self) -> None:
        table = _table(_row(1, "127.0.0.1", 59471, "0.0.0.0", 0, 4242))

        [row] = processes.parse_tcp_owner_table(table)

        assert row == processes.TcpRow(1, "127.0.0.1", 59471, "0.0.0.0", 0, 4242)

    def test_ports_above_32767_and_with_unequal_bytes_survive_the_byte_swap(self) -> None:
        table = _table(
            _row(2, "0.0.0.0", 65280, "0.0.0.0", 0, 7),
            _row(5, "10.0.0.2", 258, "93.184.216.34", 443, 8),
        )

        rows = processes.parse_tcp_owner_table(table)

        assert [(r.local_port, r.remote_address, r.remote_port) for r in rows] == [
            (65280, "0.0.0.0", 0),
            (258, "93.184.216.34", 443),
        ]

    def test_an_empty_table_is_no_rows(self) -> None:
        assert processes.parse_tcp_owner_table(_table()) == []

    @pytest.mark.parametrize("buffer", [b"", b"\x01\x00", struct.pack("<I", 3) + b"\x00" * 24])
    def test_a_buffer_shorter_than_its_header_claims_is_an_error_not_an_empty_answer(
        self, buffer: bytes
    ) -> None:
        with pytest.raises(ValueError):
            processes.parse_tcp_owner_table(buffer)


class TestDecodeUnicodeString:
    def test_the_characters_after_the_header_are_the_text(self) -> None:
        text = '"C:\\Program Files\\fpstune\\fpstune.exe" serve --port 8000'
        header = struct.pack("<HHxxxxQ", len(text) * 2, len(text) * 2 + 2, 0)

        assert processes.decode_unicode_string(header + text.encode("utf-16-le"), 16) == text

    def test_a_length_longer_than_the_buffer_is_an_error(self) -> None:
        header = struct.pack("<HHxxxxQ", 200, 202, 0)

        with pytest.raises(ValueError):
            processes.decode_unicode_string(header + b"a\x00", 16)


class TestSplitCommandLine:
    def test_it_splits_the_way_windows_does(self) -> None:
        line = r'"C:\Program Files\Python312\python.exe" -m fpstune.api.serving --port 8000'

        assert processes.split_command_line(line) == [
            r"C:\Program Files\Python312\python.exe",
            "-m",
            "fpstune.api.serving",
            "--port",
            "8000",
        ]

    def test_an_empty_line_is_no_arguments(self) -> None:
        assert processes.split_command_line("   ") == []


class TestAskingTheKernel:
    def test_a_listening_socket_is_found_with_this_pid(self) -> None:
        """What the lock socket now is: bound *and* listening, so the owner table names it."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]

            assert processes.socket_owner_pids(port) == [os.getpid()]

    def test_a_socket_that_is_only_bound_is_not_in_the_table(self) -> None:
        """Measured on Windows 11: TCP_TABLE_OWNER_PID_ALL does not list a bound socket
        that never listened, though a second bind to it fails. Every release before
        the lock started to listen holds the lock exactly so, which is why the
        takeover cannot rely on this table alone (utils/instance_reclaim.py). If this
        test ever goes red, Windows lists them and the server-scan fallback is
        unnecessary."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            with (
                socket.socket(socket.AF_INET, socket.SOCK_STREAM) as second,
                pytest.raises(OSError),
            ):
                second.bind(("127.0.0.1", port))

            assert processes.socket_owner_pids(port) == []

    def test_a_free_port_has_no_owner(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        assert processes.socket_owner_pids(port) == []

    def test_an_outgoing_connection_whose_local_port_matches_is_not_a_holder(self) -> None:
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            with socket.create_connection(server.getsockname()) as client:
                client_port = client.getsockname()[1]

                assert processes.socket_owner_pids(client_port) == []

    def test_a_childs_image_and_exact_arguments_are_readable(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)", "marker arg"]
        )
        try:
            image = processes.image_path(child.pid)
            line = processes.command_line(child.pid)

            assert image is not None and Path(image).name.casefold().startswith("python")
            assert line is not None
            assert processes.split_command_line(line)[-3:] == [
                "-c",
                "import time; time.sleep(30)",
                "marker arg",
            ]
        finally:
            child.kill()
            child.wait()

    def test_a_pid_that_does_not_exist_reads_as_none(self) -> None:
        assert processes.image_path(0x7FFFFFF0) is None
        assert processes.command_line(0x7FFFFFF0) is None
        assert processes.creation_time(0x7FFFFFF0) is None
        assert processes.terminate(0x7FFFFFF0) == "already_gone"

    def test_the_snapshot_links_a_child_to_the_process_that_started_it(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            entries = {e.pid: e for e in processes.list_processes()}

            assert entries[child.pid].parent_pid == os.getpid()
            assert entries[child.pid].exe_name.casefold().startswith("python")
        finally:
            child.kill()
            child.wait()

    def test_an_exited_process_someone_still_holds_a_handle_to_reads_as_exited(self) -> None:
        """Popen keeps the child's handle, so it stays in the process list after it
        ends; the takeover must tell that from a live process that merely refuses to
        be opened."""
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            assert processes.has_exited(child.pid) is False
            assert processes.has_exited(os.getpid()) is False
            child.kill()
            deadline = time.monotonic() + 5
            while not processes.has_exited(child.pid) and time.monotonic() < deadline:
                time.sleep(0.05)

            assert processes.has_exited(child.pid) is True
        finally:
            child.kill()
            child.wait()

    def test_a_child_starts_after_its_parent(self) -> None:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            parent_started = processes.creation_time(os.getpid())
            child_started = processes.creation_time(child.pid)
            assert parent_started is not None and child_started is not None
            assert parent_started <= child_started
        finally:
            child.kill()
            child.wait()


class TestEndToEndOnAChildTheTestSpawned:
    """The whole fallback against one real process: a script named like fpstune's
    own, holding a listening socket and answering nothing.

    The holder listens on purpose: a merely bound one is not in the owner table, and
    the server-scan path that serves it would end every fpstune server on the
    machine running these tests, the developer's own included. That path is tested
    on a pretend machine only."""

    def _holder(self, tmp_path: Path) -> tuple[subprocess.Popen[str], int]:
        script = tmp_path / "fpstune-script.py"
        script.write_text(
            "import socket, sys, time\n"
            "s = socket.socket()\n"
            "s.bind(('127.0.0.1', 0))\n"
            "s.listen(1)\n"
            "print(s.getsockname()[1], flush=True)\n"
            "time.sleep(120)\n",
            encoding="utf-8",
        )
        child = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
        assert child.stdout is not None
        return child, int(child.stdout.readline())

    def test_a_hung_fpstune_shaped_holder_is_found_verified_and_ended(self, tmp_path: Path) -> None:
        child, port = self._holder(tmp_path)
        try:
            result = instance_reclaim.reclaim_lock_holder(port)

            assert result.status == "ended", result.message
            assert any(done.outcome == "ended" for done in result.ended)
            assert child.wait(timeout=10) is not None
            assert processes.socket_owner_pids(port) == []
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_a_holder_that_is_python_running_something_else_is_left_alone(
        self, tmp_path: Path
    ) -> None:
        script = tmp_path / "other_tool.py"
        script.write_text(
            "import socket, time\n"
            "s = socket.socket()\n"
            "s.bind(('127.0.0.1', 0))\n"
            "s.listen(1)\n"
            "print(s.getsockname()[1], flush=True)\n"
            "time.sleep(120)\n",
            encoding="utf-8",
        )
        child = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE, text=True)
        assert child.stdout is not None
        try:
            port = int(child.stdout.readline())

            result = instance_reclaim.reclaim_lock_holder(port)

            assert result.status == "refused"
            assert result.holder_pid is not None
            assert str(result.holder_pid) in result.message
            assert "python" in result.holder_image.casefold()
            assert child.poll() is None, "a stranger must still be running"
        finally:
            child.kill()
            child.wait()
