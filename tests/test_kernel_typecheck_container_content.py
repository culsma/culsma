from __future__ import annotations

from culsma.pipeline.ir_nodes import IRArg, IRProgram, IRProtocol, IRQuantity, IRStep
from culsma.pipeline.typecheck import typecheck


def _codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def test_descriptor_type_errors_are_typecheck():
    """CF-CNT-004: descriptor type failures are owned by typecheck stage."""
    ir = IRProgram(
        protocols=[
            IRProtocol(
                id="p0",
                name="T",
                statements=[
                    IRStep(
                        id="p0.s0",
                        name="DefineContent",
                        args=[
                            IRArg(name="kind", value=IRQuantity(5.0, "uL")),
                            IRArg(name="type", value=IRQuantity(2.0, "uL")),
                            IRArg(name="code", value=IRQuantity(3.0, "uL")),
                            IRArg(name="attrs", value=IRQuantity(1.0, None)),
                        ],
                    )
                ],
            )
        ]
    )
    result = typecheck(ir)
    codes = _codes(result)
    assert "TYPE_CONTENT_KIND_NOT_TEXT" in codes
    assert "TYPE_CONTENT_TYPE_NOT_TEXT" in codes
    assert "TYPE_CONTENT_CODE_NOT_TEXT" in codes
    assert "TYPE_CONTENT_ATTRS_NOT_RECORD" in codes
