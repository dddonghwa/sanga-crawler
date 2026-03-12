'use client'

import { Fragment, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Listing } from '@/types/listings'

interface ListingsTableProps {
  listings: Listing[]
  page: number
  totalPages: number
  searchParams: Record<string, string | undefined>
}

function fmt만원(v: number | null) {
  if (v == null) return '-'
  if (v >= 10000) return `${(v / 10000).toFixed(1)}억`
  return `${v.toLocaleString()}만`
}

function fmtMgmt(원: number | null) {
  if (원 == null) return '-'
  return `${Math.round(원 / 10000).toLocaleString()}만원`
}

export default function ListingsTable({ listings, page, totalPages, searchParams }: ListingsTableProps) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const router = useRouter()

  function navigate(p: number) {
    const params = new URLSearchParams()
    Object.entries(searchParams).forEach(([k, v]) => { if (v) params.set(k, v) })
    params.set('page', String(p))
    router.push(`/?${params.toString()}`)
  }

  return (
    <div>
      <div className="overflow-x-auto rounded-lg shadow-sm">
        <table className="w-full text-sm bg-white border-collapse">
          <thead>
            <tr className="bg-gray-100 text-gray-700 text-left">
              <th className="px-3 py-2 font-medium">지역</th>
              <th className="px-3 py-2 font-medium">현재용도</th>
              <th className="px-3 py-2 font-medium text-right">면적(평)</th>
              <th className="px-3 py-2 font-medium">층</th>
              <th className="px-3 py-2 font-medium text-right">매매가</th>
              <th className="px-3 py-2 font-medium text-right">보증금</th>
              <th className="px-3 py-2 font-medium text-right">월세</th>
              <th className="px-3 py-2 font-medium text-right text-blue-700">수익률</th>
              <th className="px-3 py-2 font-medium">방향</th>
              <th className="px-3 py-2 font-medium">태그</th>
            </tr>
          </thead>
          <tbody>
            {listings.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-12 text-gray-400">
                  조회 결과가 없습니다
                </td>
              </tr>
            )}
            {listings.map((l) => {
              const isExpanded = expandedRow === l.article_no
              return (
                <Fragment key={l.article_no}>
                  <tr
                    className="border-t border-gray-100 hover:bg-blue-50 cursor-pointer transition-colors"
                    onClick={() => setExpandedRow(isExpanded ? null : l.article_no)}
                  >
                    <td className="px-3 py-2 whitespace-nowrap">
                      {l.sido} {l.sigungu}
                      <br />
                      <span className="text-gray-500 text-xs">{l.dong}</span>
                    </td>
                    <td className="px-3 py-2 text-gray-700">{l.current_usage ?? '-'}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {l.contract_pyeong ?? '-'}평
                      {l.exclusive_pyeong != null && (
                        <span className="text-xs text-gray-400 ml-1">(전용 {l.exclusive_pyeong})</span>
                      )}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {l.floor ?? '-'}/{l.total_floors ?? '-'}층
                    </td>
                    <td className="px-3 py-2 text-right font-medium">{fmt만원(l.sale_price)}</td>
                    <td className="px-3 py-2 text-right">{fmt만원(l.deposit)}</td>
                    <td className="px-3 py-2 text-right">{fmt만원(l.monthly_rent)}</td>
                    <td className="px-3 py-2 text-right font-bold text-blue-600">
                      {l.yield_rate != null ? `${l.yield_rate.toFixed(2)}%` : '-'}
                    </td>
                    <td className="px-3 py-2">{l.direction ?? '-'}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {l.tag_list?.map((t) => (
                          <span key={t} className="bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded">
                            {t}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>

                  {isExpanded && (
                    <tr className="bg-blue-50 border-t border-blue-100">
                      <td colSpan={10} className="px-4 py-4">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
                          <div><span className="text-gray-500">법정용도</span><br />{l.law_usage ?? '-'}</div>
                          <div><span className="text-gray-500">건물구조</span><br />{l.structure_name ?? '-'}</div>
                          <div><span className="text-gray-500">사용승인일</span><br />{l.building_approve_ymd ?? '-'}</div>
                          <div><span className="text-gray-500">전용률</span><br />{l.exclusive_rate != null ? `${l.exclusive_rate}%` : '-'}</div>
                          <div><span className="text-gray-500">관리비</span><br />{fmtMgmt(l.monthly_mgmt_cost)}</div>
                          <div><span className="text-gray-500">융자금</span><br />{fmt만원(l.finance_price)}</div>
                          <div><span className="text-gray-500">지하철 도보</span><br />{l.walking_to_subway != null ? `${l.walking_to_subway}분` : '-'}</div>
                          <div><span className="text-gray-500">주차</span><br />{l.parking_count != null ? `${l.parking_count}대` : '-'}</div>
                          <div><span className="text-gray-500">연면적</span><br />{l.total_area != null ? `${l.total_area}㎡` : '-'}</div>
                          <div><span className="text-gray-500">지하층수</span><br />{l.underground_floors ?? '-'}</div>
                          <div><span className="text-gray-500">중개사 전화</span><br />{l.realtor_tel ?? '-'}</div>
                          <div><span className="text-gray-500">중개사 휴대폰</span><br />{l.realtor_cell ?? '-'}</div>
                        </div>

                        {l.detail_description && (
                          <div className="bg-white rounded p-3 text-xs text-gray-700 whitespace-pre-wrap max-h-48 overflow-y-auto border mb-2">
                            {l.detail_description}
                          </div>
                        )}

                        {l.detail_url && (
                          <a
                            href={l.detail_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block text-blue-600 text-xs underline"
                          >
                            네이버 부동산에서 보기 →
                          </a>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* 페이지네이션 */}
      {totalPages > 1 && (
        <div className="flex justify-center items-center gap-2 mt-4">
          <button
            disabled={page <= 1}
            onClick={() => navigate(page - 1)}
            className="px-3 py-1.5 rounded border text-sm disabled:opacity-40 hover:bg-gray-100"
          >
            이전
          </button>
          <span className="text-sm text-gray-600">{page} / {totalPages}</span>
          <button
            disabled={page >= totalPages}
            onClick={() => navigate(page + 1)}
            className="px-3 py-1.5 rounded border text-sm disabled:opacity-40 hover:bg-gray-100"
          >
            다음
          </button>
        </div>
      )}
    </div>
  )
}
