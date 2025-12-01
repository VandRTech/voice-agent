import Link from "next/link";

const cards = [
  {
    title: "Simulate a Call",
    body: "Upload short audio or type a transcript to exercise the voice pipeline without Twilio.",
    href: "/simulate",
  },
  {
    title: "Call Logs",
    body: "Inspect transcripts, retrieved docs, and responses saved in Postgres.",
    href: "/logs",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-900">
      <div className="mx-auto max-w-4xl space-y-10">
        <header className="space-y-4">
          <p className="text-sm uppercase tracking-[0.3em] text-indigo-500">
            Precision Pain & Spine Institute
          </p>
          <h1 className="text-4xl font-semibold tracking-tight">
            Voice Agent Test Console
          </h1>
          <p className="text-base text-slate-600">
            Use the tools below to simulate Twilio conversations with the FastAPI
            backend or to inspect recent persisted call logs. Everything runs
            against the same RAG + Whisper + ElevenLabs pipeline used for live
            calls.
          </p>
        </header>

        <section className="grid gap-6 md:grid-cols-2">
          {cards.map((card) => (
            <Link
              key={card.title}
              href={card.href}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-lg"
            >
              <div className="text-sm font-medium uppercase tracking-wide text-indigo-500">
                {card.title}
              </div>
              <p className="mt-3 text-sm text-slate-600">{card.body}</p>
              <span className="mt-6 inline-flex items-center text-sm font-semibold text-indigo-600">
                Open →
              </span>
            </Link>
          ))}
        </section>

        <section className="rounded-2xl border border-dashed border-slate-200 bg-white/70 p-6 text-sm text-slate-500">
          <p>
            Frontend requests are proxied to the FastAPI backend via{" "}
            <code className="rounded bg-slate-100 px-1 text-xs">/api/*</code>{" "}
            routes. Configure the destination host with{" "}
            <code className="rounded bg-slate-100 px-1 text-xs">
              API_BASE_URL
            </code>{" "}
            (server) or{" "}
            <code className="rounded bg-slate-100 px-1 text-xs">
              NEXT_PUBLIC_API_BASE_URL
            </code>{" "}
            (browser) env vars if you are not running on{" "}
            <span className="font-semibold text-slate-700">http://localhost:8000</span>.
          </p>
        </section>
      </div>
    </main>
  );
}
