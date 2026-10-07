"""Is something on this machine hurting the games it runs?

`benchmark/` answers *how fast is it, and did a setting change that*: instruments
that produce comparable samples. This package answers a different question over
the same instruments: *is any part of the machine in trouble right now*, and says
so as a short list of findings a person can act on. A healthy machine yields an
empty list; a measurement that could not be taken is named beside the list, never
folded into it, so a missing sensor cannot read as a healthy one (C11 rule 3).

It sits beside `benchmark/` rather than inside it because a finding is a verdict
over a reading and a limit, not a sample for a before/after comparison, and
because the import direction is one-way: `health` reads `benchmark`, never the
other way round.
"""
