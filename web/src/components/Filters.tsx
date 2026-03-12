'use client'

import { useRouter } from 'next/navigation'
import { useMemo } from 'react'

interface Region {
  sido: string
  sigungu: string
  dong: string
}

interface FiltersProps {
  regions: Region[]
  searchParams: Record<string, string | undefined>
}

export default function Filters({ regions, searchParams }: FiltersProps) {
  const router = useRouter()

  const sido = searchParams.sido ?? ''
  const sigungu = searchParams.sigungu ?? ''
  const dong = searchParams.dong ?? ''
  const yieldMin = searchParams.yield_min ?? ''
  const currentUsage = searchParams.current_usage ?? ''

  const sidos = useMemo(() => [...new Set(regions.map((r) => r.sido))], [regions])
  const sigungus = useMemo(
    () => sido ? [...new Set(regions.filter((r) => r.sido === sido).map((r) => r.sigungu))] : [],
    [regions, sido]
  )
  const dongs = useMemo(
    () => sigungu ? [...new Set(regions.filter((r) => r.sigungu === sigungu).map((r) => r.dong))] : [],
    [regions, sigungu]
  )

  function navigate(updates: Record<string, string>) {
    const params = new URLSearchParams()
    const merged = {
      ...Object.fromEntries(
        Object.entries(searchParams).filter(([, v]) => v !== undefined) as [string, string][]
      ),
      ...updates,
      page: '1',
    }
    Object.entries(merged).forEach(([k, v]) => { if (v) params.set(k, v) })
    router.push(`/?${params.toString()}`)
  }

  return (
    <div className="bg-white rounded-lg shadow-sm p-4 mb-4 flex flex-wrap gap-3 items-end">
      {/* 시/도 */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">시/도</label>
        <select
          className="border rounded px-2 py-1.5 text-sm min-w-[120px]"
          value={sido}
          onChange={(e) => navigate({ sido: e.target.value, sigungu: '', dong: '' })}
        >
          <option value="">전체</option>
          {sidos.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* 시/군/구 */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">시/군/구</label>
        <select
          className="border rounded px-2 py-1.5 text-sm min-w-[130px]"
          value={sigungu}
          onChange={(e) => navigate({ sigungu: e.target.value, dong: '' })}
          disabled={!sido}
        >
          <option value="">전체</option>
          {sigungus.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {/* 동 */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">동</label>
        <select
          className="border rounded px-2 py-1.5 text-sm min-w-[120px]"
          value={dong}
          onChange={(e) => navigate({ dong: e.target.value })}
          disabled={!sigungu}
        >
          <option value="">전체</option>
          {dongs.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {/* 수익률 최소 */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">최소 수익률 (%)</label>
        <input
          type="number"
          step="0.1"
          min="0"
          placeholder="예: 4.0"
          className="border rounded px-2 py-1.5 text-sm w-28"
          defaultValue={yieldMin}
          onBlur={(e) => navigate({ yield_min: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') navigate({ yield_min: (e.target as HTMLInputElement).value })
          }}
        />
      </div>

      {/* 현재 용도 */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">현재 용도</label>
        <input
          type="text"
          placeholder="예: 병원, 음식점"
          className="border rounded px-2 py-1.5 text-sm w-32"
          defaultValue={currentUsage}
          onBlur={(e) => navigate({ current_usage: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === 'Enter') navigate({ current_usage: (e.target as HTMLInputElement).value })
          }}
        />
      </div>

      {/* 초기화 */}
      <button
        className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded border text-gray-600"
        onClick={() => router.push('/')}
      >
        초기화
      </button>
    </div>
  )
}
