from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Annotated, Literal, Union

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine

from scripts.route_evacuation import database_url, plan_evacuation
from scripts.route_rescue_dispatch import route_rescue_dispatch


LOGGER = logging.getLogger(__name__)
MAP_PAGE = Path(__file__).resolve().parent / "static" / "route_map.html"


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

    return app


app = create_app()
