import { useEffect, useRef, useState } from "react"
import { streamNews } from "@/lib/api/news"
import type { Article } from "@/lib/types/news"

type State =
  | { status: "idle"; articles: [] }
  | { status: "loading"; articles: [] }
  | { status: "success"; articles: Article[] }
  | { status: "error"; articles: []; error: string }

export function useNewsSearch(query: string) {
  const [state, setState] = useState<State>({ status: "idle", articles: [] })
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    // Cleanup previous stream
    if (cleanupRef.current) {
      cleanupRef.current()
      cleanupRef.current = null
    }

    // Skip if query is empty
    if (!query.trim()) {
      setState({ status: "idle", articles: [] })
      return
    }

    // Set loading state
    setState({ status: "loading", articles: [] })

    cleanupRef.current = streamNews({
      query,
      onUpdate: (payload) => {
        setState({ status: "success", articles: payload.articles })
      },
      onDone: (payload) => {
        setState({ status: "success", articles: payload.articles })
      },
      onError: (error) => {
        setState({
          status: "error",
          articles: [],
          error: error.message || "Failed to fetch news",
        })
      },
    })

    // Cleanup: abort on unmount or query change
    return () => {
      if (cleanupRef.current) {
        cleanupRef.current()
        cleanupRef.current = null
      }
    }
  }, [query])

  return state
}
