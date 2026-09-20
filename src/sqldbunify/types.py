# SPDX-FileCopyrightText: 2026 Tsyganov Pavel
# SPDX-License-Identifier: MIT

from typing import Any, Literal, Optional, TypeVar, Union

OperatorType = Literal['==', '!=', '>', '<', '>=', '<=', 'in', 'not_in', 'between']

FilterTuple = tuple[str, OperatorType, Any]
FilterGroup = list[Union[str, FilterTuple, "FilterGroup"]]
FilterType = Optional[Union[dict, list[FilterTuple], FilterGroup]]

ReturnMode = Literal['list', 'lists', 'tuple', 'tuples', 'dict', 'single_item', 'default']

JoinType = Literal['inner', 'outer']
LogicType = Literal['and', 'or']

ModelType = TypeVar('ModelType')
FilterValue = Any


__all__ = [
    "OperatorType",
    "FilterTuple",
    "FilterGroup",
    "FilterType",
    "ReturnMode",
    "JoinType",
    "LogicType",
    "ModelType",
    "FilterValue",
]
