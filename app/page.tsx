import TodoList from "@/app/components/todo-list";

export default function Home() {
  const source = process.env.NEXT_PUBLIC_TODO_SOURCE ||
  "https://docs.google.com/spreadsheets/d/1U-r0YqCZ2oXnExBnwdVUtEfVx7fgG8oSLaEG79dN23U"

  return (
    <div className="flex flex-col flex-1  justify-center bg-zinc-50 font-sans dark:bg-black">
      <header className="flex flex-col items-center justify-center w-full h-24 border-b dark:border-white/20 ">
        <h1 className="text-3xl font-bold text-black dark:text-white m-4">
          TODO App
        </h1>
      </header>
      <main className="flex flex-1 w-full max-w-3xl flex-col items-center justify-between py-32 px-16 bg-white dark:bg-black sm:items-start">
        <TodoList source={source} />
      </main>
           <p className="text-sm text-black dark:text-white position-absolute bottom-4 right-0 text-center">
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
