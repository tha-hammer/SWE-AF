"""BAML Schema-Aligned-Parser bridge for SWE-AF (parser-only, no LLM call).

Maps a runtime SWE-AF pydantic schema onto BAML's ``@@dynamic DynamicOutput``
root via ``TypeBuilder``, parses raw harness text with ``b.parse.ExtractDynamic``
(no network), and casts the generated ``DynamicOutput`` instance back to the
target pydantic model.

Two parse helpers with deliberately different failure contracts:
  * ``baml_parse(text, schema) -> M``         — RAISES ValueError on failure.
  * ``baml_parse_or_none(text, schema) -> M?`` — returns None on failure (used by
    the codex_harness_patch seam so the SDK's FailureType.SCHEMA path is preserved).
"""

from __future__ import annotations

import types
import typing
from enum import Enum
from typing import Any, Optional, TypeVar, Union, get_args, get_origin

import baml_py.errors
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from baml_client.sync_client import b
from baml_client.type_builder import TypeBuilder

M = TypeVar("M", bound=BaseModel)

_NoneType = type(None)


def _is_optional(annotation: Any) -> tuple[bool, Any]:
    """Return (is_optional, inner_type) for Optional[X] / X | None."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        non_none = [a for a in args if a is not _NoneType]
        if _NoneType in args:
            if len(non_none) == 1:
                return True, non_none[0]
            # Optional[Union[A, B]] -> optional union of the rest
            return True, Union[tuple(non_none)]
    return False, annotation


def _map_type(annotation: Any, tb: TypeBuilder):
    """Map a Python/pydantic type annotation onto a BAML FieldType.

    Hand-aligned with the plan's mapping table. Unsupported constructs raise
    TypeError rather than silently coercing.
    """
    is_opt, annotation = _is_optional(annotation)
    if is_opt:
        return _map_type(annotation, tb).optional()

    # Primitives
    if annotation is str:
        return tb.string()
    if annotation is bool:  # bool before int (bool is a subclass of int)
        return tb.bool()
    if annotation is int:
        return tb.int()
    if annotation is float:
        return tb.float()

    origin = get_origin(annotation)

    # list[X]
    if origin in (list, typing.List):
        (inner,) = get_args(annotation) or (Any,)
        return tb.list(_map_type(inner, tb))

    # dict[K, V]
    if origin in (dict, typing.Dict):
        args = get_args(annotation)
        if len(args) != 2:
            raise TypeError(f"Unsupported dict annotation without K,V: {annotation!r}")
        k, v = args
        return tb.map(_map_type(k, tb), _map_type(v, tb))

    # Literal["a", "b", ...]
    if origin is typing.Literal:
        members = []
        for lit in get_args(annotation):
            if isinstance(lit, bool):
                members.append(tb.literal_bool(lit))
            elif isinstance(lit, int):
                members.append(tb.literal_int(lit))
            elif isinstance(lit, str):
                members.append(tb.literal_string(lit))
            else:
                raise TypeError(f"Unsupported Literal value: {lit!r}")
        return tb.union(members)

    # Union[A, B, ...] (non-optional; optional handled above)
    if origin is Union or origin is types.UnionType:
        return tb.union([_map_type(a, tb) for a in get_args(annotation)])

    # Enum E
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        eb = tb.add_enum(annotation.__name__)
        for member in annotation:
            eb.add_value(member.value if isinstance(member.value, str) else member.name)
        return eb.type()

    # nested BaseModel M
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        cb = tb.add_class(annotation.__name__)
        for fname, finfo in annotation.model_fields.items():
            cb.add_property(fname, _field_type(finfo, tb))
        return cb.type()

    raise TypeError(f"Unsupported type for BAML mapping: {annotation!r}")


def _field_type(finfo: FieldInfo, tb: TypeBuilder):
    """Map a pydantic FieldInfo, marking it optional when it has a default.

    A pydantic field with a default (``confidence: float = 0.5``,
    ``issue_name: str = ""``) must become an *optional* BAML property — otherwise
    SAP treats it as required and drops any object that omits it.
    """
    annotation = finfo.annotation
    mapped = _map_type(annotation, tb)
    is_opt_annotation, _ = _is_optional(annotation)
    if not finfo.is_required() and not is_opt_annotation:
        mapped = mapped.optional()
    return mapped


def pydantic_to_typebuilder(model: type[BaseModel]) -> TypeBuilder:
    """Build a fresh TypeBuilder whose @@dynamic DynamicOutput root mirrors *model*.

    **omit-if-defaulted contract (Behavior 0a):** a field whose type cannot be
    mapped onto a BAML FieldType (``_map_type`` raises ``TypeError`` — e.g. a bare
    ``dict`` / ``Any`` / ``list[dict]`` / ``dict[str, Any]``) is **skipped** when it
    has a Pydantic default, and **re-raised** when it is required. Skipping a
    *defaulted* unmappable field is safe: it is simply absent from the BAML type, so
    SAP never emits it, ``_strip_none`` leaves it absent, and ``model_validate``
    restores the Pydantic default. A *required* unmappable field still raises, so we
    never silently drop required data. This lets dict-bearing reasoner schemas
    (``QAResult``, ``MergeResult``, ``CoderResult``) map and benefit from BAML parse
    + the ``output_format`` render, instead of declining wholesale to ``None``.

    Upgrade path (opt-in, not wired here): a field whose dict *contents* must
    survive the round-trip can be mapped via a recursive ``JsonValue`` alias emitted
    through ``tb.add_baml`` (``map<string, JsonValue>``); see the plan's Behavior 0a
    spike. The ``string`` + ``json.loads`` approach is rejected — BAML SAP writes
    non-strict JSON (unquoted keys) that ``json.loads`` cannot read.
    """
    tb = TypeBuilder()
    for fname, finfo in model.model_fields.items():
        try:
            tb.DynamicOutput.add_property(fname, _field_type(finfo, tb))
        except TypeError:
            if finfo.is_required():
                raise
            # Defaulted + unmappable → omit; the Pydantic default fills it back in.
            continue
    return tb


def _strip_none(value: Any) -> Any:
    """Recursively drop None-valued keys so pydantic applies field defaults.

    BAML renders an optional property that the input omitted as ``None``. A
    pydantic field with a non-optional default (``issue_name: str = ""``) would
    reject that ``None``; dropping the key lets the default take over. Optional
    fields (default ``None``) round-trip to the same value either way.
    """
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value]
    return value


def deserialize(raw: Any, model: type[M]) -> M:
    """Cast a generated DynamicOutput instance back to *model*.

    ``raw`` is BAML's generated ``DynamicOutput`` pydantic instance (output_type
    "python/pydantic"), NOT a dict. The @@dynamic-added properties surface as raw
    model fields, so ``raw.model_dump()`` keys match the schema field names.
    """
    try:
        payload = raw.model_dump() if isinstance(raw, BaseModel) else raw
        return model.model_validate(_strip_none(payload))
    except (ValidationError, baml_py.errors.BamlError, ValueError) as exc:
        raise ValueError(f"Could not parse structured response: {exc}") from exc


def baml_parse(text: str, schema: type[M]) -> M:
    """Parse *text* into *schema* via BAML SAP. RAISES ValueError on any failure.

    SAP coercion errors surface from ``b.parse`` as ``baml_py.errors.BamlError``
    (base of BamlValidationError); both are translated to ValueError here.
    """
    try:
        raw = b.parse.ExtractDynamic(
            text, baml_options={"tb": pydantic_to_typebuilder(schema)}
        )
    except baml_py.errors.BamlError as exc:
        raise ValueError(f"Could not parse structured response: {exc}") from exc
    return deserialize(raw, schema)


def baml_parse_or_none(text: str, schema: type[M]) -> Optional[M]:
    """Parse *text* into *schema*; return None on ANY failure (seam contract).

    Deliberately catches every exception — including the ``TypeError`` raised when
    a schema contains an unmappable field (untyped ``dict``/``Any``). The seam runs
    on the SDK's ``None`` for arbitrary reasoner schemas; it must never crash the
    parse path, only decline to improve on it. Declining preserves the SDK's
    existing None → FailureType.SCHEMA fallback.
    """
    try:
        return baml_parse(text, schema)
    except Exception:
        return None


# Private marker fed as the ExtractDynamic `prompt` so we can split the rendered
# request and keep only the `{{ ctx.output_format }}` section after it.
_OUTPUT_FORMAT_MARKER = "@@SWE_AF_OUTPUT_FORMAT_MARKER@@"


def baml_output_format(model: type[BaseModel]) -> str:
    """Render *model*'s output-shape section via BAML's ``ctx.output_format`` (no LLM).

    Uses ``b.request`` — which BUILDS the request without sending it — and splits the
    rendered prompt on a private marker to return only the ``output_format`` section.
    The result is materially smaller than ``json.dumps(model.model_json_schema())``:
    BAML renders nested types inline (``{ criterion: string, … }``) instead of JSON
    Schema's ``$defs``/``$ref``. Raises whatever ``pydantic_to_typebuilder`` raises
    for an unmappable schema (a *required* bare ``dict``/``Any``), so callers can fall
    back to the SDK's JSON-Schema injection. Makes **no** network/LLM call.
    """
    tb = pydantic_to_typebuilder(model)
    req = b.request.ExtractDynamic(_OUTPUT_FORMAT_MARKER, baml_options={"tb": tb})
    text = req.body.json()["messages"][0]["content"][0]["text"]
    return text.split(_OUTPUT_FORMAT_MARKER, 1)[1].strip()


__all__ = [
    "pydantic_to_typebuilder",
    "deserialize",
    "baml_parse",
    "baml_parse_or_none",
    "baml_output_format",
]
