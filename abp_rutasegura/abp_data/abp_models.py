from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

abp_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def abp__utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class abpBase(DeclarativeBase):
    metadata = MetaData(naming_convention=abp_NAMING_CONVENTION)


class abpProjectRecord(abpBase):
    __tablename__ = "proyecto"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_name: Mapped[str] = mapped_column("nombre", String(200))
    abp_use_type: Mapped[str] = mapped_column("tipo_uso", String(30))
    abp_address: Mapped[str] = mapped_column("direccion", String(300), default="")
    abp_created_at: Mapped[datetime] = mapped_column(
        "fecha_creacion", DateTime, default=abp__utcnow
    )
    abp_district: Mapped[str] = mapped_column(
        "distrito", String(120), default="", server_default=""
    )
    abp_province: Mapped[str] = mapped_column(
        "provincia", String(120), default="", server_default=""
    )
    abp_department: Mapped[str] = mapped_column(
        "departamento", String(120), default="", server_default=""
    )
    abp_responsible: Mapped[str] = mapped_column(
        "responsable", String(200), default="", server_default=""
    )
    abp_responsible_role: Mapped[str] = mapped_column(
        "cargo_responsable", String(200), default="", server_default=""
    )
    abp_phone: Mapped[str] = mapped_column("telefono", String(60), default="", server_default="")
    abp_email: Mapped[str] = mapped_column("correo", String(200), default="", server_default="")
    abp_schedule: Mapped[str] = mapped_column("horario", String(200), default="", server_default="")
    abp_notes: Mapped[str] = mapped_column("notas", Text, default="", server_default="")
    abp_logo_path: Mapped[str | None] = mapped_column("logo", Text, nullable=True)

    abp_floors: Mapped[list[abpFloorRecord]] = relationship(
        back_populates="abp_project",
        cascade="all, delete-orphan",
        order_by="abpFloorRecord.abp_level",
    )
    abp_scenarios: Mapped[list[abpScenarioRecord]] = relationship(
        back_populates="abp_project",
        cascade="all, delete-orphan",
        order_by="abpScenarioRecord.abp_id",
    )
    abp_drills: Mapped[list[abpRealDrillRecord]] = relationship(
        back_populates="abp_project",
        cascade="all, delete-orphan",
        order_by="abpRealDrillRecord.abp_id",
    )


class abpFloorRecord(abpBase):
    __tablename__ = "piso"
    __table_args__ = (UniqueConstraint("proyecto_id", "nivel"),)

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_project_id: Mapped[int] = mapped_column(
        "proyecto_id", ForeignKey("proyecto.id", ondelete="CASCADE"), index=True
    )
    abp_level: Mapped[int] = mapped_column("nivel", Integer)
    abp_original_image: Mapped[str | None] = mapped_column("imagen_original", Text)
    abp_scale_m_per_px: Mapped[float | None] = mapped_column("escala_m_por_px", Float)

    abp_project: Mapped[abpProjectRecord] = relationship(back_populates="abp_floors")
    abp_elements: Mapped[list[abpElementRecord]] = relationship(
        back_populates="abp_floor", cascade="all, delete-orphan", order_by="abpElementRecord.abp_id"
    )
    abp_rooms: Mapped[list[abpRoomRecord]] = relationship(
        back_populates="abp_floor", cascade="all, delete-orphan", order_by="abpRoomRecord.abp_id"
    )


class abpElementRecord(abpBase):
    __tablename__ = "elemento"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_floor_id: Mapped[int] = mapped_column(
        "piso_id", ForeignKey("piso.id", ondelete="CASCADE"), index=True
    )
    abp_kind: Mapped[str] = mapped_column("tipo", String(20))
    abp_geometry: Mapped[str] = mapped_column("geometria", Text)
    abp_width_m: Mapped[float | None] = mapped_column("ancho_m", Float)

    abp_floor: Mapped[abpFloorRecord] = relationship(back_populates="abp_elements")


class abpRoomRecord(abpBase):
    __tablename__ = "ambiente"
    __table_args__ = (UniqueConstraint("piso_id", "nombre"),)

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_floor_id: Mapped[int] = mapped_column(
        "piso_id", ForeignKey("piso.id", ondelete="CASCADE"), index=True
    )
    abp_name: Mapped[str] = mapped_column("nombre", String(200))
    abp_use: Mapped[str] = mapped_column("uso", String(30))
    abp_category: Mapped[str] = mapped_column(
        "categoria", String(40), default="", server_default=""
    )
    abp_exit_name: Mapped[str] = mapped_column("salida", String(80), default="", server_default="")
    abp_polygon: Mapped[str] = mapped_column("poligono", Text)
    abp_area_m2: Mapped[float | None] = mapped_column("area_m2", Float)

    abp_floor: Mapped[abpFloorRecord] = relationship(back_populates="abp_rooms")
    abp_occupancies: Mapped[list[abpOccupancyRecord]] = relationship(
        back_populates="abp_room", cascade="all, delete-orphan"
    )


class abpPersonProfileRecord(abpBase):
    __tablename__ = "perfil_persona"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_name: Mapped[str] = mapped_column("nombre", String(100), unique=True)
    abp_max_speed_mps: Mapped[float] = mapped_column("vel_max_mps", Float)
    abp_reaction_mean_s: Mapped[float] = mapped_column("reaccion_media_s", Float)
    abp_reaction_std_s: Mapped[float] = mapped_column("reaccion_desv_s", Float)
    abp_radius_m: Mapped[float] = mapped_column("radio_m", Float)


class abpScenarioRecord(abpBase):
    __tablename__ = "escenario"
    __table_args__ = (UniqueConstraint("proyecto_id", "nombre"),)

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_project_id: Mapped[int] = mapped_column(
        "proyecto_id", ForeignKey("proyecto.id", ondelete="CASCADE"), index=True
    )
    abp_name: Mapped[str] = mapped_column("nombre", String(200))
    abp_blocked_exits: Mapped[list[str]] = mapped_column("salidas_bloqueadas", JSON, default=list)
    abp_seed: Mapped[int] = mapped_column("semilla", Integer)
    abp_description: Mapped[str] = mapped_column("descripcion", Text, default="", server_default="")
    abp_reaction_factor: Mapped[float] = mapped_column(
        "factor_reaccion", Float, default=1.0, server_default="1.0"
    )
    abp_speed_factor: Mapped[float] = mapped_column(
        "factor_velocidad", Float, default=1.0, server_default="1.0"
    )
    abp_runs: Mapped[int] = mapped_column("corridas", Integer, default=1, server_default="1")
    abp_routes: Mapped[list[dict[str, Any]]] = mapped_column(
        "rutas", JSON, default=list, server_default="[]"
    )

    abp_project: Mapped[abpProjectRecord] = relationship(back_populates="abp_scenarios")
    abp_occupancies: Mapped[list[abpOccupancyRecord]] = relationship(
        back_populates="abp_scenario",
        cascade="all, delete-orphan",
        order_by="abpOccupancyRecord.abp_id",
    )
    abp_simulations: Mapped[list[abpSimulationRecord]] = relationship(
        back_populates="abp_scenario",
        cascade="all, delete-orphan",
        order_by="abpSimulationRecord.abp_id",
    )


class abpOccupancyRecord(abpBase):
    __tablename__ = "ocupacion"
    __table_args__ = (UniqueConstraint("escenario_id", "ambiente_id", "perfil_id"),)

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_scenario_id: Mapped[int] = mapped_column(
        "escenario_id", ForeignKey("escenario.id", ondelete="CASCADE"), index=True
    )
    abp_room_id: Mapped[int] = mapped_column(
        "ambiente_id", ForeignKey("ambiente.id", ondelete="CASCADE"), index=True
    )
    abp_profile_id: Mapped[int] = mapped_column(
        "perfil_id", ForeignKey("perfil_persona.id", ondelete="RESTRICT")
    )
    abp_count: Mapped[int] = mapped_column("cantidad", Integer)

    abp_scenario: Mapped[abpScenarioRecord] = relationship(back_populates="abp_occupancies")
    abp_room: Mapped[abpRoomRecord] = relationship(back_populates="abp_occupancies")
    abp_profile: Mapped[abpPersonProfileRecord] = relationship()


class abpSimulationRecord(abpBase):
    __tablename__ = "simulacion"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_scenario_id: Mapped[int] = mapped_column(
        "escenario_id", ForeignKey("escenario.id", ondelete="CASCADE"), index=True
    )
    abp_seed: Mapped[int] = mapped_column("semilla", Integer)
    abp_total_time_s: Mapped[float] = mapped_column("tiempo_total_s", Float)
    abp_time_per_exit_s: Mapped[dict[str, float]] = mapped_column("tiempo_por_salida", JSON)
    abp_trajectories_path: Mapped[str | None] = mapped_column("ruta_trayectorias", Text)
    abp_created_at: Mapped[datetime] = mapped_column("fecha", DateTime, default=abp__utcnow)
    abp_statistics: Mapped[dict[str, Any] | None] = mapped_column(
        "estadisticas", JSON, nullable=True
    )
    abp_fingerprint: Mapped[str] = mapped_column(
        "huella_plano", String(64), default="", server_default=""
    )

    abp_scenario: Mapped[abpScenarioRecord] = relationship(back_populates="abp_simulations")
    abp_observations: Mapped[list[abpObservationRecord]] = relationship(
        back_populates="abp_simulation",
        cascade="all, delete-orphan",
        order_by="abpObservationRecord.abp_id",
    )


class abpObservationRecord(abpBase):
    __tablename__ = "observacion"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_simulation_id: Mapped[int] = mapped_column(
        "simulacion_id", ForeignKey("simulacion.id", ondelete="CASCADE"), index=True
    )
    abp_kind: Mapped[str] = mapped_column("tipo", String(20))
    abp_description: Mapped[str] = mapped_column("descripcion", Text)
    abp_norm: Mapped[str | None] = mapped_column("norma", String(100))
    abp_article: Mapped[str | None] = mapped_column("articulo_rne", String(100))
    abp_verified: Mapped[bool] = mapped_column("verificado", Boolean, default=True)
    abp_location: Mapped[str | None] = mapped_column("ubicacion", Text)
    abp_recommendation: Mapped[str] = mapped_column("recomendacion", Text)

    abp_simulation: Mapped[abpSimulationRecord] = relationship(back_populates="abp_observations")


class abpRealDrillRecord(abpBase):
    __tablename__ = "simulacro_real"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_project_id: Mapped[int] = mapped_column(
        "proyecto_id", ForeignKey("proyecto.id", ondelete="CASCADE"), index=True
    )
    abp_drill_date: Mapped[date] = mapped_column("fecha", Date)
    abp_participants: Mapped[int] = mapped_column("participantes", Integer)
    abp_total_time_s: Mapped[float] = mapped_column("tiempo_total_s", Float)
    abp_time_per_exit_s: Mapped[dict[str, float]] = mapped_column("tiempos_por_salida", JSON)

    abp_project: Mapped[abpProjectRecord] = relationship(back_populates="abp_drills")


class abpRuleVerificationRecord(abpBase):
    __tablename__ = "verificacion_regla"

    abp_id: Mapped[int] = mapped_column("id", Integer, primary_key=True)
    abp_rule_id: Mapped[str] = mapped_column("regla_id", String(80), unique=True)
    abp_value: Mapped[float | None] = mapped_column("valor", Float, nullable=True)
    abp_norm: Mapped[str] = mapped_column("norma", String(120))
    abp_article: Mapped[str] = mapped_column("articulo", String(120))
    abp_source: Mapped[str] = mapped_column("fuente", Text, default="")
    abp_verified: Mapped[bool] = mapped_column("verificado", Boolean, default=True)
    abp_verified_by: Mapped[str] = mapped_column("verificado_por", String(200), default="")
    abp_verified_on: Mapped[date | None] = mapped_column("fecha", Date, nullable=True)
