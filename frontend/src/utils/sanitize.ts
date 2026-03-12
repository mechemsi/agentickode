// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import DOMPurify from "dompurify";
import { marked } from "marked";

const HTML_TAG_PATTERN = /<[a-z][\s\S]*>/i;

/**
 * Renders a description string as sanitized HTML.
 *
 * - If the input contains HTML tags, it is sanitized directly with DOMPurify.
 * - Otherwise it is treated as Markdown, parsed with `marked`, then sanitized.
 *
 * Always sanitizes output to prevent XSS.
 */
export function renderDescription(text: string): string {
  const isHtml = HTML_TAG_PATTERN.test(text);

  if (isHtml) {
    return DOMPurify.sanitize(text);
  }

  const parsed = marked(text) as string;
  return DOMPurify.sanitize(parsed);
}