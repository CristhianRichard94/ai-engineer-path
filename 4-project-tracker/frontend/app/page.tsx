import TodoList from "@/app/components/todo-list";

export default function Home() {
  const source = process.env.NEXT_PUBLIC_TODO_SOURCE ||
  "https://docs.google.com/spreadsheets/d/1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U"

  return (
    <div className="flex flex-col h-full min-h-0 font-sans">
      <header className="flex flex-col items-center justify-center w-full h-14 shrink-0 border-b border-white/10 backdrop-blur-sm">
        <h1 className="text-lg font-bold tracking-tight text-white">
          TODO App
        </h1>
      </header>
      <main className="flex flex-1 min-h-0 w-full max-w-3xl mx-auto flex-col items-center gap-3 py-4 px-4 sm:px-6 sm:items-start">
        <TodoList source={source} />
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
