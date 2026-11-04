# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators of BBone to Bones: aggregator over the per-area modules.

Every operator validates the context, relays the outcome through the reports
and calls core; the math stays in core/.
"""

from .operator_convert import (
    BTOB_OT_convert_all,
    BTOB_OT_convert_segments,
    BTOB_OT_revert_to_bbones,
)
from .operator_export import BTOB_OT_export_rig
from .operator_follow import (
    BTOB_OT_add_constraints,
    BTOB_OT_bake_animation,
    BTOB_OT_remove_constraints,
)
from .operator_weights import (
    BTOB_OT_limit_influences,
    BTOB_OT_transfer_weights,
)

__all__ = [
    "BTOB_OT_convert_segments",
    "BTOB_OT_transfer_weights",
    "BTOB_OT_add_constraints",
    "BTOB_OT_remove_constraints",
    "BTOB_OT_bake_animation",
    "BTOB_OT_limit_influences",
    "BTOB_OT_export_rig",
    "BTOB_OT_convert_all",
    "BTOB_OT_revert_to_bbones",
]
