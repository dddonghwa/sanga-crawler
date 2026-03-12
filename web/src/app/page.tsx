import { supabase, LISTING_SELECT_COLS } from '@/lib/supabase'
import { Listing } from '@/types/listings'
import Filters from '@/components/Filters'
import ListingsTable from '@/components/ListingsTable'

const PAGE_SIZE = 50

interface SearchParams {
  sido?: string
  sigungu?: string
  dong?: string
  yield_min?: string
  current_usage?: string
  page?: string
}

async function getRegions() {
  const { data } = await supabase
    .from('region_hierarchy')
    .select('sido,sigungu,dong')
    .order('sido')
    .order('sigungu')
    .order('dong')
  return data ?? []
}

async function getListings(params: SearchParams) {
  const page = Number(params.page ?? 1)
  const from = (page - 1) * PAGE_SIZE
  const to = from + PAGE_SIZE - 1

  let query = supabase
    .from('listings_with_yield')
    .select(LISTING_SELECT_COLS, { count: 'exact' })
    .range(from, to)

  if (params.sido) query = query.eq('sido', params.sido)
  if (params.sigungu) query = query.eq('sigungu', params.sigungu)
  if (params.dong) query = query.eq('dong', params.dong)
  if (params.yield_min) query = query.gte('yield_rate', Number(params.yield_min))
  if (params.current_usage) query = query.ilike('current_usage', `%${params.current_usage}%`)

  const { data, count, error } = await query
  if (error) throw error
  return { listings: (data ?? []) as Listing[], total: count ?? 0 }
}

export default async function HomePage({
  searchParams,
}: {
  searchParams: SearchParams
}) {
  const [regions, { listings, total }] = await Promise.all([
    getRegions(),
    getListings(searchParams),
  ])

  const page = Number(searchParams.page ?? 1)
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <main className="max-w-screen-xl mx-auto px-4 py-6">
      <h1 className="text-2xl font-bold mb-6 text-gray-800">
        🏪 상가 매물 수익률 분석
      </h1>
      <Filters regions={regions} searchParams={searchParams} />
      <p className="text-sm text-gray-500 mb-3">
        총 <span className="font-semibold text-gray-700">{total.toLocaleString()}</span>건
      </p>
      <ListingsTable
        listings={listings}
        page={page}
        totalPages={totalPages}
        searchParams={searchParams}
      />
    </main>
  )
}
