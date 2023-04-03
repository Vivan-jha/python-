from datetime import datetime, timedelta
from tkinter import Menu
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, extract
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import pytz


Base = declarative_base()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "mysql://root:@localhost/loop_monitoring"
db = SQLAlchemy(app)

app.run(debug=True)

class StoreStatus(Base):
    __tablename__ = 'store_status'

    id = Column(Integer, primary_key=True)
    menu_hours_id = Column(Integer, ForeignKey('menu_hours.id'))
    timestamp_utc = Column(DateTime, nullable=False)
    status = Column(Enum('active', 'inactive'), nullable=False)

    menu_hours = relationship('MenuHours', back_populates='statuses')


class MenuHours(Base):
    __tablename__ = 'menu_hours'

    id = Column(Integer, primary_key=True)
    store_id = Column(Integer, ForeignKey('store.id'))
    start_time_local = Column(DateTime)
    end_time_local = Column(DateTime)
    timezone_id = Column(Integer, ForeignKey('timezones.id'))

    store = relationship('Store', back_populates='menu_hours')
    timezone = relationship('Timezone', back_populates='store_hours')
    statuses = relationship('StoreStatus', back_populates='menu_hours')


class Timezone(Base):
    __tablename__ = 'timezones'

    id = Column(Integer, primary_key=True)
    timezone_str = Column(String(50), nullable=False, default='America/Chicago')

    store_hours = relationship('MenuHours', back_populates='timezone')


class Store(Base):
    __tablename__ = 'store'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)

    menu_hours = relationship('MenuHours', back_populates='store')


@app.route('/trigger_report')
def trigger_report():
    # Get the latest timestamp from all observations
    latest_timestamp = db.session.query(func.max(StoreStatus.timestamp_utc)).scalar()

    # Calculate the start and end of the business hours interval for the latest timestamp
    timezone = db.session.query(Timezone).filter_by(store_id=1).first()
    local_start_time = timezone.store_hours.start_time_local
    local_end_time = timezone.store_hours.end_time_local
    local_latest_timestamp = latest_timestamp.astimezone(pytz.timezone(timezone.timezone_str))
    start = datetime.combine(local_latest_timestamp.date(), local_start_time.time())
    end = datetime.combine(local_latest_timestamp.date(), local_end_time.time())

    # Calculate the time intervals for each report period
    hour_interval = (latest_timestamp - timedelta(hours=1), latest_timestamp)
    day_interval = (latest_timestamp - timedelta(days=1), latest_timestamp)
    week_interval = (latest_timestamp - timedelta(weeks=1), latest_timestamp)

    # Query the database for the necessary data
    uptime_last_hour = db.session.query(func.sum(MenuHours.end_time_local - MenuHours.start_time_local)) \
        .filter(MenuHours.store_id == 1) \
        .filter(MenuHours.dayOfWeek == extract('weekday', StoreStatus.timestamp_utc)) \
        .filter(StoreStatus.timestamp_utc >= hour_interval[0]) \
        .filter(StoreStatus.timestamp_utc < hour_interval[1]) \
        .scalar() or 0

    uptime_last_day = db.session.query(func.sum(MenuHours.end_time_local - MenuHours.start_time_local)) \
        .filter(MenuHours.store_id == 1) \
        .filter(MenuHours.dayOfWeek == extract('weekday', StoreStatus.timestamp_utc)) \
        .filter(StoreStatus.timestamp_utc >= day_interval[0]) \
        .filter(StoreStatus.timestamp_utc < day_interval[1]) \
        .scalar() or 0

    uptime_last_week = db.session.query(func.sum(MenuHours.end_time_local - MenuHours.start_time_local))\
        .filter(MenuHours.store_id == 1)\
        .filter(MenuHours.dayOfWeek == extract('weekday', StoreStatus.timestamp_utc))\
        .filter(StoreStatus.timestamp_utc >= week_interval[0])\
        .filter(StoreStatus.timestamp_utc < week_interval[1])\
        .scalar() or 0

    downtime_last_hour = (60 - uptime_last_hour) if (60 - uptime_last_hour) > 0 else 0
    downtime_last_day = (24 - uptime_last_day) if (24 - uptime_last_day) > 0 else 0
    downtime_last_week = (7 * 24 - uptime_last_week) if (7 * 24 - uptime_last_week) > 0 else 0

    # Return the report to the user
    report = {
        'store_id': 1,
        'uptime_last_hour': uptime_last_hour,
        'uptime_last_day': uptime_last_day,
        'uptime_last_week': uptime_last_week,
        'downtime_last_hour': downtime_last_hour,
        'downtime_last_day': downtime_last_day,
        'downtime_last_week': downtime_last_week
    }
    return report
