import asyncio
import contextlib
import json

import asyncpg
import starlette.applications
import starlette.responses
import starlette.routing

import app.database as database
import app.errors as errors
import app.mqtt as mqtt
import app.settings as settings
import app.validation as validation
from app.logs import logger


async def get_status(request):
    """Return some status information about the server."""
    return starlette.responses.JSONResponse(
        status_code=200,
        content={
            "environment": settings.ENVIRONMENT,
            "commit_sha": settings.COMMIT_SHA,
            "branch_name": settings.BRANCH_NAME,
            "start_time": settings.START_TIME,
        },
    )


@validation.validate(schema=validation.PostSensorsRequest)
async def post_sensors(request):
    """Create a new sensor and configuration."""
    try:
        async with database_client.transaction():
            # Insert sensor
            query, arguments = database.build(
                template="create-sensor.sql",
                template_arguments={},
                query_arguments={"sensor_name": request.body.sensor_name},
            )
            result = await database_client.fetch(query, *arguments)
            sensor_identifier = database.dictify(result)[0]["sensor_identifier"]
            # Create new configuration
            query, arguments = database.build(
                template="create-configuration.sql",
                template_arguments={},
                query_arguments={
                    "sensor_identifier": sensor_identifier,
                    "configuration": request.body.configuration,
                },
            )
            result = await database_client.fetch(query, *arguments)
            revision = database.dictify(result)[0]["revision"]
        # Send MQTT message
        await mqtt_client.publish_configuration(
            sensor_identifier=sensor_identifier,
            revision=revision,
            configuration=request.body.configuration,
        )
    except asyncpg.exceptions.UniqueViolationError:
        logger.warning("[POST /sensors] Sensor already exists")
        raise errors.ConflictError()
    except Exception as e:
        logger.error(f"[POST /sensors] Unknown error: {repr(e)}")
        raise errors.InternalServerError()
    # Return successful response
    # TODO Return sensor_identifier and revision? Same for PUT?
    return starlette.responses.JSONResponse(status_code=201, content=None)


@validation.validate(schema=validation.PutSensorsRequest)
async def put_sensors(request):
    """Update an existing sensor's configuration."""
    try:
        async with database_client.transaction():
            # Update sensor
            query, arguments = database.build(
                template="update-sensor.sql",
                template_arguments={},
                query_arguments={
                    "sensor_name": request.path.sensor_name,
                    "new_sensor_name": request.body.sensor_name,
                },
            )
            result = await database_client.fetch(query, *arguments)
            sensor_identifier = database.dictify(result)[0]["sensor_identifier"]
            # Create new configuration
            query, arguments = database.build(
                template="create-configuration.sql",
                template_arguments={},
                query_arguments={
                    "sensor_identifier": sensor_identifier,
                    "configuration": request.body.configuration,
                },
            )
            result = await database_client.fetch(query, *arguments)
            revision = database.dictify(result)[0]["revision"]
        # Send MQTT message
        await mqtt_client.publish_configuration(
            sensor_identifier=sensor_identifier,
            revision=revision,
            configuration=request.body.configuration,
        )
    except IndexError:
        logger.warning("[PUT /sensors] Sensor doesn't exist")
        raise errors.NotFoundError()
    except Exception as e:
        logger.error(f"[PUT /sensors] Unknown error: {repr(e)}")
        raise errors.InternalServerError()
    # Return successful response
    return starlette.responses.JSONResponse(status_code=204, content=None)


class ServerSentEvent:
    def __init__(self, data: dict):
        self.data = data

    def encode(self):
        return f"data: {json.dumps(self.data)}\n\n"


@validation.validate(schema=validation.StreamSensorsRequest)
async def stream_sensors(request):
    """Stream aggregated information about sensors via Server Sent Events.

    This includes:
      - the number of measurements in 4 hour intervals over the last 28 days
    Ideas:
      - last sensor heartbeats
      - last measurement timestamps
    """

    # first version: just return new aggregation in fixed interval
    # improvements:
    # - use a cache (redis?) to store the last aggregation?
    # - then we can return the cached value immediately and update the cache when a new
    #   measurement comes in
    # - or better: re-aggregate fixed interval, but only if there are new measurements

    async def stream(request):
        while True:
            query, arguments = database.build(
                template="aggregate-measurements.sql",
                template_arguments={},
                query_arguments={
                    "sensor_names": request.query.sensor_names,
                },
            )
            result = await database_client.fetch(query, *arguments)
            yield ServerSentEvent(data=database.dictify(result)).encode()
            await asyncio.sleep(5)

    # was geben wir hier zurueck? sensor_name oder sensor_identifier?
    # sensor_name ist schwierig, weil sich der aendern kann
    # sensor_identifier waere ok, aber dann muss der client das mapping kennen

    return starlette.responses.StreamingResponse(
        content=stream(request),
        status_code=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def get_sensors(request):
    """Return configurations of selected sensors."""
    raise errors.NotImplementedError()


@validation.validate(schema=validation.GetMeasurementsRequest)
async def get_measurements(request):
    """Return measurements sorted chronologically, optionally filtered."""
    try:
        query, arguments = database.build(
            template="fetch-measurements.sql",
            template_arguments={"request": request},
            query_arguments={
                "sensor_identifiers": request.query.sensors,
                "start_timestamp": request.query.start,
                "end_timestamp": request.query.end,
                "skip": request.query.skip,
                "limit": request.query.limit,
            },
        )
        # TODO limiting size and paginating is fine for now, but we should also
        # either implement streaming or some other way to export the data in different
        # formats (parquet, ...)
        result = await database_client.fetch(query, *arguments)
    except Exception as e:
        logger.error(f"[PUT /sensors] Unknown error: {repr(e)}")
        raise errors.InternalServerError()
    # Return successful response
    return starlette.responses.JSONResponse(
        status_code=200,
        content=database.dictify(result),
    )


database_client = None
mqtt_client = None


@contextlib.asynccontextmanager
async def lifespan(app):
    """Manage lifetime of database client and MQTT client.

    This creates the necessary database tables if they don't exist yet. It also starts
    a new asyncio task that listens for incoming sensor measurements over MQTT messages
    and stores them in the database.
    """
    global database_client
    global mqtt_client
    async with database.Client() as x:
        async with mqtt.Client(x) as y:
            # Make clients globally available
            database_client = x
            mqtt_client = y
            # Start MQTT listener in (unawaited) asyncio task
            loop = asyncio.get_event_loop()
            task = loop.create_task(mqtt_client.listen())

            # TODO Spawn tasks for configurations that have not yet been sent

            yield
            task.cancel()


app = starlette.applications.Starlette(
    routes=[
        starlette.routing.Route(
            path="/status",
            endpoint=get_status,
            methods=["GET"],
        ),
        starlette.routing.Route(
            path="/sensors",
            endpoint=post_sensors,
            methods=["POST"],
        ),
        starlette.routing.Route(
            path="/sensors/{sensor_name}",
            endpoint=put_sensors,
            methods=["PUT"],
        ),
        starlette.routing.Route(
            path="/sensors",
            endpoint=get_sensors,
            methods=["GET"],
        ),
        starlette.routing.Route(
            path="/measurements",
            endpoint=get_measurements,
            methods=["GET"],
        ),
        starlette.routing.Route(
            path="/streams/sensors",
            endpoint=stream_sensors,
            methods=["GET"],
        ),
    ],
    lifespan=lifespan,
)
