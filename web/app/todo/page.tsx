import TodoList from "@/app/todo/components/todo-list";

export default function TodoPage() {
  const source = process.env.NEXT_PUBLIC_TODO_SOURCE ||
  "https://docs.google.com/spreadsheets/d/1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U"

  return (
    <div className="flex flex-col h-full min-h-0 bg-zinc-50 font-sans dark:bg-black">
      <header className="flex flex-col items-center justify-center w-full h-14 shrink-0 border-b dark:border-white/20 ">
        <h1 className="text-lg font-bold text-black dark:text-white">
          TODO App
        </h1>
      </header>
      <main className="flex flex-1 min-h-0 w-full max-w-3xl mx-auto flex-col items-center gap-3 py-4 px-4 sm:px-6 bg-white dark:bg-black sm:items-start">
        <TodoList source={source} />
      </main>
    </div>
  );
}
