export type Article = {
  source: string
  title: string
  description?: string | null
  url: string
  published_at?: string | number | null
  raw: Record<string, unknown>
}
