// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useEffect, useRef, useCallback } from 'react';
import { useOfficeSocket } from '../../hooks/useOfficeSocket';
import OfficeCanvas from './OfficeCanvas';

interface Props {
  onClose: () => void;
}

export default function OfficeModal({ onClose }: Props) {
  const { rooms, agents, connected, onEvent } = useOfficeSocket(true);
  const backdropRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current) onClose();
  };

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
    >
      <div className="relative w-[95vw] h-[90vh] bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-10 bg-gray-900/90 border-b border-gray-800 flex items-center px-4 z-10">
          <span className="text-sm font-mono text-gray-300">
            Agent Office
            {connected
              ? <span className="ml-2 text-green-400 text-xs">● connected</span>
              : <span className="ml-2 text-red-400 text-xs">● disconnected</span>
            }
          </span>
          <span className="ml-4 text-xs text-gray-500">
            {agents.size} agent{agents.size !== 1 ? 's' : ''} active
          </span>
          <button
            onClick={onClose}
            className="ml-auto text-gray-400 hover:text-white text-sm"
          >
            ESC
          </button>
        </div>
        <div className="pt-10 w-full h-full">
          <OfficeCanvas rooms={rooms} agents={agents} onEvent={onEvent} />
        </div>
      </div>
    </div>
  );
}
