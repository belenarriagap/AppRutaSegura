from __future__ import annotations

from enum import IntEnum, StrEnum


class abpElementType(StrEnum):
    abp_WALL = "muro"
    abp_DOOR = "puerta"
    abp_EXIT = "salida"
    abp_STAIR = "escalera"
    abp_OBSTACLE = "obstaculo"
    abp_SAFE_ZONE = "zona_segura"
    abp_SIGN = "senal"


class abpSignKind(StrEnum):
    abp_EXIT = "salida"
    abp_DIRECTION = "direccion"
    abp_STAIRS = "escalera"
    abp_SAFE_ZONE = "zona_segura"
    abp_FIRST_AID = "botiquin"
    abp_EMERGENCY_LIGHT = "luz_emergencia"
    abp_EXTINGUISHER = "extintor"
    abp_ALARM = "alarma"
    abp_ELECTRIC_RISK = "riesgo_electrico"
    abp_CAPACITY = "aforo"
    abp_HYDRANT = "hidrante"
    abp_PROHIBITION = "prohibicion"
    abp_MANDATORY = "obligacion"
    abp_WARNING = "advertencia"
    abp_STRETCHER = "camilla"
    abp_EMERGENCY_EXIT = "salida_emergencia"
    abp_SMOKE_DETECTOR = "detector_humo"
    abp_HEAT_DETECTOR = "detector_temperatura"
    abp_STROBE = "luz_estroboscopica"
    abp_MANUAL_STATION = "estacion_manual"
    abp_ALARM_PANEL = "central_alarma"


class abpStairUse(StrEnum):
    abp_AUTO = "automatico"
    abp_UP = "sube"
    abp_DOWN = "baja"
    abp_BOTH = "sube_baja"
    abp_SAME_FLOOR = "mismo_piso"
    abp_OUTSIDE = "exterior"
    abp_CLOSED = "no_se_usa"


class abpUseType(StrEnum):
    abp_EDUCATION = "educacion"
    abp_OFFICE = "oficinas"
    abp_COMMERCE = "comercio"


class abpObservationType(StrEnum):
    abp_NORM = "norma"
    abp_CONGESTION = "congestion"


class abpAgentStatus(IntEnum):
    abp_WAITING = 0
    abp_MOVING = 1
    abp_EVACUATED = 2


class abpCellType(IntEnum):
    abp_FREE = 0
    abp_WALL = 1
    abp_OBSTACLE = 2
    abp_DOOR = 3
    abp_EXIT = 4
    abp_STAIR = 5
    abp_SAFE_ZONE = 6
    abp_OUTSIDE = 7
