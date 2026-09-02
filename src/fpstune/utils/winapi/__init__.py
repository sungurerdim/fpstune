"""Native Windows calls through ``ctypes``, never through PowerShell ``Add-Type``.

Eight shipped code paths used to compile a C# class at run time inside a
PowerShell command — ``Add-Type`` plus ``[DllImport]`` plus unmanaged memory —
to reach ``kernel32``, ``user32``, ``ntdll`` and ``wlanapi``. On 2026-09-02
Windows Defender on the developer machine flagged exactly that pattern as trojan
behaviour and killed the process tree: it is the shape of a malware loader, and
AMSI heuristics score it as one whatever the code inside does. A machine with a
stricter policy or a third-party antivirus would have lost CPU topology, monitor
detection, Wi-Fi facts, the refresh-rate action and the standby-list purge at
once, and every call also paid a C# compile.

``ctypes`` is not AMSI-instrumented, needs no compiler, and is what the rest of
the tree already uses (``hardware_context.has_battery``, ``core/nvapi.py``,
``benchmark/dpc.py``). Each module here wraps one API family, keeps the buffer
walking in Python where a unit test can hand it a fake buffer, and exposes the
same facts the C# classes produced. ``tests/test_quality_gates.py`` holds the
line: no ``Add-Type`` in shipped code.
"""
