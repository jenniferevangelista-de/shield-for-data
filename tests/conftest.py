import os
from pathlib import Path

import pytest

os.environ["SHIELD_LLM"] = "off"  # tests never call a model

from shield.catalog import MockCatalog  # noqa: E402
from shield.desk import Desk  # noqa: E402
from shield.warehouse import Warehouse  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def wh():
    w = Warehouse.open()
    w.reset()
    return w


@pytest.fixture
def catalog():
    return MockCatalog(ROOT / "catalog" / "lineage.yaml")


@pytest.fixture
def desk(wh, catalog):
    return Desk(wh, catalog)
