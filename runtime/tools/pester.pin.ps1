# Single source of truth for the pinned Pester version (dev/CI only).
# Dot-sourced by restore.ps1 and test.ps1. Nothing here ships to user machines.
#
# Trust Verification: version and hash taken from the live PowerShell Gallery
# OData feed (FindPackagesById, id 'Pester') on 2026-10-27: 5.9.1 is the newest
# stable 5.x (IsPrerelease=false, published 2026-08-11).
$PesterVersion = '5.9.1'
# Base64 SHA-512 of the .nupkg as reported by the gallery for that version.
$PesterPackageHash = 'Ro5dZIKb89GI4ljjInQc3m6sI74uvph1y4QAqBPZ1Jhg0l1wBv8rT0izkGKbOw2Brzn8rNV2NKpDbyvoi7ARqg=='
