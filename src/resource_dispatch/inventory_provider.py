"""Standard interface for reading current resource availability."""

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


INVENTORY_COLUMNS = [
    "resource_id",
    "resource_type",
    "district",
    "available_count",
]


class InventoryProvider(ABC):
    """Source-neutral interface for the latest recorded inventory snapshot."""

    @abstractmethod
    def get_current_inventory(self):
        """Return current availability using the standardized inventory columns."""
        raise NotImplementedError


class WorkbookInventoryProvider(InventoryProvider):
    """Read current availability from the project inventory workbook."""

    def __init__(self, workbook_path, sheet_name="Resource_Inventory"):
        self.workbook_path = Path(workbook_path)
        self.sheet_name = sheet_name

    def get_current_inventory(self):
        if not self.workbook_path.is_file():
            raise FileNotFoundError(
                "Inventory workbook does not exist: {}".format(self.workbook_path)
            )

        workbook_inventory = pd.read_excel(
            self.workbook_path,
            sheet_name=self.sheet_name,
        )
        missing = sorted(
            set(INVENTORY_COLUMNS) - set(workbook_inventory.columns)
        )
        if missing:
            raise ValueError(
                "Inventory workbook sheet {!r} is missing columns: {}".format(
                    self.sheet_name, missing
                )
            )

        inventory = workbook_inventory[INVENTORY_COLUMNS].copy()
        if inventory["resource_id"].isna().any() or inventory[
            "resource_id"
        ].duplicated().any():
            raise ValueError(
                "Inventory workbook contains blank or duplicate resource IDs"
            )
        if inventory["resource_type"].isna().any() or inventory[
            "district"
        ].isna().any():
            raise ValueError(
                "Inventory workbook contains blank resource types or districts"
            )

        inventory["resource_type"] = (
            inventory["resource_type"].astype("string").str.strip().str.upper()
        )
        inventory["district"] = (
            inventory["district"].astype("string").str.strip()
        )
        availability = pd.to_numeric(
            inventory["available_count"], errors="coerce"
        )
        if (
            availability.isna().any()
            or (availability < 0).any()
            or (availability % 1 != 0).any()
        ):
            raise ValueError(
                "Inventory availability must contain nonnegative integers"
            )
        inventory["available_count"] = availability.astype("int64")
        return inventory.reset_index(drop=True)
