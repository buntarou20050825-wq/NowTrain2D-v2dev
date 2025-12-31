# backend/database.py
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Float, Integer, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker

# プロジェクトルートの nowtrain.db を参照する
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nowtrain.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# SQLite はデフォルトでマルチスレッド通信を許可しないため check_same_thread=False が必要
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Station(Base):
    __tablename__ = "stations"

    id = Column(String, primary_key=True, index=True)
    line_id = Column(String, index=True)     # JSONの "railway" (Step1: 単一)
    name_ja = Column(String, nullable=True)
    name_en = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

class StationRank(Base):
    __tablename__ = "station_ranks"

    station_id = Column(String, ForeignKey("stations.id"), primary_key=True, index=True)
    rank = Column(String, nullable=False)          # S, A, B...
    dwell_time = Column(Integer, nullable=False)   # 停車秒

def init_db() -> None:
    """テーブルを作成する"""
    Base.metadata.create_all(bind=engine)
