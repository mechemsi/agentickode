// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ConfirmProvider } from "../components/shared/ConfirmDialog";
import { ToastProvider } from "../components/shared/Toast";

const mockGetNotificationChannels = vi.fn().mockResolvedValue([]);
const mockCreateNotificationChannel = vi.fn().mockResolvedValue({
  id: 1,
  name: "Test TG",
  channel_type: "telegram",
  config: { bot_token: "123", chat_id: "-100" },
  events: ["run_started"],
  enabled: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
});
const mockDeleteNotificationChannel = vi.fn().mockResolvedValue(undefined);
const mockTestNotificationChannel = vi
  .fn()
  .mockResolvedValue({ success: true, error: null });
const mockUpdateNotificationChannel = vi.fn().mockResolvedValue({});

vi.mock("../api", () => ({
  getNotificationChannels: (...args: unknown[]) =>
    mockGetNotificationChannels(...args),
  createNotificationChannel: (...args: unknown[]) =>
    mockCreateNotificationChannel(...args),
  deleteNotificationChannel: (...args: unknown[]) =>
    mockDeleteNotificationChannel(...args),
  testNotificationChannel: (...args: unknown[]) =>
    mockTestNotificationChannel(...args),
  updateNotificationChannel: (...args: unknown[]) =>
    mockUpdateNotificationChannel(...args),
}));

import NotificationSettings from "../components/settings/NotificationSettings";

function renderComponent() {
  return render(
    <ConfirmProvider>
      <ToastProvider>
        <NotificationSettings />
      </ToastProvider>
    </ConfirmProvider>,
  );
}

describe("NotificationSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetNotificationChannels.mockResolvedValue([]);
  });

  it("renders the heading and add button", async () => {
    renderComponent();
    expect(screen.getByText("Notifications")).toBeInTheDocument();
    expect(screen.getByText("Add Channel")).toBeInTheDocument();
  });

  it("shows empty state when no channels", async () => {
    renderComponent();
    expect(
      await screen.findByText(/No notification channels configured/),
    ).toBeInTheDocument();
  });

  it("shows form when Add Channel is clicked", async () => {
    const user = userEvent.setup();
    renderComponent();
    await user.click(screen.getByText("Add Channel"));
    expect(screen.getByPlaceholderText("My Telegram Channel")).toBeInTheDocument();
  });

  it("renders existing channels", async () => {
    mockGetNotificationChannels.mockResolvedValue([
      {
        id: 1,
        name: "My Telegram",
        channel_type: "telegram",
        config: { bot_token: "x", chat_id: "y" },
        events: ["run_started", "run_failed"],
        enabled: true,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
      {
        id: 2,
        name: "Slack Alerts",
        channel_type: "slack",
        config: { webhook_url: "https://test" },
        events: ["run_completed"],
        enabled: false,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    ]);

    renderComponent();
    expect(await screen.findByText("My Telegram")).toBeInTheDocument();
    expect(await screen.findByText("Slack Alerts")).toBeInTheDocument();
    expect(await screen.findByText("disabled")).toBeInTheDocument();
    expect(await screen.findByText("TG")).toBeInTheDocument();
    expect(await screen.findByText("SL")).toBeInTheDocument();
  });

  it("shows event badges on channels", async () => {
    mockGetNotificationChannels.mockResolvedValue([
      {
        id: 1,
        name: "Ch1",
        channel_type: "discord",
        config: {},
        events: ["run_started", "run_failed"],
        enabled: true,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    ]);

    renderComponent();
    expect(await screen.findByText("run started")).toBeInTheDocument();
    expect(await screen.findByText("run failed")).toBeInTheDocument();
  });

  it("calls test endpoint when Test button clicked", async () => {
    const user = userEvent.setup();
    mockGetNotificationChannels.mockResolvedValue([
      {
        id: 5,
        name: "Test Ch",
        channel_type: "webhook",
        config: { url: "https://test" },
        events: [],
        enabled: true,
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    ]);

    renderComponent();
    const testBtn = await screen.findByText("Test");
    await user.click(testBtn);
    expect(mockTestNotificationChannel).toHaveBeenCalledWith(5);
  });
});