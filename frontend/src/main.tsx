// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { ConfirmProvider } from "./components/shared/ConfirmDialog";
import { ToastProvider } from "./components/shared/Toast";
import AgentSettingsPage from "./pages/AgentSettings";
import Dashboard from "./pages/Dashboard";
import GpuDashboard from "./pages/GpuDashboard";
import RoleConfigs from "./pages/RoleConfigs";
import NewRun from "./pages/NewRun";
import Projects from "./pages/Projects";
import RunDetail from "./pages/RunDetail";
import Settings from "./pages/Settings";
import WorkflowTemplates from "./pages/WorkflowTemplates";
import WorkspaceServers from "./pages/WorkspaceServers";
import ErrorBoundary from "./components/shared/ErrorBoundary";
import Nav from "./components/shared/Nav";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ConfirmProvider>
        <ToastProvider>
          <div className="min-h-screen flex flex-col">
            <Nav />
            <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">
              <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/runs/new" element={<NewRun />} />
                <Route path="/runs/:id" element={<RunDetail />} />
                <Route path="/projects" element={<Projects />} />
                <Route path="/workspace-servers" element={<WorkspaceServers />} />
                <Route path="/roles" element={<RoleConfigs />} />
                <Route path="/gpu-dashboard" element={<GpuDashboard />} />
                <Route path="/agents" element={<AgentSettingsPage />} />
                <Route path="/workflows" element={<WorkflowTemplates />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
              </ErrorBoundary>
            </main>
          </div>
        </ToastProvider>
      </ConfirmProvider>
    </BrowserRouter>
  </StrictMode>,
);