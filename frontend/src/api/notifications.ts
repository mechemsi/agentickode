// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type {
  NotificationChannel,
  NotificationChannelCreate,
  NotificationTestResult,
} from "../types";
import { get, post, put, httpDelete } from "./client";

export const getNotificationChannels = () =>
  get<NotificationChannel[]>("/notification-channels");

export const createNotificationChannel = (data: NotificationChannelCreate) =>
  post<NotificationChannel>("/notification-channels", data);

export const updateNotificationChannel = (
  id: number,
  data: Partial<NotificationChannelCreate>,
) => put<NotificationChannel>(`/notification-channels/${id}`, data);

export const deleteNotificationChannel = (id: number) =>
  httpDelete(`/notification-channels/${id}`);

export const testNotificationChannel = (id: number) =>
  post<NotificationTestResult>(`/notification-channels/${id}/test`);