from __future__ import annotations

from . import config


def aggregate() -> dict[str, list[list[object]]]:
    """Phase 1 stub: реальные метрики появятся в Phase 2."""
    if not config.TM_USERS or not config.MOP_USERS:
        raise RuntimeError(
            "TM_USERS/MOP_USERS пусты — заполни в config.py "
            "подтверждённым списком перед запуском Phase 2"
        )
    return {
        "tm_metrics": [],
        "sales_plan": [],
        "mop_metrics": [],
        "mrr": [],
    }
