// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import type { HealthResponse } from "../types";
import { get } from "./client";

export const getHealth = () => get<HealthResponse>("/health");