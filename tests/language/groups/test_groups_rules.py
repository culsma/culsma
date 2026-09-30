"""Static group bounds with real binding values and no compiler scaffolding."""

import pytest

from culsma.domains.groups import GroupBinding, index_bounds_error


@pytest.mark.parametrize(
    "binding,index,expected",
    [
        (GroupBinding("sep_container_group", 2), 0, None),
        (GroupBinding("sep_container_group", 2), 1, None),
        (GroupBinding("sep_container_group", 2), 2,
         "sep_container_group only supports indices 0 and 1"),
        (GroupBinding("container_group", 2), 1, None),
        (GroupBinding("container_group", 2), 2,
         "container_group index 2 is out of range for size=2"),
        (GroupBinding("container_group", 0), 0,
         "container_group index 0 is out of range for size=0"),
        (GroupBinding("fraction_group", 4), 3, None),
        (GroupBinding("fraction_group", 4), 4,
         "fraction_group index 4 is out of range for bins=4"),
        (GroupBinding("data_group", 2), 1, None),
        (GroupBinding("data_group", 2), 2,
         "data_group_ref index 2 is out of range for size=2"),
        (GroupBinding("container_group"), 10, None),
        (GroupBinding("fraction_group"), 10, None),
        (GroupBinding("data_group"), 10, None),
        (GroupBinding("unbound_parameter"), 10, None),
    ],
)
def test_group_index_bounds(binding, index, expected):
    assert index_bounds_error(binding, index) == expected
