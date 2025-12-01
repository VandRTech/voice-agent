"use client";

import { useMemo, useState } from "react";

type DocumentHit = {
  id: string;
  score: number;
  text: string;
  metadata?: Record<string, unknown>;
};

type Slots = Record<string, string | null | undefined>;

type SimulationResult = {
  call_sid: string;
  transcript: string;
  reply_text: string;
  audio_url: string;
  slots?: Slots;
  missing_slots?: string[];
  appointment_id?: string | null;
  continue_recording?: boolean;
  developer_note?: Record<string, unknown>;
  documents?: DocumentHit[];
};

const MODES = [
  { id: "text", label: "Text Prompt" },
  { id: "audio", label: "Audio Upload" },
] as const;

export default function SimulatePage() {
  const [mode, setMode] = useState<(typeof MODES)[number]["id"]>("text");
  const [text, setText] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [callerId, setCallerId] = useState("+15551234567");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);

  const hasResult = Boolean(result);

  const developerNote = useMemo(() => {
    if (!result?.developer_note) return null;
    return JSON.stringify(result.developer_note, null, 2);
  }, [result]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (mode === "text" && !text.trim()) {
      setError("Please provide a prompt.");
      return;
    }
    if (mode === "audio" && !audioFile) {
      setError("Please select an audio file (<= 20s).");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("from_number", callerId);
      if (mode === "text") {
        formData.append("text", text.trim());
      } else if (audioFile) {
        formData.append("audio", audioFile);
      }

      const response = await fetch("/api/simulate", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const { detail } = await response.json().catch(() => ({
          detail: "Simulation failed",
        }));
        throw new Error(detail || "Simulation failed");
      }

      const data: SimulationResult = await response.json();
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-900">
      <div className="mx-auto flex max-w-5xl flex-col gap-8">
        <div>
          <p className="text-sm uppercase tracking-[0.3em] text-indigo-500">
            Simulation Lab
          </p>
          <h1 className="mt-2 text-4xl font-semibold">Trigger the pipeline</h1>
          <p className="mt-4 text-base text-slate-600">
            Submit short snippets (text or audio) to exercise Whisper →
            Chroma/LLM → ElevenLabs without dialing through Twilio.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="flex flex-wrap gap-2">
            {MODES.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setMode(opt.id)}
                className={`rounded-full px-4 py-2 text-sm font-medium ${
                  mode === opt.id
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="mt-6 space-y-4">
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Caller ID (optional)
              <input
                type="text"
                value={callerId}
                onChange={(e) => setCallerId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-4 py-2 text-sm outline-none focus:border-indigo-400"
                placeholder="+15551234567"
              />
            </label>

            {mode === "text" ? (
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Prompt
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={5}
                  className="mt-2 w-full rounded-lg border border-slate-200 px-4 py-3 text-sm outline-none focus:border-indigo-400"
                  placeholder="Example: Hi, what are your hours tomorrow?"
                />
              </label>
            ) : (
              <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
                Audio File (wav/mp3, &lt;= 20s)
                <input
                  type="file"
                  accept="audio/*"
                  onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)}
                  className="mt-2 block w-full text-sm text-slate-600"
                />
              </label>
            )}
          </div>

          {error && (
            <p className="mt-4 text-sm font-medium text-red-500">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-6 inline-flex items-center rounded-full bg-indigo-600 px-6 py-2 text-sm font-semibold text-white shadow transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Running..." : "Run Simulation"}
          </button>
        </form>

        {hasResult && result && (
          <section className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <header>
              <p className="text-xs uppercase tracking-[0.3em] text-indigo-500">
                Response
              </p>
              <h2 className="mt-2 text-2xl font-semibold">Call {result.call_sid}</h2>
              <p className="text-sm text-slate-500">
                Transcript processed through Whisper/RAG
              </p>
            </header>

            <div className="grid gap-4 md:grid-cols-2">
              <InfoCard title="Transcript" value={result.transcript} />
              <InfoCard title="Reply" value={result.reply_text} />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-xl border border-slate-200 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Audio Preview
                </div>
                <audio
                  className="mt-3 w-full"
                  controls
                  src={result.audio_url}
                  preload="none"
                />
              </div>

              <div className="rounded-xl border border-slate-200 p-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Mode &amp; Confidence
                </div>
                <p className="mt-3 text-base font-semibold text-slate-900">
                  {String(result.developer_note?.mode ?? "slot_filling")}
                </p>
                <p className="text-xs text-slate-500">
                  Docs:{" "}
                  {(result.developer_note?.used_docs as string[])?.join(", ") ||
                    "—"}
                </p>
              </div>
            </div>

            {result.slots && (
              <SlotGrid slots={result.slots} missing={result.missing_slots} />
            )}

            {result.appointment_id && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                Appointment saved with ID {result.appointment_id}. A
                confirmation SMS will be sent to the caller.
              </div>
            )}

            {result.documents && result.documents.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Retrieved Documents
                </h3>
                <div className="mt-3 space-y-3">
                  {result.documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="rounded-xl border border-slate-200 p-4"
                    >
                      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-slate-500">
                        <span>{doc.id}</span>
                        <span className="font-semibold text-indigo-600">
                          {doc.score.toFixed(2)}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-slate-700">{doc.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {developerNote && (
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Developer Note
                </h3>
                <pre className="mt-3 max-h-64 overflow-auto rounded-xl bg-slate-950/90 p-4 text-xs text-slate-100">
                  {developerNote}
                </pre>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}

function InfoCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </div>
      <p className="mt-2 text-sm text-slate-700">{value}</p>
    </div>
  );
}

function SlotGrid({
  slots,
  missing,
}: {
  slots: Slots;
  missing?: string[];
}) {
  const missingSet = new Set(missing ?? []);
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="mb-4 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Slot Progress
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(slots).map(([key, value]) => {
          const isMissing = !value;
          return (
            <div
              key={key}
              className={`rounded-xl border p-3 text-sm ${
                isMissing
                  ? "border-amber-300 bg-amber-50 text-amber-900"
                  : "border-slate-200 bg-slate-50 text-slate-700"
              }`}
            >
              <div className="text-xs uppercase tracking-wide text-slate-500">
                {key.replace(/_/g, " ")}
              </div>
              <p className="mt-1 font-medium">
                {value || `Pending (${missingSet.has(key) ? "needed" : "—"})`}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

