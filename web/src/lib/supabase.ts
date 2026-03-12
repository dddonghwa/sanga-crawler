import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// 프론트엔드에서 가져올 컬럼만 명시 (SELECT * 금지)
export const LISTING_SELECT_COLS = [
  'article_no',
  'crawled_at',
  'sido',
  'sigungu',
  'dong',
  'location',
  'features',
  'contract_pyeong',
  'exclusive_pyeong',
  'contract_area',
  'exclusive_area',
  'floor',
  'total_floors',
  'direction',
  'realtor',
  'sale_price',
  'deposit',
  'monthly_rent',
  'yield_rate',
  'detail_url',
  'latitude',
  'longitude',
  'expose_start_ymd',
  'current_usage',
  'law_usage',
  'building_approve_ymd',
  'structure_name',
  'underground_floors',
  'total_area',
  'exclusive_rate',
  'monthly_mgmt_cost',
  'finance_price',
  'walking_to_subway',
  'parking_count',
  'tag_list',
  'detail_description',
  'realtor_tel',
  'realtor_cell',
].join(',')
