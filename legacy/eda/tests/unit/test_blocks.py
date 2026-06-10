"""Smoke test: every registered carrier block builds without error.

This catches:
  * Broken imports in any block builder.
  * Block model validation errors (duplicate net names, invalid edges,
    missing required fields, etc.) — :class:`Block.__post_init__` and
    its peers raise on these.
  * Refcircuit lookup failures (block references a key that's not in
    :data:`REFCIRCUITS`).

It does NOT validate KiCad symbol library availability, layout, ERC,
or anything beyond "the declarative block object materialises cleanly".
"""

from __future__ import annotations

import pytest

from zynq_eda.core.model.block import Block
from zynq_eda.projects.carrier import board as carrier_board


@pytest.mark.parametrize("block_name", carrier_board.block_names())
def test_block_builds(block_name: str) -> None:
    """Each registered block factory returns a valid :class:`Block`."""
    blocks = carrier_board.build_blocks(only=block_name)
    assert len(blocks) == 1
    block = blocks[0]
    assert isinstance(block, Block)
    assert block.name == block_name
    assert block.title, f"block {block_name!r} has empty title"
    # External nets must be unique by name (Block.__post_init__ enforces this,
    # so the assertion is belt-and-braces).
    seen = set()
    for net in block.external_nets:
        assert net.name not in seen, (
            f"block {block_name!r}: duplicate external net {net.name!r}"
        )
        seen.add(net.name)


def test_all_blocks_build_in_one_pass() -> None:
    """The full carrier (every registered block) builds in a single call."""
    blocks = carrier_board.build_blocks()
    assert len(blocks) == len(carrier_board.block_names())
    names = [b.name for b in blocks]
    assert names == list(carrier_board.block_names()), (
        "build_blocks() preserves the factory-registration order"
    )


def test_block_registry_is_complete() -> None:
    """Sanity check that the carrier has the expected breadth of blocks."""
    names = set(carrier_board.block_names())
    expected_minimum = {
        "power", "usb_pd",
    }
    missing = expected_minimum - names
    assert not missing, f"core blocks missing from registry: {missing}"
    # Catch obvious typos / case mismatches: every name should be a valid
    # Python identifier (we use the name as the sheet filename stem and as
    # the --only argument value).
    for name in names:
        assert name.replace("_", "").isalnum(), (
            f"block name {name!r} not alphanumeric/underscore"
        )
