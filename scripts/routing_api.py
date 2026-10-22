from contextlib import asynccontextmanager
import logging
from pathlib import Path
import json
import sys
from typing import Annotated, Literal, Union

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine

from scripts.route_evacuation import database_url, plan_evacuation
from scripts.route_rescue_dispatch import route_rescue_dispatch


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))
import pandas as pd

from resource_dispatch import solve_allocation
from resource_dispatch.dispatch_safety import (
    inventory_after_reservations,
    load_reservations,
    validate_dispatch_plan,
)
from resource_dispatch.inventory_provider import WorkbookInventoryProvider
from run_allocation_solver import (
    ALLOCATION_DIR,
    RESERVATIONS_PATH,
    _prepare_pending_inputs,
)


LOGGER = logging.getLogger(__name__)
MAP_PAGE = Path(__file__).resolve().parent / "static" / "route_map.html"
ALLOCATION_REQUESTS = ALLOCATION_DIR / "allocation_requests.csv"
ALLOCATION_CANDIDATES = ALLOCATION_DIR / "allocation_candidates.csv"
INVENTORY_PATH = PROJECT_DIR / "Resource_Inventory_5Districts.xlsx"


def _frame_records(frame):
    """Convert pandas scalar and missing values into JSON-safe records."""
    return json.loads(frame.to_json(orient="records", date_format="iso"))


class RescueRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["rescue_dispatch"]
    facility_id: str = Field(min_length=1, max_length=128)
    incident_record_id: str = Field(min_length=1, max_length=128)
    alert_id: str | None = Field(default=None, min_length=1, max_length=128)


class EvacuationRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["evacuation"]
    scenario_id: str = Field(min_length=1, max_length=128)
    alert_id: str | None = Field(default=None, min_length=1, max_length=128)


RouteRequest = Annotated[
    Union[RescueRouteRequest, EvacuationRouteRequest],
    Field(discriminator="mode"),
]


def create_app(engine: Engine | None = None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.engine is None:
            app.state.engine = create_engine(database_url(), pool_pre_ping=True)
            app.state.owns_engine = True
        try:
            yield
        finally:
            if app.state.owns_engine:
                app.state.engine.dispose()
                app.state.engine = None

    app = FastAPI(
        title="Hazard-aware dual routing API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.owns_engine = False
    app.mount(
        "/static",
        StaticFiles(directory=MAP_PAGE.parent),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/map")

    @app.get("/map", include_in_schema=False)
    def map_page():
        return FileResponse(MAP_PAGE, media_type="text/html")

    def get_engine(request: Request):
        if request.app.state.engine is None:
            raise HTTPException(
                status_code=503,
                detail="Routing database is not available",
            )
        return request.app.state.engine

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/route")
    def route(
        payload: RouteRequest,
        routing_engine: Engine = Depends(get_engine),
    ):
        try:
            if isinstance(payload, RescueRouteRequest):
                result = route_rescue_dispatch(
                    routing_engine,
                    payload.facility_id,
                    payload.incident_record_id,
                )
                route_type = "rescue_dispatch"
            else:
                result = plan_evacuation(
                    routing_engine,
                    payload.scenario_id,
                )
                route_type = "evacuation"
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            LOGGER.exception("Routing database request failed")
            raise HTTPException(
                status_code=503,
                detail="Routing database request failed",
            ) from exc

        return {
            "alert_id": payload.alert_id,
            "route_type": route_type,
            "result": result,
        }

    @app.get("/dispatch/preview")
    def dispatch_preview():
        """Compute a fresh, read-only allocation preview for the map dashboard."""
        try:
            missing = [
                str(path) for path in (
                    ALLOCATION_REQUESTS, ALLOCATION_CANDIDATES, INVENTORY_PATH
                ) if not path.is_file()
            ]
            if missing:
                raise FileNotFoundError(
                    "Allocation inputs are missing: {}. Prepare allocation inputs first.".format(
                        ", ".join(missing)
                    )
                )
            requests = pd.read_csv(ALLOCATION_REQUESTS)
            candidates = pd.read_csv(ALLOCATION_CANDIDATES)
            inventory = WorkbookInventoryProvider(INVENTORY_PATH).get_current_inventory()
            reservations = load_reservations(RESERVATIONS_PATH)
            pending_requests, supply, pending_candidates = _prepare_pending_inputs(
                requests, candidates, inventory, reservations
            )
            result = solve_allocation(
                pending_requests,
                supply[["resource_id", "resource_type", "available_count"]],
                pending_candidates,
            )
            validate_dispatch_plan(
                result["allocations"],
                inventory_after_reservations(inventory, reservations),
            )

            location_columns = [
                "alert_id", "requested_resource_type", "resource_id",
                "latitude", "longitude", "resource_latitude",
                "resource_longitude", "hazard_type",
            ]
            locations = pending_candidates[
                [column for column in location_columns if column in pending_candidates]
            ].drop_duplicates(
                ["alert_id", "requested_resource_type", "resource_id"]
            )
            allocations = result["allocations"].merge(
                locations,
                on=["alert_id", "requested_resource_type", "resource_id"],
                how="left",
                validate="one_to_one",
            )
            request_results = result["request_results"]
            return jsonable_encoder({
                "status": "preview",
                "inventory_source": "workbook_snapshot",
                "reservation_records": len(reservations),
                "summary": {
                    "pending_requests": int(len(request_results)),
                    "districts": int(request_results["district"].nunique()),
                    "districts_receiving_allocations": int(
                        allocations["district"].nunique()
                    ) if not allocations.empty else 0,
                    "allocated_units": int(allocations["allocated_quantity"].sum())
                    if not allocations.empty else 0,
                    "unfilled_units": int(request_results["unfilled_quantity"].sum()),
                    "partially_or_unfilled_requests": int(
                        request_results["unfilled_quantity"].gt(0).sum()
                    ),
                },
                "allocations": _frame_records(allocations),
                "requests": _frame_records(request_results),
                "inventory": inventory_after_reservations(
                    inventory, reservations
                ).pipe(_frame_records),
                "notice": (
                    "Preview only. Availability comes from the recorded workbook "
                    "snapshot; this view does not dispatch resources or reserve stock."
                ),
            })
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return app


app = create_app()
