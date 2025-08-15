import { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GenAI Chatbot',
  description: 'A production-grade GenAI chatbot application',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
