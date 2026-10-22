"""Launch a local desktop dashboard for the resource allocation prototype."""

from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))
from resource_dispatch.allocator import solve_allocation
from resource_dispatch.comparison import compare_allocation_methods
from resource_dispatch.dispatch_safety import (
    inventory_after_reservations,
    load_reservations,
    reserve_dispatch_plan,
    validate_dispatch_plan,
)
from resource_dispatch.inventory_provider import WorkbookInventoryProvider
from run_allocation_solver import (
    ALLOCATION_DIR,
    RESERVATIONS_PATH,
    _prepare_pending_inputs,
)


REQUESTS_PATH = ALLOCATION_DIR / "allocation_requests.csv"
CANDIDATES_PATH = ALLOCATION_DIR / "allocation_candidates.csv"
INVENTORY_PATH = PROJECT_DIR / "Resource_Inventory_5Districts.xlsx"

ALLOCATION_COLUMNS = [
    "alert_id", "district", "hazard_type", "severity",
    "requested_resource_type", "requested_quantity", "allocated_quantity",
    "unfilled_quantity", "priority_score", "local_scarcity_score",
    "resource_id", "resource_district", "straight_line_distance_km",
]
REQUEST_COLUMNS = [
    "alert_id", "district", "hazard_type", "requested_resource_type",
    "requested_quantity", "allocated_quantity", "unfilled_quantity",
    "priority_score", "local_scarcity_score",
]
INVENTORY_COLUMNS = [
    "resource_id", "resource_type", "district", "available_count",
]
RESERVATION_COLUMNS = [
    "alert_id", "requested_resource_type", "resource_id",
    "reserved_quantity", "reserved_at",
]
RESOURCE_METRIC_COLUMNS = [
    "method", "requested_resource_type", "requested_quantity",
    "allocated_quantity", "unfilled_quantity", "fulfillment_rate",
    "available_quantity", "quantity_utilization_rate",
]


def allocation_table(allocations, requests, request_results):
    """Add alert context and unfilled quantities for display."""
    context = requests[
        ["alert_id", "requested_resource_type", "hazard_type", "severity"]
    ]
    unfilled = request_results[
        [
            "alert_id", "requested_resource_type", "unfilled_quantity",
        ]
    ]
    table = allocations.merge(
        context,
        on=["alert_id", "requested_resource_type"],
        how="left",
        validate="many_to_one",
    ).merge(
        unfilled,
        on=["alert_id", "requested_resource_type"],
        how="left",
        validate="many_to_one",
    )
    return table


def filtered_frame(table, district, hazard, resource_type):
    """Filter a display table without changing the solver's input scenario."""
    filtered = table
    if district != "All":
        filtered = filtered.loc[filtered["district"] == district]
    if hazard != "All":
        filtered = filtered.loc[filtered["hazard_type"] == hazard]
    if resource_type != "All":
        filtered = filtered.loc[
            filtered["requested_resource_type"] == resource_type
        ]
    return filtered


def _format_value(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return "{:.3f}".format(value)
    return str(value)


class ResourceDispatchDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Resource-Aware Dispatch Prototype")
        self.root.geometry("1280x800")
        self.root.minsize(980, 640)

        self.preview = None
        self.original_requests = None
        self.current_inventory = None
        self.reservations = None
        self.requests = None
        self.supply = None
        self.candidates = None
        self.plan_table = pd.DataFrame()
        self.request_table = pd.DataFrame()
        self.status = tk.StringVar(value="Ready. Generate a preview to begin.")
        self.district_filter = tk.StringVar(value="All")
        self.hazard_filter = tk.StringVar(value="All")
        self.resource_filter = tk.StringVar(value="All")

        self._build_window()
        self._load_initial_data()

    def _build_window(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("MetricValue.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("MetricName.TLabel", font=("Segoe UI", 9))
        style.configure("Treeview", rowheight=25)

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Resource-Aware Dispatch",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            container,
            text=(
                "Allocation preview using prepared project data and a workbook "
                "inventory snapshot. This is not a live dispatch system."
            ),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        controls = ttk.Frame(container)
        controls.pack(fill="x", pady=(0, 10))
        self.preview_button = ttk.Button(
            controls, text="Generate preview", command=self.generate_preview
        )
        self.preview_button.pack(side="left")
        self.compare_button = ttk.Button(
            controls, text="Compare methods", command=self.compare_methods,
            state="disabled",
        )
        self.compare_button.pack(side="left", padx=(8, 0))
        self.approve_button = ttk.Button(
            controls, text="Approve and reserve plan",
            command=self.approve_plan, state="disabled",
        )
        self.approve_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            controls,
            text="Approval writes reservations to the local CSV ledger.",
        ).pack(side="left", padx=(14, 0))

        self.metrics_frame = ttk.Frame(container)
        self.metrics_frame.pack(fill="x", pady=(0, 10))
        self.metric_values = []
        for column in range(4):
            self.metrics_frame.columnconfigure(column, weight=1)
            card = ttk.LabelFrame(self.metrics_frame, text="")
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
            value = ttk.Label(card, text="—", style="MetricValue.TLabel")
            value.pack(anchor="w", padx=10, pady=(8, 0))
            label = ttk.Label(card, text="", style="MetricName.TLabel")
            label.pack(anchor="w", padx=10, pady=(0, 8))
            self.metric_values.append((value, label, card))

        filters = ttk.Frame(container)
        filters.pack(fill="x", pady=(0, 8))
        for label, variable, width in [
            ("District", self.district_filter, 20),
            ("Hazard", self.hazard_filter, 20),
            ("Resource", self.resource_filter, 12),
        ]:
            ttk.Label(filters, text=label).pack(side="left", padx=(0, 5))
            combo = ttk.Combobox(
                filters, textvariable=variable, state="readonly", width=width
            )
            combo.pack(side="left", padx=(0, 14))
            combo.bind("<<ComboboxSelected>>", self._apply_filters)
            setattr(self, "{}_combobox".format(label.lower()), combo)

        self.tabs = ttk.Notebook(container)
        self.tabs.pack(fill="both", expand=True)
        self.plan_tab = ttk.Frame(self.tabs, padding=8)
        self.request_tab = ttk.Frame(self.tabs, padding=8)
        self.inventory_tab = ttk.Frame(self.tabs, padding=8)
        self.comparison_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.plan_tab, text="Proposed allocations")
        self.tabs.add(self.request_tab, text="Request fulfillment")
        self.tabs.add(self.inventory_tab, text="Inventory and reservations")
        self.tabs.add(self.comparison_tab, text="Method comparison")

        self.plan_tree = self._create_table(self.plan_tab, ALLOCATION_COLUMNS)
        self.request_tree = self._create_table(self.request_tab, REQUEST_COLUMNS)
        self.inventory_tree = self._create_table(
            self.inventory_tab, INVENTORY_COLUMNS
        )
        self.reservation_tree = self._create_table(
            self.inventory_tab, RESERVATION_COLUMNS
        )
        ttk.Label(
            self.inventory_tab, text="Current reservations in local ledger"
        ).pack(anchor="w", pady=(12, 4), before=self.reservation_tree.master)
        self.resource_metric_tree = self._create_table(
            self.comparison_tab, RESOURCE_METRIC_COLUMNS
        )
        self.comparison_text = tk.Text(
            self.comparison_tab, height=8, wrap="word", state="disabled"
        )
        self.comparison_text.pack(fill="x", expand=False, pady=(12, 0))

        ttk.Label(
            container, textvariable=self.status, relief="sunken", anchor="w"
        ).pack(fill="x", pady=(10, 0))

    def _create_table(self, parent, columns):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            wrapper, columns=columns, show="headings", selectmode="browse"
        )
        vertical = ttk.Scrollbar(
            wrapper, orient="vertical", command=tree.yview
        )
        horizontal = ttk.Scrollbar(
            wrapper, orient="horizontal", command=tree.xview
        )
        tree.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set
        )
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)
        for column in columns:
            tree.heading(column, text=column.replace("_", " ").title())
            tree.column(column, width=max(110, min(220, len(column) * 11)))
        return tree

    def _load_initial_data(self):
        try:
            self.original_requests = pd.read_csv(REQUESTS_PATH)
            if not CANDIDATES_PATH.is_file():
                raise FileNotFoundError(
                    "Prepared candidate input is missing: {}".format(
                        CANDIDATES_PATH
                    )
                )
            self.current_inventory = WorkbookInventoryProvider(
                INVENTORY_PATH
            ).get_current_inventory()
            self.reservations = load_reservations(RESERVATIONS_PATH)
            self._update_inventory_tables()
            self._set_filter_options(self.original_requests)
            self.status.set(
                "Inputs loaded. Generate a preview to calculate a plan."
            )
        except (OSError, ValueError, KeyError, pd.errors.ParserError) as error:
            self.status.set("Unable to load dashboard inputs.")
            messagebox.showerror("Input loading failed", str(error), parent=self.root)

    def _set_filter_options(self, requests):
        values = [
            ("district", self.district_combobox),
            ("hazard_type", self.hazard_combobox),
            ("requested_resource_type", self.resource_combobox),
        ]
        for column, combo in values:
            options = ["All"] + sorted(
                requests[column].dropna().astype(str).unique().tolist()
            )
            combo["values"] = options
            combo.current(0)

    def _update_inventory_tables(self):
        effective = inventory_after_reservations(
            self.current_inventory, self.reservations
        )
        self._fill_table(self.inventory_tree, effective, INVENTORY_COLUMNS)
        self._fill_table(
            self.reservation_tree,
            self.reservations,
            RESERVATION_COLUMNS,
        )

    def generate_preview(self):
        if self.original_requests is None:
            return
        self.approve_button.configure(state="disabled")
        self.compare_button.configure(state="disabled")
        self.preview = None
        self.plan_tree.delete(*self.plan_tree.get_children())
        self.request_tree.delete(*self.request_tree.get_children())
        self.status.set("Calculating allocation preview…")
        self.root.update_idletasks()
        try:
            self.original_requests = pd.read_csv(REQUESTS_PATH)
            candidates = pd.read_csv(CANDIDATES_PATH)
            self.current_inventory = WorkbookInventoryProvider(
                INVENTORY_PATH
            ).get_current_inventory()
            self.reservations = load_reservations(RESERVATIONS_PATH)
            requests, supply, candidates = _prepare_pending_inputs(
                self.original_requests.copy(),
                candidates,
                self.current_inventory,
                self.reservations,
            )
            result = solve_allocation(
                requests=requests,
                supply=supply[["resource_id", "resource_type", "available_count"]],
                candidates=candidates,
            )
            validate_dispatch_plan(
                result["allocations"],
                inventory_after_reservations(
                    self.current_inventory, self.reservations
                ),
            )
            self.requests = requests
            self.supply = supply[[
                "resource_id", "resource_type", "available_count",
            ]].copy()
            self.candidates = candidates
            self.preview = result
            self.plan_table = allocation_table(
                result["allocations"], requests, result["request_results"]
            )
            self.request_table = result["request_results"].copy()
            self._render_preview()
            self._update_inventory_tables()
            self.compare_button.configure(state="normal")
            self.approve_button.configure(
                state="normal" if not result["allocations"].empty else "disabled"
            )
            self.status.set(
                "Preview ready. No reservations were written. "
                "Inventory source: workbook snapshot."
            )
        except (OSError, ValueError, RuntimeError, KeyError,
                pd.errors.ParserError) as error:
            self.status.set("Preview failed.")
            messagebox.showerror("Preview failed", str(error), parent=self.root)

    def _render_preview(self):
        filtered_allocations = filtered_frame(
            self.plan_table,
            self.district_filter.get(),
            self.hazard_filter.get(),
            self.resource_filter.get(),
        )
        filtered_requests = filtered_frame(
            self.request_table,
            self.district_filter.get(),
            self.hazard_filter.get(),
            self.resource_filter.get(),
        )
        self._fill_table(
            self.plan_tree, filtered_allocations, ALLOCATION_COLUMNS
        )
        self._fill_table(
            self.request_tree, filtered_requests, REQUEST_COLUMNS
        )

        covered = self.preview["allocations"]["district"].nunique()
        districts = self.requests["district"].nunique()
        unfilled_count = int(
            self.preview["request_results"]["unfilled_quantity"].gt(0).sum()
        )
        cards = [
            (str(len(self.requests)), "Pending request rows"),
            ("{}/{}".format(covered, districts), "Districts receiving allocations"),
            (str(unfilled_count), "Requests partially or wholly unfilled"),
            (str(len(self.reservations)), "Existing reservation records"),
        ]
        for (value_widget, label_widget, _), (value, label) in zip(
            self.metric_values, cards
        ):
            value_widget.configure(text=value)
            label_widget.configure(text=label)

    def _apply_filters(self, _event=None):
        if self.preview is not None:
            self._render_preview()

    def compare_methods(self):
        if self.preview is None:
            return
        self.status.set("Comparing greedy and CP-SAT methods…")
        self.root.update_idletasks()
        try:
            result = compare_allocation_methods(
                self.requests, self.supply, self.candidates
            )
            metrics = result["resource_type_metrics"]
            columns = [
                column for column in RESOURCE_METRIC_COLUMNS
                if column in metrics.columns
            ]
            self._fill_table(
                self.resource_metric_tree, metrics, columns
            )
            lines = [
                "Same prepared requests, inventory availability, and candidate pairs are used.",
                "The greedy method is a reference heuristic, not a manual DDMC baseline.",
                "Coverage is eventual allocation coverage, not ETA-window coverage.",
            ]
            for row in result["method_summary"].itertuples(index=False):
                lines.append(
                    "{}: districts {}/{}, scarcity-affected districts {}/{}, "
                    "weighted score {:.2f}, straight-line quantity-distance "
                    "{:.2f} km-units".format(
                        row.method,
                        row.districts_covered,
                        row.alerted_districts,
                        row.scarce_districts_covered,
                        row.scarce_districts,
                        row.dispatch_score_weighted_units,
                        row.straight_line_quantity_distance_km,
                    )
                )
            self.comparison_text.configure(state="normal")
            self.comparison_text.delete("1.0", "end")
            self.comparison_text.insert("1.0", "\n".join(lines))
            self.comparison_text.configure(state="disabled")
            self.tabs.select(self.comparison_tab)
            self.status.set("Comparison complete.")
        except (ValueError, RuntimeError, KeyError) as error:
            self.status.set("Comparison failed.")
            messagebox.showerror(
                "Comparison failed", str(error), parent=self.root
            )

    def approve_plan(self):
        if self.preview is None or self.preview["allocations"].empty:
            return
        allocation_count = len(self.preview["allocations"])
        if not messagebox.askyesno(
            "Confirm reservation",
            "Reserve {} proposed allocation row(s) in the local ledger?\n\n"
            "This records a reservation against the workbook snapshot; it does "
            "not notify DDMC or update the inventory workbook.".format(
                allocation_count
            ),
            parent=self.root,
        ):
            return
        try:
            self.reservations = reserve_dispatch_plan(
                self.preview["allocations"],
                self.original_requests,
                self.current_inventory,
                RESERVATIONS_PATH,
            )
            self._update_inventory_tables()
            self.status.set(
                "Reservation recorded in the local ledger. Refreshing preview…"
            )
            self.generate_preview()
        except (OSError, ValueError, RuntimeError, KeyError) as error:
            self.status.set("Reservation failed.")
            messagebox.showerror(
                "Reservation failed", str(error), parent=self.root
            )

    @staticmethod
    def _fill_table(tree, frame, columns):
        tree.delete(*tree.get_children())
        for column in columns:
            if column in frame.columns:
                tree.column(column, width=max(110, min(220, len(column) * 11)))
        for row in frame.reindex(columns=columns).itertuples(
            index=False, name=None
        ):
            tree.insert("", "end", values=tuple(
                _format_value(value) for value in row
            ))


def main():
    root = tk.Tk()
    ResourceDispatchDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
