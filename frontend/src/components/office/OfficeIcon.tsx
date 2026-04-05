// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from 'react';
import OfficeModal from './OfficeModal';

export default function OfficeIcon() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="relative px-2 py-1.5 rounded text-gray-400 hover:text-white hover:bg-gray-800/50 text-xs font-mono tracking-tight"
        title="Agent Office"
      >
        <span className="inline-block" style={{ imageRendering: 'pixelated', fontSize: '16px', lineHeight: 1 }}>
          🏢
        </span>
      </button>
      {open && <OfficeModal onClose={() => setOpen(false)} />}
    </>
  );
}
