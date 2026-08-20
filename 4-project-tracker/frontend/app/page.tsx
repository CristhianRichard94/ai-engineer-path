"use client";
import { useEffect, useState } from "react";
import TodoList from "@/app/components/todo-list";
import SheetPicker from "@/app/components/sheet-picker";

const STORAGE_KEY = "todo_source";

function getDefaultSource(): string {
  return (
    process.env.NEXT_PUBLIC_TODO_SOURCE ||
    "https://docs.google.com/spreadsheets/d/1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U"
  );
}

// Read localStorage synchronously in the useState initializer (rather than in
// a post-mount useEffect) so the first render already targets the
// previously-selected sheet, instead of briefly rendering the default sheet's
// todos before flipping over.
function getInitialSource(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      return stored;
    }
  } catch {
    // localStorage may be unavailable — fall back to the env default.
  }
  return getDefaultSource();
}

export default function Home() {
  const [source, setSource] = useState<string>(getInitialSource);
  // The server has no access to localStorage, so it always renders using the
  // default source. If the source-dependent tree rendered immediately on the
  // client with the real (possibly non-default) stored source, the client's
  // first render would differ from the server's markup — a hydration
  // mismatch. Render a stable, source-independent placeholder until mounted,
  // so SSR output and the first client render are always identical.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="flex flex-col h-full min-h-0 font-sans">
      <header className="flex flex-col items-center justify-center w-full h-14 shrink-0 border-b border-white/10 backdrop-blur-sm gap-0.5">
        <h1 className="text-lg font-bold tracking-tight text-white">
          TODO App
        </h1>
        {mounted && <SheetPicker source={source} onSourceChange={setSource} />}
      </header>
      <main className="flex flex-1 min-h-0 w-full max-w-3xl mx-auto flex-col items-center gap-3 py-4 px-4 sm:px-6 sm:items-start">
        {mounted ? (
          <TodoList source={source} />
        ) : (
          <div className="w-full flex-1 flex items-center justify-center text-sm text-white/50">
            Loading…
          </div>
        )}
      </main>
      <p className="fixed bottom-4 right-6 z-10 text-xs text-white bg-slate-950/50 border border-white/10 rounded-full px-3 py-1.5 backdrop-blur-md shadow-sm">
        Made with ❤️ by{" "}
        <a
          className="underline underline-offset-2"
          href="https://cristhian-richard.com"
          target="_blank"
          rel="noopener noreferrer"
        >
          Cristhian Richard
        </a>
      </p>
    </div>
  );
}
