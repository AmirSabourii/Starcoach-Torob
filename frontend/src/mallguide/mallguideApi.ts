// «راهنمای رسیدن داخل پاساژ» — API types + calls (backend: /workspace/torob/eval/playground_mallguide.py)
import { api } from '../api'

export type Src = { title: string; url: string; host?: string }
export type Mode = { key: 'elevator' | 'escalator' | 'stairs'; label: string; text: string; source?: Src | null }
export type Visual =
  | { type: 'building'; lat: number | null; lon: number | null }
  | { type: 'floors'; target: number | null; label: string; levels: number[] | null; half_above?: number | null }
  | { type: 'corridor'; unit: string | null; unit_label?: string; name: string }
  | { type: 'shop'; name: string; unit_label: string | null; open: boolean | null; open_label: string | null; price_toman: number | null; price_label: string | null }
export type Step = {
  n: number; kind: 'arrive' | 'floor' | 'unit' | 'shop'; title: string; text: string; text2?: string; visual: Visual
  source?: Src; modes?: Mode[]; links?: { google: string; neshan: string } | null
  facts?: { key: string; text: string; source: Src | null }[]; photo?: { url: string; source_title: string; source_url: string }
}
export type Guide = {
  eligible: boolean; reason?: string; shop_id: string; shop_name: string; mall: string | null; mall_key: string | null; street: string | null
  floor: { level: number | null; label: string; raw: string } | null; unit: { label: string; raw: string; kind: string } | null
  steps: Step[]; sources: (Src & { n: number })[]; facts_status: 'none' | 'not_fetched' | 'cached' | 'spend_cap' | 'error'
  entry?: { title: string; sub: string }
}

const q = (pid?: string | null) => (pid ? `?pid=${encodeURIComponent(pid)}` : '')
export const getGuide = (sid: string, pid?: string | null) => api<Guide>(`/api/shop/${encodeURIComponent(sid)}/mallguide${q(pid)}`)
/** one cited web lookup per mall (cached on the server forever); returns the same guide with the facts merged */
export const getGuideWithFacts = (sid: string, pid?: string | null) =>
  api<Guide>(`/api/shop/${encodeURIComponent(sid)}/mallguide/facts${q(pid)}`, { body: {}, timeout: 60000 })
