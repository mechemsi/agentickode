# Copyright (c) 2026 Mechemsi. All rights reserved.
# Licensed under AGPLv3. See LICENSE file.
# Commercial licensing: info@mechemsi.com

from sqlalchemy import Boolean, Column, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.models.base import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    channel_type = Column(Text, nullable=False)  # telegram|slack|discord|webhook
    config = Column(JSONB, nullable=False, default=dict)
    events = Column(JSONB, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
