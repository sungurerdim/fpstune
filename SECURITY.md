# Security Policy

## Reporting a vulnerability

Report privately through GitHub's
[security advisory form](https://github.com/sungurerdim/fpstune/security/advisories/new).
Please do not open a public issue for a vulnerability.

Include what you did, what happened, and what you expected. A reproduction on a
clean Windows 11 install is the most useful thing you can send.

You will get an acknowledgement within 7 days. Once a fix is released the
advisory is published with credit, unless you ask otherwise.

## Supported versions

fpstune has no published release yet. Until the first tag, only `main` is
supported — report against the current commit. After the first release, the
latest release and `main` are supported; older tags are not patched.

## What fpstune does to your machine

This is the part that matters more than any CVE, because it is true by design.

**fpstune runs as Administrator and changes system state.** It has to: the
things it tunes — registry keys under `HKLM`, service start types, power
schemes, network adapter driver keywords, boot configuration — are not
writable otherwise. If you are not comfortable granting that, do not run it.

Concretely, fpstune:

- reads and writes registry values under `HKLM` and `HKCU`
- changes Windows service start types
- runs `powershell.exe`, `netsh`, `powercfg`, `bcdedit` and `dism` as
  Administrator
- changes network adapter advanced properties through the driver
- edits per-game configuration files in your user profile
- creates System Restore points before bulk operations

**What fpstune never does**, and what a build claiming otherwise is not ours:

- no telemetry, analytics, crash reporting, or any outbound call about you
- no account, no license check, no phone-home
- no kernel driver, no test-signing, no driver signature enforcement changes
- no Secure Boot, HVCI, or core isolation changes
- no hardware identifier changes
- no bundled third-party software

The only network requests fpstune makes are ones you trigger. As of this
commit they are, in full: downloading PresentMon, FurMark and NVIDIA Profile
Inspector from their own project pages when you use the feature that needs
them, asking the GitHub releases API which version of Profile Inspector is
current, and measuring your own connection (ping, path MTU). Nothing is sent
about you, your hardware, or what you changed.

## Threat model

The trust boundary is the machine's Administrator account. fpstune assumes the
person running it already has it.

| Concern | Position |
|---|---|
| **Local web UI** | The backend binds `127.0.0.1` only. It is not intended to be exposed to a network, and doing so hands Administrator-level system control to anyone who can reach the port. |
| **Command injection** | Every dynamic value reaching a shell is validated at the boundary. Network adapters are addressed by numeric `InterfaceIndex`, never by name, precisely so a crafted adapter name cannot reach a command line. |
| **Registry writes** | Pinned to the 64-bit view (`KEY_WOW64_64KEY`), so a 32-bit build cannot be silently redirected into `Wow6432Node` and report success against a key it never touched. |
| **Debug endpoints** | `/api/debug/*` and the interactive API docs are not mounted at all unless `FPSTUNE_DEBUG=1` is set, so they cannot be reached on a normal run. |
| **Supply chain** | Dependencies are pinned in `uv.lock` and `package-lock.json`. Dependabot alerts are treated as release blockers. |
| **Unsigned binaries** | Releases are not code-signed. SmartScreen will warn. Verify the published SHA256 and the build provenance attestation instead of trusting the warning's absence. |

## Out of scope

- Anything requiring physical access or an already-compromised Administrator
  account — fpstune runs with those rights by design and cannot defend against
  someone who already has them.
- Performance results not matching a benchmark you read somewhere. That is a
  correctness discussion, not a security one; open an issue.
