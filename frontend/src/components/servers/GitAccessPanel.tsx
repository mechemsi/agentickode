// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, Key, Link, Loader2, RefreshCw, Users, X } from "lucide-react";
import { checkGitAccess, generateGitKey, syncGitKeys } from "../../api";
import type { GitAccessStatus, GitProviderStatus, UserGitAccessStatus } from "../../types";

function ProviderBadge({ provider }: { provider: GitProviderStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border ${
        provider.connected
          ? "bg-green-500/5 border-green-800/40 text-green-400"
          : "bg-red-500/5 border-red-800/40 text-red-400"
      }`}
      title={provider.connected ? `Connected as ${provider.username}` : provider.error || "Not connected"}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${provider.connected ? "bg-green-400" : "bg-red-400"}`} />
      {provider.name}
      {provider.connected && provider.username && (
        <span className="text-green-500/70 font-mono">{provider.username}</span>
      )}
      {!provider.connected && (
        <X className="w-3 h-3 text-red-400/60" />
      )}
    </span>
  );
}

function SshKeyDisplay({
  hasKey,
  publicKey,
  keyType,
  copied,
  onCopy,
  onGenerate,
  generating,
  showGenerateButton,
}: {
  hasKey: boolean;
  publicKey: string | null;
  keyType: string | null;
  copied: boolean;
  onCopy: () => void;
  onGenerate: () => void;
  generating: boolean;
  showGenerateButton: boolean;
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1.5">
        <Key className="w-3.5 h-3.5 text-gray-400" />
        <span className="text-xs font-medium text-gray-300">SSH Key</span>
        {keyType && (
          <span className="text-xs text-gray-500 font-mono">{keyType}</span>
        )}
      </div>
      {hasKey && publicKey ? (
        <div className="flex items-center gap-2">
          <code className="flex-1 text-xs font-mono bg-gray-800/80 border border-gray-700/50 rounded px-2.5 py-1.5 text-gray-300 truncate">
            {publicKey}
          </code>
          <button
            onClick={onCopy}
            className="text-xs text-gray-400 hover:text-white px-2 py-1.5 rounded hover:bg-gray-700/50 transition-colors shrink-0"
            title="Copy public key"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">No SSH key found on server</span>
          {showGenerateButton && (
            <button
              onClick={onGenerate}
              disabled={generating}
              className="text-xs px-2.5 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded transition-colors inline-flex items-center gap-1"
            >
              {generating ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Key className="w-3 h-3" />
                  Generate Key
                </>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function UserGitSection({
  userStatus,
  isMainUser,
  index,
  copied,
  onCopy,
  onGenerate,
  generating,
}: {
  userStatus: UserGitAccessStatus;
  isMainUser: boolean;
  index: number;
  copied: boolean;
  onCopy: (key: string) => void;
  onGenerate: () => void;
  generating: boolean;
}) {
  const label = isMainUser ? "SSH user" : "worker user";

  return (
    <div className={index > 0 ? "pt-3 mt-3 border-t border-gray-700/40" : ""}>
      <div className="flex items-center gap-2 mb-2">
        <Users
          className={`w-3.5 h-3.5 ${userStatus.has_key ? "text-blue-400" : "text-gray-500"}`}
        />
        <span
          className={`text-xs font-semibold font-mono ${
            userStatus.has_key ? "text-blue-300" : "text-gray-500"
          }`}
        >
          {userStatus.user}
        </span>
        <span className="text-xs text-gray-600">({label})</span>
      </div>

      <div className="space-y-3 pl-1">
        <SshKeyDisplay
          hasKey={userStatus.has_key}
          publicKey={userStatus.public_key}
          keyType={userStatus.key_type}
          copied={copied && isMainUser}
          onCopy={() => userStatus.public_key && onCopy(userStatus.public_key)}
          onGenerate={onGenerate}
          generating={generating}
          showGenerateButton={isMainUser}
        />

        {userStatus.providers.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {userStatus.providers.map((p) => (
              <ProviderBadge key={p.host} provider={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function GitAccessPanel({ serverId }: { serverId: number }) {
  const [status, setStatus] = useState<GitAccessStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await checkGitAccess(serverId);
      setStatus(result);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, [serverId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await generateGitKey(serverId);
      setStatus(result);
      // Re-check providers after key generation
      const full = await checkGitAccess(serverId);
      setStatus(full);
    } catch {
      // keep existing status
    } finally {
      setGenerating(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await syncGitKeys(serverId);
      setStatus(result);
    } catch {
      // keep existing status
    } finally {
      setSyncing(false);
    }
  };

  const handleCopy = async (key: string) => {
    await window.navigator.clipboard.writeText(key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCopyMain = async () => {
    if (status?.public_key) {
      await handleCopy(status.public_key);
    }
  };

  if (loading && !status) {
    return (
      <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
        <Loader2 className="w-3 h-3 animate-spin" />
        Checking git access...
      </div>
    );
  }

  const hasByUser = (status?.by_user?.length ?? 0) > 0;

  return (
    <div className="space-y-3">
      {hasByUser ? (
        <>
          {status!.by_user.map((userStatus, index) => (
            <UserGitSection
              key={userStatus.user}
              userStatus={userStatus}
              isMainUser={index === 0}
              index={index}
              copied={copied}
              onCopy={handleCopy}
              onGenerate={handleGenerate}
              generating={generating}
            />
          ))}
          <div className="flex justify-end gap-2">
            {status!.by_user.length > 1 && status!.by_user[0]?.has_key && (
              <button
                onClick={handleSync}
                disabled={syncing}
                className="text-xs text-blue-400 hover:text-blue-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-blue-700/20 transition-colors disabled:opacity-50"
                title="Copy root SSH keys to worker user"
              >
                {syncing ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Link className="w-3 h-3" />
                )}
                Sync Keys
              </button>
            )}
            <button
              onClick={load}
              disabled={loading}
              className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
              Test All
            </button>
          </div>
        </>
      ) : (
        <>
          {/* SSH Key Section — flat/legacy display */}
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <Key className="w-3.5 h-3.5 text-gray-400" />
              <span className="text-xs font-medium text-gray-300">SSH Key</span>
              {status?.key_type && (
                <span className="text-xs text-gray-500 font-mono">{status.key_type}</span>
              )}
            </div>
            {status?.has_key && status.public_key ? (
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs font-mono bg-gray-800/80 border border-gray-700/50 rounded px-2.5 py-1.5 text-gray-300 truncate">
                  {status.public_key}
                </code>
                <button
                  onClick={handleCopyMain}
                  className="text-xs text-gray-400 hover:text-white px-2 py-1.5 rounded hover:bg-gray-700/50 transition-colors shrink-0"
                  title="Copy public key"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">No SSH key found on server</span>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="text-xs px-2.5 py-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded transition-colors inline-flex items-center gap-1"
                >
                  {generating ? (
                    <>
                      <Loader2 className="w-3 h-3 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <Key className="w-3 h-3" />
                      Generate Key
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* Git Providers Section */}
          {status?.providers && status.providers.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium text-gray-300">Git Providers</span>
                <button
                  onClick={load}
                  disabled={loading}
                  className="text-xs text-gray-500 hover:text-gray-300 inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-gray-700/50 transition-colors"
                >
                  <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
                  Test All
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {status.providers.map((p) => (
                  <ProviderBadge key={p.host} provider={p} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}