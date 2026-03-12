// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

export default function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="border-b border-gray-800/50 pb-2">
      <span className="text-gray-500">{label}: </span>
      <span className="text-gray-200">{value}</span>
    </div>
  );
}