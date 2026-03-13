// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  Bot,
  Cpu,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  Menu,
  Plus,
  Server,
  Settings,
  X,
} from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/workspace-servers", label: "Servers", icon: Server },
  { to: "/roles", label: "Roles", icon: Cpu },
  { to: "/gpu-dashboard", label: "GPU", icon: Activity },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/workflows", label: "Workflows", icon: GitBranch },
  { to: "/settings", label: "Settings", icon: Settings },
];

export default function Nav() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);

  return (
    <nav className="bg-gray-900 border-b border-gray-800">
      <div className="max-w-7xl mx-auto px-4 flex items-center h-14 gap-8">
        <span className="text-lg font-bold tracking-tight text-white inline-flex items-center gap-2">
          <Cpu className="w-5 h-5 text-blue-400" />
          AgenticKode
        </span>

        {/* Desktop nav */}
        <div className="hidden md:flex gap-1">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.to}
                to={l.to}
                className={`px-3 py-1.5 rounded text-sm inline-flex items-center gap-1.5 ${
                  pathname === l.to
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-white hover:bg-gray-800/50"
                }`}
              >
                <Icon className="w-4 h-4" />
                {l.label}
              </Link>
            );
          })}
        </div>

        {/* New Run CTA */}
        <div className="hidden md:flex ml-auto">
          <Link
            to="/runs/new"
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm inline-flex items-center gap-1.5 shadow-sm shadow-blue-900/30 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500/40"
          >
            <Plus className="w-4 h-4" />
            New Run
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button
          className="md:hidden ml-auto text-gray-400 hover:text-white"
          onClick={() => setOpen(!open)}
        >
          {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile dropdown */}
      {open && (
        <div className="md:hidden border-t border-gray-800 px-4 py-2 animate-slide-down">
          <Link
            to="/runs/new"
            onClick={() => setOpen(false)}
            className="block px-3 py-2 rounded text-sm flex items-center gap-2 text-blue-400 hover:text-white hover:bg-gray-800/50"
          >
            <Plus className="w-4 h-4" />
            New Run
          </Link>
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.to}
                to={l.to}
                onClick={() => setOpen(false)}
                className={`block px-3 py-2 rounded text-sm flex items-center gap-2 ${
                  pathname === l.to
                    ? "bg-gray-800 text-white"
                    : "text-gray-400 hover:text-white hover:bg-gray-800/50"
                }`}
              >
                <Icon className="w-4 h-4" />
                {l.label}
              </Link>
            );
          })}
        </div>
      )}
    </nav>
  );
}