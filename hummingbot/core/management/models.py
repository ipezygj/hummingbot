from sqlalchemy import Column, String, Float, JSON
from hummingbot.model.sql_connection_manager import SQLAlchemyBase

class ExecutorEntity(SQLAlchemyBase):
"""
Tämä malli tallentaa executor-tiedot tietokantaan.
"""
tablename = "executors"
