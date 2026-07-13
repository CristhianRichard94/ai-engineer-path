import Link from "next/link";

export default function HubPage() {
  return (
    <div className="flex flex-1 items-center justify-center font-sans px-4">
      <div className="w-full max-w-md">
        <h1 className="text-2xl font-bold mb-6 text-center">Choose an app</h1>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link
            href="/chat"
            className="block rounded-lg border border-zinc-200 dark:border-zinc-800 p-4 hover:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <h2 className="font-semibold mb-1">AI Chat</h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Chat with the assistant →
            </p>
          </Link>
          <Link
            href="/docbot"
            className="block rounded-lg border border-zinc-200 dark:border-zinc-800 p-4 hover:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <h2 className="font-semibold mb-1">Doc Bot</h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Ask questions about a GitHub repo →
            </p>
          </Link>
        </div>
      </div>
    </div>
  );
}
