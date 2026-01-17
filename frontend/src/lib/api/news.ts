import type { Article } from "@/lib/types/news"

export type NewsSearchParams = {
  query: string
  providers?: string[]
  limit?: number
  signal?: AbortSignal
}

export type NewsStreamPayload = {
  provider?: string
  articles: Article[]
}

/**
 * Calls GET /news/search
 * - MUST throw on network failure
 * - MUST return Article[]
 * - MUST support AbortController
 */
export async function fetchNews(
  params: NewsSearchParams
): Promise<Article[]> {
  const baseUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL) || "http://localhost:8000"
  
  const searchParams = new URLSearchParams()
  searchParams.append("q", params.query)
  
  if (params.providers) {
    params.providers.forEach((provider) => {
      searchParams.append("providers", provider)
    })
  }
  
  if (params.limit !== undefined) {
    searchParams.append("limit", String(params.limit))
  }
  
  const url = `${baseUrl}/news/search?${searchParams.toString()}`
  
  const response = await fetch(url, {
    signal: params.signal,
  })
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  
  const data = await response.json()
  return data as Article[]
}

export function streamNews(
  params: Omit<NewsSearchParams, "signal"> & {
    onUpdate: (payload: NewsStreamPayload) => void
    onDone?: (payload: NewsStreamPayload) => void
    onError?: (error: Error) => void
  }
): () => void {
  const baseUrl = (typeof import.meta !== "undefined" && import.meta.env?.VITE_API_BASE_URL) || "http://localhost:8000"

  const searchParams = new URLSearchParams()
  searchParams.append("q", params.query)
  searchParams.append("stream", "true")

  if (params.providers) {
    params.providers.forEach((provider) => {
      searchParams.append("providers", provider)
    })
  }

  if (params.limit !== undefined) {
    searchParams.append("limit", String(params.limit))
  }

  const url = `${baseUrl}/news/search?${searchParams.toString()}`
  const source = new EventSource(url)

  const handleUpdate = (event: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(event.data) as NewsStreamPayload
      params.onUpdate(payload)
    } catch (error) {
      params.onError?.(error as Error)
    }
  }

  const handleDone = (event: MessageEvent<string>) => {
    try {
      const payload = JSON.parse(event.data) as NewsStreamPayload
      params.onDone?.(payload)
    } catch (error) {
      params.onError?.(error as Error)
    } finally {
      source.close()
    }
  }

  source.addEventListener("update", handleUpdate)
  source.addEventListener("done", handleDone)
  source.onerror = () => {
    params.onError?.(new Error("News stream error"))
    source.close()
  }

  return () => {
    source.removeEventListener("update", handleUpdate)
    source.removeEventListener("done", handleDone)
    source.close()
  }
}
