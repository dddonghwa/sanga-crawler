export interface Listing {
  article_no: string
  crawled_at: string
  sido: string
  sigungu: string
  dong: string
  location: string | null
  features: string | null
  contract_pyeong: number | null
  exclusive_pyeong: number | null
  contract_area: number | null
  exclusive_area: number | null
  floor: number | null
  total_floors: number | null
  direction: string | null
  realtor: string | null
  sale_price: number | null       // 만원
  deposit: number | null          // 만원
  monthly_rent: number | null     // 만원
  yield_rate: number | null       // %
  detail_url: string | null
  latitude: number | null
  longitude: number | null
  expose_start_ymd: string | null
  current_usage: string | null
  law_usage: string | null
  building_approve_ymd: string | null
  structure_name: string | null
  underground_floors: number | null
  total_area: number | null       // ㎡
  exclusive_rate: number | null   // %
  monthly_mgmt_cost: number | null  // 원
  finance_price: number | null    // 만원
  walking_to_subway: number | null  // 분
  parking_count: number | null
  tag_list: string[] | null
  detail_description: string | null
  realtor_tel: string | null
  realtor_cell: string | null
}
