// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { BASE } from "./client";
import type {
  ExportRequest,
  ImportOptions,
  ImportResult,
  PreviewResult,
} from "../types/backup";

export async function exportConfig(req: ExportRequest): Promise<Blob> {
  const res = await fetch(`${BASE}/backup/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  return res.blob();
}

export async function importPreview(
  file: File,
  options: ImportOptions,
): Promise<PreviewResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("options", JSON.stringify(options));
  const res = await fetch(`${BASE}/backup/import/preview`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Preview failed: ${res.status}`);
  return res.json();
}

export async function importConfig(
  file: File,
  options: ImportOptions,
): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("options", JSON.stringify(options));
  const res = await fetch(`${BASE}/backup/import`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(`Import failed: ${res.status}`);
  return res.json();
}