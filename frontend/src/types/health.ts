// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export interface ServiceHealth {
  name: string;
  status: string;
  latency_ms: number | null;
  error: string | null;
}

export interface HealthResponse {
  status: string;
  services: ServiceHealth[];
  worker_running: boolean;
  active_runs: number;
}