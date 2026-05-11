from __future__ import annotations
import math
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text, Enum, JSON
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session
import enum

from app.core.config import get_app_data_dir

DB_PATH = get_app_data_dir() / "mymini3d.db"


class Base(DeclarativeBase):
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MachineStatus(str, enum.Enum):
    offline = "offline"
    idle = "idle"
    busy = "busy"
    error = "error"


class JobSheetStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    archived = "archived"


class RunStatus(str, enum.Enum):
    queued = "queued"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Machine(Base):
    __tablename__ = "machines"
    id             = Column(Integer, primary_key=True)
    name           = Column(String(100), nullable=False)
    usb_vendor_id    = Column(String(10),  default="1a86")
    usb_product_id   = Column(String(10),  default="5512")
    serial_number    = Column(String(100), default="")
    usb_device_index = Column(Integer,     default=0)   # 0=first K40, 1=second, etc.
    status         = Column(String(20),  default=MachineStatus.offline)
    bed_width_mm   = Column(Float,  default=400.0)
    bed_height_mm  = Column(Float,  default=400.0)
    notes          = Column(Text,   default="")
    created_at     = Column(DateTime, default=datetime.utcnow)

    # ── General Settings (K40W parity) ──────────────────────────────
    units                = Column(String(4),  default="mm")    # mm | inch
    board_type           = Column(String(20), default="LASER-M2")
    home_upon_initialize = Column(Boolean, default=True)
    home_in_upper_right  = Column(Boolean, default=False)
    x_scale_factor       = Column(Float,   default=1.0)
    y_scale_factor       = Column(Float,   default=1.0)
    wait_for_laser       = Column(Boolean, default=True)
    unlock_rail_after_job= Column(Boolean, default=False)
    preprocess_crc       = Column(Boolean, default=True)
    reduce_memory        = Column(Boolean, default=False)
    max_power_pct        = Column(Integer, default=30)   # M3 Nano only

    # ── Speed & Power ────────────────────────────────────────────────
    raster_speed         = Column(Float,   default=200.0)
    vector_engrave_speed = Column(Float,   default=20.0)
    vector_cut_speed     = Column(Float,   default=8.0)
    raster_power_pct     = Column(Integer, default=100)
    vector_engrave_power = Column(Integer, default=100)
    vector_cut_power     = Column(Integer, default=16)

    # ── Raster Settings ──────────────────────────────────────────────
    scanline_step        = Column(Float,   default=0.002)   # inches
    engrave_bottom_up    = Column(Boolean, default=False)
    halftone_dither      = Column(Boolean, default=True)
    halftone_resolution  = Column(Integer, default=500)     # dpi
    slope_black          = Column(Float,   default=2.5)
    slope_white          = Column(Float,   default=0.5)
    transition           = Column(Float,   default=3.5)

    # ── Rotary Settings ──────────────────────────────────────────────
    use_rotary           = Column(Boolean, default=False)
    rotary_scale_y       = Column(Float,   default=1.0)
    rotary_rapid_speed   = Column(Float,   default=0.0)

    # ── Advanced Settings ────────────────────────────────────────────
    raster_color         = Column(Boolean, default=False)
    mirror_design        = Column(Boolean, default=False)
    rotate_design        = Column(Boolean, default=False)
    use_input_csys       = Column(Boolean, default=False)
    cut_inside_first     = Column(Boolean, default=True)
    group_engrave_tasks  = Column(Boolean, default=False)
    group_vector_tasks   = Column(Boolean, default=False)
    raster_passes        = Column(Integer, default=1)
    vector_engrave_passes= Column(Integer, default=1)
    vector_cut_passes    = Column(Integer, default=1)

    runs: List["JobRun"] = relationship("JobRun", back_populates="machine")


class Product(Base):
    __tablename__ = "products"
    id             = Column(Integer, primary_key=True)
    name           = Column(String(200), nullable=False)
    category       = Column(String(200), default="")   # e.g. "2026 HOTWHEEL"
    folder_path    = Column(String(500), default="")   # full path to product folder on disk
    sku            = Column(String(100), default="")
    description    = Column(Text,   default="")
    units_per_sheet= Column(Integer, default=1)
    thumbnail_path = Column(String(500), default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    files: List["ProductFile"] = relationship(
        "ProductFile", back_populates="product",
        order_by="ProductFile.file_order", cascade="all, delete-orphan"
    )
    job_items: List["JobItem"] = relationship("JobItem", back_populates="product")

    @property
    def main_files(self):
        return [f for f in self.files if f.file_role == "main"]

    @property
    def part_files(self):
        return [f for f in self.files if f.file_role == "part"]

    def sheets_needed(self, quantity: int) -> int:
        return math.ceil(quantity / max(1, self.units_per_sheet))


class ProductFile(Base):
    __tablename__ = "product_files"
    id           = Column(Integer, primary_key=True)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=False)
    file_order   = Column(Integer, default=1)
    file_path    = Column(String(500), nullable=False)
    file_type    = Column(String(10),  default="svg")   # svg | dxf
    file_role    = Column(String(10),  default="main")  # main | part
    part_name    = Column(String(200), default="")      # user-given name for parts
    sheet_number = Column(Integer,     default=1)       # sheet 1, 2, 3… for main files
    label        = Column(String(100), default="")      # display label (legacy)
    product: "Product" = relationship("Product", back_populates="files")


class JobSheet(Base):
    __tablename__ = "job_sheets"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    status = Column(String(20), default=JobSheetStatus.open)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)
    items: List["JobItem"] = relationship(
        "JobItem", back_populates="job_sheet", cascade="all, delete-orphan"
    )

    @property
    def total_items(self) -> int:
        return sum(i.quantity_total for i in self.items)

    @property
    def completed_items(self) -> int:
        return sum(i.quantity_completed for i in self.items)

    @property
    def progress_pct(self) -> float:
        t = self.total_items
        return (self.completed_items / t * 100) if t > 0 else 0.0


class JobItem(Base):
    __tablename__ = "job_items"
    id = Column(Integer, primary_key=True)
    job_sheet_id = Column(Integer, ForeignKey("job_sheets.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_total = Column(Integer, default=0)
    quantity_in_progress = Column(Integer, default=0)
    quantity_completed = Column(Integer, default=0)
    cut_type      = Column(String(10), default="full")   # "full" | "parts"
    main_file_id  = Column(Integer, ForeignKey("product_files.id"), nullable=True)
    part_file_ids = Column(Text, default="[]")           # JSON list of ProductFile ids
    created_at = Column(DateTime, default=datetime.utcnow)
    job_sheet: "JobSheet" = relationship("JobSheet", back_populates="items")
    product: "Product" = relationship("Product", back_populates="job_items")
    main_file: Optional["ProductFile"] = relationship("ProductFile", foreign_keys=[main_file_id])
    runs: List["JobRun"] = relationship("JobRun", back_populates="job_item", cascade="all, delete-orphan")

    @property
    def quantity_pending(self) -> int:
        return self.quantity_total - self.quantity_in_progress - self.quantity_completed

    @property
    def is_done(self) -> bool:
        return self.quantity_completed >= self.quantity_total


class JobRun(Base):
    """One execution of a cut job — ties a JobItem to a Machine."""
    __tablename__ = "job_runs"
    id = Column(Integer, primary_key=True)
    job_item_id = Column(Integer, ForeignKey("job_items.id"), nullable=False)
    machine_id = Column(Integer, ForeignKey("machines.id"), nullable=True)
    quantity = Column(Integer, default=1)
    file_index = Column(Integer, default=0)   # which ProductFile is being cut
    status = Column(String(20), default=RunStatus.queued)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    job_item: "JobItem" = relationship("JobItem", back_populates="runs")
    machine: Optional["Machine"] = relationship("Machine", back_populates="runs")


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------

def create_db_engine():
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    Base.metadata.create_all(engine)
    _migrate(engine)
    return engine


def _migrate(engine):
    """Add any columns that exist in the models but are missing from the DB.
    Runs safely on every startup — skips columns that already exist."""
    needed = {
        # table_name: [(column_name, sql_type, default)]
        "machines": [
            ("usb_device_index", "INTEGER", "0"),
        ],
        "products": [
            ("category",    "VARCHAR(200)", "''"),
            ("folder_path", "VARCHAR(500)", "''"),
        ],
        "product_files": [
            ("file_role",    "VARCHAR(10)",  "'main'"),
            ("part_name",    "VARCHAR(200)", "''"),
            ("sheet_number", "INTEGER",      "1"),
        ],
        "job_items": [
            ("cut_type",      "VARCHAR(10)", "'full'"),
            ("main_file_id",  "INTEGER",     "NULL"),
            ("part_file_ids", "TEXT",        "'{\"list\": []}'"),
        ],
    }
    with engine.connect() as conn:
        for table, columns in needed.items():
            # Get existing column names for this table
            result = conn.execute(
                __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
            )
            existing = {row[1] for row in result}
            for col_name, col_type, default in columns:
                if col_name not in existing:
                    conn.execute(__import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN "
                        f"{col_name} {col_type} DEFAULT {default}"
                    ))
            conn.commit()


_engine = None
_SessionLocal: Optional[sessionmaker] = None


def get_session() -> Session:
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_db_engine()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _SessionLocal()


def init_db():
    global _engine, _SessionLocal
    _engine = create_db_engine()
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    _seed_defaults()


def _seed_defaults():
    with get_session() as s:
        if s.query(Machine).count() == 0:
            s.add(Machine(name="Laser #1", notes="Primary K40 machine"))
            s.commit()
