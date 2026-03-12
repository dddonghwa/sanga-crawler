import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '상가 매물 분석',
  description: '네이버 부동산 상가 매물 수익률 분석',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="bg-gray-50 min-h-screen">{children}</body>
    </html>
  )
}
