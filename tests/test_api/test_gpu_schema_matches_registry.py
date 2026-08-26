"""The GPU apply schemas must accept only what the GPU settings accept.

``GpuAmdApplyRequest`` typed ``anti_lag`` and ``shader_cache`` as
``Literal["off", "on"]`` and defaulted both to ``"on"``, while
``gpu-amd:anti_lag`` and ``gpu-amd:shader_cache`` declare
``choices=("enabled", "disabled")`` with ``apply_value_map={"enabled": 1,
"disabled": 0}``. ``_validate_apply_value`` refuses a value that is in neither,
so ``POST /api/gpu/amd/apply`` sent with its own defaults failed two of its
three settings on every AMD machine.

``threaded_opt`` was the quieter half of the same class: ``"on"`` is one of
``gpu-nvidia:threaded_opt``'s choices, so nothing was rejected, but the setting
declares ``"auto"`` for both default and recommendation — a caller omitting the
field silently got the value fpstune does not advise. ``low_latency`` defaulted
to ``"ultra"``, which ``ANTICHEAT_WARNINGS`` names as the risky value, and
``power_mode`` to ``"maximum"``, the value ``gpu-nvidia:power_mode`` exists to
undo.

Every check below reads the built registry rather than restating the choices, so
editing a setting's ``choices`` or ``recommended_value`` without the schema goes
red here instead of on a user's hardware.
"""

from __future__ import annotations

import inspect
from typing import Any, Literal, get_args

import pytest
from pydantic import BaseModel

from fpstune.api.routes.gpu import apply_gpu_settings
from fpstune.api.schemas import GpuAmdApplyRequest, GpuNvidiaApplyRequest

_REQUESTS: list[tuple[str, type[BaseModel]]] = [
    ("gpu-nvidia", GpuNvidiaApplyRequest),
    ("gpu-amd", GpuAmdApplyRequest),
]

# Schema fields with no executor behind them. Named rather than skipped in
# silence: ``anti_lag_2`` is the AMD half of a C10 symmetry gap tracked in issue
# #34, and ``gpu.py`` forwards the field only when a caller sets it explicitly,
# precisely because no setting would answer to it.
_NO_SETTING_YET = {"gpu-amd:anti_lag_2"}

# ``gpu-nvidia:vsync`` derives its recommendation from the panel
# (``create_nvidia_vsync_setting``): "on" where VRR plus a frame cap makes
# V-Sync free, "off" on fixed refresh. No literal in a request model can equal
# both, so this one field is held to membership in ``choices`` only. The schema
# carries the fixed-refresh answer, which is the safe direction to be wrong in.
_PANEL_DERIVED = {"gpu-nvidia:vsync"}

_FIELD_CASES = [
    pytest.param(prefix, model, field, id=f"{prefix}:{field}")
    for prefix, model in _REQUESTS
    for field in model.model_fields
]

# ``POST /api/gpu/apply`` takes query parameters instead of a body model, so its
# defaults live on the handler signature where ``model_fields`` cannot reach
# them — which is how that one endpoint kept defaulting to ``low_latency=ultra``
# and ``power_mode=maximum`` after both request models were corrected.
# ``eval_str`` because ``gpu.py`` has ``from __future__ import annotations``, so
# every annotation arrives as a string.
_QUERY_PARAMS = inspect.signature(apply_gpu_settings, eval_str=True).parameters
_QUERY_PARAM_CASES = [pytest.param(name, id=name) for name in _QUERY_PARAMS]


def _literals(model: type[BaseModel], field: str) -> tuple[Any, ...]:
    annotation = model.model_fields[field].annotation
    assert get_args(annotation), f"{model.__name__}.{field} is not a Literal"
    return get_args(annotation)


@pytest.fixture(scope="module")
def registry():
    """The registry the routes themselves serve from, not a second build."""
    from fpstune.api.routes.settings import _get_registry

    return _get_registry()


def test_every_schema_field_names_a_registered_setting(registry) -> None:
    """A field with no setting behind it can only fail at apply time."""
    missing = {
        f"{prefix}:{field}"
        for prefix, model in _REQUESTS
        for field in model.model_fields
        if registry.get(f"{prefix}:{field}") is None
    }

    assert missing == _NO_SETTING_YET, (
        "GPU request fields with no registered setting changed. A new name here "
        "means an apply that reports 'Unknown setting'; a name gone from here "
        "means the gap closed and this list should shrink with it."
    )


@pytest.mark.parametrize(("prefix", "model", "field"), _FIELD_CASES)
def test_every_literal_is_a_value_the_setting_accepts(
    registry, prefix: str, model: type[BaseModel], field: str
) -> None:
    setting = registry.get(f"{prefix}:{field}")
    if setting is None:
        pytest.skip(f"{prefix}:{field} has no executor yet (see _NO_SETTING_YET)")

    offered = set(_literals(model, field))
    accepted = set(setting.choices) | set(setting.apply_value_map)

    assert offered <= accepted, (
        f"{model.__name__}.{field} offers {sorted(offered - accepted)}, which "
        f"{setting.id} does not accept (choices={list(setting.choices)}). "
        "_validate_apply_value refuses those, so the endpoint fails on hardware "
        "that has the setting."
    )


@pytest.mark.parametrize(("prefix", "model", "field"), _FIELD_CASES)
def test_every_default_is_the_settings_recommendation(
    registry, prefix: str, model: type[BaseModel], field: str
) -> None:
    """Omitting a field means "apply what fpstune advises"."""
    setting_id = f"{prefix}:{field}"
    setting = registry.get(setting_id)
    if setting is None:
        pytest.skip(f"{setting_id} has no executor yet (see _NO_SETTING_YET)")

    default = model.model_fields[field].default

    if setting_id in _PANEL_DERIVED:
        assert default in setting.choices, (
            f"{model.__name__}.{field} defaults to {default!r}, which is not one "
            f"of {setting_id}'s choices."
        )
        return

    assert default == setting.recommended_value, (
        f"{model.__name__}.{field} defaults to {default!r} but {setting_id} "
        f"recommends {setting.recommended_value!r}. A caller who omits the field "
        "gets a value this product does not advise."
    )


@pytest.mark.parametrize(("prefix", "model"), _REQUESTS, ids=lambda v: getattr(v, "__name__", v))
def test_the_default_payload_survives_the_apply_validator(
    registry, prefix: str, model: type[BaseModel]
) -> None:
    """The concrete failure: an empty POST body rejected by our own validator.

    ``POST /api/gpu/amd/apply`` with ``{}`` built a request whose ``anti_lag``
    and ``shader_cache`` were ``"on"`` — a value ``gpu-amd`` never declared — and
    ``_apply_one`` refused both before any driver was touched.
    """
    from fpstune.api.routes.settings import _validate_apply_value

    request = model()
    rejected = {}
    for field, value in request.model_dump().items():
        setting = registry.get(f"{prefix}:{field}")
        if setting is None:
            continue
        invalid = _validate_apply_value(setting, value)
        if invalid:
            rejected[field] = invalid

    assert not rejected, f"{model.__name__}() defaults our own validator refuses: {rejected}"


def test_the_amd_literals_are_the_registry_spelling(registry) -> None:
    """Pins the exact instance, so the fix cannot silently regress.

    AMD writes a REG_DWORD and spells its display values "enabled"/"disabled";
    the schema said "off"/"on", which is NVIDIA's spelling for a different
    setting. Two vendors, two vocabularies, one shared field name.
    """
    for field in ("anti_lag", "shader_cache"):
        setting = registry.get(f"gpu-amd:{field}")
        assert setting is not None
        assert set(_literals(GpuAmdApplyRequest, field)) == {"enabled", "disabled"}
        assert set(setting.choices) == {"enabled", "disabled"}


def _query_param_prefixes(registry, name: str) -> list[str]:
    """Which vendors ``/apply`` can forward this parameter to, per the registry."""
    prefixes = [prefix for prefix, _ in _REQUESTS if registry.get(f"{prefix}:{name}") is not None]
    assert prefixes, (
        f"No registered setting answers to {name!r} under any vendor prefix, so "
        "the vendor-auto endpoint offers a parameter nothing can apply."
    )
    return prefixes


@pytest.mark.parametrize("name", _QUERY_PARAM_CASES)
def test_every_vendor_auto_literal_is_a_value_the_setting_accepts(registry, name: str) -> None:
    annotation = _QUERY_PARAMS[name].annotation
    offered = set(get_args(annotation))
    assert offered, f"apply_gpu_settings.{name} is not a Literal"

    for prefix in _query_param_prefixes(registry, name):
        setting = registry.get(f"{prefix}:{name}")
        assert setting is not None
        accepted = set(setting.choices) | set(setting.apply_value_map)
        assert offered <= accepted, (
            f"apply_gpu_settings.{name} offers {sorted(offered - accepted)}, which "
            f"{setting.id} does not accept (choices={list(setting.choices)})."
        )


@pytest.mark.parametrize("name", _QUERY_PARAM_CASES)
def test_every_vendor_auto_default_is_the_settings_recommendation(registry, name: str) -> None:
    """The live bug: ``POST /api/gpu/apply`` with no query string.

    It built ``low_latency="ultra"`` — the value ``ANTICHEAT_WARNINGS`` calls
    ban-risky — and ``power_mode="maximum"``, which raises no frame rate and
    holds the clocks up for the whole session. Both were corrected on the
    request models while this handler kept the old pair.
    """
    default = _QUERY_PARAMS[name].default
    assert default is not inspect.Parameter.empty, (
        f"apply_gpu_settings.{name} has no default, so an omitted parameter is a 422 "
        "rather than the recommendation."
    )

    for prefix in _query_param_prefixes(registry, name):
        setting = registry.get(f"{prefix}:{name}")
        assert setting is not None
        if setting.id in _PANEL_DERIVED:
            assert default in setting.choices, (
                f"apply_gpu_settings.{name} defaults to {default!r}, which is not one "
                f"of {setting.id}'s choices."
            )
            continue
        assert default == setting.recommended_value, (
            f"apply_gpu_settings.{name} defaults to {default!r} but {setting.id} "
            f"recommends {setting.recommended_value!r}. A caller who omits the "
            "parameter gets a value this product does not advise."
        )


@pytest.mark.parametrize("name", _QUERY_PARAM_CASES)
def test_the_three_apply_endpoints_answer_an_empty_request_alike(name: str) -> None:
    """Same field, same omission, same value — whichever endpoint was called.

    ``/apply`` forwards into ``GpuNvidiaApplyRequest``, so a default that
    disagreed with the model's would make the vendor-auto path apply something
    ``/nvidia/apply`` never would for the same empty request.
    """
    if name not in GpuNvidiaApplyRequest.model_fields:
        pytest.skip(f"{name} is not an NVIDIA request field")

    model_default = GpuNvidiaApplyRequest.model_fields[name].default
    assert _QUERY_PARAMS[name].default == model_default, (
        f"apply_gpu_settings.{name} defaults to {_QUERY_PARAMS[name].default!r} but "
        f"GpuNvidiaApplyRequest.{name} defaults to {model_default!r}."
    )


def test_literal_helper_rejects_a_non_literal_field() -> None:
    """The checks above are only worth anything while every field is a Literal;
    a field widened to ``str`` would make ``get_args`` empty and every
    subset assertion pass vacuously."""

    class Widened(BaseModel):
        ok: Literal["a"] = "a"
        widened: str = "anything"

    assert _literals(Widened, "ok") == ("a",)
    with pytest.raises(AssertionError, match="is not a Literal"):
        _literals(Widened, "widened")
