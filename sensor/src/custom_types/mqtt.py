from typing import Literal
from pydantic import BaseModel, validator

from .validators import validate_int, validate_str, validate_float
from .sensor_answers import CO2SensorData


class MQTTConfig(BaseModel):
    """fixed params loaded from the environment"""

    station_identifier: str
    mqtt_url: str
    mqtt_port: str
    mqtt_username: str
    mqtt_password: str
    mqtt_base_topic: str

    # validators
    _val_station_identifier = validator(
        "station_identifier", pre=True, allow_reuse=True
    )(
        validate_str(min_len=3, max_len=256),
    )
    _val_mqtt_url = validator("mqtt_url", pre=True, allow_reuse=True)(
        validate_str(min_len=3, max_len=256),
    )
    _val_mqtt_port = validator("mqtt_port", pre=True, allow_reuse=True)(
        validate_str(is_numeric=True),
    )
    _val_mqtt_username = validator("mqtt_username", pre=True, allow_reuse=True)(
        validate_str(min_len=8, max_len=256),
    )
    _val_mqtt_password = validator("mqtt_password", pre=True, allow_reuse=True)(
        validate_str(min_len=8, max_len=256),
    )
    _val_mqtt_base_topic = validator("mqtt_base_topic", pre=True, allow_reuse=True)(
        validate_str(min_len=1, max_len=256, regex=r"^(\/[a-z0-9_-]+)*$"),
    )


class MQTTMessageHeader(BaseModel):
    """meta data for managing message queue"""

    identifier: int | None
    status: Literal["pending", "sent", "delivered"]
    revision: int
    issue_timestamp: float  # 01.01.2022 - 19.01.2038 allowed (4 byte integer)
    success_timestamp: float | None  # 01.01.2022 - 19.01.2038 allowed (4 byte integer)

    # validators
    _val_identifier = validator("identifier", pre=True, allow_reuse=True)(
        validate_int(nullable=True),
    )
    _val_status = validator("status", pre=True, allow_reuse=True)(
        validate_str(allowed=["pending", "sent", "delivered"]),
    )
    _val_revision = validator("revision", pre=True, allow_reuse=True)(
        validate_int(minimum=0, maximum=2_147_483_648),
    )
    _val_issue_timestamp = validator("issue_timestamp", pre=True, allow_reuse=True)(
        validate_float(minimum=1_640_991_600, maximum=2_147_483_648),
    )
    _val_success_timestamp = validator("success_timestamp", pre=True, allow_reuse=True)(
        validate_float(minimum=1_640_991_600, maximum=2_147_483_648, nullable=True),
    )


class MQTTStatusMessageBody(BaseModel):
    """message body which is sent to server"""

    severity: Literal["info", "warning", "error"]
    subject: str
    details: str

    # validators
    _val_severity = validator("severity", pre=True, allow_reuse=True)(
        validate_str(allowed=["info", "warning", "error"]),
    )
    _val_subject = validator("subject", pre=True, allow_reuse=True)(
        validate_str(min_len=1, max_len=1024),
    )
    _val_details = validator("details", pre=True, allow_reuse=True)(
        validate_str(min_len=1, max_len=1024),
    )


class MQTTMeasurementMessageBody(BaseModel):
    """message body which is sent to server"""

    timestamp: int
    value: CO2SensorData


class MQTTStatusMessage(BaseModel):
    """element in local message queue"""

    header: MQTTMessageHeader
    body: MQTTStatusMessageBody


class MQTTMeasurementMessage(BaseModel):
    """element in local message queue"""

    header: MQTTMessageHeader
    body: MQTTMeasurementMessageBody


class ActiveMQTTMessageQueue(BaseModel):
    messages: list[MQTTStatusMessage | MQTTMeasurementMessage]


MQTTMessageBody = MQTTStatusMessageBody | MQTTMeasurementMessageBody
MQTTMessage = MQTTStatusMessage | MQTTMeasurementMessage
