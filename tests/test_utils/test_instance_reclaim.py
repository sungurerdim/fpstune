"""utils/instance_reclaim.py: which processes a takeover may end, decided on a pretend machine.

No process exists here, so none can be ended. The pretend machine answers the
same questions the real one does (who owns the port, parent links, image paths,
command lines, start times) and records what it was told to terminate.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import pytest

from fpstune.utils import instance_reclaim
from fpstune.utils.winapi import processes

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="CommandLineToArgvW")

PORT = 59471
PYTHON = r"C:\Python312\python.exe"
FPSTUNE_EXE = r"C:\Program Files\fpstune\fpstune.exe"


@dataclass
class Proc:
    pid: int
    parent: int
    image: str | None
    cmd: str | None
    created: int

    @property
    def exe_name(self) -> str:
        return (self.image or "unknown.exe").rsplit("\\", 1)[-1]


class Machine:
    """A pretend process table that implements ``instance_reclaim.System``."""

    def __init__(self, own: int = 500) -> None:
        self.own = own
        self.procs: dict[int, Proc] = {}
        self.owners: list[int] = []
        self.terminated: list[int] = []
        self.also_exits: dict[int, list[int]] = {}
        self.terminate_outcome: dict[int, str] = {}
        self.owner_lookup_error: OSError | None = None

    def add(
        self,
        pid: int,
        parent: int,
        image: str | None,
        cmd: str | None = None,
        *,
        created: int | None = None,
    ) -> Machine:
        self.procs[pid] = Proc(pid, parent, image, cmd, pid if created is None else created)
        return self

    def python(self, pid: int, parent: int, args: str, **kwargs: int) -> Machine:
        return self.add(pid, parent, PYTHON, f'"{PYTHON}" {args}', **kwargs)

    def fpstune_exe(self, pid: int, parent: int, args: str = "", **kwargs: int) -> Machine:
        return self.add(pid, parent, FPSTUNE_EXE, f'"{FPSTUNE_EXE}" {args}'.strip(), **kwargs)

    # --- instance_reclaim.System -------------------------------------------------
    def own_pid(self) -> int:
        return self.own

    def lock_owner_pids(self, port: int) -> list[int]:
        assert port == PORT
        if self.owner_lookup_error is not None:
            raise self.owner_lookup_error
        return list(self.owners)

    def list_processes(self) -> list[processes.ProcessEntry]:
        return [processes.ProcessEntry(p.pid, p.parent, p.exe_name) for p in self.procs.values()]

    def image_path(self, pid: int) -> str | None:
        proc = self.procs.get(pid)
        return proc.image if proc else None

    def command_line(self, pid: int) -> str | None:
        proc = self.procs.get(pid)
        return proc.cmd if proc else None

    def creation_time(self, pid: int) -> int | None:
        proc = self.procs.get(pid)
        return proc.created if proc else None

    def has_exited(self, _pid: int) -> bool:
        return False

    def terminate(self, pid: int) -> str:
        if pid not in self.procs:
            return "already_gone"
        outcome = self.terminate_outcome.get(pid, "ended")
        if outcome == "ended":
            self.terminated.append(pid)
            for gone in [pid, *self.also_exits.get(pid, [])]:
                self.procs.pop(gone, None)
        return outcome


def _hung_pair(machine: Machine) -> Machine:
    """The owner's observed shape: a launcher (100) and its child (200), child owns the port."""
    machine.python(100, 1, "-m fpstune serve")
    machine.python(200, 100, "-m fpstune serve")
    machine.owners = [200]
    return machine


def _reclaim(machine: Machine) -> instance_reclaim.Reclaimed:
    return instance_reclaim.reclaim_lock_holder(PORT, system=machine)


class TestWhatCountsAsFpstune:
    @pytest.mark.parametrize(
        ("image", "cmd"),
        [
            (FPSTUNE_EXE, f'"{FPSTUNE_EXE}"'),
            (r"C:\Users\someone\proj\.venv\Scripts\fpstune.exe", "fpstune.exe serve --no-browser"),
            (r"D:\Apps\FPSTUNE.EXE", "FPSTUNE.EXE serve"),
            (PYTHON, f'"{PYTHON}" -m fpstune serve'),
            (PYTHON, f'"{PYTHON}" -m fpstune.api.serving --port 8000'),
            (PYTHON, f'"{PYTHON}" -X utf8 -u -m fpstune'),
            (PYTHON, f'"{PYTHON}" "C:\\proj\\.venv\\Scripts\\fpstune.exe" serve'),
            (PYTHON, f'"{PYTHON}" C:\\proj\\.venv\\Scripts\\fpstune-script.py serve'),
            (PYTHON, f'"{PYTHON}" C:\\proj\\src\\fpstune\\cli.py serve'),
            (r"C:\Python312\pythonw.exe", r'"C:\Python312\pythonw.exe" -m fpstune'),
            (r"C:\Python313\python3.13.exe", r'"C:\Python313\python3.13.exe" -m fpstune'),
        ],
    )
    def test_the_shapes_fpstune_runs_in_are_accepted(self, image: str, cmd: str) -> None:
        argv = processes.split_command_line(cmd)

        verdict = instance_reclaim.judge(7, image, argv)

        assert verdict.is_fpstune, verdict.reason

    @pytest.mark.parametrize(
        ("image", "cmd", "why"),
        [
            (PYTHON, f'"{PYTHON}" -m pytest tests', "something other than fpstune"),
            (PYTHON, f'"{PYTHON}" -m pip install fpstune', "something other than fpstune"),
            (PYTHON, f'"{PYTHON}" other_tool.py fpstune serve', "something other than fpstune"),
            (PYTHON, f'"{PYTHON}" -c "import fpstune; fpstune.cli.run()"', "something other"),
            (PYTHON, f'"{PYTHON}" -m fpstune_helper', "something other than fpstune"),
            (PYTHON, f'"{PYTHON}" -m http.server 59471', "something other than fpstune"),
            (PYTHON, f'"{PYTHON}" C:\\tools\\my-fpstune-notes.py', "something other than fpstune"),
            (PYTHON, None, "command line could not be read"),
            (r"C:\Windows\System32\notepad.exe", "notepad.exe", "not fpstune"),
            (r"C:\Program Files\nodejs\node.exe", "node.exe server.js", "not fpstune"),
            (r"C:\Tools\fpstune-helper.exe", "fpstune-helper.exe", "not fpstune"),
            (None, None, "could not be read"),
        ],
    )
    def test_everything_else_is_a_stranger(
        self, image: str | None, cmd: str | None, why: str
    ) -> None:
        argv = None if cmd is None else processes.split_command_line(cmd)

        verdict = instance_reclaim.judge(7, image, argv)

        assert not verdict.is_fpstune
        assert why in verdict.reason

    @pytest.mark.parametrize(
        ("cmd", "serves"),
        [
            (f'"{FPSTUNE_EXE}"', True),
            (f'"{FPSTUNE_EXE}" serve --port 9000', True),
            (f'"{FPSTUNE_EXE}" -v serve', True),
            (f'"{FPSTUNE_EXE}" status', False),
            (f'"{FPSTUNE_EXE}" benchmark --duration 30', False),
            (f'"{FPSTUNE_EXE}" --help', False),
            (f'"{PYTHON}" -m fpstune.api.serving --port 8000', True),
            (f'"{PYTHON}" -m fpstune gpu', False),
        ],
    )
    def test_only_a_server_shaped_fpstune_counts_as_a_previous_instance(
        self, cmd: str, serves: bool
    ) -> None:
        argv = processes.split_command_line(cmd)
        image = PYTHON if cmd.startswith(f'"{PYTHON}"') else FPSTUNE_EXE

        verdict = instance_reclaim.judge(7, image, argv)

        assert verdict.is_fpstune and verdict.serves is serves


class TestTheOwnerTheTableNames:
    def test_a_hung_launcher_and_child_are_both_ended_child_first_and_each_is_reported(
        self,
    ) -> None:
        machine = _hung_pair(Machine())

        result = _reclaim(machine)

        assert result.status == "ended", result.message
        assert machine.terminated == [200, 100]
        assert [(e.pid, e.outcome) for e in result.ended] == [(200, "ended"), (100, "ended")]
        assert "owns the lock port" in result.ended[0].why
        assert "supervising PID 200" in result.ended[1].why
        assert result.holder_pid == 200 and result.holder_image == PYTHON

    def test_the_frozen_bootloader_over_its_runtime_goes_with_it(self) -> None:
        machine = Machine()
        machine.fpstune_exe(100, 1).fpstune_exe(200, 100)
        machine.owners = [200]

        result = _reclaim(machine)

        assert result.status == "ended"
        assert machine.terminated == [200, 100]

    def test_a_stranger_holding_the_port_is_refused_by_pid_and_image_and_never_touched(
        self,
    ) -> None:
        machine = Machine()
        machine.python(300, 1, "-m http.server 59471")
        machine.owners = [300]

        result = _reclaim(machine)

        assert result.status == "refused"
        assert "PID 300" in result.message and PYTHON in result.message
        assert result.holder_pid == 300 and result.holder_image == PYTHON
        assert machine.terminated == []

    def test_an_unrelated_exe_holding_the_port_is_refused(self) -> None:
        machine = Machine()
        machine.add(300, 1, r"C:\Games\Server\game.exe", "game.exe --serve")
        machine.owners = [300]

        result = _reclaim(machine)

        assert result.status == "refused" and "game.exe" in result.message
        assert machine.terminated == []

    def test_an_owner_whose_image_cannot_be_read_is_refused_not_guessed(self) -> None:
        machine = Machine()
        machine.add(300, 1, None)
        machine.owners = [300]

        result = _reclaim(machine)

        assert result.status == "refused" and "PID 300" in result.message
        assert machine.terminated == []

    def test_a_stranger_among_several_owners_stops_everything(self) -> None:
        machine = _hung_pair(Machine())
        machine.python(300, 1, "-m http.server 59471")
        machine.owners = [200, 300]

        result = _reclaim(machine)

        assert result.status == "refused"
        assert machine.terminated == []

    def test_a_parent_that_is_not_fpstune_is_left_running(self) -> None:
        machine = Machine()
        machine.add(50, 1, r"C:\Windows\explorer.exe", "explorer.exe")
        machine.python(200, 50, "-m fpstune serve")
        machine.owners = [200]

        result = _reclaim(machine)

        assert machine.terminated == [200]
        assert result.status == "ended"

    def test_a_child_that_is_not_fpstune_is_left_running(self) -> None:
        machine = _hung_pair(Machine())
        machine.add(900, 200, r"C:\Windows\System32\powershell.exe", "powershell.exe -NoProfile")

        _reclaim(machine)

        assert 900 not in machine.terminated and machine.terminated == [200, 100]

    def test_an_fpstune_child_of_the_owner_goes_before_it(self) -> None:
        machine = _hung_pair(Machine())
        machine.python(300, 200, "-m fpstune.api.serving --port 8000")

        result = _reclaim(machine)

        assert machine.terminated == [300, 200, 100]
        assert "child of PID 200" in result.ended[0].why

    def test_a_parent_that_also_supervises_another_fpstune_is_not_ended(self) -> None:
        machine = _hung_pair(Machine())
        machine.python(201, 100, "-m fpstune.api.serving --port 8001")

        _reclaim(machine)

        assert machine.terminated == [200]

    def test_this_process_and_its_ancestors_are_never_ended(self) -> None:
        """A start launched by an fpstune shim must not end the shim: here the old
        owner's parent *is* this start's own shim."""
        machine = Machine(own=500)
        machine.fpstune_exe(400, 1, "serve")
        machine.python(500, 400, "-m fpstune serve")
        machine.python(200, 400, "-m fpstune serve")
        machine.owners = [200]

        result = _reclaim(machine)

        assert machine.terminated == [200]
        assert result.status == "ended"

    def test_an_owner_that_is_this_start_or_its_shim_is_refused(self) -> None:
        machine = Machine(own=500)
        machine.fpstune_exe(400, 1, "serve")
        machine.python(500, 400, "-m fpstune serve")
        machine.owners = [400]

        result = _reclaim(machine)

        assert result.status == "refused" and "this process" in result.message
        assert machine.terminated == []

    def test_a_parent_pid_the_system_reused_for_a_newer_process_is_not_a_parent(self) -> None:
        machine = Machine()
        machine.python(100, 1, "-m fpstune serve", created=900)  # younger than the "child"
        machine.python(200, 100, "-m fpstune serve", created=200)
        machine.owners = [200]

        _reclaim(machine)

        assert machine.terminated == [200]

    def test_a_pid_that_stopped_being_fpstune_before_its_turn_is_not_ended(self) -> None:
        """The image is read again right before each end: a PID the system handed
        to something else between planning and ending is left alone."""
        machine = _hung_pair(Machine())

        class Swapping(Machine):
            def terminate(self, pid: int) -> str:
                outcome = super().terminate(pid)
                if pid == 200:  # the launcher's PID is reused by another program
                    self.procs[100].image = r"C:\Windows\System32\notepad.exe"
                return outcome

        swapping = Swapping()
        swapping.procs, swapping.owners = machine.procs, machine.owners

        result = _reclaim(swapping)

        assert swapping.terminated == [200]
        assert result.status == "failed" and "PID 100" in result.message

    def test_a_parent_that_exits_with_its_child_counts_as_gone_not_failed(self) -> None:
        machine = _hung_pair(Machine())
        machine.also_exits[200] = [100]

        result = _reclaim(machine)

        assert result.status == "ended"
        assert [(e.pid, e.outcome) for e in result.ended] == [(200, "ended"), (100, "already_gone")]

    def test_a_launcher_on_its_way_out_is_waited_for_then_counts_as_gone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Right after its child ends, the launcher is still listed but can no longer
        be opened; that is an exit in progress, not a failure."""
        monkeypatch.setattr(instance_reclaim, "_EXIT_POLL_SECONDS", 0.0)

        class Leaving(Machine):
            polls_left = 0

            def terminate(self, pid: int) -> str:
                outcome = super().terminate(pid)
                if pid == 200:
                    self.procs[100].image = None  # still listed, no longer openable
                    self.polls_left = 3
                return outcome

            def list_processes(self) -> list[processes.ProcessEntry]:
                listed = super().list_processes()
                if self.polls_left:
                    self.polls_left -= 1
                    if not self.polls_left:
                        self.procs.pop(100, None)
                return listed

        machine = _hung_pair(Leaving())

        result = _reclaim(machine)

        assert result.status == "ended"
        assert [(e.pid, e.outcome) for e in result.ended] == [(200, "ended"), (100, "already_gone")]

    def test_an_unopenable_process_that_never_leaves_is_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(instance_reclaim, "_EXIT_GRACE_SECONDS", 0.0)

        class Stuck(Machine):
            def terminate(self, pid: int) -> str:
                outcome = super().terminate(pid)
                if pid == 200:
                    self.procs[100].image = None  # listed, never openable: access denied, say
                return outcome

        result = _reclaim(_hung_pair(Stuck()))

        assert result.status == "failed" and "PID 100" in result.message

    def test_a_process_that_refuses_to_end_is_a_failure_naming_it(self) -> None:
        machine = _hung_pair(Machine())
        machine.terminate_outcome[200] = "failed"

        result = _reclaim(machine)

        assert result.status == "failed" and "PID 200" in result.message

    def test_a_machine_that_cannot_be_read_is_a_failure_with_the_reason(self) -> None:
        machine = Machine()
        machine.owner_lookup_error = OSError("table unavailable")

        result = _reclaim(machine)

        assert result.status == "failed" and "table unavailable" in result.message


class TestWhenTheTableNamesNoOwner:
    """A socket that is only bound is not in the table; the servers are the lead then."""

    def test_every_server_shaped_fpstune_tree_is_ended(self) -> None:
        machine = Machine()
        machine.python(100, 1, "-m fpstune serve").python(200, 100, "-m fpstune serve")
        machine.fpstune_exe(300, 1, "serve").fpstune_exe(310, 300, "serve")

        result = _reclaim(machine)

        assert result.status == "ended"
        assert sorted(machine.terminated) == [100, 200, 300, 310]
        assert all(
            "answered no stop request" in e.why or "child" in e.why or "parent" in e.why
            for e in result.ended
        )

    def test_a_cli_command_that_is_not_a_server_is_left_running(self) -> None:
        machine = Machine()
        machine.python(100, 1, "-m fpstune serve")
        machine.fpstune_exe(400, 1, "benchmark --duration 30")
        machine.fpstune_exe(410, 1, "status")

        _reclaim(machine)

        assert machine.terminated == [100]

    def test_python_running_something_else_and_unrelated_exes_are_left_running(self) -> None:
        machine = Machine()
        machine.python(100, 1, "-m fpstune serve")
        machine.python(600, 1, "-m http.server 8000")
        machine.add(610, 1, r"C:\Windows\System32\notepad.exe", "notepad.exe")

        _reclaim(machine)

        assert machine.terminated == [100]

    def test_this_start_and_its_shim_are_not_previous_instances(self) -> None:
        machine = Machine(own=500)
        machine.fpstune_exe(400, 1, "serve")
        machine.python(500, 400, "-m fpstune serve")

        result = _reclaim(machine)

        assert result.status == "no_holder"
        assert machine.terminated == []

    def test_nothing_serving_and_no_owner_is_reported_as_no_holder(self) -> None:
        machine = Machine()
        machine.python(600, 1, "-m http.server 8000")

        result = _reclaim(machine)

        assert result.status == "no_holder"
        assert "never listened" in result.message
        assert machine.terminated == []
