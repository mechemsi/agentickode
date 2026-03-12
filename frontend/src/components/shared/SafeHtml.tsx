// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { renderDescription } from "../../utils/sanitize";

interface SafeHtmlProps {
  html: string;
  className?: string;
}

/**
 * Renders user-provided HTML/Markdown safely.
 * Content is sanitized via DOMPurify in renderDescription().
 */
export default function SafeHtml({ html, className }: SafeHtmlProps) {
  return (
    <div
      className={className}
      // Safe: renderDescription() sanitizes via DOMPurify
      dangerouslySetInnerHTML={{ __html: renderDescription(html) }}
    />
  );
}