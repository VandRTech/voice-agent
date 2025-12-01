"use client";

import { useEffect, useState } from "react";

type Slots = Record<string, string | null | undefined>;

type DeveloperNote = {
  mode?: string;
  slots?: Slots;
  missing_slots?: string[];
  appointment_id?: string | null;
};

type CallLog = {
  call_sid: string;
  phone_number?: string | null;
  transcript?: string | null;
  used_docs?: string[];
  llm_response?: string | null;
  tts_url?: string | null;
  metadata?: {
    developer_note?: DeveloperNote;
  } | null;
  created_at?: string;
};

export default function LogsPage() {
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchLogs() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/call-logs");
      if (!res.ok) {
        throw new Error("Unable to fetch call logs");
      }
      const data = await res.json();
      setLogs(data.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchLogs();
  }, []);

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-6xl flex-col gap-6">
        <div className="flex flex-col gap-2">
          <p className="text-sm uppercase tracking-[0.3em] text-indigo-500">
            Analytics
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <h1 className="text-4xl font-semibold">Recent Call Logs</h1>
            <button
              type="button"
              onClick={fetchLogs}
              className="rounded-full border border-slate-300 px-4 py-1 text-sm font-medium text-slate-700 transition hover:border-indigo-400 hover:text-indigo-600"
            >
              Refresh
            </button>
          </div>
          <p className="text-base text-slate-600">
            Data fetched from Postgres via FastAPI <code>/api/call-logs</code>.
          </p>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-100 text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Call SID</th>
                <th className="px-4 py-3">Caller</th>
                <th className="px-4 py-3">Transcript</th>
                <th className="px-4 py-3">Reply</th>
                <th className="px-4 py-3">Slots / Status</th>
                <th className="px-4 py-3">Docs</th>
                <th className="px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-500">
                    Loading...
                  </td>
                </tr>
              )}
              {!loading && logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                    No call logs found. Trigger a simulation to create one.
                  </td>
                </tr>
              )}
              {!loading &&
                logs.map((log) => (
                  <tr key={log.call_sid}>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">
                      {log.call_sid}
                    </td>
                    <td className="px-4 py-3 text-slate-700">
                      {log.phone_number || "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {truncate(log.transcript)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {truncate(log.llm_response)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {renderSlotStatus(log.metadata?.developer_note)}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {Array.isArray(log.used_docs) && log.used_docs.length > 0
                        ? log.used_docs.join(", ")
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {formatDate(log.created_at)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}

function truncate(value?: string | null, length = 60) {
  if (!value) return "—";
  return value.length > length ? `${value.slice(0, length)}…` : value;
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat("en", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function renderSlotStatus(note?: DeveloperNote) {
  if (!note) return "—";
  if (note.mode === "confirmation") {
    const date = note.slots?.preferred_date ?? "unscheduled date";
    const time = note.slots?.preferred_time ?? "unscheduled time";
    return `Confirmed: ${date} @ ${time}`;
  }
  if (note.missing_slots && note.missing_slots.length > 0) {
    return `Missing: ${note.missing_slots.join(", ")}`;
  }
  if (note.slots) {
    const name = note.slots.patient_name || "Unknown patient";
    return `Collecting details for ${name}`;
  }
  return "In progress";
}

