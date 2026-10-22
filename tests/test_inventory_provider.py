import tempfile
import unittest
from pathlib import Path

import pandas as pd

import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.inventory_provider import (
    INVENTORY_COLUMNS,
    InventoryProvider,
    WorkbookInventoryProvider,
)


class WorkbookInventoryProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workbook_path = Path(self.temp_dir.name) / "inventory.xlsx"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_inventory(self, table, sheet_name="Resource_Inventory"):
        with pd.ExcelWriter(str(self.workbook_path), engine="openpyxl") as writer:
            table.to_excel(writer, sheet_name=sheet_name, index=False)

    def test_provider_implements_standard_inventory_interface(self):
        source = pd.DataFrame([
            {
                "resource_id": "R1",
                "resource_type": " amb ",
                "district": " Ratnapura ",
                "available_count": 2,
                "station_name": "Station",
            },
        ])
        self.write_inventory(source)

        provider = WorkbookInventoryProvider(self.workbook_path)
        result = provider.get_current_inventory()

        self.assertIsInstance(provider, InventoryProvider)
        self.assertEqual(result.columns.tolist(), INVENTORY_COLUMNS)
        self.assertEqual(result.iloc[0]["resource_type"], "AMB")
        self.assertEqual(result.iloc[0]["district"], "Ratnapura")
        self.assertEqual(int(result.iloc[0]["available_count"]), 2)

    def test_missing_workbook_fails_explicitly(self):
        provider = WorkbookInventoryProvider(
            Path(self.temp_dir.name) / "missing.xlsx"
        )

        with self.assertRaisesRegex(FileNotFoundError, "does not exist"):
            provider.get_current_inventory()

    def test_missing_required_columns_fail_explicitly(self):
        self.write_inventory(pd.DataFrame([
            {"resource_id": "R1", "resource_type": "AMB"},
        ]))

        with self.assertRaisesRegex(ValueError, "missing columns"):
            WorkbookInventoryProvider(
                self.workbook_path
            ).get_current_inventory()

    def test_invalid_availability_is_rejected(self):
        self.write_inventory(pd.DataFrame([
            {
                "resource_id": "R1",
                "resource_type": "AMB",
                "district": "Ratnapura",
                "available_count": -1,
            },
        ]))

        with self.assertRaisesRegex(ValueError, "nonnegative integers"):
            WorkbookInventoryProvider(
                self.workbook_path
            ).get_current_inventory()


if __name__ == "__main__":
    unittest.main()
